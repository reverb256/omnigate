#!/usr/bin/env python3
"""Hardware compatibility snapshot — Linux, macOS, Windows.

Read-only. No secrets. Goal: keep the IDs that a wipe would destroy
(PCI/USB VEN/DEV, GPU, display, storage controller) so Omarchy driver
and linux-hardware.org lookups still work after cutover.

Inspired by RadioPizza/win2linux-prewipe (MIT) — pattern only, no code
copied. macOS uses system_profiler; Linux uses sysfs; Windows uses
CIM/WMI when present.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCHEMA = "omnigate/hardware/v1"


def _run(cmd: list[str], timeout: int = 20) -> str:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
        return proc.stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _read(path: str) -> str | None:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
        return text or None
    except OSError:
        return None


def _linux() -> dict:
    cpu = None
    try:
        for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
            if line.lower().startswith("model name"):
                cpu = line.split(":", 1)[-1].strip()
                break
    except OSError:
        cpu = None
    gpus = []
    drm = Path("/sys/class/drm")
    if drm.is_dir():
        seen = set()
        for card in sorted(drm.glob("card[0-9]")):
            vendor = _read(str(card / "device" / "vendor"))
            device = _read(str(card / "device" / "device"))
            key = (vendor, device)
            if vendor and key not in seen:
                seen.add(key)
                gpus.append({
                    "vendor_id": vendor,
                    "device_id": device,
                    "name": _read(str(card / "device" / "uevent")),
                    "source": "sysfs",
                })
    lspci = _run(["lspci", "-nmm"], timeout=8)
    if lspci and not gpus:
        for line in lspci.splitlines():
            if "VGA" in line or "3D" in line or "Display" in line:
                gpus.append({"raw": line[:200], "source": "lspci"})
    return {
        "system": {
            "vendor": _read("/sys/class/dmi/id/sys_vendor"),
            "product": _read("/sys/class/dmi/id/product_name"),
            "bios": _read("/sys/class/dmi/id/bios_version"),
        },
        "cpu": {"model": cpu or platform.processor() or None},
        "gpus": gpus,
        "kernel": platform.release(),
        "machine": platform.machine(),
    }


def _macos() -> dict:
    raw = _run(
        ["system_profiler", "-json",
         "SPHardwareDataType", "SPDisplaysDataType", "SPStorageDataType"],
        timeout=25,
    )
    parsed: dict = {}
    if raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
    hw = (parsed.get("SPHardwareDataType") or [{}])[0]
    displays = parsed.get("SPDisplaysDataType") or []
    storage = parsed.get("SPStorageDataType") or []
    gpus = []
    for d in displays:
        gpus.append({
            "name": d.get("sppci_model") or d.get("_name"),
            "vendor": d.get("spdisplays_vendor"),
            "vram": d.get("spdisplays_vram") or d.get("spdisplays_vram_shared"),
            "source": "system_profiler",
        })
    return {
        "system": {
            "vendor": "Apple",
            "product": hw.get("machine_model") or hw.get("machine_name"),
            "serial_hidden": True,
            "chip": hw.get("chip_type") or hw.get("cpu_type"),
            "memory": hw.get("physical_memory"),
        },
        "cpu": {"model": hw.get("chip_type") or hw.get("cpu_type")},
        "gpus": gpus,
        "storage": [
            {"name": s.get("_name"), "size": s.get("size"),
             "protocol": s.get("protocol")}
            for s in storage[:12]
        ],
        "machine": platform.machine(),
    }


def _windows() -> dict:
    # CIM is read-only inventory. Do not touch Credential Manager.
    ps = (
        "$cs = Get-CimInstance Win32_ComputerSystem | "
        "Select-Object Manufacturer,Model | ConvertTo-Json -Compress; "
        "$cpu = Get-CimInstance Win32_Processor | "
        "Select-Object -First 1 Name | ConvertTo-Json -Compress; "
        "$gpu = Get-CimInstance Win32_VideoController | "
        "Select-Object Name,PNPDeviceID | ConvertTo-Json -Compress; "
        "Write-Output '---CS---'; $cs; Write-Output '---CPU---'; $cpu; "
        "Write-Output '---GPU---'; $gpu"
    )
    out = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        timeout=25,
    )
    sections = {"CS": "", "CPU": "", "GPU": ""}
    cur = None
    for line in out.splitlines():
        if line.strip() == "---CS---":
            cur = "CS"
            continue
        if line.strip() == "---CPU---":
            cur = "CPU"
            continue
        if line.strip() == "---GPU---":
            cur = "GPU"
            continue
        if cur:
            sections[cur] += line
    def _j(text: str):
        text = text.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    cs, cpu, gpu = _j(sections["CS"]), _j(sections["CPU"]), _j(sections["GPU"])
    gpus = gpu if isinstance(gpu, list) else ([gpu] if gpu else [])
    return {
        "system": {
            "vendor": (cs or {}).get("Manufacturer") if isinstance(cs, dict) else None,
            "product": (cs or {}).get("Model") if isinstance(cs, dict) else None,
        },
        "cpu": {"model": (cpu or {}).get("Name") if isinstance(cpu, dict) else None},
        "gpus": [
            {"name": g.get("Name"), "pnp": g.get("PNPDeviceID"), "source": "cim"}
            for g in gpus if isinstance(g, dict)
        ],
        "machine": platform.machine(),
    }


def snapshot(os_name: str | None = None) -> dict:
    """Collect a hardware compatibility record. Always returns a valid dict."""
    os_name = os_name or {
        "linux": "linux", "darwin": "macos",
    }.get(sys.platform, "windows")
    body: dict
    if os_name == "linux":
        body = _linux()
    elif os_name == "macos":
        body = _macos()
    else:
        body = _windows()
    return {
        "schema": SCHEMA,
        "generated": datetime.now().isoformat(),
        "os": os_name,
        "note": "Compatibility IDs only. No serials/secrets. Use for "
                "Omarchy driver + linux-hardware.org after cutover.",
        **body,
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = None
    os_name = None
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    if "--os" in argv:
        os_name = argv[argv.index("--os") + 1]
    data = snapshot(os_name)
    text = json.dumps(data, indent=2)
    if out:
        Path(out).write_text(text)
        print(f"Wrote {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
