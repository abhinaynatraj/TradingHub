# Fractal Sweep

This folder contains the **Fractal Sweep** backtesting engine — scans 15 years of 1-minute NQ/ES futures data for a sweep-of-prior-candle setup followed by a CISD (Change in State of Delivery) confirmation. Results drive an interactive probability dashboard with 6 runtime-toggleable filters and 64 precomputed filter combinations.

> Consolidated from the old `Fractal Sweep Legacy/` folder on 2026-04-19. See `LEGACY_NOTE.md` for the history.

---

## What This Model Does

The backtest looks for setups where:
1. Price sweeps (trades just beyond) the high or low of a previous candle on a higher timeframe
2. Price then returns inside the prior candle's range
3. A lower-timeframe CISD candle confirms the reversal

It tests **2 timeframe combinations** (1-Hour sweep / 5-Minute CISD, and 30-Minute sweep / 3-Minute CISD). Sweep, return-to-range, and CISD-fire must all occur within the same anchor HTF window — setups that don't complete before the next anchor are discarded (matches the Pine indicator's behavior). Each setup records MAE/MFE, WIN/LOSS, and a row of confirmation flags that drive the dashboard's runtime filters.

---

## Folder Layout

| Path | What it does |
|---|---|
| `model_dashboard.html` | The dashboard — open in your browser to see results |
| `model_stats.json` | Engine output — **gitignored**. Run `python3 engine/model_stats.py` once to generate. |
| `candle_science.duckdb` | Shared DB (gitignored, ~550 MB). Recreate locally from Databento. |
| `engine/model_stats.py` | The backtest engine — runs the analysis, writes `model_stats.json` |
| `engine/daily_update.py` | Optional — fetches new bar data from Databento |
| `engine/install_cron.sh` | One-time cron setup helper for `daily_update.py` |
| `engine/master_backtester.py`, `engine/sltp_analyzer.py`, `engine/recalc.py` | Supporting tooling |
| `pine/fractal_sweep.pine` | TradingView Pine indicator |
| `pine/fractal_sweep_strategy.pine` | TradingView Pine strategy |
| `pine/ttfm+fadi.pine` | TTFM+Fadi indicator (separate experiment) |
| `pine/snapshots/` | Dated backups of the indicator |
| `data/` | Raw Databento `.dbn` dumps (gitignored) |
| `docs/` | Indicator description and standalone analysis write-ups |
| `assets/` | Images used by the dashboard and hub |
| `tests/` | pytest suite |

---

## Step 1 — Install Dependencies

Install Python (see the repo root README), then the required packages.

**Mac:**
```
pip3 install duckdb pandas numpy
```

**Windows:**
```
pip install duckdb pandas numpy
```

---

## Step 2 — Generate Results + View the Dashboard

`model_stats.json` is a build artifact and isn't committed (it's ~140 MB of backtest output). Run the engine once before opening the dashboard.

1. Run the engine from this folder:

   **Mac:**
   ```
   cd "path/to/Statistic.ally/Fractal Sweep"
   python3 engine/model_stats.py
   ```

   **Windows:**
   ```
   cd "C:\path\to\Statistic.ally\Fractal Sweep"
   python engine\model_stats.py
   ```

   Takes roughly 20–40 seconds and writes `model_stats.json` next to the dashboard.

2. Start the web server from the **repo root** (not this subfolder):

   **Mac:**
   ```
   cd path/to/Statistic.ally
   python3 -m http.server 8001
   ```

   **Windows:**
   ```
   cd C:\path\to\Statistic.ally
   python -m http.server 8001
   ```

3. Open your browser:
   ```
   http://localhost:8001/Fractal Sweep/model_dashboard.html
   ```

   Or navigate from the hub page at `http://localhost:8001`.

   If `model_stats.json` is missing, the dashboard renders a "Run `python3 engine/model_stats.py` to generate data" fallback.

---

## Step 3 (Optional) — Re-Run Specific Models

```
python3 engine/model_stats.py --models 1H_5M
python3 engine/model_stats.py --table es_1m
```

---

## Step 4 (Optional) — Keep Data Current

With a Databento API key:

```
python3 engine/daily_update.py
```

Schedule it via `bash engine/install_cron.sh`.

---

## The 2 Timeframe Combinations

| Key | Sweep TF | CISD TF |
|---|---|---|
| `1H_5M` | 1-Hour | 5-Minute |
| `30M_3M` | 30-Minute | 3-Minute |

---

## Runtime Filters

The dashboard filter bar (below the dropdowns) toggles 6 filters live — no re-running. Each chip shows a live `±N` count before you click.

**Setup Quality** (default ON — uncheck to relax)

| Chip | What it requires | Standalone edge |
|---|---|---|
| Shallow Sweep (`F3`) | Sweep pierced ≤ 50% of the prior candle's range | +3-4% WR · +0.05-0.06R EV |
| Closed Back Inside (`F4`) | Price closed back inside the prior candle's range after sweeping | Noise |

**Add Confirmation** (default OFF — check to narrow)

| Chip | What it requires | Standalone edge |
|---|---|---|
| **NQ-ES Divergence** (`SMT`) | NQ swept its prior level but ES did not | **+7-8% WR · +0.15R EV** (strongest single filter) |
| Hour Open Aligned (`HOUR_ALIGNED`) | CISD candle closed on the correct side of the current hour's open | Noise |
| Prior Bar Counters (`PRIOR_COUNTER`) | Prior sweep-TF candle closed against the trade direction | Noise |
| Prior Bar Engulfs (`PRIOR_ENGULFING`) | Prior sweep-TF candle engulfs the one before it (wick-inclusive) | +0.5-1.3% WR |

All 2⁶ = 64 combinations are pre-computed and sortable by EV in the Filters tab.

### Baseline & best combos (post-alignment)

After engine ↔ indicator alignment (2026-04-24), baseline WR is ~50% on both models — the model has no standalone edge without filters. The previously-reported ~70% baseline WR was an artifact of a pandas resolution bug ([ns] vs [us]) that silently inflated anchor windows from 1h to 41 days.

| Combo | Model | WR | EV | N |
|---|---|---|---|---|
| Best by EV | 1H_5M: F3+F4+SMT+HOUR_ALIGNED+PRIOR_COUNTER | 60.1% | +0.202R | 1,015 |
| Best by EV | 30M_3M: F3+F4+SMT+HOUR_ALIGNED+PRIOR_ENGULFING | 61.6% | +0.232R | 151 |
| Practical high-N | 1H_5M: F3+F4+SMT | 59.1% | +0.182R | 1,711 |
| Practical high-N | 30M_3M: F3+F4+SMT | 58.6% | +0.172R | 3,234 |

SMT is the dominant edge — every meaningful combo includes it.

---

## Common Problems

**Dashboard shows "Run `python3 engine/model_stats.py` to generate data"**
→ `model_stats.json` is missing. Run the engine as shown in Step 2.

**Dashboard shows no data / blank page**
→ Web server isn't running, or you're opening the HTML file directly. Serve from the repo root and use `http://localhost:8001/...`.

**`python3 engine/model_stats.py` gives a database error**
→ `candle_science.duckdb` (~550 MB) isn't in the repo. You need the DB locally — fetch it via `python3 engine/daily_update.py` or restore from backup.

**Port already in use**
→ Change the port: `python3 -m http.server 8002`, then use `http://localhost:8002/Fractal Sweep/model_dashboard.html`.
