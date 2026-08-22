# omnigate — Vision

> Five minutes. Feels like fifteen seconds. Then Omarchy.
> Keep the old disk. Mount, don't copy. We get out of the way.

Omnigate is the on-ramp. Omarchy is the home — for people who love their computers, or want to. Do not sand Omarchy down. Do not linger.

## Credits & attribution

**Research:** The world-breaking ten below were researched and synthesized
by a delegated research agent (Hermes subagent, `deleg_b94ce619`,
2026-08-21), which verified each concept against real, existing technology
before it entered this document. The agent's full output is preserved in
the session record.

**Underlying technologies (all open source / standard, verified by the
research agent; licenses verified 2026-08-21):**

| Concept | Built on | License | Exists since |
|---------|----------|---------|--------------|
| Ghost Drive | systemd `gpt-auto-generator`, Discoverable Partitions Spec | GPL-2.0 (systemd) | systemd 240+ (2018) |
| The Coffin | systemd-sysext/confext, DDI format, dm-verity | GPL-2.0 (systemd) | systemd 248+ (2021) |
| Living Ghost VM | qemu-img backing chains, virtiofs DAX | GPL-2.0+ (QEMU) | QEMU 5.0+ (2020) |
| Time-Travel Boot | swsusp hibernation, systemd-boot boot counting | GPL-2.0 (kernel) | Linux kernel (long-standing) |
| One-File Computer | Nix/Home Manager declarative model | LGPL-2.1+ (Nix) | 2003 / 2016 |
| Chunked-Time Machine | casync (rolling-hash chunking) | LGPL-2.1+ | 2017–2019 (dormant) |
| Process Resurrection | CRIU (checkpoint/restore) | GPL-2.0, LGPL-2.1 (lib/) | 2015 (Linux) |
| The Oracle | fanotify kernel API | GPL-2.0 (kernel) | Linux 2.6.36 (2010) |
| State Alchemy | Win2Linux mapping engine pattern | GPL-3.0 (Win2Linux) | 2025 |
| Cross-OS Delta Feed | zsync/rsync algorithm, IPFS/kubo | GPL-2.0+ / MIT+Apache-2.0 | 2003 / 2015 |
| Hardware snapshot | win2linux-prewipe pattern (IDs before wipe) | MIT (prewipe) | 2026 |
| In-place Linux install | Omarchy Jump (ISO→RAM, no USB) | community | 2026 |
| Native Windows deploy | iGloo (partition + restore) | GPL-3.0 | 2026 |

**Pattern inspiration:** the two-sided export/import shape follows the
Win2Linux migration helper (`AtillaTokmak/Win2Linux`, GPL-3.0) and the
dotfiles-migration pattern (`fedesapuppo/dotfiles-migration`, **no license —
referenced as a pattern only; no code copied**). Hardware compatibility
records follow the *intent* of `RadioPizza/win2linux-prewipe` (MIT) —
keep PCI/GPU/display IDs that a wipe destroys; no code copied. Omarchy
Jump and iGloo are adjacent installers (USB-less Linux hop; Windows-native
repartition). Neither does mount-not-copy. We credit them; we do not
vendor them.

**License compliance stance:** `omnigate` is MIT. We do NOT copy code from
any referenced project — we call standard systemd/QEMU/kernel tools (GPL is
compatible with using tools as separate programs) and reference patterns.
The one hard rule: never vendor code from a no-license repo
(`dotfiles-migration`); treat no-license as all-rights-reserved.

**Product vision:** the "migration = a mount, not a copy" framing and the
three-pillar architecture were directed by the project owner; the ten ideas
are the research agent's synthesis of verified technology.

## The thesis

Migrating an OS is not a file copy. It is **nixos-anywhere for Omarchy**:
reach the machine, install Omarchy, **keep the old disk**, and bring
every app, config, and library with you. The install is a mount + a
delta + a manifest — a 0-second event. The old system stays bootable.

nixos-anywhere (nix-community, MIT) is SSH → kexec → **wipe** → install →
reboot. omnigate anywhere is the same reach with the opposite disk ethic:
SSH → export stuff → **keep-disk** → install Omarchy beside the old OS →
restore → optional reboot. Wipe is opt-in (`--wipe --i-understand-wipe`).

## The three pillars (current)

| Pillar | What | Status |
|--------|------|--------|
| 1. Union mount | Old disk = overlayfs lower layer, zero-copy data visibility | ✅ implemented (`mount.py`) |
| 2. Differential sync | Reflink-first, copy only changed, skip re-downloadable | ✅ implemented (`sync.py`) |
| 3. Declarative manifest | Whole machine described, rebuildable | 🔜 planned |

## The Windows pillar (2026-08-21 — containerize, don't port)

For Windows sources, omnigate's answer is three-tier:

1. **SKIP** — Steam games stay on the existing NTFS library; Proton mounts
   it, no reinstall, no copy (Proton/NTFS pattern).
2. **DEFER** — apps with an Omarchy equivalent map to it (the existing
   mapper).
