# fleet-ssh — uniform SSH across the Omarchy fleet

Model: **one mental model, zero special treatment.** Every host runs the same
sshd baseline, the same restart policy, the same client config, and the same
fleet key. Differences that exist are documented here — not archaeology.

Hosts: zephyr, nexus, forge, sentry (Linux/Omarchy). krash2/krash3 = Windows
rigs, LAN-only, not on the tailnet; client entries for them live in the shared
~/.ssh/config.

## Components
- `sshd/12-fleet-sshd.conf` -> `/etc/ssh/sshd_config.d/12-fleet-sshd.conf`
  (pubkey-only, no root, no empty passwords, AllowUsers j_kro)
- `sshd/restart-forever.conf` -> `/etc/systemd/system/sshd.service.d/restart-forever.conf`
  (Restart=always, no start limit: a boot/tailnet race can never strand sshd —
  this class of outage took sentry down for 2h18m once)
- `ssh_config.fleet` -> `~/.ssh/config` (identical on every host; tailnet
  IPs; fleet key; accept-new; publickey-only auth)
- Fleet identity: `~/.ssh/id_ed25519_fleet` (same keypair on every host) +
  its pubkey in every `authorized_keys`.
- `tailscale-ssh/` — the Tailscale SSH second-path kit (parked pending one
  credential; see its README).
- `GATES.md` + `scripts/gates-run.sh` — the acceptance test (7 gates).

## Acceptance test (must be 7/7 after any change)
```bash
bash fleet-ssh/scripts/gates-run.sh all
```
G1 baseline uniform (sshd -T), G2 restart-forever active, G3 fleet key
identical, G4 client config identical, G5 connectivity matrix 15/15
(13 Linux pairs + 2 Windows rigs), G6 miner-plugin consumers reach every
host, G7 Tailscale SSH state matches the safe documented state.

## Gotchas (learned the hard way)
- sentry: sshd once bound ONLY the tailnet IP; a tailnet flap at restart
  tripped systemd's start limit and sshd stayed dead while the host was fine
  (ping ok, ssh refused). The restart-forever drop-in eliminates the class.
  Rescue without ssh: `kubectl debug node/<name>`.
- krash2 = Windows user `krash`; **krash3 = Windows user `j_kro`**. Wrong user
  looks like a key rejection.
- Tailscale SSH: OFF on every fleet host (RunSSH false). Enabling it while
  the tailnet ACL `ssh` rules are in check mode intercepts tailnet:22 with a
  browser approval prompt — scripts stall until timeout (observed). The
  pubkey-pin client workaround does NOT bypass it on current builds
  (verified 2026-09-17). The fix + full kit: `tailscale-ssh/README.md`.
- The shared config keeps `PreferredAuthentications publickey` so automation
  never negotiates interactive auth.

## Apply
`./apply.sh zephyr nexus forge sentry` (sshd -t gates every reload).
