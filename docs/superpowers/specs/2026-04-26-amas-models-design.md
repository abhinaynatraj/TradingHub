# Amas Models — Design Spec

**Date:** 2026-04-26
**Location:** `Statistic.ally/Amas Models/`
**Source materials:** `/Users/abhi/Projects/Amas + Bootcamp/` (8 PDF pairs + 8 transcript files, NoteGPT-formatted)
**Instruments:** NQ and ES futures (1m bars, 14 years), via shared `candle_science.duckdb`
**Audience:** personal use only

## Goal

Turn the Amas mentorship materials into:

1. A precise, machine-readable spec for every distinct trading model the materials describe.
2. A backtest engine that measures each model's edge over 14 years of NQ/ES 1-minute data.
3. A single-page dashboard that presents both the rules (reference) and the results (interactive analysis), in the same Fractal Sweep style.
4. (Deferrable) Pine indicators per validated model, aligned with the Python engine.

The end-state is a personal research tool: study the model, verify it has an edge, see when/where the edge concentrates, then trade or discard.

## Non-goals

- Multi-user features, auth, deployment. Local-only, runs via `python3 -m http.server`.
- Live trading execution. Daily-update cron is a Phase 7 stretch goal at most.
- Chart-per-trade interactivity in v1 (sortable trades table only — visualization deferred).
- Multi-model engine dependencies. Cross-model logic is expressed as filter flags, not detector→detector wiring. Defer real dependencies until materials force the issue.

## Stack & conventions

Match Statistic.ally / Fractal Sweep exactly:

- Python 3.14, DuckDB 1.4.4, pandas
- Plain HTML + vanilla JS dashboards, zero CDN deps
- Engine pre-computes every stat into `model_stats.json`; dashboard does only filtering/aggregation client-side
- Theme via shared `localStorage.getItem('hub-theme')`
- DB read-only from this folder; write path stays in `Fractal Sweep/engine/daily_update.py`
- Timestamps in DB are `America/Toronto` — always convert: `timezone('America/New_York', timestamp)`
- Same baseline gates as Fractal Sweep: `MIN_RISK_PTS = 3.0`, `MAX_RISK_PTS = 112.5`
- Same outcome scanner: `OUTCOME_MAX_BARS = 1440`, same-bar TP/SL → SL
- Same risk profiles: `simple_1r` (default) and `raw_measure`
- Tests via pytest, fixture-based per model

If a specific Amas model documents different values (e.g., a different stop placement rule), the model's spec entry overrides — but defaults match Fractal Sweep so cross-project comparisons are valid.

## Folder layout

```
Statistic.ally/Amas Models/
├── CLAUDE.md
├── README.md
├── model_dashboard.html        single-file dashboard
├── model_stats.json            engine output (gitignored)
├── engine/
│   ├── model_stats.py          orchestrator: load DB, run detectors, resolve outcomes, write JSON
│   ├── models/                 one Python file per Amas model
│   │   ├── __init__.py         registry
│   │   ├── h1_reversal.py
│   │   ├── h1_candle_rules.py
│   │   └── tf_15m_h1.py        (etc.)
│   ├── outcomes.py             shared SL/TP scanner (ported from Fractal Sweep)
│   ├── filters.py              shared filter primitives (SMT, shallow sweep, etc.)
│   ├── db.py                   DB path resolution + TZ conversion helpers
│   └── daily_update.py         (Phase 7) hook into Fractal Sweep's cron
├── pine/                       (Phase 6) one .pine per validated model
├── docs/
│   ├── model_specs.md          Phase 1 deliverable — formalized models + backtest results
│   └── source_index.md         per-source-file summary (24 files)
├── data/                       cached intermediates (gitignored)
├── assets/                     dashboard images
└── tests/
    ├── test_db.py              smoke test: DB connects, tables exist
    ├── test_outcomes.py        SL/TP scanner unit tests
    ├── test_filters.py         filter primitives unit tests
    └── test_<model>.py         per-model fixture tests
```

DB resolves to `Path(__file__).parent.parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'`. The DB is **not** copied or moved.

## Phase 1: Study deliverable

`docs/model_specs.md` is the contract between the study and every line of engine code. It has three top-level sections plus one section per model.

### Top-level sections

