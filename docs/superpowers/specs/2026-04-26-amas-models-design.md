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
│   ├── db.py                   DB path resolution + TZ conversion + data-quality checks
│   ├── constants.py            single source of truth: MIN_RISK_PTS, MAX_RISK_PTS, point values, OUTCOME_MAX_BARS
│   └── daily_update.py         (Phase 7) hook into Fractal Sweep's cron
├── pine/                       (Phase 6) one .pine per validated model
├── docs/
│   ├── model_specs.md          Phase 1 deliverable — formalized models + backtest results
│   └── source_index.md         per-source-file summary (24 files)
├── data/                       cached intermediates (gitignored)
├── assets/                     dashboard images
└── tests/
    ├── test_db.py              smoke test: DB connects, tables exist, TZ sentinel
    ├── test_outcomes.py        SL/TP scanner unit tests + idempotency
    ├── test_filters.py         filter primitives unit tests
    ├── test_reproducibility.py byte-for-byte JSON reproducibility
    └── test_<model>.py         per-model fixture tests (trade-count, lookahead audit, direction symmetry)
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
      "summary": {"n": 1234, "n_resolved": 1198, "n_expired": 36, "wr": 0.51, "wr_ci_low": 0.48, "wr_ci_high": 0.54, "ev": 0.04, "pf": 1.12, ...},
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

## Correctness invariants (non-negotiable)

A backtest's most dangerous failure mode is producing a *plausible but inflated* edge. Fractal Sweep shipped at 72% baseline WR for months before the team discovered it should have been ~50% — a 22-point fake edge driven by a single dtype mismatch. The cost wasn't the bug; the cost was *believing* the bug.

These invariants exist to make every category of "silent edge" bug fail loudly, ideally at engine startup or first test run, never in production-but-quietly-wrong.

The categories below are based on Fractal Sweep's actual incident history plus the standard backtester pitfall taxonomy. Every one is a class of bug, not a single instance.

### Category A: Timestamp / timezone correctness

The Fractal Sweep engine had a real incident where pandas 2.0+ defaulted timestamp arrays to `[us]` resolution while the engine assumed `[ns]`, silently inflating 1h anchor windows into ~41 days. Baseline WR appeared as ~70% when the true figure was ~50%. The Amas engine must not be allowed to repeat any version of this.

Required invariants:

1. **DB read** — every query that pulls bars `SELECT timezone('America/New_York', timestamp) AS ts, ...`. The DB stores `America/Toronto`; we never use raw timestamps in detection logic.
2. **pandas dtype lock** — immediately after pulling bars: (a) assert `df['ts'].dt.tz is not None` (timestamp must be tz-aware), (b) assert resolution is `[ns]` not `[us]` via `df['ts'].dtype.unit == 'ns'`, (c) if not, force `df['ts'] = df['ts'].astype('datetime64[ns, UTC]').dt.tz_convert('America/New_York')`. Both checks run on every load, not just in tests. Naive timestamps and `[us]` resolution are both fail-fast errors.
3. **Window math is duration-based, not row-count-based** — when defining "the H1 window for this anchor," compute as `anchor_ts ≤ ts < anchor_ts + Timedelta('1h')`. Never as `bars_df.iloc[i:i+60]`. Row counts are fragile under data gaps (weekends, holidays, missing minutes); duration math is robust.
4. **Anchor floor is explicit** — `anchor_ts = ts.dt.floor('1h')` and similar floors are applied in the timezone we're using for analysis (`America/New_York`), not the DB-stored zone. Floor in the analysis tz, never floor first then convert.
5. **No epoch math anywhere** — never convert to int64 nanoseconds for window comparisons. Use `pd.Timestamp` and `pd.Timedelta` exclusively.
6. **Sentinel test** — `tests/test_db.py` includes a sanity test: load a known historical day (e.g., a known NFP release minute), assert the bar's wall-clock timestamp matches expectation in NY tz. This test catches ANY regression in the load path.
7. **Cross-instrument alignment** — when computing SMT (NQ + ES jointly), both instruments must be loaded through the same code path with the same dtype lock. Misaligned tz on one side silently produces phantom SMT.

The detection layer assumes timestamps are correct. If the load layer is wrong, every model is wrong. Therefore the load layer is the most heavily tested module in the engine.

### Category B: Trade deduplication

