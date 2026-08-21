# omnigate — Performance Design (PERF.md)

> AI builds it. The runtime is deterministic and hyper-optimized.
> The #1 rule: **skip the hard work** (skip-ladder), then make the
> unavoidable work fast.

## The skip-ladder (the #1 optimization)

1. **Mount, don't copy** — Ghost Drive / union mount. Zero transfer, zero
   calculation. (`mount.py ghost`)
2. **Reflink, don't stream** — CoW on btrfs/xfs/APFS. Near-instant, no
   bytes move. (`core/src/transfer.rs`)
3. **Skip re-downloadable** — Steam manifests, caches, node_modules. Don't
   move what you'll redownload. (`steam.py`)
4. **Dedup, don't duplicate** — chunked sync (casync rolling hash), only
   novel bytes. *(roadmap)*
5. **Hash only what changed** — blake3 on deltas; trust reflink (CoW =
   verified). (`core/src/hash.rs`)
6. **THEN make the unavoidable fast** — parallel workers, blake3 SIMD/GPU,
   GPUDirect Storage, nvCOMP.

## Fast primitives (implemented)

| Primitive | Tech | Speed |
|---|---|---|
| Discovery | Parallel + direct DB reads (pacman local/, dpkg status) | millisecond-class |
| Windows discovery | Registry uninstall keys (never Win32_Product) | ~2.2s full scan |
| Hashing | blake3 (AVX-512 5.8 GB/s vs sha256 0.45 GB/s = 12×) | ~3 min per 1TB |
| Copy | reflink-first (CoW), parallel workers | 0 bytes streamed on CoW |
| Config porting | parallel copy, cache-pruned | fast |

## Fast primitives (roadmap)

| Primitive | Tech | Why |
|---|---|---|
| Chunked sync | casync content-defined chunking | sub-file deltas, cross-file dedup |
| Network deltas | zsync/rdiff over HTTP | only novel bytes over the wire |
| GPU hashing | Vulkan compute kernel / CUDA | 59× over single-thread CPU (VaultxGPU) |
| GPU compression | nvCOMP (zstd/lz4/GDeflate) | 600 GB/s decompress on Blackwell |
| Zero-copy transfer | GPUDirect Storage (NVMe↔GPU DMA) | no CPU bounce buffer |
| In-line dedup | StreamDedup architecture | 12.7 GB/s single-node dedup |

## GPU backend strategy (portable, not CUDA-locked)

- **Vulkan compute** = portable default (AMD / Intel / NVIDIA) — implemented
  in `core/src/backends.rs`.
- **CUDA** = NVIDIA (GDS, nvcomp) — feature-gated.
- **ROCm** = AMD, **SYCL/oneAPI** = Intel — feature-gated.
- Multi-backend: hashing + compression accelerate on ANY GPU.

## Transfer targets

- **1 TB migration over 10 GbE** should be **transfer-limited, not
  tool-limited** (~15 min at line rate, minus skips).
- The skip-ladder makes the *effective* transfer far smaller: mount skips
  the copy entirely; Steam skips re-downloadable; dedup skips novel bytes.

## Cross-cutting

- **Parallelism everywhere** — any multi-file op uses a worker pool.
- **Cache everything** — discovery cache, hash cache, manifest cache.
- **Non-blocking UI** — the TUI progress callback never serializes on
  transfer workers.
- **Rust core** (`core/`) for the hot path; Python CLI for planning.
