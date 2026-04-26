# Amas Models — Phase 1+2+3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `Statistic.ally/Amas Models/` project with: a thorough study of the Amas mentorship materials produced as `docs/model_specs.md`, a correctness-invariant-enforced engine scaffold (DB load, outcome resolver, filter primitives, model registry), and one end-to-end model proving the architecture works (detector → backtest → dashboard).

**Architecture:** Mirrors `Fractal Sweep/` — Python engine writes a fat `model_stats.json`; standalone HTML dashboard does only filtering/aggregation client-side. Reads the shared `Fractal Sweep/candle_science.duckdb` read-only. Every silent-edge bug class (TZ, dedup, lookahead, resolver fidelity, data quality, risk arithmetic, statistical hygiene, determinism) is enforced via assertions and fixture tests from the first commit.

**Tech Stack:** Python 3.14 · DuckDB 1.4.4 · pandas · pytest · plain HTML/vanilla JS (zero CDN deps)

**Spec:** [`docs/superpowers/specs/2026-04-26-amas-models-design.md`](../specs/2026-04-26-amas-models-design.md)

**Out of scope (separate plan after Phase 3):**
- Phase 4: implementing remaining models
- Phase 5: cross-model analysis, walk-forward
- Phase 6: Pine indicators
- Phase 7: daily-update cron integration

---

## File Structure

### Phase 1 deliverables (study, no code)

- Create: `Statistic.ally/Amas Models/docs/model_specs.md` — formal spec per model + glossary + cross-cutting concepts + source map
- Create: `Statistic.ally/Amas Models/docs/source_index.md` — per-source-file (24 files) summary

### Phase 2 deliverables (scaffold)

- Create: `Statistic.ally/Amas Models/CLAUDE.md` — agent guidance for this folder
- Create: `Statistic.ally/Amas Models/README.md` — human-facing overview, run instructions
- Create: `Statistic.ally/Amas Models/.gitignore`
- Create: `Statistic.ally/Amas Models/engine/__init__.py`
- Create: `Statistic.ally/Amas Models/engine/constants.py` — single source of truth for risk/sizing/resolver constants
- Create: `Statistic.ally/Amas Models/engine/db.py` — DB path resolution, TZ-safe load, data-quality checks
- Create: `Statistic.ally/Amas Models/engine/outcomes.py` — SL/TP scanner, MAE/MFE, equity tracking
- Create: `Statistic.ally/Amas Models/engine/filters.py` — filter primitives (SMT scaffolding, generic helpers)
- Create: `Statistic.ally/Amas Models/engine/stats.py` — agg(), Wilson CI, EV/PF, walk-forward helpers
- Create: `Statistic.ally/Amas Models/engine/models/__init__.py` — `MODELS` registry, `ModelDefinition`/`Filter` dataclasses
- Create: `Statistic.ally/Amas Models/engine/model_stats.py` — orchestrator + CLI
- Create: `Statistic.ally/Amas Models/model_dashboard.html` — empty chrome (header, model selector, theme toggle, tabs)
- Create: `Statistic.ally/Amas Models/tests/__init__.py`
- Create: `Statistic.ally/Amas Models/tests/conftest.py` — shared fixtures (synthetic OHLC factories)
- Create: `Statistic.ally/Amas Models/tests/test_db.py`
- Create: `Statistic.ally/Amas Models/tests/test_constants.py`
- Create: `Statistic.ally/Amas Models/tests/test_outcomes.py`
- Create: `Statistic.ally/Amas Models/tests/test_filters.py`
- Create: `Statistic.ally/Amas Models/tests/test_stats.py`
- Create: `Statistic.ally/Amas Models/tests/test_registry.py`
- Create: `Statistic.ally/Amas Models/tests/test_reproducibility.py`
- Modify: `Statistic.ally/index.html` — add hub link to Amas Models

### Phase 3 deliverables (first model end-to-end)

- Create: `Statistic.ally/Amas Models/engine/models/<chosen_model>.py` — `detect_setups`, model-specific filters
- Create: `Statistic.ally/Amas Models/tests/test_<chosen_model>.py` — fixture tests (trade-count, lookahead audit, direction symmetry)
- Modify: `Statistic.ally/Amas Models/engine/models/__init__.py` — register the model
- Modify: `Statistic.ally/Amas Models/model_dashboard.html` — wire up rendering against `model_stats.json`

The model name is determined during Phase 1; Phase 3 tasks reference `<chosen_model>` as a variable.

---

# PHASE 1: Study & Spec Document

The study phase produces no code. It produces two markdown files that are the contract for Phase 2 and 3.

### Task 1.1: Set up the docs folder skeleton

**Files:**
- Create: `Statistic.ally/Amas Models/docs/model_specs.md`
- Create: `Statistic.ally/Amas Models/docs/source_index.md`

- [ ] **Step 1: Create the folder and skeleton files**

```bash
mkdir -p "/Users/abhi/Projects/Statistic.ally/Amas Models/docs"
```

Create `Statistic.ally/Amas Models/docs/model_specs.md` with this exact content:

```markdown
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
```

Create `Statistic.ally/Amas Models/docs/source_index.md` with this exact content:

```markdown
# Source Index — Amas Materials

For each of the 24 files in `/Users/abhi/Projects/Amas + Bootcamp/`, a 2–3 sentence summary of what's in it and which models in [`model_specs.md`](model_specs.md) it informs.

(to be filled during Phase 1 reading)

## Files

### PDFs (8 long + 8 summary; the `(1).pdf` files are typically long versions)

- [ ] `Mentorship1-H1 Candle Trading Guide.pdf`
- [ ] `Mentorship1-H1 Candle Trading Guide (1).pdf`
- [ ] `Mentorship2-H1 Model & Risk.pdf`
- [ ] `Mentorship2-H1 Model & Risk (1).pdf`
- [ ] `Mentorship3-Trading Candle Analysis.pdf`
- [ ] `Mentorship3-Trading Candle Analysis-Summary.pdf`
- [ ] `Mentorship4-H1 Candle Trading Rules.pdf`
- [ ] `Mentorship4-H1 Candle Trading Rules (1).pdf`
- [ ] `Mentorship 6-H1 Reversal Models.pdf`
- [ ] `Mentorship 6-H1 Reversal Models (1).pdf`
- [ ] `Mentorship7-15m & H1 Trading Models.pdf`
- [ ] `Mentorship7-15m & H1 Trading Models (1).pdf`
- [ ] `Mentorship8-Trading Strategy Deep Dive.pdf`
- [ ] `Mentorship8-Trading Strategy Deep Dive (1).pdf`

### Transcripts (8 NoteGPT-formatted call transcripts)

- [ ] `NoteGPT_TRANSCRIPT_1st Call Mentorship 2025.txt`
- [ ] `NoteGPT_TRANSCRIPT_2nd Call Mentorship 2025.txt`
- [ ] `NoteGPT_TRANSCRIPT_3rd Call Mentorship 2025.txt`
- [ ] `NoteGPT_TRANSCRIPT_4th Call Mentorship 2025.txt`
- [ ] `NoteGPT_TRANSCRIPT_5th Call Mentorship 2025.txt`
- [ ] `NoteGPT_TRANSCRIPT_6th Call Mentorship 2025.txt`
- [ ] `NoteGPT_TRANSCRIPT_7th Call Mentorship 2025.txt`
- [ ] `NoteGPT_TRANSCRIPT_8th Call Mentorship 2025.txt`
```

- [ ] **Step 2: Commit the skeleton**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/docs/model_specs.md" "Amas Models/docs/source_index.md"
git commit -m "docs(amas): add Phase 1 study skeleton (model_specs + source_index)"
```

---

### Task 1.2: Read all 8 PDFs (long versions first)

The `(1).pdf` files are typically the longer/full versions; the smaller variants are summaries. Read in pairs and note any divergence between them — divergences become entries in the Open Questions / Ambiguities section of the relevant model.

**Files:**
- Modify: `Statistic.ally/Amas Models/docs/source_index.md` (fill in summaries)
- Modify: `Statistic.ally/Amas Models/docs/model_specs.md` (extract glossary terms, draft model sections)

- [ ] **Step 1: Read each PDF and update `source_index.md`**

For each PDF in `/Users/abhi/Projects/Amas + Bootcamp/`:

1. Use the Read tool with the absolute file path. Read the full document.
2. After reading, replace its `- [ ]` checkbox in `source_index.md` with `- [x]` and append a 2–3 sentence summary on the same line: what's in it, which models/topics it covers, and any notable rules or thresholds. If it overlaps with another file, note that too.
3. Whenever the PDF introduces a new term (CISD, sweep, FVG, displacement, BOS, premium/discount, draw on liquidity, OTE, smart money concept, etc.), add a glossary entry to `model_specs.md` under `## Glossary`. One entry per term, with the source citation (filename + page).
4. Whenever the PDF describes a distinct trading model (a setup with detection rules, entry, stop, target), draft a section under `# Models` using the per-model template. Fill what's specified; leave TBDs with the source quote inline for anything ambiguous.
5. Note divergences between long and summary versions (e.g., "Long version says wick must be ≥60%; summary doesn't specify") in the relevant model's Open Questions section.

Read order:

1. `Mentorship1-H1 Candle Trading Guide (1).pdf`
2. `Mentorship1-H1 Candle Trading Guide.pdf`
3. `Mentorship2-H1 Model & Risk (1).pdf`
4. `Mentorship2-H1 Model & Risk.pdf`
5. `Mentorship3-Trading Candle Analysis.pdf`
6. `Mentorship3-Trading Candle Analysis-Summary.pdf`
7. `Mentorship4-H1 Candle Trading Rules (1).pdf`
8. `Mentorship4-H1 Candle Trading Rules.pdf`
9. `Mentorship 6-H1 Reversal Models (1).pdf`
10. `Mentorship 6-H1 Reversal Models.pdf`
11. `Mentorship7-15m & H1 Trading Models (1).pdf`
12. `Mentorship7-15m & H1 Trading Models.pdf`
13. `Mentorship8-Trading Strategy Deep Dive (1).pdf`
14. `Mentorship8-Trading Strategy Deep Dive.pdf`

- [ ] **Step 2: Commit progress after each pair of files**

After each pair (long + summary of one mentorship session), commit:

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/docs/"
git commit -m "docs(amas): study Mentorship<N> — <topic in 6 words>"
```

Frequent commits ensure if the session ends mid-study, the next session knows exactly where to resume from `source_index.md`'s checkbox state.

---

### Task 1.3: Read all 8 transcripts

Transcripts add context, examples, exceptions, and live trade walkthroughs the PDFs don't have. They often clarify ambiguities marked during PDF reading.

**Files:**
- Modify: `Statistic.ally/Amas Models/docs/source_index.md` (fill in summaries)
- Modify: `Statistic.ally/Amas Models/docs/model_specs.md` (refine model sections, resolve TBDs)

- [ ] **Step 1: Read each transcript in order and update both docs**

For each transcript file in `/Users/abhi/Projects/Amas + Bootcamp/`:

1. Use the Read tool with the absolute file path.
2. Update `source_index.md`'s checkbox to `- [x]` with a 2–3 sentence summary.
3. For each ambiguity already in `model_specs.md`'s Open Questions, check whether this transcript resolves it. If yes, update the rule and remove the ambiguity (citing the transcript).
4. Add new ambiguities discovered in the transcript.
5. Add new glossary terms if the mentor introduces any new vocabulary.
6. If a transcript describes a model not yet in `model_specs.md`, add it.

Read order: 1st through 8th in numerical order.

- [ ] **Step 2: Commit after each transcript**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/docs/"
git commit -m "docs(amas): study Call <N> transcript — <topic in 6 words>"
```