A trade row must be uniquely identified by `(model_key, instrument, anchor_ts, direction)`. Duplicate trade rows (same model firing twice on the same anchor, or the same setup logged from two code paths) are a correctness bug, not a curiosity.

Required invariants:

1. **Per-anchor cap** — each model's `detect_setups` returns AT MOST ONE setup per anchor_ts (per direction, if the model is bidirectional). If a model can theoretically generate multiple in one anchor, the spec must explicitly say so and define the tie-break rule.
2. **Post-detect dedup pass** — after detection, `model_stats.py` runs a dedup check per model+instrument: `keys = [(s.anchor_ts, s.direction) for s in setups]; assert len(keys) == len(set(keys)), f"{model_key}/{instrument}: duplicate setups at {<diff>}"`. Hard fail on duplicates, never silently dedupe. The error message names which anchors collided so we can debug the detector that produced them.
3. **Same-anchor opposite-direction is allowed but logged** — if a model can fire long AND short on the same anchor (rare, but possible), the engine must log a warning and the spec must document why.
4. **Outcome resolution is deterministic and idempotent** — given the same setup and same bars, `resolve_outcome` must produce the same trade row every time. No randomness, no time-of-day dependency in the resolver.
5. **Idempotency test** — `tests/test_outcomes.py` runs the engine twice on the same input fixture and asserts the trade lists are identical (`==`, not just same length). Catches accidental nondeterminism.
6. **Per-model trade-count test** — each model's test suite asserts an exact trade count on a small fixed fixture (e.g., "30 days of synthetic OHLC produces exactly N setups"). Drift in this number is a regression signal even if the dashboard summary still looks plausible.

### Category C: Lookahead / future-leak

The single most common silent-edge bug. The detector or outcome resolver accidentally uses information that wouldn't be available at the trade's decision time.

Required invariants:

1. **Detection is causal** — a setup at `anchor_ts` can only use bars where `bar.ts ≤ anchor_ts`. The detector function takes `(bars_up_to_now, anchor_ts)` or operates on a windowed slice. No `bars.iloc[i+1:]` reads in the detection path. Period.
2. **Cross-anchor lookahead is forbidden** — Fractal Sweep had this bug: the CISD confirmation could fire from a future anchor's window, inflating WR. The fix was "sweep, return-to-range, and CISD-fire must all occur within the same anchor HTF window." Every Amas model with a multi-stage trigger inherits the same rule: every condition must be satisfied within the anchor's own window unless the spec explicitly defines a permitted lookahead.
3. **Outcome resolution starts strictly after entry** — `resolve_outcome` scans bars where `bar.ts > entry_ts`. Bars with `bar.ts == entry_ts` (the entry bar itself) do NOT contribute to TP/SL resolution. They contribute to entry price only.
4. **No closing-price-of-current-bar in entry logic** — if the model's entry is "next bar open after anchor close," then we must NOT use the next bar's high/low/close to decide whether to enter. This is a subtle bug — easy to write `if next_bar.close > X: enter at next_bar.open`, which uses next bar's close for a decision applied at next bar's open. Decisions made at time T use only bars closed before T.
5. **Lookahead audit per model** — for every model, a structural review (in code review) confirms that detection only reads bars at indices `≤ anchor_ts`. Where feasible, supplement with a sanity test that runs the detector on `bars[:anchor_idx+1]` slices and confirms the same setup is produced as when running on the full DataFrame. (A full streaming implementation is overkill for a personal research engine; the targeted slice test catches the common cases.)
6. **Future-information filters** — confluences computed across the whole dataset (e.g., "trade only on days where the daily range is in the top quartile") are anti-edge: at decision time we don't know that day's range yet. Every filter must declare which bars it reads (`reads_up_to_anchor` or `reads_session_close` or similar) and the engine asserts the filter only reads up to its declared horizon.

### Category D: Outcome resolver fidelity

The SL/TP scanner is the second most error-prone component. Fractal Sweep had two outcome-resolver bugs that flipped baseline WR: same-bar tie-break (was TP, should be SL) and `OUTCOME_MAX_BARS` set too low (360 vs 1440), which silently truncated trades that would have hit TP.

Required invariants:

1. **Same-bar tie-break is SL** — if a single bar's high ≥ TP and low ≤ SL, the trade is a loss. Documented in spec, asserted in test, never overridable per model unless the model's spec explicitly justifies it.
2. **`OUTCOME_MAX_BARS = 1440` is the default** — a trade that hasn't resolved within 1440 bars (24h of 1m data) is marked `EXPIRED`. Expired trades are EXCLUDED from WR/EV but counted in the trade total (matching Fractal Sweep convention). Lowering this number on a per-model basis requires explicit justification in the spec.
3. **Expired trades are visible** — `summary` reports `n_expired` separately. If `n_expired / n_total > 5%`, the dashboard flashes a warning. Expired trades hide losses (a trade going to MFE then reversing past SL but past the bar limit becomes "expired" instead of "loss"), so they need eyes on them.
4. **MAE/MFE measured to resolution, not to MAX_BARS** — MAE/MFE for resolved trades stop at the resolution bar. For expired trades they extend to MAX_BARS. Never the reverse.
5. **Direction symmetry test** — for every model, feed it a synthetic upward-trending fixture and assert long setups produce expected outcomes; then mirror the fixture and assert short setups behave symmetrically. Catches sign errors.
6. **No survivorship in resolution** — a trade that "would have hit TP eventually" but is cut off by EOD or weekend is not retroactively a winner. The resolver scans the bars it has and reports what happened in those bars.

### Category E: Data quality

Bars themselves can be wrong. Garbage in, fake edge out.

Required invariants:

1. **Gap detection** — `engine/db.py` includes a `check_gaps(bars_df)` helper that reports any intra-session gap > 5 minutes (RTH = Regular Trading Hours, 09:30–16:00 ET). The engine logs gaps but does not abort; large gaps are tagged on affected setups (`has_data_gap: bool`) so the dashboard can filter them out. Cross-session gaps (e.g., overnight, weekend) are expected and not flagged.
2. **Duplicate bar detection** — `assert bars_df['ts'].is_unique` immediately after load. Duplicate bars from a botched Databento merge would silently double-count.
3. **Monotonic timestamps** — `assert bars_df['ts'].is_monotonic_increasing` after load. Out-of-order bars break every windowing operation.
4. **OHLC sanity** — `assert (bars_df['low'] <= bars_df[['open','close','high']].min(axis=1)).all()` and `assert (bars_df['high'] >= bars_df[['open','close','low']].max(axis=1)).all()`. Bad bars from data feed errors must be caught.
5. **Nonzero volume on regular bars** — most bars during RTH should have volume > 0. A long run of zero-volume bars usually means a data feed gap that was filled with last-price, which corrupts MAE/MFE. Tagged but not aborted.
6. **Stable schema** — DB schema (`timestamp TIMESTAMPTZ, o/h/l/c/v`) is asserted at load. If a schema change creeps in via Databento, fail fast.

### Category F: Risk profile and sizing arithmetic

Fractal Sweep's R math depends on `MIN_RISK_PTS = 3.0`, `MAX_RISK_PTS = 112.5`, `RISK_PER_TRADE = $225`, `POINT_VALUE = $2`. A bug in any one silently shifts EV.

Required invariants:

1. **Single source of truth for constants** — `engine/constants.py` holds them; no model file redefines them. If a model's spec needs different sizing (different point value for ES vs NQ), the override is explicit and tested.
2. **NQ vs ES point values are different** — NQ = $2/pt for MNQ; ES = $5/pt for MES. The engine must use the right one per `--table` argument. Default-NQ assumptions that leak into ES results are a silent-edge category.
3. **R is computed in points, not dollars, then converted** — `r = (exit_price - entry_price) / risk_pts` for longs, mirrored for shorts. Stops in dollar terms are derived, not stored. Fewer places to drift.
4. **MIN_RISK / MAX_RISK gates are applied symmetrically per direction** — gate uses `abs(entry - sl)`, never signed.
5. **Equity tracking ships both R and USD** — `min_equity_R`/`max_dd_R` are the canonical, instrument-comparable metrics; `min_equity_usd`/`max_dd_usd` (matching Fractal Sweep) are derived from R × point-value × risk for display. If the two disagree (R says drawdown, USD doesn't), that's a bug — covered by a test.
6. **Test: known-fixture R math** — given a synthetic trade with entry=100, SL=95, exit=110, the resolver returns `r = 2.0`. Mirror for shorts. Failing this test means the basic arithmetic is wrong, full stop.

### Category G: Statistical hygiene

Even with a correct engine, statistical reporting bugs can fake an edge.

Required invariants:

1. **EV is mean R, not median R** — `ev = sum(r) / n_resolved`. Median R is reported separately but never as headline EV.
2. **PF is gross profit / gross loss, computed from R values** — `pf = sum(r where r>0) / abs(sum(r where r<0))`. Bug-prone if computed from dollar amounts with mixed point values.
3. **Sample size visible everywhere** — every WR/EV/PF cell in the dashboard shows N alongside. A 65% WR over 12 trades is not the same finding as 65% over 1,200; suppressing N hides this.
4. **Confidence intervals on WR** — for every breakdown cell, compute Wilson 95% CI on WR. Cells with N < 30 are flagged. Prevents reading edge into noise.
5. **No look-ahead in filters' edge measurement** — when computing "F1 standalone edge: +3.4% WR," the comparison uses the SAME period for filtered and unfiltered, not "F1 trades from 2018-2026 vs all trades from 2010-2026." Period-mismatched comparisons are a silent-edge classic.
6. **Walk-forward overfitting reporting** — train EV vs test EV ratio is shown explicitly; if `test_ev / train_ev < 0.5` the dashboard flags it as likely overfit.
7. **Filter combos use AND semantics, not "best single filter applied"** — when computing "F1+F2+F3" combo edge, every filter must pass. Bug: accidentally OR-ing filter passage.

### Category H: Determinism and reproducibility

Backtests must be exactly reproducible. Same code + same DB + same date range = same JSON byte-for-byte (modulo the `generated_at` field).

Required invariants:

1. **No randomness** — no `np.random` calls in detection or resolution paths. Tied bars resolved deterministically (same-bar TP/SL → SL, documented above).
2. **Stable iteration order** — pandas operations preserve order; dict-of-models is iterated in registration order. JSON output uses sorted keys.
3. **No wall-clock time in logic** — `datetime.now()` appears only in the `meta.generated_at` field. Never in detection (e.g., "if this anchor is from this year").
4. **Reproducibility test** — `tests/test_reproducibility.py` runs the engine twice on a fixed-date subset and diffs the resulting JSON (excluding `meta.generated_at`). Must be byte-identical.

### Cross-cutting review discipline

- Every PR / commit that touches `engine/db.py`, `engine/outcomes.py`, `engine/constants.py`, or any model's `detect_setups` requires re-running the full test suite. No exceptions.
- All assertions above run in production, not gated on `DEBUG`. The cost is nanoseconds; the value is loud failure.
- Every reported finding (in the dashboard, in `model_specs.md`'s Backtest Results) is reviewed against this invariant list before being trusted. The "edge inflation checklist": did we read TZ correctly? are trades deduped? is detection causal? are expired trades excluded? are point values right per instrument? does the dashboard show N and CIs? is the test suite green? Until every box is checked, the number is provisional.
- When porting Fractal Sweep code, line-by-line review the timestamp math, lookahead boundaries, and tie-break semantics; do not trust that "it worked in Fractal Sweep" — Fractal Sweep itself shipped multiple silent-edge bugs and only caught them after months of trusting bad numbers.
- New invariants are added to this section any time we discover a new bug class. The list grows; it never shrinks.

## Risks & mitigations

- **Materials are imprecise.** Many trading rules in mentorship-style content use words like "strong" or "clear" without thresholds. Mitigation: every vague term gets translated to a numeric threshold OR flagged as TBD with the source quote. Ambiguities become parameter sweeps later.
- **Model count unknown until reading.** Could be 3, could be 8. Folder layout assumes ~5; registry pattern handles N.
- **Same-bar tie semantics.** Fractal Sweep tie-breaks SL on same-bar TP/SL. If an Amas model's source dictates differently, override in that model's spec — don't silently inherit.
- **JSON size.** With ~5 models × 14y of trades, JSON should be tens of MB, not hundreds (no per-trade bars). If a model produces >50K trades, revisit.
- **Spec drift.** If the engine's behavior diverges from `model_specs.md`, which is canonical? Canonical = the spec. Engine should fail loudly if a TBD is hit. Add a CI check (Phase 5) that engine constants are documented in the spec.
- **Trust drift on ported code.** Fractal Sweep's `outcomes.py` and `filters.py` are ported, not blindly reused. Each ported function gets a fresh test suite in the Amas project, not just a smoke test.

## Open items

None blocking. Items deferred for Phase 4+:

- Whether to extract a shared `Statistic.ally/lib/` once the engine code stabilizes
- Whether to add per-trade chart visualization (currently deferred)
- Whether to add "today's setups" live monitoring (Phase 7)
