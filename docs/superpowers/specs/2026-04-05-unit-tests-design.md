# Fractal Sweep Unit Test Suite — Design Spec

**Date:** 2026-04-05
**Goal:** 90%+ logic coverage for `model_stats.py` using pytest with synthetic fixtures, no DB dependency.

---

## Architecture

- **Framework:** pytest + pytest-cov
- **Location:** `Fractal Sweep/tests/`
- **Data:** Synthetic numpy arrays built in fixtures — no `candle_science.duckdb` required
- **Execution:** `cd "Fractal Sweep" && python3 -m pytest tests/ -v --cov=model_stats --cov-report=term-missing`

---

## Test Files

| File | Functions Under Test | Focus |
|------|---------------------|-------|
| `conftest.py` | — | Shared fixtures: synthetic 1m/sweep-TF/CISD-TF arrays, pre-built scenarios |
| `test_detection.py` | `detect_setups_base()` | Sweep detection, Q1 window, sweep_ext locking, sweep_max, min_range |
| `test_cisd.py` | `find_cisd()`, `_find_cisd()` | Backward scan, doji skipping, run start, CISD level, scan origin, edge cases |
| `test_anchor.py` | Anchor bar scan logic | Sweep line anchoring to correct bar, tolerance, period boundary, pre-seed |
| `test_resolution.py` | `resolve_outcomes_vectorised()`, `resolve_outcomes_structural()`, `resolve_outcomes_split_tp()` | WIN/LOSS/EXPIRED, risk capping, split exit, BE stop, runner |
| `test_smt.py` | SMT logic in `detect_setups_base()` | ES swept vs not, missing ES data, both directions |
| `test_filters.py` | Filter paths in detection + resolution | All 7 rejection codes |
| `test_aggregation.py` | `agg()`, `get_session()`, `_classify_tspot()`, `build_model_stats()` | Grouping, session mapping, T-Spot classification |
| `test_mae_mfe.py` | `_full_mae_stats()`, `_full_mfe_stats()` | PTQ, opt_sl, percentiles, edge cases |
| `test_resampling.py` | `resample()`, `df_to_arrays()`, `df_1m_to_arrays()` | OHLCV aggregation, timestamp alignment, array shape |

---

## Shared Fixtures (`conftest.py`)

### `make_m1_arrs(n_bars, start_price, trend, volatility)`
Builds synthetic 1-minute numpy arrays with controllable price action.

Returns dict: `{'ts_ns', 'high', 'low', 'open', 'close', 'hr', 'mn', 'dow', 'trade_date', 'yr'}`

- `trend`: per-bar drift (e.g., +0.5 = uptrend, -0.5 = downtrend, 0 = flat)
- `volatility`: random range per bar (e.g., 5.0 = ±5 pts)
- Timestamps: sequential 1-minute intervals starting from a fixed epoch
- Hours cycle 7-16 (RTH), DOW cycles Mon-Fri

### `make_sweep_arrs(m1_arrs, tf_min)`
Resamples synthetic 1m arrays into sweep-TF candles (4H/1H/30M).

Returns dict: same keys as `df_to_arrays()` output.

### `make_sweep_scenario(direction, sweep_pct, risk_pts, cisd_bars_after_return)`
Builds a complete scenario with known outcome: prior candle → sweep → return → CISD.

Returns `(m1_arrs, s_arrs, c_arrs)` where detection should find exactly 1 setup.

Parameters:
- `direction`: 'LONG' or 'SHORT'
- `sweep_pct`: how deep the sweep goes (fraction of prior range)
- `risk_pts`: entry-to-SL distance
- `cisd_bars_after_return`: how many bars after return before CISD fires

### `make_trade_rows(n, wr, avg_r_win, avg_r_loss)`
Builds a list of resolved trade row dicts for testing aggregation and MAE/MFE functions.

---

## Test Scenarios by File

### `test_detection.py`

**Sweep detection:**
- LONG: price breaks below prior low in Q1 → `swept_long = True`
- SHORT: price breaks above prior high in Q1 → `swept_short = True`
- Sweep outside Q1 window → detected but `q1_sweep = False`
- No sweep (price stays within range) → no setup

**Sweep extreme locking:**
- Sweep detected on bar 2, deeper low on bar 3 (still in Q1) → `sweep_ext` updated via backward scan
- Sweep detected, deeper low on bar 8 (after Q1) → `sweep_ext` NOT updated (locked)

**Filters at detection time:**
- `ref_range < min_range` → `rejected_by = 'F1_SMALL_RANGE'`
- `sweep_ext / ref_range > SWEEP_MAX_PCT` → `rejected_by = 'F3_SWEEP_TOO_LARGE'`
- No close back inside range → `rejected_by = 'F4_NO_CLOSE_BACK'`

**Q1 window:**
- 1H_5M model: Q1 = 3 bars (15 min). Sweep on bar 3 = Q1. Sweep on bar 4 = non-Q1.
- 4H_15M model: Q1 = 4 bars (60 min).

