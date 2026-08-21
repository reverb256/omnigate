//! omnigate-core: GPU-accelerated hashing, transfer, and compression.
//!
//! Backend strategy (portable, not CUDA-locked):
//!   - Vulkan compute = portable default (AMD / Intel / NVIDIA)
//!   - CUDA, ROCm, SYCL = optional feature-gated backends
//!
//! The skip-ladder is the #1 optimization (mount > reflink > skip > dedup);
//! the GPU accelerates only the unavoidable work: hashing, compression,
//! and zero-copy transfer (GPUDirect Storage where present).

pub mod backends;
pub mod hash;
pub mod transfer;