3. **CONTAINERIZE** — apps with NO equivalent (MS/Adobe suites, kernel
   anti-cheat games) run in a Windows container (WinPodX-style: dockur +
   Podman + FreeRDP RemoteApp) surfaced as native Linux windows.
   Migration = "install the container, don't port the app."

Hard wall: kernel-level anti-cheat (Valorant/Vanguard) cannot run on Linux.

## The world-breaking ten (research, verified against real tech)

1. **Ghost Drive** — old disk becomes a *permanent* zero-copy lower layer:
   rewrite each partition's GPT type GUID to the Discoverable Partitions
   Spec so `systemd-gpt-auto-generator` auto-mounts it forever. Migration =
   0-second event. Rollback = boot the old ESP (dual-boot without
   dual-booting). *This is pillar 1 upgraded from transitional to
   permanent — implemented as `mount.py ghost`.*

2. **The Coffin** — seal the old OS's `/usr` (+ `/etc`) as a signed
   `systemd-sysext`/`confext` image (DDI + dm-verity), merge it under the
   new kernel. The old OS becomes an immutable artifact you *run as an app*.
   Mutability routing captures old-OS writes as a replayable diff layer.

3. **Living Ghost VM** — boot the old physical partition as a qcow2 backing
   file in QEMU with **virtiofs DAX** (page cache shared into guest memory,
   ~20× faster, zero double-caching). Windows/macOS keep "running" while
   Omarchy owns the bare metal. CXL coherent memory is the end-state: two
   computers as one.

4. **Time-Travel Boot** — before cutover, hibernate the old OS (swsusp);
   the entire RAM state becomes a file. Resume it later in a VM. Fork a
   session: resume the same image twice, let one diverge, diff the machines.

5. **The One-File Computer** — the manifest captures *state*, not just
   packages: Steam library + verified signatures, browser profiles, dconf,
   registry → equivalents, content-addressed hashes for every blob.
   Migration = `git diff old-manifest omarchy-manifest`. The defer rule
   fires automatically against the Omarchy reference manifest.

6. **Chunked-Time Machine** — casync-style content-defined chunking
   (buzhash + SHA-512/256 + zstd). The delta between two OSes (or two Steam
   versions) approaches "only what's novel on earth." Chunks dedupe *across
   file boundaries* — two games sharing engine assets transfer once.

7. **Process Resurrection** — CRIU-checkpoint running apps (editor, browser,
   terminals — with open files, scrollback, TCP connections) before cutover,
   restore them on Omarchy. The OS changes *underneath running applications*.
   Checkpoint a game mid-boss-fight; your "save file" is a ptrace dump.

8. **The Oracle** — a pre-flight agent that runs on the OLD machine:
   enumerate apps/profiles/caches, clean re-downloadable content, checksum
   everything, generate the complete plan (union spec + manifest + diff) as
   a reviewable artifact. Fanotify keeps a live change journal during
   cutover — the final sync is only the diff since the Oracle started.

9. **State Alchemy** — semantic converters for app *state*: Steam saves +
   cloud-manifest reconciliation, browser profile conversion, dconf →
   equivalents, Windows registry hives → flat config. Migrate *meaning*, not
   just files. Defer-to-Omarchy applies per-field.

10. **Cross-OS Delta Feed** — zsync/rdiff binary deltas over HTTP + an
    IPFS/LAN seeding channel where the first migrated machine seeds the
    fleet. The chunk store is content-addressed, so unrelated users migrating
    different distros exchange chunks they both need. Migrating N machines
    costs ~1 copy of the data.

## Roadmap

1. ✅ Core pipeline (scanner/mapper/gate/generator/export-import)
2. ✅ Union mount (Layer 1) + `ghost` (Ghost Drive, #1)
3. ✅ Differential sync (Layer 2, reflink-first)
4. 🔜 **Flet wizard** — one window, three piles, five minutes (Phase 1–4)
5. 🔜 **Dual-boot walk** — wizard points at official Omarchy ISO + keep-disk
6. 🔜 **`omarchy setup import`** — destination first-run hook + menu leaf
7. 🔜 Manifest with state (Layer 3, #5)
8. 🔜 Oracle (#8 — the export side at full power; on-device LLM research
   done, see `docs/ONDEVICE_LLM_RESEARCH.md` — decision: **Needle is a
   leftover/path verb classifier, not the mapping oracle. Tables + curated DB
   are the oracle.**)
9. 🔜 State Alchemy (#9)
10. 🔜 Chunked sync (#6 — upgrades Layer 2)

## Principles

- **Tables first; Needle second.** Never auto-map a package. Needle is
  internal (leftover/path verbs). Not a chat. Fail-open without the engine.
- **Defer to Omarchy.** If Omarchy provides it, don't duplicate it.
- **Never guess.** Unknown apps get flagged, not auto-mapped.
- **Zero-copy first.** Mount before you copy. Copy only what changed.
- **Rollback always.** The old system stays bootable until you say otherwise.