**Gap handling:**
- Gap > `sweep_tf_min * 3` between consecutive sweep-TF candles → skip (no setup)

### `test_cisd.py`

**Core backward scan:**
- 3 consecutive bearish candles before return bar → CISD level = open of **earliest** bearish
- 5 bearish candles with 2 dojis (close==open) mixed in → dojis skipped, level = open of earliest bearish
- Single bearish candle before return → CISD level = its open
- Bullish candle immediately before return (no opposing run) → no CISD
- All dojis before return → no CISD

**Scan origin:**
- Scans backward from `ret_bar`, not from sweep bar
- Return happens 10 bars after sweep → scan starts at offset 10
- Return on same bar as sweep → scan from that bar

**CISD level correctness:**
- CISD level = `open[run_start_k]` — the **open** of earliest candle
- LONG: opposing = bearish (close < open), fires when `close > cisd_level`
- SHORT: opposing = bullish (close > open), fires when `close < cisd_level`

**Fire timing:**
- CISD fires immediately on the bar that crosses the level
- CISD fires 50 bars after return → still valid (no bar limit with `CISD_FAST_BARS = None`)
- CISD level crossed on a doji → should still fire (crossing check is on close, not candle polarity)

**Edge cases:**
- Run extends all the way back to sweep bar
- CISD level very close to entry → risk < MIN_RISK_PTS → rejected
- Multiple opposing runs separated by a same-direction candle → only the nearest run is used
- `cisd_lookback * 4` exceeded → scan stops, no CISD found

### `test_anchor.py`

**Newest-to-oldest overwrite scan:**
- Prior 1H high made on bar 5 of 12 → `anc_hi_bar` = bar 5 (earliest)
- Prior 1H high touched on bars 3, 7, 11 → `anc_hi_bar` = bar 3 (earliest overwrite wins)
- High made on bar 12 (last bar of period) → `anc_hi_bar` = bar 12
- High made on bar 1 (first bar) → `anc_hi_bar` = bar 1
- No bar reaches high within scan range → fallback to `bar_index - 1`

**Tolerance:**
- High at 24160.00, bar high at 24159.75 (within `mintick * 2`) → match
- High at 24160.00, bar high at 24158.00 (outside tolerance) → no match

**Scan range:**
- 5M chart / 1H sweep: `_htf_bars = 12`. Bar at offset 13 → out of range, not scanned
- 15M chart / 4H sweep: `_htf_bars = 16`. Bar at offset 17 → out of range

**Both hi and lo independent:**
- High made at bar 3, low made at bar 9 → `anc_hi_bar` and `anc_lo_bar` are different bars

**Pre-seed:**
- Prior candle swept above prev-prev high and closed back below → `swept_short = True`, `ret_short = True` pre-seeded at reset
- Prior candle swept below prev-prev low and closed back above → `swept_long = True`, `ret_long = True` pre-seeded
- Prior candle did NOT sweep prev-prev → no pre-seed
- Pre-seed with `ext / pp_range > sweep_max` → no pre-seed (filter applies)
- Pre-seed with `pp_range < min_range` → no pre-seed

### `test_resolution.py`

**Vectorised (all-in/all-out):**
- Price hits target before stop → WIN, `r = +target_val`
- Price hits stop before target → LOSS, `r = -stop_val`
- Neither hit within OUTCOME_MAX_BARS (360) → EXPIRED, `r = exit_at_close`
- Stop and target hit on same bar → determined by bar OHLC order (high vs low first)

**Structural (90/10 split):**
- TP1 hit → 90% exits at +1R, runner holds with BE stop
- Runner hits TP2 → `net_r = 0.90 * 1.0 + 0.10 * runner_r`
- Runner stopped at BE → `net_r = 0.90 * 1.0 + 0.10 * 0.0 = 0.90`
- SL hit before TP1 → full loss `-1.0R`
- Expired → close position at current price

**Split TP (PTQ-based):**
- SL = `min(structural, entry * mae_p90 / 100)` — tighter of two
- TP1 at PTQ level, TP2 at p50 MFE
- MAE p90 cap tightens the stop → same trade might WIN with split but LOSS with structural

**Risk validation:**
- `risk_pts < MIN_RISK_PTS (3.0)` → INVALID
- `risk_pts > MAX_RISK_PTS (112.5)` → INVALID
- Entry on wrong side of sweep extreme (LONG entry below SL) → skipped

**MAE/MFE tracking:**
- MAE = worst drawdown during trade as % of entry
- MFE = best favorable excursion as % of entry
- Hour-normalized: `mae_pct_hr = mae_pts / hour_range_pts * 100`

### `test_smt.py`

**SMT divergence detection:**
- NQ sweeps below prior 1H low, ES holds above its prior 1H low → `smt = True`
- NQ sweeps below prior 1H low, ES also sweeps below its low → `smt = False`
- NQ sweeps above prior 1H high, ES holds below its high → `smt = True`
- NQ sweeps above prior 1H high, ES also sweeps above its high → `smt = False`

