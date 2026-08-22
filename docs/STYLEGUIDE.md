# omnigate style guide

For anyone who writes words people will see: README, the site, the wizard, notices, `--help` that a non-developer might read.

There is no Omarchy style-guide file. Their voice lives in the manual — especially `Welcome`, `Coming from Mac or Windows`, and `Dotfiles`. We learn from that. We do not impersonate DHH.

---

## 1. Who you are talking to

| When | Who | Voice |
|------|-----|--------|
| On the old PC | A gamer or someone who uses a PC at work. Not an IT shop. | Plain. Calm. Specific. |
| After first Omarchy boot | Someone who loves computers, or wants to. | Hand them *their* book. Super+Space. Stop talking. |
| Internal docs / skills | Us | You may say Needle, verbs, kexec. They may not. |

If a sentence would make a tired person on Windows 10 close the window, cut it.

---

## 2. The only promise

**Five minutes. Feels like fifteen seconds. Then Omarchy.**

Omnigate is the on-ramp. It is allowed to occupy five minutes of their life. Those five minutes must feel like fifteen seconds. Then we leave.

That is not a slogan you print once. It is a filter. If a paragraph does not serve that clock, delete it.

How fifteen seconds is possible:

- Games stay on the old drive. We do not copy a terabyte.
- We do not scan the universe. No recursive `du` of 600 GB.
- Ceremony is one breath.
- Three piles. Not a catalog.

Installing Omarchy from the ISO is *their* time. Do not apologize for it. Do not pretend we own it.

---

## 3. Voice

Steal this from Omarchy’s manual:

- Talk to **you**.
- Short paragraphs. One idea each.
- Opinionated. Not corporate.
- Specific names: Steam, Word, Valorant, Super+Space.
- “Look, …” when the rule is hard.
- Invitation, not apology. The destination is different on purpose.

Do not steal:

- First person “I” / “everything I use.” That is DHH’s house.
- A tour of the whole OS. That is their manual.
- Softening (“might possibly want to consider”). Say the thing.

Zinsser still applies: simplicity, brevity, clarity, humanity. Imperative for instructions. “Run the export.” Not “You should utilize the export functionality.”

### Temperature

Warm. Direct. A little swagger. Never cute. Never mean about the old PC. They lived there.

---

## 4. Words

### Prefer

you, we, look, keep, stay, skip, mount, boot, pick, leave, gone, old drive, next to, Super+Space

### Forbidden on user-facing surfaces

| Don't | Why |
|-------|-----|
| LLM, Needle, chatbot, model, fine-tune, prompt | Not a chat product. Businesses we meet are not AI-fluent. |
| flake, nixos-rebuild, HM fragment, colmena | Wrong destination. |
| kexec, disko, overlayfs, virtiofs, gpt-auto-generator | Internals. “Mount” is enough. |
| utilize, leverage, solution, experience, seamless, journey (as marketing) | Slop. |
| `omarchy-migrate` | That command already means Omarchy’s *update* repairs. |

### Honest labels (wizard + site)

| Internals | What they see |
|-----------|----------------|
| map | Coming with you |
| defer | Already in Omarchy |
| skip / mount | Stays on your old drive |
| no_linux | Windows only — boot Windows |
| unknown | Needs a decision |
| noise | (folded, not listed) |

---

## 5. Structure of a page

1. The clock or the keep-disk line. First.
2. What they do. Numbered. Few.
3. What we will not do. Short.
4. A door to Omarchy (`omarchy.org/manual/…`). Then stop.

No status dashboards that say “Oracle” or “Coffin” on the public home. Curious people can find architecture later.

Footers:

```
Five minutes. Then Omarchy.
```

Not: “Built by AI. Runs without AI.”

---

## 6. Color and chrome

Osaka Jade is Omarchy’s default. On the **destination**, follow the current theme (`themes/*/colors.toml`). Do not invent a second brand after they land.

On the **on-ramp** (Windows wizard, this site), Osaka Jade is fine:

| Role | Hex |
|------|-----|
| Background | `#111c18` |
| Foreground | `#C1C497` |
| Accent / cyan | `#2DD5B7` |
| Green | `#549e6a` |
| Red | `#FF5345` |
| Bright | `#F6F5DD` |

### Flet-specific overrides

Flet uses Material 3 under the hood. We set `theme=ft.Theme(color_scheme_seed=ft.Colors.GREEN)` then override tokens to match Osaka Jade exactly:

```python
import flet as ft

BG      = "#111c18"
FG      = "#C1C497"
GREEN   = "#549e6a"
CYAN    = "#2DD5B7"
RED     = "#FF5345"
WHITE   = "#F6F5DD"

theme = ft.Theme(
    color_scheme_seed=ft.Colors.GREEN,
    color_scheme=ft.ColorScheme(
        primary=GREEN,
        on_primary=WHITE,
        surface=BG,
        on_surface=FG,
        secondary=CYAN,
        on_secondary=BG,
        error=RED,
        on_error=WHITE,
    ),
)
```

Body text must be at least 18sp on Windows/macOS. Buttons are large (min 48dp touch target). High contrast on `#111c18` — prefer `#F6F5DD` for body text, not `#C1C497` if readability demands it.

Meaning is not color alone. Green = coming with you. Yellow = needs a decision. Red = stop / Windows only. Also say it in words.

---

## 7. Names

| Thing | Name |
|-------|------|
| This product, on Windows/Mac/old Linux | **omnigate** |
| Destination wizard | `omarchy setup import` |
| Menu | Setup → Import from your old PC |
| Forbidden | `omarchy migrate`, `omarchy-migrate` |

Commands on the old PC stay `omnigate.ps1` / `omnigate.sh`. Omarchy’s CLI does not exist yet.

---

## 8. Examples

**Yes**

> Your Windows stays. We do not copy your games. Super+Space from there.

> Valorant stays on Windows. That is a publisher choice. Boot Windows to play.

> Look, this is the whole point. We are not here to format C:.

**No**

> omnigate is an AI-built, deterministic, hyper-optimized migration toolchain that utilizes overlayfs…

> Needle classifies leftovers internally. The user never chats with it.

> Reach a machine over SSH and run disko with a keep-disk ethic.

---

## 9. Omarchy’s AI skills (what we learned)

Shipped under `default/agents/skills/` in basecamp/omarchy:

- **omarchy** — customize *their* desktop (`~/.config/hypr`, themes, bar). Never edit `/usr/share/omarchy`.
- **diagnose-crash** — evidence first, boring causes first, honest account.

Those skills are for life *after* Super+Space. We do not wrap them. We do not mention them on the on-ramp. If they later pick a default agent, that is Omarchy’s first-run notice, not ours.

Their contributor `AGENTS.md` is the destination code style (bash, gum, `omarchy-*`, `$OMARCHY_PATH`). Follow it when we write `contrib/omarchy/`. It is not user-facing copy.

---

## 10. Checklist before you publish

- [ ] First sentence could be the whole page.
- [ ] A tired Windows user can finish it.
- [ ] Zero forbidden words.
- [ ] Games / keep-disk / honest wall if the topic touches them.
- [ ] A link to *their* manual if we are done.
- [ ] You did not sand Omarchy down.
- [ ] You did not linger.
