# tailscale-ssh — enable Tailscale SSH as the second path (portal-free)

## Why this is parked, not done

Goal: every fleet host reachable via Tailscale SSH (identity auth, no key
files on disk, works even if sshd is dead) IN ADDITION to the harmonized
OpenSSH path (which remains the primary and the break-glass).

Blocker chain, fully investigated 2026-09-17:

1. The tailnet policy's `ssh` section is in **check mode**
   (`autogroup:member -> autogroup:self`, banner:
   "# Tailscale SSH requires an additional check. To authenticate, visit:
   https://login.tailscale.com/a/..."). Automation cannot click a browser.
2. The pubkey-pin workaround (`PreferredAuthentications publickey`) **does
   NOT bypass check mode on current builds** — verified live: with the pin
   active in the client config AND `--ssh` enabled, the check banner still
   intercepted (skill claim from 2026-08-24 corrected).
3. Fix = flip the ACL `ssh` rule `check -> accept`. This is a policy edit:
   admin console, or the **Tailscale API** (`/api/v2/tailnet/-/acl`).
4. The API route is scripted here — but the stored credential is dead:
   `nixos-secrets/secrets/cloud/tailscale-api-key.yaml` decrypts (cluster age
   key) to a key that returns **401 API token invalid** (created ~2026-06-09;
   API keys expire in 90 days). `tailscale-oauth.yaml` is a placeholder.

## The one remaining portal step (60 seconds, one time)

Admin console -> Settings -> Keys (or OAuth clients) -> generate an access
token, then either:

- save it to `~/.config/tailscale/api-key` (chmod 600), or
- re-encrypt it into nixos-secrets and update
  `secrets/cloud/tailscale-api-key.yaml`.

## Then run this (no portal again, ever)

```bash
./apply-acl-accept.sh       # GET policy -> backup -> check->accept -> PUT -> verify
./enable-ts-ssh.sh          # enable on zephyr/nexus/forge/sentry, probe, fail-safe
```

Rollback (either order works):

```bash
./enable-ts-ssh.sh --rollback          # tailscale set --ssh=false everywhere
# ACL rollback = PUT the backup saved by apply-acl-accept.sh back to /acl
```

## Notes

- `tailscale set --ssh` uses `--accept-risk=lose-ssh` (without it the command
  silently aborts with exit 0 when run over a tailnet connection — historic
  footgun documented in tailscale-tailnet-ops).
- Enabling claims tnet:22 only; LAN OpenSSH is untouched, and nexus (the only
  host without a LAN SSH fallback) has the k8s debug-node rescue
  (`kubectl debug node/nexus-agent`... use the real node name).
- Acceptance: `scripts/gates-run.sh all` must print 7/7, then a fresh
  `ssh <host> hostname` over the tailnet must print the hostname.
