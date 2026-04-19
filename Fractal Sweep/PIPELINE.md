# Fractal Sweep Pipeline

Three independent backtest engines feed three dashboards from one shared database.

```
Databento API (1m OHLCV)
    ↓
daily_update.py (cron: 7am ET, weekdays)
    ↓
candle_science.duckdb  (nq_1m, es_1m)
    ↓
 ┌──────────────────────────────┬────────────────────────────────┬──────────────────────┐
 ↓                              ↓                                ↓
model_stats_fixed_constant.py   model_stats_ttfm.py              model_stats.py
    ↓                              ↓                                ↓
*.json                           *.json                           *.json
    ↓                              ↓                                ↓
Fixed Constant dashboard         TTFM dashboard                    (Legacy dashboard)
```

The original sweep+CISD dashboard has been removed from this folder. See `Fractal Sweep Legacy/` for the actively-maintained version with runtime filter toggles and F1 removed.

---

## Database

**File:** `candle_science.duckdb` (gitignored, ~550 MB)

| Table | Schema |
|-------|--------|
| `nq_1m` | `timestamp TIMESTAMPTZ, open/high/low/close DOUBLE, volume BIGINT` |
| `es_1m` | Same schema |

Timestamps stored as `America/Toronto`. Always convert: `timezone('America/New_York', timestamp)`.

---

## Fixed Constant Engine

Doctrine-compliant locked-anchor MAE/MFE study. For each new HTF block, the engine locks the anchor at the **close of the first chart-TF bar** inside that block. From that lock close, up/down excursions are measured to the end of the HTF block.

**Passes all four fixed-constant qualification tests:**
1. Same time every rep (locked HTF block boundary)
2. Consistent structure (same anchor TF every rep)
3. Zero conditional judgment (no setup criteria)
4. Decision anchor only (direction comes from external sources)

| Key | HTF | Chart TF |
|---|---|---|
| `30M_3M` | 30 min | 3 min |
| `1H_5M` | 1 hour | 5 min |
| `4H_15M` | 4 hour | 15 min |

`15M_1M` is deliberately excluded — measurement window too short.

**Output JSON is large (>100 MB) and gitignored.** The dashboard degrades gracefully to a "Run the engine" fallback.

---

## TTFM Engine (TTrades Fractal Model)

T-Spot → Touch → Pivot Sweep Confirmation. MAE/MFE only — no WIN/LOSS, no filters, no SMT, no Q1/CISD.

- **T-Spot zone:** `C3.close ↔ sweep_mid` (log-weighted midpoint of the C3 sweep candle)
- **6 variants:** `Normal` × `Expansive` × `ProTrend` crossed with `BEAR`/`BULL`
- **Defaults:** `DEFAULT_MIN_RISK = 5.0 pts`, `DEFAULT_MAX_HOLD = 240 bars`
- **Models:** `15M_1M`, `30M_3M`, `1H_5M`, `4H_15M`

---

## Original Sweep + CISD Engine

Still lives here as the reference implementation. F1 filter intact.

**Phase 1 — Sweep:** Price breaks beyond the prior HTF candle's high or low within Q1. Sweep must be ≤50% of prior range. Prior range ≥ `min_range`.

**Phase 2 — Return:** Price closes back inside the prior candle's range. No deadline within the HTF period.

**Phase 3 — CISD:** Backward scan from the return bar finds the consecutive opposing delivery run. CISD level = open of the earliest candle in that run. Fires when current close crosses through it.

**Entry:** Next CISD-TF candle open. **Stop:** sweep extreme. **Target:** 1R (structural).

| Key | Sweep TF | CISD TF | Q1 Window | min_range |
|-----|----------|---------|-----------|-----------|
| `4H_15M` | 4 Hour | 15 Min | 60 min | 30 pts |
| `1H_5M` | 1 Hour | 5 Min | 15 min | 12 pts |
| `1H_3M` | 1 Hour | 3 Min | 15 min | 12 pts |
| `30M_3M` | 30 Min | 3 Min | 8 min | 8 pts |

**Constants:** `SWEEP_MAX_PCT = 0.50` · `MIN_RISK_PTS = 3.0` · `MAX_RISK_PTS = 112.5` · `CISD_FAST_BARS = None`

### SMT Divergence
Loads `es_1m`, builds ES sweep-TF candles, checks the ES Q1 window at NQ sweep time. Each trade carries `smt: bool`. JSON output includes `smt_summary` with WR/EV/PF split.

### Risk Profiles
- **`structural_dynamic`** — SL = sweep extreme; TP1 = 1R @ 90%; 10% runner with BE stop
- **`split_80_20`** — SL = min(sweep extreme, MAE p90 of winners); TP1 = PTQ level @ 90%; TP2 = p50 MFE for 10% runner
- **`sl_NNN_tp_NNN`** — 10 fixed-% DDLI-ranked profiles

---

## Daily Update

**File:** `daily_update.py` (cron: 7am ET, weekdays)

```
Query DB for max(timestamp) per table
  → Fetch new bars from Databento API
  → Upsert into candle_science.duckdb
  → Mac notification (success/error)
```

Install with `install_cron.sh`.

---

## Execution

```bash
python3 model_stats_fixed_constant.py           # Fixed Constant
python3 model_stats_ttfm.py                     # TTFM
python3 model_stats.py                          # Sweep + CISD

# Any engine:
python3 <engine>.py --models 1H_5M 4H_15M       # subset
python3 <engine>.py --table es_1m               # ES instead of NQ

# Serve (from repo root)
python3 -m http.server 8001
```
