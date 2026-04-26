# Amas Models — Formal Specs

This document is the contract between the Amas mentorship materials and every line of engine code in `engine/models/`. Each model below has its rules formalized to a level the engine can implement without interpretation.

**Companion docs:**
- Source-by-source summary: [`source_index.md`](source_index.md)
- Engine design and correctness invariants: [`../../docs/superpowers/specs/2026-04-26-amas-models-design.md`](../../docs/superpowers/specs/2026-04-26-amas-models-design.md)

---

## Glossary

_Every term the mentor uses, defined once. Models reference glossary terms instead of redefining them._

(to be filled during Phase 1 reading)

---

## Cross-cutting concepts

_Risk rules, session definitions, bias frameworks, confluences that apply to multiple models._

(to be filled during Phase 1 reading)

---

## Source map

_For each of the 24 source files, 2–3 sentences on what's in it and which models it informs. Detailed per-file summaries live in [`source_index.md`](source_index.md)._

(to be filled during Phase 1 reading)

---

# Models

(One H2-prefixed section per model identified in the materials, using the per-model template below.)

---

## Per-model template (reference, do not edit)

```
## Model: <name>

### Source citations
- Mentorship 6-H1 Reversal Models.pdf p.4–7
- 1st Call Mentorship 2025.txt L1240–1380

### Plain-English description
2–4 sentences.

### Anchor / setup timeframe
e.g., "H1 candle that closes between 09:30 and 16:00 ET"

### Detection rules (all must be true)
1. Numbered list. Each rule is one boolean condition expressed in OHLC values, prior bars, time, or other models' state.
2. Vague terms are translated to a numeric threshold or flagged TBD with the source quote.

### Entry trigger
Exact bar/condition that fires the trade.

### Stop loss
Defined price relative to a specific bar's high/low.

### Take profit / exit
Either fixed R or a defined condition.

### Direction logic
How long vs short is determined.

### Invalidation / discard
When the setup is dropped before resolution.

### Confluences / filters mentioned
Each becomes a togglable dashboard chip, computed as a `passes_<key>: bool` flag on every trade row.

### Open questions / ambiguities
Numbered list with source quote.

### Backtest results (filled in during Phase 4)
- Baseline (no filters): WR, EV, PF, N, period
- With recommended filter combo: WR, EV, PF, N
- Notable regime breaks
- Walk-forward: train EV vs test EV, overfitting score
```
