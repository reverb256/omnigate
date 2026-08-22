# Omniport Transformation Plan

Source: local | VERSION_ID="26.11" | kernel: Linux zephyr 7.1.3-cachyos #1-NixOS SMP PREEMPT_DYNAMIC Tue 
k3s role: none | kexec: True

## Summary
- Services: 24 mapped, 0 defer to Omarchy, 3 unknown
- Secrets: 2 mapped, 10 need review
- Packages: 0 mapped, 0 deferred, 112 unknown

## Services
- **flatpak** → defer_omarchy (n/a)
- **cluster-mesh** → tailscale (tailscaled.service)
- **recovery-specialisation** → defer_omarchy (n/a)
- **cachix-auth** → cachix (n/a)
- **cns-setup** → tailscale (n/a)
- **cns-watcher** → tailscale (n/a)
- **pcscd** → pcsclite (n/a)
- **gaming** → defer_omarchy (n/a)
- **opencode** → openrouter-cli (n/a)
- **my-service** → defer_omarchy (n/a)
- **sunshine** → sunshine (n/a)
- **freebuff-desktop** → defer_omarchy (n/a)
- **status-auto-update** → pacman-init (n/a)
- **systemd-user-timeout** → systemd (default) (n/a)
- **cluster-ca** → step-ca (step-ca.service)
- **unbound-common** → UNK (review: No mapping in nixos-to-arch.json — manual review required)
- **fake-backlight-bridge** → defer_omarchy (n/a)
- **storage-assertions** → defer_omarchy (n/a)
- **thermal-monitor** → sensors + lm_sensors (n/a)
- **hermes-a2a** → hermes-a2a-mesh (hermes-a2a.service)
- **memlawb-healthcheck** → systemd timer (memlawb-healthcheck.timer)
- **gitlawb-client** → gitlawb (n/a)
- **power-profiles-daemon** → power-profiles-daemon (n/a)
- **llama-swap-cluster** → llama-swap (n/a)
- **gitlawb-node** → gitlawb (n/a)
- ... and 2 more

## Secrets

- /etc/nixos/secretspec.toml → /etc/omnigate/secretspec.toml (secretspec_toml)
- /etc/nixos/.age/key.txt → /etc/age/keys.txt (age_key)
- /etc/nixos/hosts/zephyr/k8s-haven/haven-secret.yaml → None (sops_yaml)
- /etc/nixos/hosts/zephyr/k8s-haven/haven-namespace-secrets.yaml → None (sops_yaml)
- /etc/nixos/hosts/zephyr/k8s-haven/haven-cloudflared-cm-secret.yaml → None (sops_yaml)
- /etc/nixos/kubernetes-manifests/ai-inference/helm/ai-inference-gateway/templates/secret.yaml → None (sops_yaml)
- /etc/nixos/kubernetes-manifests/ai-inference/ai-inference-gateway-secrets.yaml → None (sops_yaml)
- /etc/nixos/kubernetes-manifests/archive/backup-20260322/xmrig-proxy-secret.yaml → None (sops_yaml)
- /etc/nixos/kubernetes-manifests/mining/xmrig-proxy-secret.yaml → None (sops_yaml)
- /etc/nixos/docs/kubernetes/storage/garage-s3-secret.yaml → None (sops_yaml)
- /etc/nixos/secrets/cloud/cloudflared-token.yaml → None (sops_yaml)
- /home/j_kro/.config/fish/conf.d/api-keys.fish → None (user_env_creds)

## Partitions

Strategy: ghost-drive
Disk: nvme0n1 | ghost partition: None
Actions:
  1. Shrink btrfs partition by 50GB (btrfs filesystem resize)
  2. Create new partition in freed space (50GB, ext4)
  3. Install Arch + Omarchy into new partition
  4. Mount old btrfs as /nixos-legacy (ghost, read-only)
  5. Bind-mount preserved dirs from /nixos-legacy to Arch
Warnings:
  ⚠ btrfs shrink requires defrag + balance first (run: btrfs filesystem defrag -r /)
  ⚠ Old NixOS EFI entry stays in ESP — both boot entries available
  ⚠ Rollback: boot old NixOS entry from GRUB/systemd-boot menu

## Conflicts

[info] btrfs partition needs defrag+balance before shrink

## Stages
- Stage 0: discovery — complete — audit.py scan executed
- Stage 1: plan — complete — plan.py generated this transformation plan
- Stage 2: vm-test — pending — Boot omarchy ISO in QEMU, validate configs restore
- Stage 3: transform — pending — Ghost-drive: shrink btrfs, install Arch+omarchy beside NixOS
- Stage 4: restore — pending — Bind-mount preserved dirs, port services, port secrets
