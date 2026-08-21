//! Transfer: reflink-first, parallel workers.
//!
//! The skip-ladder is the #1 optimization: mount > reflink > skip > dedup.
//! This module does the UNAVOIDABLE copy fast:
//!   - reflink (CoW) when the filesystem supports it (btrfs/xfs/APFS)
//!   - parallel workers for independent files
//!   - zero-copy transfer (GPUDirect Storage / RDMA) as a future backend

use std::fs;
use std::path::Path;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc;
use std::sync::Arc;

/// Tries a CoW reflink copy; falls back to a regular copy.
///
/// On btrfs/xfs this is near-instant (no byte movement). Returns bytes
/// actually transferred (0 for reflink).
pub fn copy_file(src: &Path, dst: &Path) -> std::io::Result<u64> {
    if let Ok(()) = reflink::reflink(src, dst) {
        return Ok(0); // CoW: nothing moved
    }
    // Fallback: streaming copy
    fs::copy(src, dst)
}

/// Copies many files with a worker pool (embarrassingly parallel).
///
/// Returns total bytes transferred (0 = all reflinked, the ideal case).
pub fn copy_many(files: &[(String, String)], threads: usize) -> std::io::Result<u64> {
    let total = Arc::new(AtomicUsize::new(0));
    let files = Arc::new(files.to_vec());
    let (tx, rx) = mpsc::channel::<u64>();
    let pool_size = threads.max(1);

    let mut handles = Vec::new();
    for t in 0..pool_size {
        let files = Arc::clone(&files);
        let total = Arc::clone(&total);
        let tx = tx.clone();
        handles.push(std::thread::spawn(move || {
            let mut i = t;
            while i < files.len() {
                let (s, d) = &files[i];
                let src = Path::new(s);
                let dst = Path::new(d);
                if let Some(parent) = dst.parent() {
                    let _ = fs::create_dir_all(parent);
                }
                match copy_file(src, dst) {
                    Ok(n) => {
                        total.fetch_add(n as usize, Ordering::Relaxed);
                        let _ = tx.send(n);
                    }
                    Err(e) => {
                        let _ = tx.send(0);
                        eprintln!("copy {} -> {}: {}", s, d, e);
                    }
                }
                i += pool_size;
            }
        }));
    }
    drop(tx);
    for h in handles {
        let _ = h.join();
    }
    let _: Vec<u64> = rx.iter().collect();
    Ok(total.load(Ordering::Relaxed) as u64)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn copy_reflink_or_fallback() {
        let dir = std::env::temp_dir().join("omnigate-test");
        fs::create_dir_all(&dir).unwrap();
        let src = dir.join("src.txt");
        let dst = dir.join("dst.txt");
        let mut f = fs::File::create(&src).unwrap();
        writeln!(f, "hello").unwrap();
        drop(f);
        copy_file(&src, &dst).unwrap();
        assert!(dst.exists());
        fs::remove_dir_all(&dir).ok();
    }
}
