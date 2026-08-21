//! omnigate-core CLI: GPU/hash/transfer demo + bench.

use clap::{Parser, Subcommand};

mod backends;
mod hash;
mod transfer;

#[derive(Parser)]
#[command(name = "omnigate-core", about = "GPU-accelerated core for omnigate")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Detect GPU compute backends
    Gpus,
    /// Hash files with blake3 (parallel)
    Hash {
        /// Files to hash
        files: Vec<String>,
        /// Worker threads (default: num_cpus)
        #[arg(long, default_value_t = 8)]
        threads: usize,
    },
    /// Copy files with reflink-first + parallel workers
    Copy {
        /// source:dest pairs
        pairs: Vec<String>,
        #[arg(long, default_value_t = 8)]
        threads: usize,
    },
}

fn main() {
    let cli = Cli::parse();
    match cli.command {
        Commands::Gpus => {
            let info = backends::detect();
            println!("Vulkan: {}", info.vulkan);
            println!("CUDA:   {}", info.cuda);
            println!("ROCm:   {}", info.rocm);
            println!("SYCL:   {}", info.sycl);
            for d in &info.devices {
                println!(
                    "  - {} ({}) [{}] {} MiB",
                    d.name, d.api, d.device_type, d.memory_mb
                );
            }
        }
        Commands::Hash { files, threads } => {
            let paths: Vec<std::path::PathBuf> =
                files.iter().map(std::path::PathBuf::from).collect();
            let results = hash::hash_files_parallel(&paths, threads);
            for (i, res) in results {
                match res {
                    Ok(h) => println!("{}  {}", hex(&h), files[i]),
                    Err(e) => eprintln!("{}: {}", files[i], e),
                }
            }
        }
        Commands::Copy { pairs, threads } => {
            let files: Vec<(String, String)> = pairs
                .iter()
                .filter_map(|p| {
                    let (s, d) = p.split_once(':')?;
                    Some((s.to_string(), d.to_string()))
                })
                .collect();
            match transfer::copy_many(&files, threads) {
                Ok(bytes) => println!("copied {} files, {} bytes streamed (0 = all reflink)", files.len(), bytes),
                Err(e) => eprintln!("error: {}", e),
            }
        }
    }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{:02x}", x)).collect()
}
