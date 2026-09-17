# VM test plan for kexec pipeline

QEMU is not installed on zephyr, so the full kexec loop cannot be tested here yet.
This document captures the exact test plan so it can be executed on any machine
with QEMU/KVM available.

## Prerequisites

- QEMU/KVM (`qemu-system-x86_64`) with KVM acceleration
- Omarchy ISO: `~/Downloads/omarchy-4.0.1.iso`
- Omarchy migration repo cloned to `/home/j_kro/Projects/omarchy-migrate/`
- 16GB+ RAM available for VM
- 40GB+ disk space for VM image

## Test 1: ISO extraction (prep phase)

```bash
cd ~/Projects/omarchy-migrate
python3 kexec.py prep --iso ~/Downloads/omarchy-4.0.1.iso --workdir kexec/test-vm
```

Expected:
- `kexec/test-vm/arch/` directory created
- `arch/boot/x86_64/vmlinuz-linux-t2` (17MB)
- `arch/boot/x86_64/initramfs-linux-t2.img` (253MB)
- `arch/x86_64/airootfs.sfs` (5.9GB)
- Prep JSON output shows all paths

## Test 2: HTTP serve

```bash
# In one terminal
python3 kexec.py serve --iso ~/Downloads/omarchy-4.0.1.iso --port 8091 --workdir kexec/test-vm

# In another terminal
curl -I http://localhost:8091/arch/x86_64/airootfs.sfs
```

Expected:
- HTTP 200 with correct content-length
- Squashfs file accessible

## Test 3: VM kexec boot

```bash
# Boot VM with kernel+initrd from ISO
qemu-system-x86_64 \
  -machine q35,accel=kvm \
  -cpu host \
  -smp 4 \
  -m 8192 \
  -netdev user,id=net0,net=192.168.15.0/24 \
  -device virtio-net,netdev=net0 \
  -kernel kexec/test-vm/arch/boot/x86_64/vmlinuz-linux-t2 \
  -initrd kexec/test-vm/arch/boot/x86_64/initramfs-linux-t2.img \
  -append "archisobasedir=arch archiso_http_srv=http://10.0.2.2:8091/ ip=dhcp initramfs_async=0" \
  -drive file=/tmp/omarchy-vm-test.qcow2,format=qcow2,if=virtio \
  -drive file=/home/j_kro/Downloads/omarchy-4.0.1.iso,format=raw,if=none,id=cd0 \
  -device virtio-blk-pci,drive=cd0 \
  -virtfs local,path=/home/j_kro/Projects/omarchy-migrate,security_model=passthrough,mount_tag=omnigate \
  -serial stdio \
  -display none
```

Expected:
- VM boots into Omarchy live environment
- SSH accessible on port 2222
- Can run `cat /etc/os-release` and see Omarchy/Arch

## Test 4: Full pipeline (kexec.py run)

```bash
# From the orchestrator machine
python3 kexec.py run \
  --target user@vm-host \
  --iso ~/Downloads/omarchy-4.0.1.iso \
  --orchestrator local \
  --port 8091 \
  --yes \
  --log-file /tmp/kexec-test.log
```

Expected:
- All phases complete (prep → serve → load → execute → monitor)
- Monitor detects Omarchy installer
- JSON log written to /tmp/kexec-test.log

## Test 5: Rollback

```bash
# From inside the VM
reboot

# At boot menu, select original kernel
```

Expected:
- VM boots back to original state
- Old kernel/OS intact

## Known issues

- `nvidia-smi` won't work in VM (no NVIDIA GPU passthrough)
- peakminer cannot run in VM
- Some GPU-dependent services won't work

## Blockers

- QEMU/KVM not installed on zephyr
- Need a separate test host with KVM support
