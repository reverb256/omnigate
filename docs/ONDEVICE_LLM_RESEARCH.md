# On-device LLM research — Needle spike (2026-08-22)

## Why we looked

omnigate's governing rule is "deterministic runtime, no LLM calls." A
sub-100MB on-device model would be a bundled primitive (like the Rust core),
not a network dependency — so it could add judgment without violating the
rule. The question: **can a 14MB model classify unknown apps with
confidence, offline?**

## What we tested

- **Needle 2** (`cactus-needle`, 45M params, 14MB single binary, 28MB RAM,
  600-1200 tok/s). Simple Attention Network architecture, distilled from
  Gemini tool-calling, Apache-2.0 weights, source-available C++ engine.
- Installed the engine + JAX CUDA on the homelab 3090 (had to fix a NixOS
  libz ELFCLASS32 trap: the system's `nix-ld/libz.so.1` is a 32-bit build
  that shadows the 64-bit one for pip-installed numpy/jax — fix is to
  prepend the 64-bit zlib store path to `LD_LIBRARY_PATH`).
- Ran 3 LoRA fine-tunes on `mappings/apps.json` (95 → 668 → 150 examples),
  built merged `.cact` models, tested structured extraction + tool calls.

## Results (honest)

| Attempt | Outcome |
|---|---|
| Base model, C++ engine, JSON tools | Emits calls, but echoes app name (no domain knowledge) |
| LoRA on 95 examples, 3 epochs | Loss 2.6 → 2.1; model "responds" instead of calling |
| LoRA on 668 examples, 4 epochs | Loss 2.6 → 1.66; still won't emit calls reliably; "unknown tool" bug |
| LoRA on 150 plain-output examples | Worse (3.6 loss) — model is trained for function-calling, not plain JSON |
| Base model + system prompt with mappings | Echos app name; 45M model can't reason from a 256-token context |

**Root cause:** small models narrate instead of acting. The EdgeVox
benchmark (18 small models) shows Qwen3-1.7B, SmolLM3-3B, Hermes-3-3B and
Phi-4-mini all "hallucinate an answer" instead of emitting tool calls at
≤3B scale. Our result matches the literature exactly: this is a known wall,
not our bug.

## What actually works

**Structured extraction.** Base Needle 2 reliably turns text into JSON
against a schema (its documented strength). Useful for parsing messy source
data (registry strings, Steam manifests) into the mapping schema.

## Alternatives researched (better for our case)

| Model | Size | License | Why it matters |
|---|---|---|---|
| Granite-4.0-1B | 1GB Q4 | Apache-2.0 | Best permissive ≤2B; actually emits calls (BFCL 50.2) |
| Granite-4.0-350M | 350MB | Apache-2.0 | Ultra-tiny; truncates but exists |
| FunctionGemma 270M | ~270MB | Gemma terms | Edge function-calling; fine-tune +47% accuracy |
| Qwen3-4B | ~3.5GB | Apache-2.0 | "Excellent" native JSON tool calling, 4GB VRAM |
| SmolLM3-3B | 1.9GB | Apache-2.0 | Fully open recipe, fine-tune + redistribute freely |
| Phi-4-mini | 2.8GB | MIT | Best reasoning per MB |
| ToolACE-2-8B | 4.9GB | Apache-2.0 | Best-quality 8B tool caller |

## Decision / recommendation

Keep the deterministic mapping DB (45 entries, 56 tests) as the source of
truth. Use a small model only as an **extractor + confidence gate**, never
as the oracle:

1. Parse messy source data (registry, Steam manifests, desktop files) into
   the mapping schema → a small extractor (base Needle 2, or Granite-1B)
   works today.
2. Confidence-gate unknown apps for human review → the deterministic "never
   auto-map" rule stays; the model pre-ranks the review list.

Do NOT try to make a ≤1B model learn the mapping table. If we want smarter
judgment later, Qwen3-4B (Apache-2.0) is the smallest model that reliably
emits tool calls.

## Artifacts (gitignored — large binaries)

- `checkpoints/needle_omnigate*.cact` — merged LoRA models (13.7MB each)
- `checkpoints/needle_lora*.pkl` — LoRA adapters
- `needle2.cact`, `linux-x86_64/needle` — base engine
- `needle_train*.jsonl` — training data (regenerable from mappings)
- `.venv-needle/` — Python 3.11 venv with jax CUDA + cactus-needle
