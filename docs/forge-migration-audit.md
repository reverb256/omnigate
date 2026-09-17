# Forge migration audit — 2026-08-27

## Host facts (from live state + memory)

| Property | Value |
|---|---|
| Host | forge (10.1.1.110) |
| Current OS | NixOS 26.11 Zokor |
| RAM | 15GB |
| Cores | 6 |
| GPUs | 2x RTX 4060 |
| Miner | peakminer v2.11.0 |
| Hashrate | ~61 TH/s per GPU (122 TH/s total) |
| Power | 118W per GPU (--gpu-power 118) |
| Temp | 66-69°C |
| Efficiency | 241 GH/W |
| Disk | Single btrfs, layout similar to zephyr |
| Bootloader | limine (NixOS) |
| SSH | Tailscale alias works, key-based |

## Services to migrate

| Service | NixOS | Omarchy target | Status |
|---|---|---|---|
| peakminer-4060-0 | dropin .service | systemd unit in /etc/systemd/system/ | needs port |
| peakminer-4060-1 | dropin .service | systemd unit in /etc/systemd/system/ | needs port |
| keepalived | NixOS module | Arch package + systemd unit | 2 failed units on NixOS — audit why |
| nvidia drivers | nixos-config module | pacman nvidia-dkms | straightforward |
| tailscaled | NixOS module | pacman tailscale | straightforward |
| sshd | NixOS module | Arch base | straightforward |
| sddm/hyprland | NixOS module | Omarchy base | defer to Omarchy |

## GPU migration path

### NVIDIA driver migration

**Current (NixOS)**:
- Declarative module in nixos-config
- kernel packages include NVIDIA modules
- nvidia-smi works, power limits set via ExecStartPre

**Target (Omarchy)**:
```bash
# Install via pacman (non-free repo)
sudo pacman -S nvidia-dkms nvidia-utils lib32-nvidia-utils

# Enable DKMS auto-rebuild
sudo systemctl enable dkms.service
```

**Gotcha**: Forge runs 2x RTX 4060 — needs nvidia-dkms for kernel module rebuild on kernel update. Verify Omarchy kernel package includes headers.

### peakminer migration

**Current (NixOS)**:
- Script-based drop-in: `/home/j_kro/forge-4060-{0,1}-imp.sh`
- Transient systemd units: `peakminer-dropin-forge-4060-{0,1}.service`
- Power cap via `--gpu-power 118`
- v2.11.0 binary (updated 2026-08-26)

**Target (Omarchy)**:
```bash
# Option 1: Script-based (same pattern as NixOS)
# /home/j_kro/forge-4060-{0,1}-imp.sh stays, units become native:
sudo tee /etc/systemd/system/peakminer-forge-4060-0.service << 'EOF'
[Unit]
Description=peakminer forge 4060 GPU 0
After=network.target nvidia-smi.service

[Service]
Type=simple
ExecStartPre=/usr/bin/nvidia-smi -i 0 -pl 118
ExecStart=/home/j_kro/forge-4060-0-imp.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Repeat for GPU 1
sudo systemctl daemon-reload
sudo systemctl enable --now peakminer-forge-4060-0 peakminer-forge-4060-1
```

**Option 2: Use peakminer's native --gpu-power flag**
The NixOS drop-in pattern used nvidia-smi ExecStartPre. Omarchy can use peakminer's own flag:
```bash
/home/j_kro/forge-4060-0-imp.sh --gpu-power 118
```

### Dual GPU considerations

- Both GPUs need separate systemd units
- Power limits must be set per-GPU (`nvidia-smi -i 0 -pl 118`, `nvidia-smi -i 1 -pl 118`)
- Temperature monitoring: `nvidia-smi -l 1` for live monitoring
- Fan control: if using nvidia-settings, need Xorg/Wayland session

## Migration sequence for forge

1. **Pre-migration** (NixOS, done):
   - [x] Verify peakminer running, hash rate stable
   - [x] Document current configs
   - [x] Backup /home/j_kro (includes miner scripts)
   - [x] Set power cap 118W (already done 2026-08-26)

2. **Kexec boot** (new):
   - [ ] Boot forge into Omarchy installer via kexec
   - [ ] Verify both GPUs detected in live environment (`nvidia-smi`)

3. **Install Omarchy**:
   - [ ] Partition disk (keep existing /home or Ghost Drive)
   - [ ] Install Omarchy base
   - [ ] Install nvidia-dkms
   - [ ] Verify dual GPU: `nvidia-smi` shows both 4060s

4. **Restore miner**:
   - [ ] Copy forge-4060-{0,1}-imp.sh from backup
   - [ ] Create systemd units for each GPU
   - [ ] Set power limits
   - [ ] Start peakminer, verify hash rate

5. **Verify**:
   - [ ] Both GPUs mining
   - [ ] Hash rate ≥ 60 TH/s per GPU
   - [ ] Power ≤ 120W per GPU
   - [ ] Temperature ≤ 75°C
   - [ ] Rollback possible (old NixOS boot entry present)

## Risks

| Risk | Mitigation |
|---|---|
| nvidia-dkms fails to build | Test on VM first; have NVIDIA .run installer fallback |
| peakminer binary doesn't run on Arch | peakminer is static binary — should work |
| Dual GPU detection fails | nvidia-smi in live environment before install |
| Mining downtime > 1 hour | kexec is fast (~5min), rollback is reboot |
| keepalived failure mode | Investigate on NixOS first, don't migrate broken state |

## Open questions

1. Does peakminer v2.11.0 static binary run on Omarchy's glibc? (likely yes — Arch is upstream)
2. Is nvidia-dkms in Omarchy repos? (Arch extra has it, Omarchy inherits)
3. Should forge use systemd-nspawn containers for miners? (isolation, easier rollback)

## Next actions

1. Test nvidia-dkms install on Omarchy VM
2. Test peakminer v2.11.0 on Omarchy (binary compatibility)
3. Document keepalived failure on NixOS (root cause)
4. Build forge-specific kexec plan
