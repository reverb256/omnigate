# AGENTS.md — for AI coding agents

Guidance for AI agents working on this repo. The same rules apply to agent
and human contributions.

## Hard rules

- **Deterministic runtime.** No LLM calls at runtime. The shipped tool must
  work without any model. AI is used to BUILD, never to run.
- **Never guess.** Unknown apps get flagged for review, never auto-mapped.
- **Defer to Omarchy.** If Omarchy provides a capability, don't duplicate it.
- **No stubs.** Every deliverable is complete, verified by execution.
- **License.** MIT. Never vendor code from a no-license repo.

## Layout

- `scanner/` — detect installed apps (Linux/macOS/Windows)
- `mapper/` — classify (defer/map/unknown), compat gate, config porting
- `generator/` — emit Reverb-OS HM profile fragment
- `mount.py` — union-mount / Ghost Drive (zero-copy)
- `sync.py` — differential sync (reflink-first)
- `migrate.py` — export/import CLI

## Before committing

```bash
python -m compileall -q scanner mapper generator migrate.py mount.py sync.py
python -c "import json; json.load(open('mappings/apps.json'))"
```

See `docs/VISION.md` for the architecture + attribution.
