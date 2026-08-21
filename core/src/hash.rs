//! Hashing: blake3 (SIMD + multithreaded) as the fast path.
//!
//! blake3 is ~12x faster than sha256 (AVX-512) and its Merkle-tree
//! structure parallelizes across threads. The GPU (Vulkan compute) kernel
//! is a future accelerator for the unavoidable hashing work.

use std::fs::File;
use std::io::Read;
use std::path::Path;

/// Hashes a file with blake3 (multithreaded by default).
///
/// Returns the 32-byte blake3 hash. This is the fast verification path.
pub fn hash_file(path: &Path) -> std::io::Result<[u8; 32]> {
    let mut file = File::open(path)?;
    let mut hasher = blake3::Hasher::new();
    let mut buf = vec![0u8; 1 << 20]; // 1 MiB buffer
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(*hasher.finalize().as_bytes())
}

/// Hashes a byte slice with blake3 (fast for in-memory configs).
pub fn hash_bytes(data: &[u8]) -> [u8; 32] {
    *blake3::hash(data).as_bytes()
}

/// Computes blake3 hashes for many files in parallel.
///
/// The work is embarrassingly parallel; `threads` controls the pool size.
pub fn hash_files_parallel(
    paths: &[std::path::PathBuf],
    threads: usize,
) -> Vec<(usize, std::io::Result<[u8; 32]>)> {
    use std::sync::mpsc;
    use std::sync::Arc;

    let paths = Arc::new(paths.to_vec());
    let (tx, rx) = mpsc::channel();
    let pool_size = threads.max(1);

    let mut handles = Vec::new();
    for t in 0..pool_size {
        let paths = Arc::clone(&paths);
        let tx = tx.clone();
        handles.push(std::thread::spawn(move || {
            let mut i = t;
            while i < paths.len() {
                let res = hash_file(&paths[i]);
                let _ = tx.send((i, res));
                i += pool_size;
            }
        }));
    }
    drop(tx);
    for h in handles {
        let _ = h.join();
    }

    let mut results: Vec<(usize, std::io::Result<[u8; 32]>)> =
        rx.iter().collect();
    results.sort_by_key(|(i, _)| *i);
    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hash_known_vector() {
        // blake3("") = af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262
        let h = hash_bytes(b"");
        assert_eq!(
            hex(&h),
            "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
        );
    }

    fn hex(b: &[u8]) -> String {
        b.iter().map(|x| format!("{:02x}", x)).collect()
    }
}
