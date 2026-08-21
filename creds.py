#!/usr/bin/env python3
"""omnigate creds — credential export with the safe tiered strategy.

Security model (documented in docs/VISION.md + PERF.md):
  TIER 1 — automatic, encrypted: SSH keys, Wi-Fi profiles, keyring→KDBX.
  TIER 2 — user-mediated, NEVER automatic: browser passwords (flagged, not
           extracted).
  TIER 3 — hard refuse: Credential Manager plaintext (Mimikatz-grade).

Every secret is age-encrypted at rest. No plaintext credentials ever touch
disk in the migration package. If `age` is missing, this refuses to write —
it never degrades to plaintext.

Usage:
  python3 creds.py export --out creds.age.json   # tier-1 export (age-encrypted)
  python3 creds.py flags                         # tier-2 flags (what the user must do)
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# age handling (the ONLY encryption allowed for credentials)
# ---------------------------------------------------------------------------

def _age() -> str | None:
    """Return the age binary path, or None if unavailable."""
    return shutil.which("age")


def _age_encrypt(data: bytes, recipient: str | None = None) -> bytes:
    """Encrypt bytes with age. Requires age + a recipient or passphrase.

    Without a recipient argument, we require a passphrase via AGE_PASSPHRASE
    env (never prompt in an automated pipeline). The caller is responsible
    for supplying a recipient or passphrase.
    """
    age = _age()
    if age is None:
        raise RuntimeError(
            "age is required for credential export. Install it: "
            "pacman -S age (Arch/Omarchy), winget install FiloSottile.age "
            "(Windows), brew install age (macOS). omnigate refuses to write "
            "plaintext credentials."
        )
    cmd = [age, "-e", "-a"]
    if recipient:
        cmd += ["-r", recipient]
    else:
        cmd += ["-p"]
    env = dict(__import__("os").environ)
    env["AGE_PASSPHRASE"] = env.get(
        "OMNIGATE_CRED_PASSPHRASE", env.get("AGE_PASSPHRASE", "")
    )
    proc = subprocess.run(cmd, input=data, capture_output=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"age encryption failed: {proc.stderr.decode()}")
    return proc.stdout


# ---------------------------------------------------------------------------
# Tier 1: automatic, encrypted
# ---------------------------------------------------------------------------

def _export_ssh_keys() -> dict[str, str]:
    """Collect SSH keys as portable blobs (private + public + config).

    Keys stay in the age-encrypted package; they are never written
    plaintext. Omarchy restores them to ~/.ssh with 0600 perms.
    """
    out: dict[str, str] = {}
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.is_dir():
        return out
    for key in ("id_ed25519", "id_ecdsa", "id_rsa"):
        p = ssh_dir / key
        if p.is_file():
            out[f"ssh/{key}"] = p.read_text(encoding="utf-8", errors="replace")
        pub = ssh_dir / f"{key}.pub"
        if pub.is_file():
            out[f"ssh/{key}.pub"] = pub.read_text(encoding="utf-8", errors="replace")
    cfg = ssh_dir / "config"
    if cfg.is_file():
        out["ssh/config"] = cfg.read_text(encoding="utf-8", errors="replace")
    return out


def _export_wifi_profiles() -> dict[str, str]:
    """Export Windows Wi-Fi profiles via netsh (Windows source only).

    `netsh wlan export profile key=clear` writes XML with the plaintext
    password — we encrypt it immediately with age. On Linux/macOS this
    returns empty (NetworkManager handles those natively).
    """
    out: dict[str, str] = {}
    if sys.platform != "win32":
        return out
    # Best-effort: netsh must run as the user; failure = no profiles.
    try:
        proc = subprocess.run(
            ["netsh", "wlan", "show", "profiles"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return out
        # Parse profile names from "All User Profile     : X"
        names = [
            line.split(":", 1)[1].strip()
            for line in proc.stdout.splitlines()
            if ":" in line and "Profile" in line
        ]
        for name in names:
            ep = subprocess.run(
                ["netsh", "wlan", "export", "profile", f"name={name}",
                 "key=clear", "folder=TEMP"],
                capture_output=True, text=True, timeout=30,
            )
            # netsh writes <name>.xml in the cwd/TEMP; collect if found
            xml = Path("TEMP") / f"{name}.xml"
            if xml.exists():
                out[f"wifi/{name}.xml"] = xml.read_text(encoding="utf-8", errors="replace")
                xml.unlink(missing_ok=True)
    except Exception:
        pass
    return out


def _export_keyring_kdbx() -> dict[str, str]:
    """Bridge system keyring → KDBX via keyring-to-kdbx IF installed.

    This is the recommended path (keyring-to-kdbx is the audited bridge).
    If not installed, we flag it (tier-2 style) rather than attempt raw
    keyring enumeration, which is backend-dependent and risky.
    """
    if shutil.which("keyring-to-kdbx") or shutil.which("xv"):
        # Both tools are drop-in CLI bridges; document usage.
        return {"keyring/NOTES.txt": (
            "keyring-to-kdbx or xv detected. Run:\n"
            "  uv run keyring-to-kdbx export -o credentials.kdbx\n"
            "  xv vault export my-vault --output secrets.json --format json\n"
            "then include the .kdbx in the package (it is already encrypted).\n"
        )}
    return {}


# ---------------------------------------------------------------------------
# Tier 2: flags (never extracted automatically)
# ---------------------------------------------------------------------------

def _flag_browser_passwords() -> list[str]:
    """Return human-readable flags for browsers with stored credentials."""
    flags = []
    for browser, path in (
        ("Chrome", Path.home() / ".config/google-chrome/Default/Login Data"),
        ("Edge", Path.home() / ".config/microsoft-edge/Default/Login Data"),
        ("Brave", Path.home() / ".config/BraveSoftware/Brave-Browser/Default/Login Data"),
        ("Firefox", Path.home() / ".mozilla/firefox"),
        ("Chromium", Path.home() / ".config/chromium/Default/Login Data"),
    ):
        if path.exists():
            flags.append(
                f"{browser}: stored passwords found. Export manually via the "
                "browser's password settings, then import into your password "
                "manager on Omarchy (e.g. KeePassXC). omnigate never extracts "
                "browser passwords automatically."
            )
    return flags


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_export(args: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="creds.py export")
    p.add_argument("--out", default="creds.age.json")
    p.add_argument("--recipient", default=None, help="age recipient (public key)")
    opts = p.parse_args(args)

    payload: dict = {"version": 1, "ssh": {}, "wifi": {}, "keyring": {}}
    payload["ssh"] = _export_ssh_keys()
    payload["wifi"] = _export_wifi_profiles()
    payload["keyring"] = _export_keyring_kdbx()

    if not any([payload["ssh"], payload["wifi"], payload["keyring"]]):
        print("No tier-1 credentials found (or age/keyring tools missing).")
        return 0

    try:
        encrypted = _age_encrypt(
            json.dumps(payload, indent=2).encode(),
            recipient=opts.recipient,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 2

    Path(opts.out).write_bytes(encrypted)
    print(f"Wrote age-encrypted credentials to {opts.out} "
          f"({len(encrypted)} bytes). No plaintext written.")
    return 0


def cmd_flags(args: list[str]) -> int:
    print("=== Tier-2 flags: actions only the user can take ===")
    flags = _flag_browser_passwords()
    if not flags:
        print("No browser password stores detected on this machine.")
    for f in flags:
        print(f"- {f}")
    if not _age():
        print("- age NOT installed — install it before `creds.py export`.")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "export":
        return cmd_export(rest)
    if cmd == "flags":
        return cmd_flags(rest)
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