1. **Glossary** — every term the mentor uses (CISD, sweep, FVG, BOS, displacement, premium/discount, etc.) defined once with the source where it's introduced. Models reference glossary terms instead of redefining them.
2. **Cross-cutting concepts** — risk rules, session definitions, bias frameworks, confluences that apply to multiple models. Pulled out so they're not duplicated per model.
3. **Source map** (== `docs/source_index.md`'s key data, summarized) — for each of the 24 files, 2–3 sentences on what's in it and which models it informs.

### Per-model template

```
## Model: <name>

### Source citations
- Mentorship 6-H1 Reversal Models.pdf p.4–7
- 1st Call Mentorship 2025.txt L1240–1380
- (etc.)

### Plain-English description
2–4 sentences. What is this model trying to capture?

### Anchor / setup timeframe
e.g., "H1 candle that closes between 09:30 and 16:00 ET"

### Detection rules (all must be true)
Numbered list. Each rule is one boolean condition expressed in OHLC values, prior bars, time, or other models' state. No vague language — vague terms are translated to a numeric threshold or flagged as TBD with the source quote.

### Entry trigger
Exact bar/condition that fires the trade.

### Stop loss
Defined price relative to a specific bar's high/low.

### Take profit / exit
Either fixed R or a defined condition.

### Direction logic
How long vs. short is determined.

### Invalidation / discard
When the setup is dropped (e.g., "if price exits range before CISD fires").

### Confluences / filters mentioned (optional layers)
Anything the mentor presents as "extra confirmation" — bias, SMT, session, day-of-week. Each becomes a togglable dashboard chip, computed as a `passes_<key>: bool` flag on every trade row.

### Open questions / ambiguities
Numbered list with source quote. These are the items to clarify before engine code locks them in.

### Backtest results (filled in during Phase 4)
- Baseline (no filters): WR, EV, PF, N, period
- With recommended filter combo: WR, EV, PF, N
- Notable regime breaks (year, session, DOW)
- Walk-forward: train EV vs test EV, overfitting score
```

### Reading approach

- All 8 PDFs first (structured material); then all 8 transcripts (context, examples, exceptions).
- The `(1).pdf` files are likely long versions; smaller variants are summaries — read in pairs to catch divergence.
- Anything that contradicts itself across sources is logged as an ambiguity. These often point to parameter sweeps worth running later.
- Soft checkpoint: I self-review `model_specs.md` and start engine scaffolding in parallel. The user reviews the doc at their own pace; corrections feed back before deep implementation.

## Phase 2: Engine architecture

### Pipeline

```
DuckDB (nq_1m, es_1m)
    │
    ▼
engine/models/<model>.py
  detect_setups(bars_df, **params) → list[Setup]
    │
    ▼
engine/model_stats.py
  for setup in setups:
    resolve_outcome(bars, setup)        # shared, from outcomes.py
    compute_mae_mfe(...)                # shared
    compute_filter_flags(setup, bars)   # passes_<filter> per filter the model declares
    │
    ▼
model_stats.json (one file, all models, all variants)
    │
    ▼
model_dashboard.html (loads JSON, all interactivity client-side)
```

### Model registry

`engine/models/__init__.py` exposes a registry:

```python
MODELS: dict[str, ModelDefinition] = {
    "h1_reversal": ModelDefinition(
        key="h1_reversal",
        label="H1 Reversal",
        detect=h1_reversal.detect_setups,
        filters=[
            Filter("F1", "Shallow Sweep", h1_reversal.passes_f1, default=False),
            Filter("F2", "SMT", filters.passes_smt, default=False),
            ...
        ],
        spec_anchor="model-h1-reversal",  # anchor in model_specs.md
    ),
    ...
}
```

Adding a model = adding one file in `engine/models/` and registering it. `model_stats.py` iterates `MODELS` and produces one JSON block per model.

### `model_stats.json` shape

```json
{
  "meta": {
    "engine_version": "0.1.0",
    "generated_at": "2026-04-26T19:23:00Z",
    "table": "nq_1m",
    "data_range": "2010-09-01 to 2026-04-25",
    "spec_sha": "<sha256 of model_specs.md>"
  },
  "models": {
    "h1_reversal": {
      "label": "H1 Reversal",
      "filters": [
        {"key": "F1", "label": "Shallow Sweep", "default": false, "delta_wr": 0.034, "delta_ev": 0.061},
        ...
      ],
      "trades": [ /* one row per trade, with passes_* flags */ ],
      "summary": {"n": 1234, "wr": 0.51, "ev": 0.04, "pf": 1.12, ...},
      "by_year": {...},
      "by_session": {...},
      "by_dow": {...},
      "by_hour": {...},
      "smt_summary": {...},
      "filter_variants": [ /* 2^N combos sorted by EV */ ],
      "spec_html": "<rendered markdown of this model's section from model_specs.md>"
    },
    ...
  }
}
```

`spec_html` is pre-rendered at engine time — the dashboard does not run a markdown parser at load time. Engine reads `docs/model_specs.md`, splits by H2 headings, renders the matching block per model.

### CLI

```bash
python3 engine/model_stats.py                         # all models, NQ
python3 engine/model_stats.py --models h1_reversal    # subset
python3 engine/model_stats.py --table es_1m           # ES instead of NQ
python3 -m pytest tests/ -q                           # test suite
```

### Reused Fractal Sweep components

Ported into `engine/outcomes.py` and `engine/filters.py`:

- Outcome resolver with `OUTCOME_MAX_BARS = 1440`, same-bar SL tie-break
- MAE/MFE computation (raw + hourly normalized)
- PTQ / opt_sl recommendation logic (P(positive exit | MFE ≥ X) ≥ 0.70 thresholds)
- Equity tracking (`min_equity_usd`, `max_dd_usd`, `max_dd_pct`)
- SMT primitive (NQ-ES divergence) — adapted to take any sweep-TF window, not just Fractal Sweep's 1H/30M
- `agg()` aggregator

These start as ports rather than imports because the two projects might diverge over time. If they stay identical for a few months we can extract a shared `Statistic.ally/lib/` package.

### Model independence

Models are computed in isolation. Cross-model behavior expressed as a `passes_<filter>` flag on the trade row (e.g., `passes_h4_bias_long`). If the materials require true model→model dependencies later, revisit. Default for v1 is independence.

## Dashboard architecture

### Page layout

```
┌─ Header ────────────────────────────────────────────────────┐
│ Amas Models    [NQ ▼] [Model: H1 Reversal ▼]   ●  ⌂        │
├─────────────────────────────────────────────────────────────┤
│ Filter Chips (model-specific, rendered from JSON)           │
│ [F1: Shallow Sweep ±2.3%]  [F2: SMT ±5.1%]  [F3: …]         │
├─────────────────────────────────────────────────────────────┤
│ Period: [All Time] [2y] [1y] [6m] [3m] [1m] [Custom…]       │
├─────────────────────────────────────────────────────────────┤
│ Headline: WR · EV · PF · N · Avg Risk · Avg RR              │
├─────────────────────────────────────────────────────────────┤
│ Tabs:                                                        │
│  • Overview     equity curve, drawdown, MAE/MFE distros     │
│  • Breakdowns   by year, session, DOW, hour                 │
│  • Filters      2^N combo grid sorted by EV                 │
│  • Trades       sortable table (no per-row chart in v1)     │
│  • Walk-Forward train→test pairs                            │
│  • Spec         pre-rendered model_specs.md (this model)    │
└─────────────────────────────────────────────────────────────┘
```

### Decisions

- **Single page, model selector at top.** Switching model rerenders chip bar, stats, all tabs.
- **Filter chips read from JSON.** Each model declares its own `filters[]`. The dashboard renders chips from that list — no per-model hardcoded UI.
- **Spec tab uses pre-rendered HTML.** Engine renders the markdown at build time and stores in `models.<key>.spec_html`. No JS markdown parser shipped.
- **Trade chart deferred.** v1 ships sortable trades table only. No bars in `model_stats.json` for individual trades. Revisit after Phase 5.
- **Theme key shared with hub:** `localStorage.getItem('hub-theme')`.
- **Single HTML file, zero CDN deps.** Match Fractal Sweep's `model_dashboard.html` pattern.

## Phasing

| Phase | What | Output |
|---|---|---|
| 1 | Read all 24 source files; produce `docs/model_specs.md` + `docs/source_index.md` | Phase 1 deliverable; soft checkpoint |
| 2 | Scaffold `Amas Models/` folder, DB helper, model registry, empty dashboard chrome, hub link, smoke tests | Folder runs; dashboard opens; tests pass; **no models yet** |
| 3 | Pick the simplest model from `model_specs.md` (chosen after reading, not pre-decided); implement detector, register, run engine, render in dashboard, write fixture tests | One model end-to-end; architecture validated |
| 4 | Each remaining model: spec → file → tests → registered → results documented inline in `model_specs.md` | All models in dashboard, each with measured edge |
| 5 | Cross-model analysis, walk-forward per model, head-to-head comparison, promote shared filters if any | Comparative view; identify which models survive |
| 6 | (Optional) Pine indicators per surviving model, engine↔Pine alignment | TradingView confirmation |
| 7 | (Stretch) Hook into Fractal Sweep's `daily_update.py` cron; "today's setups" view | Daily auto-recompute |

The hard milestone is **Phase 3** — one model fully end-to-end. Phases 4+ are replication on a proven architecture.

## Hybrid spec+results doc

`docs/model_specs.md` is both rules (Phase 1) and measured edge (Phase 4 backfill). Each model's section gains a `### Backtest results` subsection during Phase 4 with WR/EV/PF/N at baseline and at the recommended filter combo, plus regime notes.

Rationale: for personal research the rules and their measured edge belong in one place. Two-file separation (rules + results) is cleaner archivally but adds friction every time you want to know "does this model work, and what are its rules?"

## Risks & mitigations

- **Materials are imprecise.** Many trading rules in mentorship-style content use words like "strong" or "clear" without thresholds. Mitigation: every vague term gets translated to a numeric threshold OR flagged as TBD with the source quote. Ambiguities become parameter sweeps later.
- **Model count unknown until reading.** Could be 3, could be 8. Folder layout assumes ~5; registry pattern handles N.
- **Same-bar tie semantics.** Fractal Sweep tie-breaks SL on same-bar TP/SL. If an Amas model's source dictates differently, override in that model's spec — don't silently inherit.
- **JSON size.** With ~5 models × 14y of trades, JSON should be tens of MB, not hundreds (no per-trade bars). If a model produces >50K trades, revisit.
- **Spec drift.** If the engine's behavior diverges from `model_specs.md`, which is canonical? Canonical = the spec. Engine should fail loudly if a TBD is hit. Add a CI check (Phase 5) that engine constants are documented in the spec.

## Open items

None blocking. Items deferred for Phase 4+:

- Whether to extract a shared `Statistic.ally/lib/` once the engine code stabilizes
- Whether to add per-trade chart visualization (currently deferred)
- Whether to add "today's setups" live monitoring (Phase 7)
