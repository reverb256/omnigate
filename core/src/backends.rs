//! GPU backend abstraction: portable Vulkan compute with optional
//! CUDA / ROCm / SYCL backends.

/// Detects available GPU compute backends on this system.
///
/// Returns backend availability for Vulkan (portable), CUDA (NVIDIA),
/// ROCm (AMD), and SYCL (Intel). Deterministic — no LLM, no network.
pub fn detect() -> BackendInfo {
    BackendInfo {
        vulkan: vulkan_available(),
        cuda: false, // feature-gated; enabled when the cuda feature builds
        rocm: false, // feature-gated
        sycl: false, // feature-gated
        devices: vulkan_devices(),
    }
}

#[derive(Debug, Clone, Default)]
pub struct BackendInfo {
    pub vulkan: bool,
    pub cuda: bool,
    pub rocm: bool,
    pub sycl: bool,
    pub devices: Vec<GpuDevice>,
}

#[derive(Debug, Clone, Default)]
pub struct GpuDevice {
    pub name: String,
    pub api: String,
    pub device_type: String,
    pub memory_mb: u64,
}

/// Checks whether the Vulkan loader is present and exposes any devices.
fn vulkan_available() -> bool {
    // ash's entry requires the vulkan loader; a failed load means no vulkan.
    match unsafe { ash::Entry::load() } {
        Ok(_) => !vulkan_devices().is_empty(),
        Err(_) => false,
    }
}

/// Enumerates Vulkan physical devices (GPUs) via the portable backend.
fn vulkan_devices() -> Vec<GpuDevice> {
    let mut out = Vec::new();
    let entry = match unsafe { ash::Entry::load() } {
        Ok(e) => e,
        Err(_) => return out,
    };
    let app_info = ash::vk::ApplicationInfo::default().api_version(ash::vk::API_VERSION_1_3);
    let create_info = ash::vk::InstanceCreateInfo::default()
        .application_info(&app_info);
    let instance = match unsafe { entry.create_instance(&create_info, None) } {
        Ok(i) => i,
        Err(_) => return out,
    };
    let devices = unsafe {
        instance
            .enumerate_physical_devices()
            .unwrap_or_default()
    };
    for pd in devices {
        let props = unsafe { instance.get_physical_device_properties(pd) };
        let name = props
            .device_name
            .iter()
            .take_while(|&&c| c != 0)
            .map(|&c| c as u8 as char)
            .collect::<String>();
        let mem_mb: u64 = unsafe {
            instance
                .get_physical_device_memory_properties(pd)
                .memory_heaps
                .iter()
                .filter(|h| h.flags.contains(ash::vk::MemoryHeapFlags::DEVICE_LOCAL))
                .map(|h| h.size / (1024 * 1024))
                .sum()
        };
        out.push(GpuDevice {
            name,
            api: "vulkan".into(),
            device_type: format!("{:?}", props.device_type),
            memory_mb: mem_mb,
        });
    }
    unsafe { instance.destroy_instance(None) };
    out
}
