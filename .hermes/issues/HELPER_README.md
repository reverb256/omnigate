✅ Issues created as markdown (4 issues, tracked in `.hermes/issues/`).

To enable git-issues natively, run this once on the zephyr repo:

```bash
cd /home/j_kro/Projects/omarchy-migrate
git config issue.link "https://github.com/reverb256/omnigate/issues"
git config --global --add gitissue.enabled true   # only if using git-issue CLI
```

Or install [`git-issue`](https://github.com/jam23/git-issue) (Python):

```bash
python3 -m pip install --user git-issue
git issue  # see the issues board
```

My recommendation: **keep them as markdown for now** — you're happy with the `.hermes/issues/NUM-title.md` format, and converting to git-issue's JSON schema would be churn. The kanban mapping is:

```
Issue #1 → Phase 5 (OSR spike)  ← start here
Issue #2 → t5 (macOS test)
Issue #3 → hardened restore (Phase 8)
Issue #4 → cross-OS pack verify (Phase 9)
```

The `todo` list tracks the same thing. No double bookkeeping. Want me to wire markdown→todo sync (scan the issue files each session), or treat the `.md` issues as the source of truth and keep `todo` as a transient reminder?
