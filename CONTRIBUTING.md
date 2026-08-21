# Contributing to omnigate

Thanks for considering a contribution. This project is AI-built but
human-reviewed; the same standards apply to both.

## How to contribute

1. **Fork** the repo.
2. **Branch**: `git checkout -b feature/your-feature`.
3. **Run the checks** before submitting:
   ```bash
   python -m compileall -q scanner mapper generator migrate.py mount.py sync.py
   python -c "import json; json.load(open('mappings/apps.json'))"
   ```
4. **Submit a PR** with a description of what you changed and why.
5. We respond to all PRs within 48h.

## Standards

- Deterministic runtime: no LLM calls at runtime — the tool must work
  without any model.
- Defer to Omarchy: if Omarchy provides it, don't duplicate it.
- Never guess: unknown apps get flagged, not auto-mapped.
- License: MIT. Do not vendor code from no-license repos.
- Attribution: if you adapt an idea from elsewhere, credit it in the PR.

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) — report privately,
never in a public issue.
