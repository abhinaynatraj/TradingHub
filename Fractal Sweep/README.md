# Fractal Sweep

This folder contains the **Fractal Sweep** backtesting engine — scans 15 years of 1-minute NQ/ES futures data for a sweep-of-prior-candle setup followed by a CISD (Change in State of Delivery) confirmation. Results drive an interactive probability dashboard with 6 runtime-toggleable filters and 64 precomputed filter combinations.

> Consolidated from the old `Fractal Sweep Legacy/` folder on 2026-04-19. See `LEGACY_NOTE.md` for the history.

---

## What This Model Does

The backtest looks for setups where:
1. Price sweeps (trades just beyond) the high or low of a previous candle on a higher timeframe
2. Price then returns inside the prior candle's range
3. A lower-timeframe CISD candle confirms the reversal

It tests **4 timeframe combinations** (e.g. 4-Hour sweep, 15-Minute CISD). Each setup records MAE/MFE, WIN/LOSS, and a row of confirmation flags that drive the dashboard's runtime filters.

---

## Files in This Folder

| File | What it does |
|---|---|
| `model_dashboard.html` | The dashboard — open in your browser to see results |
| `model_stats.py` | The backtest engine — runs the analysis, writes `model_stats.json` |
| `model_stats.json` | Build artifact — **gitignored**. Run `python3 model_stats.py` once to generate. |
| `daily_update.py` | Optional — fetches new bar data from Databento |
| `install_cron.sh` | One-time cron setup helper for `daily_update.py` |
| `fractal_sweep.pine` | TradingView Pine indicator |
| `fractal_sweep_strategy.pine` | TradingView Pine strategy |
| `ttfm+fadi.pine` | TTFM+Fadi indicator (separate experiment) |
| `candle_science.duckdb` | Shared DB (gitignored, ~550 MB). Recreate locally from Databento. |
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
   python3 model_stats.py
   ```

   **Windows:**
   ```
   cd "C:\path\to\Statistic.ally\Fractal Sweep"
   python model_stats.py
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

   If `model_stats.json` is missing, the dashboard renders a "Run `python3 model_stats.py` to generate data" fallback.

---

## Step 3 (Optional) — Re-Run Specific Models

```
python3 model_stats.py --models 1H_5M 1H_3M
python3 model_stats.py --table es_1m
```

---

## Step 4 (Optional) — Keep Data Current

With a Databento API key:

```
python3 daily_update.py
```

Schedule it via `install_cron.sh`.

---

## The 4 Timeframe Combinations

| Key | Sweep TF | CISD TF |
|---|---|---|
| `4H_15M` | 4-Hour | 15-Minute |
| `1H_5M` | 1-Hour | 5-Minute |
| `1H_3M` | 1-Hour | 3-Minute |
| `30M_3M` | 30-Minute | 3-Minute |

---

## Runtime Filters

The dashboard filter bar (below the dropdowns) toggles 6 filters live — no re-running. Each chip shows a live `±N` count before you click.

**Setup Quality** (default ON — uncheck to relax)

| Chip | What it requires |
|---|---|
| Shallow Sweep | Sweep pierced ≤ 50% of the prior candle's range |
| Closed Back Inside | Price closed back inside the prior candle's range after sweeping |

**Add Confirmation** (default OFF — check to narrow)

| Chip | What it requires |
|---|---|
| NQ-ES Divergence | NQ swept its prior level but ES did not |
| Hour Open Aligned | CISD candle closed on the correct side of the current hour's open |
| Prior Bar Counters | Prior sweep-TF candle closed against the trade direction |
| Prior Bar Engulfs | Prior sweep-TF candle engulfs the one before it (wick-inclusive) |

All 2⁶ = 64 combinations are pre-computed and sortable by EV in the Filters tab.

> The old F1 "Min Range" filter was removed on 2026-04-15. Data showed it rejected above-average trades on every TF (e.g., 4H_15M WR 86.1% → 88.5% after removal). See commit `62eda17`.

---

## Common Problems

**Dashboard shows "Run `python3 model_stats.py` to generate data"**
→ `model_stats.json` is missing. Run the engine as shown in Step 2.

**Dashboard shows no data / blank page**
→ Web server isn't running, or you're opening the HTML file directly. Serve from the repo root and use `http://localhost:8001/...`.

**`python3 model_stats.py` gives a database error**
→ `candle_science.duckdb` (~550 MB) isn't in the repo. You need the DB locally — fetch it via `daily_update.py` or restore from backup.

**Port already in use**
→ Change the port: `python3 -m http.server 8002`, then use `http://localhost:8002/Fractal Sweep/model_dashboard.html`.
