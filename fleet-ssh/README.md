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

## Acceptance test (must be all-green after any change)
From each host, `ssh <other-host> hostname` for all pairs (4x4 matrix), plus
zephyr -> krash2/krash3. All must return the target hostname.

## Gotchas (learned the hard way)
- sentry: sshd once bound ONLY the tailnet IP; a tailnet flap at restart
  tripped systemd's start limit and sshd stayed dead while the host was fine
  (ping ok, ssh refused). The restart-forever drop-in eliminates the class.
- krash2 = Windows user `krash`; **krash3 = Windows user `j_kro`**. Wrong user
  looks like a key rejection.
- Tailscale SSH: OFF on every fleet host (`tailscale debug prefs` -> RunSSH
  false). The tailnet ACL compiles to check-mode (holdAndDelegate -> browser
  approval URL); enabling `--ssh` while that policy stands WILL break
  non-interactive automation (observed: 180s stalls). If TS SSH is wanted as
  a second path, first add an `ssh` ACL rule with `action: accept` for the
  owner, then `tailscale set --ssh=true` per host and re-run the matrix.
- The old client config needed `PreferredAuthentications publickey` to dodge
  the broker; it stays in the shared config so automation never hangs.

## Apply
`./apply.sh zephyr nexus forge sentry` (sshd -t gates every reload; sentry
first has the k8s debug-node rescue path if anything ever locks you out:
`kubectl debug node/sentry-agent` -> chroot /host).