**ES data matching:**
- ES sweep-TF timestamp matches NQ within 1 minute → valid comparison
- ES timestamp doesn't match (gap in ES data) → `smt = False` (no ES ref available)

**Fallback:**
- `es_s_arrs = None` → `has_smt = False`, all trades get `smt = False`
- `es_m1_arrs = None` → `has_smt = False`
- ES Q1 window has no bars (e.g., ES halted) → `smt = False`

### `test_filters.py`

**All 7 rejection codes:**
- `F1_SMALL_RANGE`: prior range 5 pts with min_range=12 → rejected
- `F3_SWEEP_TOO_LARGE`: sweep 60% of range with SWEEP_MAX_PCT=0.50 → rejected
- `F4_NO_CLOSE_BACK`: sweep detected but close stays outside range → rejected
- `NO_CISD`: sweep + return but no opposing delivery run found → rejected
- `INVALID_RISK`: risk_pts = 1.5 (< MIN_RISK_PTS=3.0) → rejected
- `RISK_TOO_LARGE`: risk_pts = 150 (> MAX_RISK_PTS=112.5) → rejected
- Valid setup (passes all filters) → `rejected_by = ''`

**Cumulative filtering:**
- Setup fails F1 → rejected_by = 'F1_SMALL_RANGE' (doesn't check further filters)
- Setup passes F1, fails F3 → rejected_by = 'F3_SWEEP_TOO_LARGE'

### `test_aggregation.py`

**`agg()` function:**
- 10 trades (7 WIN, 3 LOSS) → wr=0.70, correct ev/pf
- All wins → pf=infinity handling (no division by zero)
- All losses → wr=0.0, ev negative
- Empty group → n=0 graceful handling

**`get_session()` mapping:**
- 7.0 → 'PRE', 8.5 → 'NY1', 11.5 → 'NY2', 3.0 → 'OVERNIGHT', 20.0 → 'OTHER'
- Boundary: 8.49 → 'PRE', 8.50 → 'NY1'

**`_classify_tspot()`:**
- sweep_pct=0.15, LONG → 'ProTrend_BULL'
- sweep_pct=0.50, SHORT → 'Normal_BEAR'
- sweep_pct=0.85, LONG → 'Expansive_BULL'
- Boundary: 0.30 → 'Normal', 0.80 → 'Expansive'

**`build_model_stats()` integration:**
- Receives DataFrame with known trades → outputs dict with correct by_hour, by_dow, by_session, dir_summary, tspot_breakdown, smt_summary

### `test_mae_mfe.py`

**PTQ (Protect the Queen):**
- Winners MFE: p_pos ≈ 1.0 at all levels → PTQ = lowest trigger (highest reach)
- Losers MFE: p_pos ≈ 0 → PTQ = None
- Mixed: PTQ = highest reach_rate where p_pos ≥ 0.70, fallback 0.50
- Fewer than 5 trades → return None/defaults

**opt_sl:**
- Winners MAE: p_ko = 0 at all levels → opt_sl = None (use p90 percentile)
- Losers MAE: p_ko = 1 → opt_sl = lowest threshold
- Mixed: first threshold where p_ko ≥ 0.70, fallback 0.50

**Percentiles:**
- 100 trades → p50/p75/p90 computed correctly
- Edge: 1 trade → percentiles = that single value
- Edge: all same value → all percentiles equal

### `test_resampling.py`

**`resample()` correctness:**
- 12 bars of 1m → 1 bar of 60m (1H)
- OHLCV: open = first open, high = max high, low = min low, close = last close
- Timestamps align to period start

**`df_to_arrays()` and `df_1m_to_arrays()`:**
- Returns dict with correct keys
- Array lengths match input DataFrame rows
- `ts_ns` is int64 nanoseconds
- `high >= low` for every bar (data integrity)

---

## Coverage Target

| Area | Target | Notes |
|------|--------|-------|
| `detect_setups_base()` | 95% | Core detection + SMT + filters |
| `find_cisd()` / `_find_cisd()` | 95% | All scan paths + edge cases |
| `resolve_outcomes_*()` | 90% | All 3 profile types + edge cases |
| `agg()` / `get_session()` / `_classify_tspot()` | 95% | Simple functions, easy to cover |
| `_full_mae_stats()` / `_full_mfe_stats()` | 90% | Recommendation logic + edge cases |
| `build_model_stats()` | 85% | Integration test with known inputs |
| `resample()` / array conversion | 85% | Shape + value correctness |
| Anchor bar scan | 90% | Tolerance, scan range, overwrite pattern |
| **Overall** | **≥90%** | |

---

## Test Execution

```bash
# Run all tests
cd "Fractal Sweep"
python3 -m pytest tests/ -v

# With coverage
python3 -m pytest tests/ -v --cov=model_stats --cov-report=term-missing

# Single file
python3 -m pytest tests/test_cisd.py -v

# Single test
python3 -m pytest tests/test_cisd.py::test_backward_scan_3_bearish -v
```

---

## Dependencies

```
pip install pytest pytest-cov
```

No other dependencies beyond what the project already uses (numpy, pandas, duckdb).