---

### Task 1.4: Cross-cutting concepts pass

After all 24 files are read, do a synthesis pass on `model_specs.md`.

**Files:**
- Modify: `Statistic.ally/Amas Models/docs/model_specs.md`

- [ ] **Step 1: Extract cross-cutting concepts**

Read every model's section. Identify rules, filters, or definitions that appear in multiple models (e.g., session definitions, bias frameworks, risk rules, SMT semantics). Move them to the `## Cross-cutting concepts` top-level section. Each model then references the cross-cutting concept by name instead of duplicating the rule.

- [ ] **Step 2: Fill in the source map**

Under `## Source map`, list each of the 24 files with which models it informs. This is a 1-line entry per file (the long-form summaries already live in `source_index.md`).

- [ ] **Step 3: Audit Open Questions**

For each model, review the Open Questions list. Flag the top 3–5 ambiguities most likely to materially affect detection (e.g., "wick threshold for 'rejection' — values from 50% to 70% across sources"). These are the items the user must decide before engine code locks them in.

- [ ] **Step 4: Pick the simplest model for Phase 3**

Read all model sections. Pick the model with:
- Fewest ambiguities (Open Questions list shortest)
- Simplest detection logic (fewest dependent bars, no multi-stage triggers, ideally single-anchor)
- Most explicit numeric thresholds

Add a note at the top of `model_specs.md` under a new `## Phase 3 candidate` heading, naming the chosen model and giving 2-3 sentences of justification. This is the `<chosen_model>` referenced throughout Phase 3 below.

- [ ] **Step 5: Commit and pause for user review**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/docs/"
git commit -m "docs(amas): synthesize cross-cutting concepts and pick Phase 3 candidate"
```

The user reviews `model_specs.md` at this point. Their corrections feed back into the doc before Phase 3 detector code is written. (Per spec, Phase 2 scaffolding may proceed in parallel with this review — it doesn't depend on the model choice.)

---

# PHASE 2: Engine Scaffold (correctness invariants enforced from line 1)

The scaffold contains zero model logic. It only stands up the load layer, outcome resolver, statistical helpers, registry, and dashboard chrome — every one with the assertions and tests required by the spec's Correctness Invariants section.

### Task 2.1: Project root files (CLAUDE.md, README.md, .gitignore, hub link)

**Files:**
- Create: `Statistic.ally/Amas Models/CLAUDE.md`
- Create: `Statistic.ally/Amas Models/README.md`
- Create: `Statistic.ally/Amas Models/.gitignore`
- Modify: `Statistic.ally/index.html` (add hub link)

- [ ] **Step 1: Create `Amas Models/CLAUDE.md`**

```markdown
# Amas Models

Backtest engine + dashboard for trading models extracted from the Amas mentorship materials. Same pattern as `Fractal Sweep/`: Python engine writes `model_stats.json`, single-file dashboard reads it.

## Stack
- Python 3.14 · DuckDB 1.4.4 · pandas
- Standalone HTML dashboard, zero CDN deps

## Folder layout

```
Amas Models/
├── model_dashboard.html        single-file dashboard
├── model_stats.json            engine output (gitignored)
├── engine/                     Python backtest code
│   ├── constants.py            single source of truth: MAX_RISK_PTS=20.0, RISK_PER_TRADE_USD=400, point values, OUTCOME_MAX_BARS=1440
│   ├── db.py                   DB load, TZ conversion, data-quality assertions
│   ├── outcomes.py             SL/TP scanner, MAE/MFE, equity tracking
│   ├── filters.py              filter primitives (SMT, etc.)
│   ├── stats.py                agg(), Wilson CI, EV/PF, walk-forward helpers
│   ├── models/                 one Python file per Amas model
│   │   ├── __init__.py         MODELS registry
│   │   └── <model>.py
│   ├── model_stats.py          orchestrator + CLI
│   └── daily_update.py         (Phase 7) hook into Fractal Sweep's cron
├── docs/
│   ├── model_specs.md          formal spec per model — canonical source of truth
│   └── source_index.md         per-source-file summary
├── pine/                       (Phase 6) one .pine per validated model
├── tests/                      pytest suite
├── data/                       cached intermediates (gitignored)
└── assets/                     dashboard images
```

## Running

Engine scripts self-locate. Run from the `Amas Models/` folder:

```bash
python3 engine/model_stats.py                            # all models, NQ
python3 engine/model_stats.py --models <model_key>       # subset
python3 engine/model_stats.py --table es_1m              # ES instead of NQ
python3 -m pytest tests/ -q                              # test suite
```

Dashboard served from the repo root (Statistic.ally/):

```bash
python3 -m http.server 8001
# → http://localhost:8001/Amas Models/model_dashboard.html
```

## Database

Reads `../Fractal Sweep/candle_science.duckdb` (the shared DB). **Read-only from this folder.** Daily updates stay in `Fractal Sweep/engine/daily_update.py`.

Schema: `nq_1m`, `es_1m` — `timestamp TIMESTAMPTZ, open/high/low/close DOUBLE, volume BIGINT`. Stored as `America/Toronto`. **Always convert at the SQL layer:** `SELECT timezone('America/New_York', timestamp) AS ts, ...`.

## Correctness invariants (non-negotiable)

See [`../docs/superpowers/specs/2026-04-26-amas-models-design.md`](../docs/superpowers/specs/2026-04-26-amas-models-design.md) section "Correctness invariants" — 8 categories of silent-edge bug each engine commit must defend against:

A. Timestamp/TZ correctness — `[ns]` resolution, NY tz, duration-based windows
B. Trade deduplication — unique by (model, instrument, anchor_ts, direction)
C. Lookahead/future-leak — causal detection, no cross-anchor lookahead
D. Outcome resolver fidelity — same-bar tie → SL, OUTCOME_MAX_BARS=1440, expired excluded from WR
E. Data quality — gap/dup/monotonic/OHLC/schema assertions on every load
F. Risk arithmetic — single-source constants, NQ vs ES point values, R-in-points-then-converted
G. Statistical hygiene — N visible, Wilson CIs, period-matched comparisons, AND-semantics filter combos
H. Determinism — no randomness, no wall-clock in logic, byte-for-byte JSON reproducibility

These invariants are enforced via runtime assertions (not gated on DEBUG) and pytest tests. Every reported finding gets the edge-inflation checklist before being trusted.
```

- [ ] **Step 2: Create `Amas Models/README.md`**

```markdown
# Amas Models

Personal research tool: turn Amas mentorship materials into formalized model specs, backtest each model over 14 years of NQ/ES 1m data, and visualize results in a single-page dashboard.

Mirrors `Fractal Sweep/`'s pattern.

## Quick start

```bash
# from Statistic.ally/
pip install duckdb pandas numpy

# generate model_stats.json for all models on NQ
cd "Amas Models"
python3 engine/model_stats.py

# run tests
python3 -m pytest tests/ -q

# serve dashboard from repo root
cd ..
python3 -m http.server 8001
# open http://localhost:8001/Amas Models/model_dashboard.html
```

See [`CLAUDE.md`](CLAUDE.md) for engine details, [`docs/model_specs.md`](docs/model_specs.md) for the formalized models.
```

- [ ] **Step 3: Create `Amas Models/.gitignore`**

```gitignore
# engine output
model_stats.json

# cached intermediates
data/

# python
__pycache__/
*.pyc
.pytest_cache/

# os
.DS_Store
```

- [ ] **Step 4: Add hub link to `Statistic.ally/index.html`**

Read `Statistic.ally/index.html` first. Find the section that links to `Fractal Sweep/model_dashboard.html` (the existing project link) and add a sibling link to `Amas Models/model_dashboard.html` immediately after it, using the same markup pattern. Do not invent new styling.

- [ ] **Step 5: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/CLAUDE.md" "Amas Models/README.md" "Amas Models/.gitignore" index.html
git commit -m "feat(amas): scaffold project root + hub link"
```

---

### Task 2.2: `engine/constants.py` — single source of truth

**Files:**
- Create: `Statistic.ally/Amas Models/engine/__init__.py`
- Create: `Statistic.ally/Amas Models/engine/constants.py`
- Create: `Statistic.ally/Amas Models/tests/__init__.py`
- Create: `Statistic.ally/Amas Models/tests/test_constants.py`

- [ ] **Step 1: Write the failing test**

Create `Statistic.ally/Amas Models/tests/__init__.py` as an empty file.

Create `Statistic.ally/Amas Models/tests/test_constants.py`:

```python
"""Tests for engine.constants — single source of truth for risk/sizing/resolver values."""
from engine import constants


def test_min_risk_pts_is_none():
    """No lower floor on risk; arbitrarily tight stops pass."""
    assert constants.MIN_RISK_PTS is None


def test_max_risk_pts_is_twenty():
    """20-point cap on NQ at $20/pt = $400 risk."""
    assert constants.MAX_RISK_PTS == 20.0


def test_outcome_max_bars_matches_fractal_sweep():
    assert constants.OUTCOME_MAX_BARS == 1440


def test_point_values_per_instrument():
    assert constants.POINT_VALUES["nq_1m"] == 20.0
    assert constants.POINT_VALUES["es_1m"] == 50.0


def test_risk_per_trade_usd():
    assert constants.RISK_PER_TRADE_USD == 400.0


def test_max_risk_dollars_consistent():
    """MAX_RISK_PTS × NQ point value = RISK_PER_TRADE_USD; 20 × $20 = $400."""
    assert constants.MAX_RISK_PTS * constants.POINT_VALUES["nq_1m"] == constants.RISK_PER_TRADE_USD
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_constants.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine'` (the package doesn't exist yet).

- [ ] **Step 3: Create the package**

Create `Statistic.ally/Amas Models/engine/__init__.py` as an empty file.

Create `Statistic.ally/Amas Models/engine/constants.py`:

```python
"""Single source of truth for risk, sizing, and outcome-resolver constants.

Per the Amas Models design spec, Category F (Risk arithmetic): no model file
redefines these values. If a model needs different sizing, it consults
POINT_VALUES[table_name].
"""
from typing import Optional

# Risk gates — applied to every setup before the outcome resolver runs.
# Setups with risk_pts > MAX_RISK_PTS are rejected. With MIN_RISK_PTS = None
# there is no lower floor; arbitrarily tight stops pass.
MIN_RISK_PTS: Optional[float] = None
MAX_RISK_PTS: float = 20.0  # = $400 / $20-per-NQ-point (NQ mini)

# Outcome resolver lookback. A trade unresolved within this many 1m bars is EXPIRED
# (excluded from WR/EV but counted in N). Matches Fractal Sweep.
OUTCOME_MAX_BARS: int = 1440  # 24h of 1m bars

# Per-trade risk in USD. Drives sizing for both NQ and ES via POINT_VALUES.
RISK_PER_TRADE_USD: float = 400.0

# Per-instrument point values (mini contracts). Mapped by DuckDB table name
# (matches the --table CLI arg).
POINT_VALUES: dict[str, float] = {
    "nq_1m": 20.0,  # NQ mini, $20/pt
    "es_1m": 50.0,  # ES mini, $50/pt
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_constants.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/engine/__init__.py" "Amas Models/engine/constants.py" "Amas Models/tests/__init__.py" "Amas Models/tests/test_constants.py"
git commit -m "feat(amas): engine.constants — single source of truth for risk/sizing values"
```

---

### Task 2.3: `engine/db.py` — TZ-safe load + data-quality checks

This is the most heavily tested module. Per the spec, "the load layer is the most heavily tested module in the engine."

**Files:**
- Create: `Statistic.ally/Amas Models/engine/db.py`
- Create: `Statistic.ally/Amas Models/tests/conftest.py`
- Create: `Statistic.ally/Amas Models/tests/test_db.py`

- [ ] **Step 1: Create the shared test fixtures file**

Create `Statistic.ally/Amas Models/tests/conftest.py`:

```python
"""Shared pytest fixtures for the Amas Models test suite.

Synthetic OHLC factories used across multiple test modules.
"""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def synthetic_bars_1m():
    """5 days of 1m bars, RTH only (09:30-16:00 ET), simple drift up.

    Returns a DataFrame with the same dtypes the real DB load produces:
    ts (tz-aware datetime64[ns, America/New_York]), open/high/low/close (float),
    volume (int64).
    """
    def _make(start: str = "2024-01-08", days: int = 5, base_price: float = 100.0):
        rows = []
        for d in pd.bdate_range(start=start, periods=days, tz="America/New_York"):
            session_start = d.replace(hour=9, minute=30, second=0, microsecond=0)
            session_end = d.replace(hour=16, minute=0, second=0, microsecond=0)
            ts_range = pd.date_range(session_start, session_end, freq="1min", inclusive="left")
            for i, ts in enumerate(ts_range):
                price = base_price + i * 0.01
                rows.append({
                    "ts": ts,
                    "open": price,
                    "high": price + 0.05,
                    "low": price - 0.05,
                    "close": price + 0.02,
                    "volume": 100,
                })
            base_price += 1.0  # carry over end-of-day to next day
        df = pd.DataFrame(rows)
        df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
        df["volume"] = df["volume"].astype("int64")
        return df
    return _make
```

- [ ] **Step 2: Write the failing tests for `db.py`**

Create `Statistic.ally/Amas Models/tests/test_db.py`:

```python
"""Tests for engine.db — DB load, TZ correctness, data-quality assertions.

Per the design spec, Category A (TZ correctness) and Category E (Data quality):
every load must be tz-aware, [ns] resolution, monotonic, no duplicates, OHLC sane,
schema validated.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from engine import db


def test_db_path_resolves_to_fractal_sweep():
    p = db.db_path()
    assert p.name == "candle_science.duckdb"
    assert p.parent.name == "Fractal Sweep"


def test_db_path_exists():
    assert db.db_path().exists(), "Shared DB not found — Fractal Sweep must be present"


def test_load_bars_returns_tz_aware_ns_resolution():
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    assert df["ts"].dt.tz is not None, "ts must be tz-aware"
    assert df["ts"].dtype.unit == "ns", "ts must be [ns] resolution"
    assert str(df["ts"].dt.tz) == "America/New_York", "ts must be in NY tz"


def test_load_bars_schema():
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert df["open"].dtype == "float64"
    assert df["volume"].dtype == "int64"


def test_load_bars_monotonic_and_unique():
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    assert df["ts"].is_monotonic_increasing
    assert df["ts"].is_unique


def test_load_bars_ohlc_sanity():
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    assert (df["low"] <= df[["open", "close", "high"]].min(axis=1)).all()
    assert (df["high"] >= df[["open", "close", "low"]].max(axis=1)).all()


def test_tz_sentinel_known_minute():
    """Sanity test: the 09:30 ET open of a known weekday must exist with the right wall-clock timestamp.

    Uses 2024-01-02 (first trading day of 2024, Tue, no half-day).
    """
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    target = pd.Timestamp("2024-01-02 09:30:00", tz="America/New_York")
    matches = df[df["ts"] == target]
    assert len(matches) == 1, f"Expected exactly one bar at 2024-01-02 09:30 ET; got {len(matches)}"


def test_assert_load_invariants_rejects_naive_timestamps():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:31"]),
        "open": [100.0, 100.1], "high": [100.5, 100.6], "low": [99.5, 99.6],
        "close": [100.2, 100.3], "volume": [10, 10],
    })
    with pytest.raises(AssertionError, match="tz-aware"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_us_resolution():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:31"], utc=True).astype("datetime64[us, UTC]"),
        "open": [100.0, 100.1], "high": [100.5, 100.6], "low": [99.5, 99.6],
        "close": [100.2, 100.3], "volume": [10, 10],
    })
    with pytest.raises(AssertionError, match=r"\[ns\]"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_duplicate_timestamps():
    ts = pd.Timestamp("2024-01-02 09:30", tz="America/New_York")
    df = pd.DataFrame({
        "ts": [ts, ts],
        "open": [100.0, 100.1], "high": [100.5, 100.6], "low": [99.5, 99.6],
        "close": [100.2, 100.3], "volume": [10, 10],
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    with pytest.raises(AssertionError, match="unique"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_non_monotonic():
    df = pd.DataFrame({
        "ts": [
            pd.Timestamp("2024-01-02 09:31", tz="America/New_York"),
            pd.Timestamp("2024-01-02 09:30", tz="America/New_York"),
        ],
        "open": [100.0, 100.1], "high": [100.5, 100.6], "low": [99.5, 99.6],
        "close": [100.2, 100.3], "volume": [10, 10],
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    with pytest.raises(AssertionError, match="monotonic"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_invalid_ohlc():
    df = pd.DataFrame({
        "ts": [pd.Timestamp("2024-01-02 09:30", tz="America/New_York")],
        "open": [100.0], "high": [99.0], "low": [101.0],  # high < low
        "close": [100.5], "volume": [10],
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    with pytest.raises(AssertionError, match="OHLC"):
        db.assert_load_invariants(df)


def test_check_gaps_flags_intra_session_gap():
    """A 10-minute gap during RTH is reported."""
    rows = []
    base = pd.Timestamp("2024-01-02 09:30", tz="America/New_York")
    for i in range(10):
        rows.append({"ts": base + pd.Timedelta(minutes=i), "open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0, "volume": 10})
    # gap: skip minutes 10..19, resume at minute 20
    for i in range(20, 30):
        rows.append({"ts": base + pd.Timedelta(minutes=i), "open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0, "volume": 10})
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    gaps = db.check_gaps(df)
    assert len(gaps) == 1
    assert gaps[0]["gap_minutes"] == 10
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_db.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine.db'`.

- [ ] **Step 4: Implement `engine/db.py`**

Create `Statistic.ally/Amas Models/engine/db.py`:

```python
"""DB load and data-quality enforcement for the Amas Models engine.

Per the design spec, Category A (TZ correctness) and Category E (Data quality):
every load must be tz-aware [ns] resolution, monotonic, unique, OHLC-sane.
The assertions run in production, not gated on DEBUG.

Reads the shared `candle_science.duckdb` from the sibling Fractal Sweep folder
in read-only mode. Never writes — daily updates stay in Fractal Sweep's cron.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd


def db_path() -> Path:
    """Path to the shared candle_science.duckdb. The DB lives in Fractal Sweep/."""
    return Path(__file__).resolve().parent.parent.parent / "Fractal Sweep" / "candle_science.duckdb"


def load_bars(
    table: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """Load 1m bars from the shared DB, converted to America/New_York at the SQL layer.

    Args:
        table: 'nq_1m' or 'es_1m'.
        start: inclusive start date as 'YYYY-MM-DD' (in NY tz). Optional.
        end: exclusive end date as 'YYYY-MM-DD' (in NY tz). Optional.

    Returns a DataFrame with columns: ts, open, high, low, close, volume.
    All invariants (tz-aware, [ns], unique, monotonic, OHLC-sane) are asserted
    before return. If they fail, this function raises AssertionError.
    """
    if table not in ("nq_1m", "es_1m"):
        raise ValueError(f"Unknown table: {table!r}. Expected 'nq_1m' or 'es_1m'.")

    where_clauses = []
    params: list[object] = []
    if start is not None:
        where_clauses.append("timezone('America/New_York', timestamp) >= ?::TIMESTAMPTZ")
        params.append(f"{start} 00:00:00-05")  # naive offset; query is tz-aware at SQL layer
    if end is not None:
        where_clauses.append("timezone('America/New_York', timestamp) < ?::TIMESTAMPTZ")
        params.append(f"{end} 00:00:00-05")
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = f"""
        SELECT
            timezone('America/New_York', timestamp) AS ts,
            open, high, low, close, volume
        FROM {table}
        {where_sql}
        ORDER BY timestamp
    """

    with duckdb.connect(str(db_path()), read_only=True) as con:
        df = con.execute(sql, params).fetchdf()

    # Force [ns] resolution + NY tz. pandas 2.0+ may hand back [us]; this is the bug
    # that bit Fractal Sweep silently for months. Be explicit.
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC").dt.tz_convert("America/New_York")
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")

    assert_load_invariants(df)
    return df


def assert_load_invariants(df: pd.DataFrame) -> None:
    """Fail loudly if the loaded DataFrame violates any silent-edge invariant.

    Runs in production, not gated on DEBUG. The cost is microseconds; the value
    is loud failure on any data corruption.
    """
    expected_cols = ["ts", "open", "high", "low", "close", "volume"]
    assert list(df.columns) == expected_cols, f"schema: expected {expected_cols}, got {list(df.columns)}"

    assert df["ts"].dt.tz is not None, "ts must be tz-aware (got naive timestamps)"
    assert df["ts"].dtype.unit == "ns", f"ts must be [ns] resolution, got [{df['ts'].dtype.unit}]"

    assert df["ts"].is_unique, "ts must be unique (duplicate bars)"
    assert df["ts"].is_monotonic_increasing, "ts must be monotonic increasing"

    if len(df) > 0:
        low_le_min = (df["low"] <= df[["open", "close", "high"]].min(axis=1)).all()
        high_ge_max = (df["high"] >= df[["open", "close", "low"]].max(axis=1)).all()
        assert low_le_min and high_ge_max, "OHLC sanity violated: low > min(o,c,h) or high < max(o,c,l)"


def check_gaps(df: pd.DataFrame, threshold_minutes: int = 5) -> list[dict]:
    """Report intra-session gaps larger than threshold_minutes.

    RTH = 09:30-16:00 ET. Cross-session gaps (overnight, weekend) are expected
    and not reported. Each reported gap is a dict with keys: prev_ts, next_ts,
    gap_minutes.

    Note: this is a best-effort check. It does not abort load; it returns the
    list of gaps so callers can tag affected setups (`has_data_gap: bool`).
    """
    if len(df) < 2:
        return []
    diffs = df["ts"].diff().dt.total_seconds() / 60.0
    times = df["ts"].dt.time
    in_rth = (times >= pd.Timestamp("09:30").time()) & (times <= pd.Timestamp("16:00").time())
    same_session = df["ts"].dt.date == df["ts"].shift(1).dt.date
    flagged = (diffs > threshold_minutes) & same_session & in_rth & in_rth.shift(1, fill_value=False)
    gaps = []
    for i in df.index[flagged]:
        gaps.append({
            "prev_ts": df.loc[i - 1, "ts"] if i - 1 in df.index else df["ts"].iloc[df.index.get_loc(i) - 1],
            "next_ts": df.loc[i, "ts"],
            "gap_minutes": float(diffs.loc[i]),
        })
    return gaps
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_db.py -v
```

Expected: all 13 tests pass. If `test_db_path_exists` and the live-load tests fail because the DB is gitignored and possibly not present on this machine, mark them with `pytest.skip` only if `db.db_path().exists()` is False — but the rest must pass.

If the live-load tests fail for reasons other than missing DB (e.g. dtype mismatches, schema drift), that's a real bug — investigate, do not silence.

- [ ] **Step 6: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/engine/db.py" "Amas Models/tests/conftest.py" "Amas Models/tests/test_db.py"
git commit -m "feat(amas): engine.db — TZ-safe load + data-quality assertions"
```

---

### Task 2.4: `engine/outcomes.py` — SL/TP scanner with all resolver invariants

**Files:**
- Create: `Statistic.ally/Amas Models/engine/outcomes.py`
- Create: `Statistic.ally/Amas Models/tests/test_outcomes.py`

- [ ] **Step 1: Write the failing tests**

Create `Statistic.ally/Amas Models/tests/test_outcomes.py`:

```python
"""Tests for engine.outcomes — SL/TP scanner.

Per the design spec, Category D (Outcome resolver fidelity): same-bar tie → SL,
expired excluded from WR, MAE/MFE measured to resolution, direction symmetric,
deterministic & idempotent.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine.outcomes import resolve_outcome, Setup, Outcome


def _make_bars(prices: list[tuple[float, float, float, float]], start_ts: str = "2024-01-02 10:00") -> pd.DataFrame:
    """prices is a list of (open, high, low, close) tuples, one per minute starting at start_ts."""
    base = pd.Timestamp(start_ts, tz="America/New_York")
    rows = []
    for i, (o, h, l, c) in enumerate(prices):
        rows.append({
            "ts": base + pd.Timedelta(minutes=i),
            "open": o, "high": h, "low": l, "close": c, "volume": 10,
        })
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    return df


def test_long_tp_hit_returns_r_one():
    bars = _make_bars([
        (100.0, 100.5, 99.8, 100.2),  # entry bar (excluded from resolution)
        (100.2, 100.6, 100.1, 100.5),
        (100.5, 105.0, 100.4, 104.8),  # high reaches TP=105
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=95.0, tp_price=105.0, direction="long",
    )
    out = resolve_outcome(bars, setup)
    assert out.outcome == "TP"
    assert out.r == pytest.approx(1.0)


def test_long_sl_hit_returns_r_negative_one():
    bars = _make_bars([
        (100.0, 100.5, 99.8, 100.2),
        (100.2, 100.6, 100.1, 100.5),
        (100.5, 100.7, 94.0, 95.0),  # low reaches SL=95
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=95.0, tp_price=105.0, direction="long",
    )
    out = resolve_outcome(bars, setup)
    assert out.outcome == "SL"
    assert out.r == pytest.approx(-1.0)


def test_same_bar_tp_and_sl_resolves_to_sl():
    """Per spec invariant D.1: same-bar tie → SL."""
    bars = _make_bars([
        (100.0, 100.5, 99.8, 100.2),  # entry bar
        (100.5, 106.0, 94.0, 100.0),  # high≥TP AND low≤SL → SL wins
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=95.0, tp_price=105.0, direction="long",
    )
    out = resolve_outcome(bars, setup)
    assert out.outcome == "SL"
    assert out.r == pytest.approx(-1.0)


def test_short_tp_hit_returns_r_one():
    """Direction symmetry: short setup with falling price."""
    bars = _make_bars([
        (100.0, 100.2, 99.5, 99.8),
        (99.8, 99.9, 95.0, 95.5),  # low reaches TP=95
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=105.0, tp_price=95.0, direction="short",
    )
    out = resolve_outcome(bars, setup)
    assert out.outcome == "TP"
    assert out.r == pytest.approx(1.0)


def test_short_sl_hit_returns_r_negative_one():
    bars = _make_bars([
        (100.0, 100.2, 99.5, 99.8),
        (99.8, 105.5, 99.7, 105.0),  # high reaches SL=105
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=105.0, tp_price=95.0, direction="short",
    )
    out = resolve_outcome(bars, setup)
    assert out.outcome == "SL"
    assert out.r == pytest.approx(-1.0)


def test_expired_when_max_bars_exhausted():
    """Per spec invariant D.2: unresolved within OUTCOME_MAX_BARS → EXPIRED."""
    # Constant prices, never hits TP or SL
    bars = _make_bars([(100.0, 100.5, 99.5, 100.0)] * 1500)
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=95.0, tp_price=105.0, direction="long",
    )
    out = resolve_outcome(bars, setup)
    assert out.outcome == "EXPIRED"
    assert out.r is None


def test_entry_bar_excluded_from_resolution():
    """Per spec invariant C.3: bars with ts == entry_ts do not contribute to TP/SL."""
    # Entry bar's high reaches TP, but it must be ignored
    bars = _make_bars([
        (100.0, 106.0, 99.9, 100.0),  # entry bar — high=106 but ignored
        (100.0, 100.2, 99.9, 100.0),  # subsequent bar, no resolution
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=95.0, tp_price=105.0, direction="long",
    )
    out = resolve_outcome(bars, setup)
    # Should NOT be TP — entry bar must be excluded
    assert out.outcome != "TP"


def test_mae_mfe_measured_to_resolution():
    """Per spec invariant D.4: MAE/MFE for resolved trades stop at resolution bar."""
    bars = _make_bars([
        (100.0, 100.5, 99.8, 100.2),  # entry bar
        (100.2, 102.0, 100.0, 101.5),
        (101.5, 103.0, 101.0, 102.5),
        (102.5, 105.5, 102.0, 105.2),  # TP hit here
        (105.2, 110.0, 95.0, 95.0),    # AFTER resolution — must not affect MAE/MFE
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=95.0, tp_price=105.0, direction="long",
    )
    out = resolve_outcome(bars, setup)
    assert out.outcome == "TP"
    # MFE in points = 5.5 (from 100 to 105.5 in resolution bar)
    assert out.mfe_pts == pytest.approx(5.5)
    # MAE in points = 1.0 (from 100 down to 99.8 in entry-not-counted ... actually first non-entry bar low=100.0)
    # Lowest low post-entry up to resolution bar = min(100.0, 101.0, 102.0) = 100.0
    assert out.mae_pts == pytest.approx(0.0, abs=0.01)


def test_resolve_is_deterministic_and_idempotent():
    """Per spec invariant B.4: same input → same output, every time."""
    bars = _make_bars([
        (100.0, 100.5, 99.8, 100.2),
        (100.2, 100.6, 100.1, 100.5),
        (100.5, 105.0, 100.4, 104.8),
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=95.0, tp_price=105.0, direction="long",
    )
    out1 = resolve_outcome(bars, setup)
    out2 = resolve_outcome(bars, setup)
    assert out1 == out2


def test_known_fixture_r_math_long():
    """Per spec invariant F.6: entry=100, SL=95, exit=110 → r=2.0 for long."""
    bars = _make_bars([
        (100.0, 100.5, 99.8, 100.2),
        (100.5, 110.5, 100.0, 110.2),  # high reaches manual TP=110 → r=2 since risk=5
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=95.0, tp_price=110.0, direction="long",
    )
    out = resolve_outcome(bars, setup)
    assert out.outcome == "TP"
    assert out.r == pytest.approx(2.0)


def test_known_fixture_r_math_short():
    """Mirror: entry=100, SL=105, exit=90 → r=2.0 for short."""
    bars = _make_bars([
        (100.0, 100.2, 99.5, 99.8),
        (99.8, 100.0, 89.5, 90.0),  # low reaches TP=90 → r=2 since risk=5
    ])
    setup = Setup(
        entry_ts=bars["ts"].iloc[0], entry_price=100.0,
        sl_price=105.0, tp_price=90.0, direction="short",
    )
    out = resolve_outcome(bars, setup)
    assert out.outcome == "TP"
    assert out.r == pytest.approx(2.0)


def test_setup_with_zero_risk_raises():
    """A setup with entry == sl_price has zero risk; we can't compute R. Reject."""
    bars = _make_bars([(100.0, 100.5, 99.8, 100.2)])
    with pytest.raises(ValueError, match="risk"):
        Setup(entry_ts=bars["ts"].iloc[0], entry_price=100.0,
              sl_price=100.0, tp_price=105.0, direction="long")


def test_invalid_direction_raises():
    bars = _make_bars([(100.0, 100.5, 99.8, 100.2)])
    with pytest.raises(ValueError, match="direction"):
        Setup(entry_ts=bars["ts"].iloc[0], entry_price=100.0,
              sl_price=95.0, tp_price=105.0, direction="sideways")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_outcomes.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine.outcomes'`.

- [ ] **Step 3: Implement `engine/outcomes.py`**

Create `Statistic.ally/Amas Models/engine/outcomes.py`:

```python
"""SL/TP outcome resolver for the Amas Models engine.

Per the design spec, Category D (Outcome resolver fidelity):
- Same-bar TP/SL tie → SL (matches Fractal Sweep + indicator)
- OUTCOME_MAX_BARS = 1440; unresolved trades are EXPIRED (excluded from WR/EV)
- MAE/MFE for resolved trades stop at resolution bar
- Direction symmetric (long/short tested separately)
- Deterministic & idempotent (same input → same output)

Entry bar (where bar.ts == setup.entry_ts) is EXCLUDED from resolution per
invariant C.3 — it contributes to entry price only, never to TP/SL detection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

from engine.constants import OUTCOME_MAX_BARS


Direction = Literal["long", "short"]
OutcomeKind = Literal["TP", "SL", "EXPIRED"]


@dataclass(frozen=True)
class Setup:
    """A trade setup ready for outcome resolution."""
    entry_ts: pd.Timestamp
    entry_price: float
    sl_price: float
    tp_price: float
    direction: Direction

    def __post_init__(self):
        if self.direction not in ("long", "short"):
            raise ValueError(f"direction must be 'long' or 'short', got {self.direction!r}")
        if abs(self.entry_price - self.sl_price) < 1e-9:
            raise ValueError(f"setup has zero risk (entry == sl_price = {self.entry_price})")
        if self.direction == "long":
            if self.sl_price >= self.entry_price:
                raise ValueError(f"long setup requires sl_price < entry_price")
            if self.tp_price <= self.entry_price:
                raise ValueError(f"long setup requires tp_price > entry_price")
        else:  # short
            if self.sl_price <= self.entry_price:
                raise ValueError(f"short setup requires sl_price > entry_price")
            if self.tp_price >= self.entry_price:
                raise ValueError(f"short setup requires tp_price < entry_price")

    @property
    def risk_pts(self) -> float:
        return abs(self.entry_price - self.sl_price)


@dataclass(frozen=True)
class Outcome:
    """Result of outcome resolution."""
    outcome: OutcomeKind
    r: Optional[float]  # None for EXPIRED
    resolution_ts: Optional[pd.Timestamp]  # None for EXPIRED
    mae_pts: float  # max adverse excursion (always non-negative)
    mfe_pts: float  # max favorable excursion (always non-negative)
    bars_to_resolve: int  # number of bars scanned (entry-bar-exclusive)


def resolve_outcome(bars: pd.DataFrame, setup: Setup, max_bars: int = OUTCOME_MAX_BARS) -> Outcome:
    """Walk forward bar-by-bar from entry+1 until TP, SL, or max_bars exhausted.

    Per spec invariants:
    - Bars where ts <= setup.entry_ts are excluded.
    - If a single bar's high >= TP AND low <= SL, outcome is SL (tie-break).
    - MAE/MFE measured only over bars actually scanned (stop at resolution).
    """
    post_entry = bars[bars["ts"] > setup.entry_ts]
    if len(post_entry) == 0:
        return Outcome(outcome="EXPIRED", r=None, resolution_ts=None, mae_pts=0.0, mfe_pts=0.0, bars_to_resolve=0)

    scan = post_entry.iloc[:max_bars]

    mae = 0.0
    mfe = 0.0

    for i, bar in enumerate(scan.itertuples(index=False), start=1):
        if setup.direction == "long":
            adverse = setup.entry_price - bar.low
            favorable = bar.high - setup.entry_price
            sl_hit = bar.low <= setup.sl_price
            tp_hit = bar.high >= setup.tp_price
        else:  # short
            adverse = bar.high - setup.entry_price
            favorable = setup.entry_price - bar.low
            sl_hit = bar.high >= setup.sl_price
            tp_hit = bar.low <= setup.tp_price

        if adverse > mae:
            mae = adverse
        if favorable > mfe:
            mfe = favorable

        if sl_hit and tp_hit:
            # Same-bar tie → SL
            return Outcome(
                outcome="SL", r=-1.0, resolution_ts=bar.ts,
                mae_pts=mae, mfe_pts=mfe, bars_to_resolve=i,
            )
        if tp_hit:
            r = (setup.tp_price - setup.entry_price) / setup.risk_pts
            if setup.direction == "short":
                r = (setup.entry_price - setup.tp_price) / setup.risk_pts
            return Outcome(
                outcome="TP", r=r, resolution_ts=bar.ts,
                mae_pts=mae, mfe_pts=mfe, bars_to_resolve=i,
            )
        if sl_hit:
            return Outcome(
                outcome="SL", r=-1.0, resolution_ts=bar.ts,
                mae_pts=mae, mfe_pts=mfe, bars_to_resolve=i,
            )

    # Exhausted max_bars
    return Outcome(
        outcome="EXPIRED", r=None, resolution_ts=None,
        mae_pts=mae, mfe_pts=mfe, bars_to_resolve=len(scan),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_outcomes.py -v
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/engine/outcomes.py" "Amas Models/tests/test_outcomes.py"
git commit -m "feat(amas): engine.outcomes — SL/TP scanner with all resolver invariants"
```

---

### Task 2.5: `engine/stats.py` — agg, Wilson CI, EV/PF

**Files:**
- Create: `Statistic.ally/Amas Models/engine/stats.py`
- Create: `Statistic.ally/Amas Models/tests/test_stats.py`

- [ ] **Step 1: Write the failing tests**

Create `Statistic.ally/Amas Models/tests/test_stats.py`:

```python
"""Tests for engine.stats — aggregation, Wilson CI, EV/PF.

Per the design spec, Category G (Statistical hygiene): EV is mean R (not median),
PF from R values (not dollars), Wilson 95% CI on WR for every breakdown cell,
expired trades excluded from WR/EV but counted in N.
"""
from __future__ import annotations

import math

import pytest

from engine.stats import agg, wilson_ci


def test_agg_basic_wr_ev_pf():
    rows = [
        {"r": 1.0, "outcome": "TP"},
        {"r": 1.0, "outcome": "TP"},
        {"r": -1.0, "outcome": "SL"},
        {"r": 1.0, "outcome": "TP"},
    ]
    result = agg(rows)
    assert result["n"] == 4
    assert result["n_resolved"] == 4
    assert result["n_expired"] == 0
    assert result["wins"] == 3
    assert result["wr"] == pytest.approx(0.75)
    assert result["ev"] == pytest.approx(0.5)  # (1+1-1+1)/4
    # PF = sum(r>0) / abs(sum(r<0)) = 3 / 1 = 3.0
    assert result["pf"] == pytest.approx(3.0)


def test_agg_excludes_expired_from_wr_and_ev():
    """Per spec invariant D.2: expired excluded from WR/EV, counted in N."""
    rows = [
        {"r": 1.0, "outcome": "TP"},
        {"r": -1.0, "outcome": "SL"},
        {"r": None, "outcome": "EXPIRED"},
        {"r": None, "outcome": "EXPIRED"},
    ]
    result = agg(rows)
    assert result["n"] == 4
    assert result["n_resolved"] == 2
    assert result["n_expired"] == 2
    assert result["wins"] == 1
    assert result["wr"] == pytest.approx(0.5)
    assert result["ev"] == pytest.approx(0.0)


def test_agg_zero_resolved_trades_returns_none_metrics():
    rows = [
        {"r": None, "outcome": "EXPIRED"},
    ]
    result = agg(rows)
    assert result["n"] == 1
    assert result["n_resolved"] == 0
    assert result["wr"] is None
    assert result["ev"] is None
    assert result["pf"] is None


def test_agg_no_losers_returns_inf_pf():
    rows = [
        {"r": 1.0, "outcome": "TP"},
        {"r": 1.0, "outcome": "TP"},
    ]
    result = agg(rows)
    assert result["pf"] == math.inf or result["pf"] is None  # implementation choice; must not crash


def test_agg_wilson_ci_present_when_resolved():
    rows = [{"r": 1.0, "outcome": "TP"}, {"r": -1.0, "outcome": "SL"}]
    result = agg(rows)
    assert "wr_ci_low" in result
    assert "wr_ci_high" in result
    assert 0.0 <= result["wr_ci_low"] <= result["wr"] <= result["wr_ci_high"] <= 1.0


def test_wilson_ci_known_values():
    """Wilson 95% CI for 50% WR on N=100 is ~ (40.4%, 59.6%). Reasonable bounds check."""
    low, high = wilson_ci(wins=50, n=100)
    assert 0.39 <= low <= 0.42
    assert 0.58 <= high <= 0.61


def test_wilson_ci_zero_n_returns_zero_one():
    low, high = wilson_ci(wins=0, n=0)
    assert low == 0.0
    assert high == 1.0


def test_agg_empty_returns_zero_n():
    result = agg([])
    assert result["n"] == 0
    assert result["wr"] is None
    assert result["ev"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_stats.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine.stats'`.

- [ ] **Step 3: Implement `engine/stats.py`**

Create `Statistic.ally/Amas Models/engine/stats.py`:

```python
"""Aggregation, Wilson CIs, and statistical helpers for the Amas Models engine.

Per the design spec, Category G (Statistical hygiene):
- EV is MEAN R, not median (computed over resolved trades only)
- PF is gross profit / gross loss in R (not dollars)
- Wilson 95% CI on WR for every breakdown cell
- Expired trades excluded from WR/EV but counted in N
- Sample size visible everywhere (returned in result dict)
"""
from __future__ import annotations

import math
from typing import Optional


def agg(rows: list[dict]) -> dict:
    """Aggregate a list of trade rows into summary metrics.

    Each row must have at least: r (float | None), outcome (str).
    Rows with outcome == 'EXPIRED' are counted in n but excluded from
    n_resolved, wr, ev, pf.

    Returns dict with: n, n_resolved, n_expired, wins, wr, wr_ci_low,
    wr_ci_high, ev, pf, avg_risk_pts (if present), avg_rr (if present),
    avg_mae, avg_mfe.
    """
    n = len(rows)
    n_expired = sum(1 for r in rows if r.get("outcome") == "EXPIRED")
    resolved = [r for r in rows if r.get("outcome") != "EXPIRED" and r.get("r") is not None]
    n_resolved = len(resolved)

    if n_resolved == 0:
        return {
            "n": n, "n_resolved": 0, "n_expired": n_expired,
            "wins": 0, "wr": None, "wr_ci_low": None, "wr_ci_high": None,
            "ev": None, "pf": None,
        }

    wins = sum(1 for r in resolved if r["r"] > 0)
    wr = wins / n_resolved
    ev = sum(r["r"] for r in resolved) / n_resolved

    gross_profit = sum(r["r"] for r in resolved if r["r"] > 0)
    gross_loss = sum(r["r"] for r in resolved if r["r"] < 0)
    if gross_loss == 0:
        pf = math.inf if gross_profit > 0 else None
    else:
        pf = gross_profit / abs(gross_loss)

    ci_low, ci_high = wilson_ci(wins=wins, n=n_resolved)

    result = {
        "n": n,
        "n_resolved": n_resolved,
        "n_expired": n_expired,
        "wins": wins,
        "wr": wr,
        "wr_ci_low": ci_low,
        "wr_ci_high": ci_high,
        "ev": ev,
        "pf": pf,
    }

    # Optional fields if present on rows
    if rows and "mae_pts" in rows[0]:
        mae_vals = [r.get("mae_pts", 0.0) for r in rows]
        result["avg_mae_pts"] = sum(mae_vals) / len(mae_vals)
    if rows and "mfe_pts" in rows[0]:
        mfe_vals = [r.get("mfe_pts", 0.0) for r in rows]
        result["avg_mfe_pts"] = sum(mfe_vals) / len(mfe_vals)
    if rows and "risk_pts" in rows[0]:
        risk_vals = [r["risk_pts"] for r in rows]
        result["avg_risk_pts"] = sum(risk_vals) / len(risk_vals)

    return result


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% confidence interval for a proportion.

    More stable than normal approx for small N or extreme proportions.
    Returns (low, high). For n=0, returns (0.0, 1.0) — the maximally uninformative
    interval.
    """
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_stats.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/engine/stats.py" "Amas Models/tests/test_stats.py"
git commit -m "feat(amas): engine.stats — agg + Wilson CI + EV/PF"
```

---

### Task 2.6: `engine/filters.py` — filter primitives

For Phase 2 we ship the framework + one universal filter primitive (SMT scaffolding). Each model's bespoke filters live in its own model file.

**Files:**
- Create: `Statistic.ally/Amas Models/engine/filters.py`
- Create: `Statistic.ally/Amas Models/tests/test_filters.py`

- [ ] **Step 1: Write the failing tests**

Create `Statistic.ally/Amas Models/tests/test_filters.py`:

```python
"""Tests for engine.filters — filter primitives + combo enumeration."""
from __future__ import annotations

import pytest

from engine.filters import enumerate_combos, apply_combo


def test_enumerate_combos_2_filters():
    keys = ["F1", "F2"]
    combos = enumerate_combos(keys)
    # 2^2 = 4: (), (F1), (F2), (F1,F2)
    assert len(combos) == 4
    assert frozenset() in combos
    assert frozenset(["F1"]) in combos
    assert frozenset(["F2"]) in combos
    assert frozenset(["F1", "F2"]) in combos


def test_enumerate_combos_3_filters():
    combos = enumerate_combos(["F1", "F2", "F3"])
    assert len(combos) == 8


def test_apply_combo_and_semantics():
    """Per spec invariant G.7: filter combos use AND, not OR."""
    rows = [
        {"id": 1, "passes_F1": True, "passes_F2": True},
        {"id": 2, "passes_F1": True, "passes_F2": False},
        {"id": 3, "passes_F1": False, "passes_F2": True},
        {"id": 4, "passes_F1": False, "passes_F2": False},
    ]
    result = apply_combo(rows, frozenset(["F1", "F2"]))
    assert [r["id"] for r in result] == [1]


def test_apply_combo_empty_returns_all():
    rows = [{"id": 1, "passes_F1": False}, {"id": 2, "passes_F1": True}]
    result = apply_combo(rows, frozenset())
    assert len(result) == 2


def test_apply_combo_missing_flag_treated_as_false():
    """A trade row missing a passes_<key> flag for an applied filter should be excluded."""
    rows = [
        {"id": 1, "passes_F1": True},  # no passes_F2 field
        {"id": 2, "passes_F1": True, "passes_F2": True},
    ]
    result = apply_combo(rows, frozenset(["F1", "F2"]))
    assert [r["id"] for r in result] == [2]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_filters.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine.filters'`.

- [ ] **Step 3: Implement `engine/filters.py`**

Create `Statistic.ally/Amas Models/engine/filters.py`:

```python
"""Filter primitives + combo enumeration for the Amas Models engine.

Per the design spec, Category G (Statistical hygiene): filter combos use AND
semantics, not OR. A row passes a combo iff every named filter's
`passes_<key>` flag is True.

Each model's bespoke filters (e.g. shallow sweep) are computed in the model's
own file and attached to trade rows as `passes_<key>: bool`. This module owns
the orchestration: enumerating 2^N combos and applying them.
"""
from __future__ import annotations

from itertools import combinations


def enumerate_combos(keys: list[str]) -> list[frozenset[str]]:
    """Return all 2^N subsets of the given filter keys, including the empty set."""
    out: list[frozenset[str]] = []
    for r in range(len(keys) + 1):
        for c in combinations(keys, r):
            out.append(frozenset(c))
    return out


def apply_combo(rows: list[dict], combo: frozenset[str]) -> list[dict]:
    """Return only the rows where every filter in `combo` passes (AND semantics).

    A row missing a `passes_<key>` flag is treated as failing that filter
    (conservative default — never include a row whose filter status is unknown).
    """
    if not combo:
        return list(rows)
    out: list[dict] = []
    for r in rows:
        if all(r.get(f"passes_{k}", False) for k in combo):
            out.append(r)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_filters.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/engine/filters.py" "Amas Models/tests/test_filters.py"
git commit -m "feat(amas): engine.filters — combo enumeration + AND-semantics application"
```

---

### Task 2.7: `engine/models/__init__.py` — registry

**Files:**
- Create: `Statistic.ally/Amas Models/engine/models/__init__.py`
- Create: `Statistic.ally/Amas Models/tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Create `Statistic.ally/Amas Models/tests/test_registry.py`:

```python
"""Tests for the model registry — ModelDefinition / Filter dataclasses."""
from __future__ import annotations

import pytest

from engine.models import ModelDefinition, Filter, MODELS


def test_models_registry_exists():
    assert isinstance(MODELS, dict)


def test_filter_dataclass_required_fields():
    f = Filter(key="F1", label="Shallow Sweep", default=False)
    assert f.key == "F1"
    assert f.label == "Shallow Sweep"
    assert f.default is False


def test_model_definition_required_fields():
    def dummy_detect(bars, **kwargs):
        return []
    md = ModelDefinition(
        key="dummy",
        label="Dummy Model",
        detect=dummy_detect,
        filters=[Filter(key="F1", label="Test Filter", default=False)],
        spec_anchor="model-dummy",
    )
    assert md.key == "dummy"
    assert callable(md.detect)
    assert len(md.filters) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_registry.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine.models'`.

- [ ] **Step 3: Implement the registry**

Create `Statistic.ally/Amas Models/engine/models/__init__.py`:

```python
"""Model registry for the Amas Models engine.

Each Amas model is one Python module under engine/models/ that exports a
detector function. This file collects them into a MODELS dict that
model_stats.py iterates over.

Adding a new model:
1. Create engine/models/<key>.py with a `detect_setups(bars_df, **kwargs)` function
   returning list[Setup] (from engine.outcomes).
2. Add an entry to MODELS below.
3. Write tests/test_<key>.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Filter:
    """A togglable confluence filter exposed in the dashboard chip bar.

    The detector attaches `passes_<key>: bool` to every trade row. The dashboard
    reads this list to render chips, and the filter combo logic in stats uses
    AND semantics.
    """
    key: str       # short code, e.g., "F1", "SMT"
    label: str     # human-readable, e.g., "Shallow Sweep"
    default: bool  # whether the chip is active by default in the dashboard


@dataclass(frozen=True)
class ModelDefinition:
    """Registration entry for one Amas model."""
    key: str                          # snake_case identifier; used in JSON, CLI --models, filenames
    label: str                        # human-readable name shown in dashboard
    detect: Callable                  # detect_setups(bars_df: pd.DataFrame, **kwargs) -> list[Setup]
    filters: list[Filter] = field(default_factory=list)
    spec_anchor: str = ""             # H2 heading slug in docs/model_specs.md for spec rendering


# The registry. Populated by Phase 3+.
MODELS: dict[str, ModelDefinition] = {}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_registry.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/engine/models/__init__.py" "Amas Models/tests/test_registry.py"
git commit -m "feat(amas): engine.models registry + ModelDefinition/Filter dataclasses"
```

---

### Task 2.8: `engine/model_stats.py` — orchestrator + CLI (no models yet)

**Files:**
- Create: `Statistic.ally/Amas Models/engine/model_stats.py`
- Create: `Statistic.ally/Amas Models/tests/test_reproducibility.py`

- [ ] **Step 1: Implement the orchestrator**

Create `Statistic.ally/Amas Models/engine/model_stats.py`:

```python
"""Orchestrator for the Amas Models engine.

Loads bars from DuckDB, iterates over registered models, runs each model's
detector, resolves outcomes, computes filter combos, and writes a single
model_stats.json.

Per the design spec, Category B (Trade deduplication) and H (Determinism):
- Post-detect dedup assertion per (anchor_ts, direction) — hard fail on duplicates
- Iteration order is registration order (dict-preserving)
- JSON output uses sorted keys for byte-stability across runs

CLI:
    python3 engine/model_stats.py                          # all models, NQ
    python3 engine/model_stats.py --models <key>           # subset
    python3 engine/model_stats.py --table es_1m            # ES instead of NQ
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from engine import db
from engine.constants import OUTCOME_MAX_BARS
from engine.filters import enumerate_combos, apply_combo
from engine.models import MODELS
from engine.outcomes import Setup, resolve_outcome
from engine.stats import agg


ENGINE_VERSION = "0.1.0"


def run(table: str = "nq_1m", model_keys: Optional[list[str]] = None) -> dict:
    """Load bars, run all (or the requested) models, return the JSON-shaped result."""
    bars = db.load_bars(table)

    keys = model_keys if model_keys else list(MODELS.keys())
    for k in keys:
        if k not in MODELS:
            raise KeyError(f"Unknown model key: {k!r}. Registered: {list(MODELS.keys())}")

    out_models: dict[str, dict] = {}
    for key in keys:
        md = MODELS[key]
        setups: list[Setup] = list(md.detect(bars))

        # Dedup invariant B.2: hard fail on duplicate (anchor_ts, direction) pairs.
        seen: set[tuple] = set()
        dups: list[tuple] = []
        for s in setups:
            anchor_key = getattr(s, "anchor_ts", s.entry_ts)  # detectors may stamp anchor_ts; fallback entry_ts
            k2 = (anchor_key, s.direction)
            if k2 in seen:
                dups.append(k2)
            else:
                seen.add(k2)
        assert not dups, f"{key}/{table}: duplicate setups at {dups[:5]} (and {max(0, len(dups)-5)} more)"

        trades: list[dict] = []
        for setup in setups:
            outcome = resolve_outcome(bars, setup, max_bars=OUTCOME_MAX_BARS)
            row = {
                "anchor_ts": str(getattr(setup, "anchor_ts", setup.entry_ts)),
                "entry_ts": str(setup.entry_ts),
                "direction": setup.direction,
                "entry_price": setup.entry_price,
                "sl_price": setup.sl_price,
                "tp_price": setup.tp_price,
                "risk_pts": setup.risk_pts,
                "outcome": outcome.outcome,
                "r": outcome.r,
                "resolution_ts": str(outcome.resolution_ts) if outcome.resolution_ts else None,
                "mae_pts": outcome.mae_pts,
                "mfe_pts": outcome.mfe_pts,
                "bars_to_resolve": outcome.bars_to_resolve,
            }
            # Carry forward any passes_<filter> flags the detector attached.
            for attr in dir(setup):
                if attr.startswith("passes_"):
                    row[attr] = getattr(setup, attr)
            trades.append(row)

        summary = agg(trades)

        # 2^N filter combo grid
        filter_keys = [f.key for f in md.filters]
        combos = enumerate_combos(filter_keys)
        variants = []
        for combo in combos:
            subset = apply_combo(trades, combo)
            variants.append({
                "filters": sorted(list(combo)),
                "stats": agg(subset),
            })
        variants.sort(key=lambda v: (v["stats"].get("ev") or -999), reverse=True)

        out_models[key] = {
            "label": md.label,
            "filters": [{"key": f.key, "label": f.label, "default": f.default} for f in md.filters],
            "trades": trades,
            "summary": summary,
            "filter_variants": variants,
            "spec_html": "",  # filled by render_spec_html (Phase 3+)
        }

    return {
        "meta": {
            "engine_version": ENGINE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "table": table,
            "data_range": f"{bars['ts'].min()} to {bars['ts'].max()}" if len(bars) else "",
            "spec_sha": _spec_sha(),
        },
        "models": out_models,
    }


def _spec_sha() -> str:
    """Hash of docs/model_specs.md, for reproducibility tracking."""
    spec = Path(__file__).resolve().parent.parent / "docs" / "model_specs.md"
    if not spec.exists():
        return ""
    return hashlib.sha256(spec.read_bytes()).hexdigest()


def write(result: dict, out_path: Optional[Path] = None) -> Path:
    """Serialize to model_stats.json with sorted keys (deterministic byte output)."""
    if out_path is None:
        out_path = Path(__file__).resolve().parent.parent / "model_stats.json"
    with out_path.open("w") as f:
        json.dump(result, f, sort_keys=True, default=str)
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Run the Amas Models engine.")
    p.add_argument("--table", default="nq_1m", choices=["nq_1m", "es_1m"])
    p.add_argument("--models", nargs="+", default=None, help="Subset of registered model keys.")
    args = p.parse_args(argv)

    result = run(table=args.table, model_keys=args.models)
    out = write(result)
    n_models = len(result["models"])
    n_trades = sum(len(m["trades"]) for m in result["models"].values())
    print(f"Wrote {out} ({n_models} model(s), {n_trades} trade(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write the reproducibility test**

Create `Statistic.ally/Amas Models/tests/test_reproducibility.py`:

```python
"""Per spec invariant H.4: same code + same DB + same args → byte-identical JSON output
(modulo meta.generated_at).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.model_stats import run, write


@pytest.mark.skipif(
    not (Path(__file__).resolve().parent.parent.parent / "Fractal Sweep" / "candle_science.duckdb").exists(),
    reason="Shared DB not present",
)
def test_engine_reproducibility(tmp_path):
    """Engine produces byte-identical JSON across runs (excluding generated_at)."""
    r1 = run(table="nq_1m")
    r2 = run(table="nq_1m")

    # Strip volatile fields
    r1["meta"].pop("generated_at", None)
    r2["meta"].pop("generated_at", None)

    s1 = json.dumps(r1, sort_keys=True, default=str)
    s2 = json.dumps(r2, sort_keys=True, default=str)
    assert s1 == s2, "Engine output is not reproducible — there's nondeterminism somewhere"
```

- [ ] **Step 3: Run all tests, full suite**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/ -v
```

Expected: all tests pass. The reproducibility test will be `SKIPPED` if the DB isn't present, which is fine — Phase 3 will exercise it for real once a model is registered.

- [ ] **Step 4: Smoke-run the engine**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 engine/model_stats.py
```

Expected: exits 0, writes `model_stats.json` containing `{"meta": {...}, "models": {}}` (empty models dict because nothing is registered yet).

- [ ] **Step 5: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/engine/model_stats.py" "Amas Models/tests/test_reproducibility.py"
git commit -m "feat(amas): engine.model_stats — orchestrator + CLI + reproducibility test"
```

---

### Task 2.9: `model_dashboard.html` — empty chrome

The dashboard at this stage shows the header, theme toggle, model selector (empty), and stub tab bar. Once Phase 3 registers a model, the dashboard renders its data.

**Files:**
- Create: `Statistic.ally/Amas Models/model_dashboard.html`

- [ ] **Step 1: Read Fractal Sweep's dashboard for patterns**

Read `Statistic.ally/Fractal Sweep/model_dashboard.html` to understand the existing patterns: how the header is structured, how the theme toggle reads `localStorage.getItem('hub-theme')`, what CSS variables are used. We want visual consistency, not divergence.

- [ ] **Step 2: Create the empty chrome**

Create `Statistic.ally/Amas Models/model_dashboard.html`. It should be a single self-contained HTML file (zero CDN deps) that:

1. Sets `<html data-theme="...">` from `localStorage.getItem('hub-theme') || 'dark'` in a `<script>` block in `<head>` (so theme is set before paint, no flash).
2. Has a header with: title "Amas Models", instrument selector `<select>` with options NQ/ES (currently visual only), model selector `<select>` (currently empty/disabled), home link `⌂` back to `../index.html`, theme toggle button.
3. Has a tab bar with these tabs (visual only, all empty for now): Overview, Breakdowns, Filters, Trades, Walk-Forward, Spec.
4. Has a placeholder `<main>` showing "Load a model to see results." centered.
5. Loads `model_stats.json` via `fetch('./model_stats.json')` on page load and stashes the result on `window.__stats`. If `models` is empty, shows the placeholder; otherwise populates the model selector (Phase 3 wires up rendering).
6. CSS variables for light/dark themes match Fractal Sweep exactly (read from its dashboard) so theme toggle from any page applies consistently.
7. Theme toggle button updates `localStorage.setItem('hub-theme', ...)` and `document.documentElement.setAttribute('data-theme', ...)`.

The file should be ≤500 lines for now. It will grow in Phase 3.

- [ ] **Step 3: Smoke-test the dashboard**

```bash
cd /Users/abhi/Projects/Statistic.ally
python3 -m http.server 8001 &
sleep 1
curl -sI "http://localhost:8001/Amas%20Models/model_dashboard.html" | head -1
```

Expected: `HTTP/1.0 200 OK`. Then open `http://localhost:8001/Amas%20Models/model_dashboard.html` in a browser and verify:

- Page loads with no console errors
- Theme toggle works (light/dark)
- Visiting `http://localhost:8001/Fractal Sweep/model_dashboard.html` and toggling theme there persists across to Amas Models on next load (shared `hub-theme` key)
- Model selector is empty and the placeholder text shows

Kill the server with `kill %1`.

- [ ] **Step 4: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/model_dashboard.html"
git commit -m "feat(amas): dashboard chrome — header, theme toggle, empty model selector"
```

---

# PHASE 3: One Model End-to-End

The model name is determined by Task 1.4. Below, `<chosen_model>` is a placeholder for the snake_case key (e.g., `h1_reversal`).

### Task 3.1: Implement `engine/models/<chosen_model>.py`

**Files:**
- Create: `Statistic.ally/Amas Models/engine/models/<chosen_model>.py`

- [ ] **Step 1: Reread the chosen model's section in `docs/model_specs.md`**

Open `Statistic.ally/Amas Models/docs/model_specs.md` and re-read the chosen model's full section: detection rules, entry trigger, stop loss, take profit, direction logic, invalidation, listed filters. Resolve any open questions inline (with the user, or by conservative interpretation that's documented).

- [ ] **Step 2: Plan the detector function signature**

Decide:
- What anchor timeframe (e.g., H1)? This determines how anchors are derived from 1m bars.
- What lookback bars does each rule need (e.g., "prior H1 bar's range")?
- Which model-specific filters (e.g., shallow sweep) live in this file vs. shared in `engine/filters.py`?
- What `passes_<key>` flags should each setup carry?

Write a short docstring at the top of the file capturing this plan, citing the section of `model_specs.md`.

- [ ] **Step 3: Implement the detector**

Create `Statistic.ally/Amas Models/engine/models/<chosen_model>.py`. Concrete code shape (replace `...` with real logic from the spec):

```python
"""<Model label> detector for Amas Models.

Per docs/model_specs.md § "Model: <name>": <one-sentence summary>.

Anchor: <e.g., H1 candle close>
Detection rules: <numbered list summary>
Entry: <description>
Stop: <description>
TP: <description>

Filters this model declares (each becomes a passes_<key> flag on every setup):
- <key> (<label>): <description>
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from engine.outcomes import Setup


@dataclass(frozen=True)
class _<ChosenModel>Setup(Setup):
    """Setup with model-specific anchor + filter flags attached."""
    anchor_ts: pd.Timestamp = field(default=None)
    passes_F1: bool = False  # add one field per declared filter


def detect_setups(bars: pd.DataFrame) -> list[Setup]:
    """Return one Setup per detected anchor where all detection rules pass.

    Per spec invariants:
    - Causal: only reads bars where bar.ts <= anchor_ts (Category C.1)
    - At most one setup per (anchor_ts, direction) (Category B.1)
    - Risk gated by MAX_RISK_PTS (Category F); MIN_RISK_PTS is None so no lower floor
    """
    # 1. Build anchor candles from 1m bars (e.g., resample to H1 closed in NY tz)
    # 2. Iterate anchor by anchor; for each:
    #    - Apply detection rules using bars up to and including this anchor close
    #    - If pass: derive entry/SL/TP, build _<ChosenModel>Setup
    #    - Compute passes_<filter> flags using same causal slice
    #    - Apply MAX_RISK gate from constants (MIN_RISK_PTS is None — skip lower-bound check)
    # 3. Return the list (deduped per spec — implementation should not produce duplicates,
    #    but if it could, dedup BEFORE return with a documented tie-break)
    setups: list[Setup] = []
    # ... actual detection logic per spec ...
    return setups
```

The actual detection code is filled in here — this plan can't hand you a body without knowing which model was chosen, but the structural contract is fixed: returns `list[Setup]`, no lookahead, no duplicates, risk-gated.

- [ ] **Step 4: Register the model**

Modify `Statistic.ally/Amas Models/engine/models/__init__.py` to import the new module and register it:

```python
from engine.models import <chosen_model>

MODELS: dict[str, ModelDefinition] = {
    "<chosen_model>": ModelDefinition(
        key="<chosen_model>",
        label="<Human-readable label>",
        detect=<chosen_model>.detect_setups,
        filters=[
            Filter(key="F1", label="<Filter 1 label>", default=False),
            # ... etc
        ],
        spec_anchor="model-<chosen-model-slug>",
    ),
}
```

- [ ] **Step 5: Commit (no test yet — TDD test comes next)**

Don't run yet. Commit the structural code first, then add the test.

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/engine/models/<chosen_model>.py" "Amas Models/engine/models/__init__.py"
git commit -m "feat(amas): scaffold <chosen_model> detector + register"
```

---

### Task 3.2: Fixture tests for `<chosen_model>` — trade-count, lookahead audit, direction symmetry

**Files:**
- Create: `Statistic.ally/Amas Models/tests/test_<chosen_model>.py`

- [ ] **Step 1: Write fixture tests**

Create `Statistic.ally/Amas Models/tests/test_<chosen_model>.py`. Replace the placeholder fixture data with bars that satisfy your model's specific detection rules. The test SHAPES below are required regardless of model:

```python
"""Tests for <chosen_model> detector.

Per spec invariants:
- B.1 / B.6: exact trade-count assertion on a fixed fixture
- C.5: lookahead audit (full bars vs slice-up-to-anchor produce same setups)
- D.5: direction symmetry on mirrored fixtures
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine.models import <chosen_model>


def _bars(prices: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """prices: list of (iso_ts_str, open, high, low, close)."""
    rows = [{"ts": pd.Timestamp(t, tz="America/New_York"), "open": o, "high": h, "low": l, "close": c, "volume": 100}
            for t, o, h, l, c in prices]
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    return df


def test_trade_count_on_known_fixture():
    """Per invariant B.6: exact trade count on a fixed input.

    A fixture crafted to produce EXACTLY N setups according to the spec.
    Drift in this number is a regression even if dashboard summaries look ok.
    """
    bars = _bars([
        # ... bars crafted to produce exactly N detection-rule-passing setups ...
    ])
    setups = <chosen_model>.detect_setups(bars)
    assert len(setups) == EXPECTED_N  # replace with the actual count


def test_no_duplicate_setups_per_anchor():
    """Per invariant B.1: at most one setup per (anchor_ts, direction)."""
    bars = _bars([
        # ... bars where multiple detection paths could trigger the same anchor ...
    ])
    setups = <chosen_model>.detect_setups(bars)
    keys = [(s.anchor_ts, s.direction) for s in setups]
    assert len(keys) == len(set(keys))


def test_lookahead_audit_full_vs_sliced():
    """Per invariant C.5: detector output on bars[:anchor_idx+1] equals output on full bars,
    for any anchor_idx that produces a setup.
    """
    full_bars = _bars([
        # ... fixture with at least one setup at a known anchor_ts ...
    ])
    full_setups = <chosen_model>.detect_setups(full_bars)
    assert len(full_setups) >= 1, "fixture must produce at least one setup"

    for s in full_setups:
        # Reconstruct the slice that ends at this anchor's window close.
        # Detector should produce the same setup from this slice alone.
        slice_end_idx = full_bars[full_bars["ts"] <= s.anchor_ts].index.max()
        sliced = full_bars.iloc[:slice_end_idx + 1].reset_index(drop=True)
        sliced_setups = <chosen_model>.detect_setups(sliced)
        # The setup at this anchor must appear in both.
        match = [x for x in sliced_setups if x.anchor_ts == s.anchor_ts and x.direction == s.direction]
        assert len(match) == 1, f"lookahead suspected: anchor {s.anchor_ts} {s.direction} not produced from causal slice"


def test_direction_symmetry():
    """Per invariant D.5: mirrored bars produce mirrored setups."""
    up_bars = _bars([
        # ... rising-trend fixture that triggers a long setup ...
    ])
    long_setups = [s for s in <chosen_model>.detect_setups(up_bars) if s.direction == "long"]
    assert len(long_setups) >= 1

    # Mirror: flip OHLC around the entry price's vicinity. Conceptually:
    #   high <-> low (with sign), open/close mirrored
    # If the detector is symmetric, the mirrored fixture produces a short setup at the mirrored anchor.
    pivot = up_bars["close"].mean()
    mirrored = up_bars.copy()
    mirrored["open"]  = 2 * pivot - up_bars["open"]
    mirrored["close"] = 2 * pivot - up_bars["close"]
    new_high = 2 * pivot - up_bars["low"]
    new_low  = 2 * pivot - up_bars["high"]
    mirrored["high"], mirrored["low"] = new_high, new_low

    short_setups = [s for s in <chosen_model>.detect_setups(mirrored) if s.direction == "short"]
    assert len(short_setups) == len(long_setups), "direction symmetry violated"


def test_risk_gates_applied():
    """Setups with risk_pts > MAX_RISK_PTS must not be returned. No lower floor (MIN_RISK_PTS is None)."""
    bars = _bars([
        # ... fixture that without gating would produce a setup with risk_pts > 20.0 ...
    ])
    setups = <chosen_model>.detect_setups(bars)
    for s in setups:
        assert s.risk_pts <= 20.0, f"setup with risk_pts={s.risk_pts} exceeded MAX_RISK_PTS"
```

- [ ] **Step 2: Run tests and iterate on the detector**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/test_<chosen_model>.py -v
```

If tests fail: the detector doesn't yet match the spec. Adjust the detector code, not the tests. Tests are derived from `model_specs.md`, which is the source of truth. If a test reveals an ambiguity in the spec, fix the spec, then revise the test, then revise the detector.

Commit each fix as a separate commit with a focused message.

- [ ] **Step 3: Run the full suite to confirm no regression**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/ -v
```

Expected: all tests pass, including reproducibility (it now has a registered model to actually exercise).

- [ ] **Step 4: Final commit for this task**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/tests/test_<chosen_model>.py" "Amas Models/engine/models/<chosen_model>.py"
git commit -m "test(amas): <chosen_model> — trade-count + lookahead + symmetry + risk-gate"
```

---

### Task 3.3: First end-to-end engine run on real data

**Files:** none new; this is a verification step.

- [ ] **Step 1: Run the engine on NQ**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 engine/model_stats.py --models <chosen_model>
```

Expected: completes without error. Output line says how many trades. Note the count.

- [ ] **Step 2: Sanity-check `model_stats.json`**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -c "
import json
d = json.load(open('model_stats.json'))
m = d['models']['<chosen_model>']
s = m['summary']
print(f\"N={s['n']}, resolved={s['n_resolved']}, expired={s['n_expired']}\")
print(f\"WR={s['wr']:.3f} CI=[{s['wr_ci_low']:.3f}, {s['wr_ci_high']:.3f}]\")
print(f\"EV={s['ev']:.3f}, PF={s['pf']:.3f}\")
print(f\"Filter variants: {len(m['filter_variants'])}\")
"
```

Sanity checks:
- N is plausible (e.g., for an H1 model over 14 years of NQ, expect 1k–20k trades)
- WR is somewhere in [0.30, 0.70] — values outside this range warrant investigation
- `n_expired / n` < 5% — if higher, dashboard should warn (Task 3.4 handles this)
- Filter variants count == 2^N where N = number of filters declared

If any of these is wildly off, STOP. Apply the edge-inflation checklist from the spec's "Cross-cutting review discipline" section before trusting any number. Common culprits:
- TZ or dtype: re-run `tests/test_db.py`
- Lookahead: re-run the `_audit` test
- Risk gates: spot-check that no setup has risk_pts > 20.0 (no lower floor)
- Same-bar tie-break: spot-check that any winners aren't actually same-bar SL hits

- [ ] **Step 3: Run on ES too**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 engine/model_stats.py --models <chosen_model> --table es_1m
```

Expected: completes. Sanity-check the same way. Note: the `--table` flag overwrites `model_stats.json` — for now, accept this; Phase 4 will multi-instrument.

- [ ] **Step 4: Re-run NQ to restore canonical model_stats.json**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 engine/model_stats.py --models <chosen_model>
```

- [ ] **Step 5: Commit nothing — but document findings in model_specs.md**

Open `Statistic.ally/Amas Models/docs/model_specs.md`. Find the chosen model's section. Fill in `### Backtest results` with:
- Baseline: N, WR (with CI), EV, PF
- Notable observation if any (e.g., "best filter combo: F1+SMT, +N WR")
- Period covered

Commit:

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/docs/model_specs.md"
git commit -m "docs(amas): record <chosen_model> Phase 3 backtest results"
```

---

### Task 3.4: Dashboard renders `<chosen_model>`

**Files:**
- Modify: `Statistic.ally/Amas Models/model_dashboard.html`

- [ ] **Step 1: Wire up the model selector**

Modify the dashboard so that when `model_stats.json` loads:
- The model `<select>` is populated from `Object.keys(stats.models)`, with `option.value = key, option.textContent = stats.models[key].label`.
- On model change, the dashboard rerenders all tabs against `stats.models[selectedKey]`.

- [ ] **Step 2: Implement the Overview tab**

Show the headline stats: WR (with CI like "51.2% [48.0%, 54.4%]"), EV, PF, N, n_resolved, n_expired. If `n_expired / n > 0.05`, display a warning chip "⚠ N expired trades may hide losses".

Below the headline: a simple equity curve in inline SVG. Each resolved trade contributes its `r` to a cumulative line. Add tick marks every 100 trades. No animation, no fancy library — just SVG.

- [ ] **Step 3: Implement the Trades tab**

A sortable table with columns: anchor_ts, direction, entry_price, sl_price, tp_price, risk_pts, outcome, r, mae_pts, mfe_pts, plus one column per `passes_<filter>` flag.

Click column header → toggle ascending/descending sort. Use Array.sort + a render function. No library.

- [ ] **Step 4: Implement the Filters tab**

For each entry in `model.filter_variants`, render a row showing: filter combo (chip-style), N, WR with CI, EV, PF. Sort by EV descending (engine already does this; preserve order).

Highlight the empty-combo row as "Baseline" and the top non-empty row as "Best".

- [ ] **Step 5: Implement the Breakdowns and Walk-Forward tabs as stubs**

Phase 3 doesn't compute breakdowns or walk-forward yet (those are Phase 5). Show "Coming in Phase 5" placeholders. The tab buttons exist but the panels are empty.

- [ ] **Step 6: Implement the Spec tab**

Show "Spec rendering: Phase 4" placeholder for now. Engine-time spec rendering is wired up in Phase 4 alongside subsequent models.

- [ ] **Step 7: Smoke-test the dashboard**

```bash
cd /Users/abhi/Projects/Statistic.ally
python3 -m http.server 8001 &
sleep 1
```

Open `http://localhost:8001/Amas Models/model_dashboard.html`.

Verify:
- Model selector shows `<chosen_model>`'s label
- Overview tab shows WR/EV/PF/N matching the JSON values
- Equity curve renders, last point's y-value ≈ `summary.ev * summary.n_resolved`
- Trades tab is sortable, all expected columns present
- Filters tab shows 2^N rows
- Theme toggle still works

```bash
kill %1
```

- [ ] **Step 8: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Amas Models/model_dashboard.html"
git commit -m "feat(amas): dashboard renders <chosen_model> — overview, trades, filters tabs"
```

---

### Task 3.5: End-to-end verification + Phase 3 wrap-up

**Files:** none new; verification only.

- [ ] **Step 1: Full test suite**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 -m pytest tests/ -v
```

Expected: all green, no skips except where the DB isn't present.

- [ ] **Step 2: Reproducibility re-check**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Amas Models"
python3 engine/model_stats.py --models <chosen_model>
cp model_stats.json /tmp/stats_run1.json
python3 engine/model_stats.py --models <chosen_model>
cp model_stats.json /tmp/stats_run2.json
python3 -c "
import json
a = json.load(open('/tmp/stats_run1.json'))
b = json.load(open('/tmp/stats_run2.json'))
a['meta'].pop('generated_at'); b['meta'].pop('generated_at')
assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str), 'Nondeterminism!'
print('Byte-identical (excluding generated_at). ✓')
"
```

Expected: ✓.

- [ ] **Step 3: Edge-inflation checklist (manual review)**

Walk through the spec's checklist:
- TZ correctness: `test_db.py` green ✓
- Trades deduped: `test_<chosen_model>.py` green ✓
- Detection causal: lookahead audit green ✓
- Expired trades excluded from WR: confirmed in `agg` test ✓
- Point values right per instrument: verified at constants level ✓
- N and CIs visible: dashboard renders them ✓
- Test suite green: confirmed ✓

If any box is unchecked, the Phase 3 numbers are provisional. Note this in the commit.

- [ ] **Step 4: Phase 3 milestone commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git commit --allow-empty -m "milestone(amas): Phase 3 complete — <chosen_model> end-to-end ✓"
```

---

## Self-review (writer-side, executed before handoff)

Re-read the plan against the spec:

**1. Spec coverage:**
- Phase 1 deliverable (`model_specs.md` + `source_index.md`) → Tasks 1.1–1.4 ✓
- Phase 2 scaffold matches folder layout in spec → Tasks 2.1–2.9 ✓
- Phase 3 first model end-to-end → Tasks 3.1–3.5 ✓
- Correctness invariants A through H all have at least one enforcing task or test:
  - A (TZ): Task 2.3 (`test_db.py` covers tz, [ns], sentinel, gaps) ✓
  - B (Dedup): Task 2.8 (orchestrator dedup assertion), Task 3.2 (per-model dedup test) ✓
  - C (Lookahead): Task 2.4 (`Setup` excludes entry bar in resolver), Task 3.2 (lookahead audit per model) ✓
  - D (Resolver fidelity): Task 2.4 (all 6 invariants tested) ✓
  - E (Data quality): Task 2.3 (assert_load_invariants + check_gaps) ✓
  - F (Risk arithmetic): Task 2.2 (constants), Task 2.4 (R-math fixtures), Task 3.2 (risk gate test) ✓
  - G (Stat hygiene): Task 2.5 (Wilson CI, expired excluded, EV-mean-not-median), Task 2.6 (AND-semantics combos) ✓
  - H (Determinism): Task 2.8 (sorted JSON keys), Task 2.8 (reproducibility test) ✓

**2. Placeholder scan:**
- `<chosen_model>` is the only placeholder in Phase 3 — explicitly defined as a variable determined in Task 1.4. Acceptable.
- No "TODO", "TBD", "implement later" outside of `model_specs.md`'s skeleton (where TBD is part of the methodology).
- Step 3.1.3 says "actual detection logic per spec" — this is unavoidable since the model isn't chosen yet. The structural contract (signature, invariants, return type) is fully specified.

**3. Type consistency:**
- `Setup` dataclass defined in Task 2.4, referenced in Tasks 2.8, 3.1, 3.2 — consistent.
- `Outcome` dataclass defined in Task 2.4, used in Task 2.8 — consistent.
- `ModelDefinition`, `Filter` defined in Task 2.7, used in Task 3.1 step 4 — consistent.
- `agg(rows) -> dict` keys: `n, n_resolved, n_expired, wins, wr, wr_ci_low, wr_ci_high, ev, pf` — consistent across Tasks 2.5 and 2.8.
- `db.load_bars(table, start, end)` signature in Task 2.3, called as `db.load_bars(table)` in Task 2.8 — consistent (start/end are optional).
- `enumerate_combos(keys)` and `apply_combo(rows, combo)` signatures in Task 2.6, used in Task 2.8 — consistent.
