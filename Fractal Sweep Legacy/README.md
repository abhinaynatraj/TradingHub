# Fractal Sweep Legacy

This folder contains the **Fractal Sweep Legacy** — the sweep+CISD model with risk profiles, equity tracking, win/loss resolution, and R-multiples. Originally extracted as a frozen pre-TTrades snapshot, it has since been evolved: plain-English filter UI, runtime filter toggling across every Period, live trade-count badges on each chip, and the F1 (min prior range) filter removed entirely after data showed it was rejecting above-average trades.

The backtest scans 11+ years of 1-minute NQ/ES futures data looking for a specific price action setup: a sweep of a prior candle's high or low, followed by a structural shift (CISD). The results are displayed in an interactive dashboard.

> See [`LEGACY_NOTE.md`](LEGACY_NOTE.md) for the full history of what changed since the snapshot and why this folder still exists separately from the main `Fractal Sweep/` directory.

---

## What This Model Does

The backtest looks for setups where:
1. Price sweeps (goes just above or below) the high or low of a previous candle on a higher timeframe
2. Then reverses back inside the prior candle's range
3. A lower-timeframe candle confirms the reversal (this is the "CISD" — Change in State of Delivery)

It tests **4 combinations** of timeframes (e.g., 4-Hour sweep detected, 15-Minute CISD confirmed). For each setup found, it records whether the trade hit its target or stopped out.

---

## Files in This Folder

| File | What it does |
|---|---|
| `model_dashboard.html` | The dashboard — open this in your browser to see the results |
| `model_stats.py` | The backtest engine — runs the analysis and saves results |
| `model_stats.json` | **Build artifact** — gitignored. Run `python3 model_stats.py` to generate it. The dashboard shows a "Run model_stats.py" fallback if it's missing. |
| `daily_update.py` | Optional — fetches new bar data from Databento to keep the database current |
| `candle_science.duckdb` | Symlink to `../Fractal Sweep/candle_science.duckdb` (shared DB). Recreate with `ln -sf "../Fractal Sweep/candle_science.duckdb" candle_science.duckdb` if missing. |

---

## Step 1 — Make Sure You've Done the Main Setup

Before using this, make sure you've:
- Installed Python (see the main README in the root folder)
- Installed the required packages:

  **Mac (Terminal):**
  ```
  pip3 install duckdb pandas numpy
  ```

  **Windows (Command Prompt):**
  ```
  pip install duckdb pandas numpy
  ```

---

## Step 2 — Generate Results + View the Dashboard

Unlike the main `Fractal Sweep/` folder, `model_stats.json` here is a **build artifact** and is not committed to the repo (it's ~140 MB after all the backtest output). You need to run the engine once locally before opening the dashboard.

1. Make sure the shared duckdb symlink exists (see the `candle_science.duckdb` row in the Files table above).

2. Run the engine from this folder:

   **Mac:**
   ```
   cd path/to/Statistic.ally/Fractal Sweep Legacy
   python3 model_stats.py
   ```

   **Windows:**
   ```
   cd C:\path\to\Statistic.ally\Fractal Sweep Legacy
   python model_stats.py
   ```

   This takes roughly 20–40 seconds depending on your machine and writes `model_stats.json` next to the dashboard.

3. Start the web server from the **root of the repo** (the main `Statistic.ally` folder, not this subfolder):

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

4. Open your browser and go to:
   ```
   http://localhost:8001/Fractal Sweep Legacy/model_dashboard.html
   ```

   Or navigate there from the hub page at `http://localhost:8001`.

   If you open the dashboard before running `model_stats.py`, you'll see a "Run `python3 model_stats.py` to generate data" message — that's the graceful fallback.

---

## Step 3 (Optional) — Re-Run the Backtest for Specific Models

You can also run just specific models:

```
python3 model_stats.py --models 1H_5M 1H_3M
```

> **Note:** The database file (`candle_science.duckdb`) is not included in the repo because it's very large (~550 MB). This folder uses a symlink to `../Fractal Sweep/candle_science.duckdb` — see the Files table above.

---

## Step 4 (Optional) — Keep Data Up to Date

If you have a Databento API key and want to pull in new bar data automatically:

```
python3 daily_update.py
```

This fetches any bars that are newer than what's in the database and saves them.

To run this automatically every weekday morning, you can set up a scheduled task. See the comments at the top of `daily_update.py` for instructions.

---

## The 4 Timeframe Combinations

| Name | Sweep Detected On | CISD Confirmed On |
|---|---|---|
| `4H_15M` | 4-Hour candle | 15-Minute candle |
| `1H_5M` | 1-Hour candle | 5-Minute candle |
| `1H_3M` | 1-Hour candle | 3-Minute candle |
| `30M_3M` | 30-Minute candle | 3-Minute candle |

The dashboard lets you switch between all four and shows stats broken down by day of week, session time, and more.

---

## Runtime Filters

The dashboard filter bar (below the dropdowns) lets you toggle 6 filters live without regenerating any data. Each chip shows a live `±N` count so you can see how many trades it would add or remove before clicking.

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

> The old F1 "Min Range" filter was removed on 2026-04-15 after the data showed it was actually rejecting **above-average** trades across all 4 timeframes (4H_15M WR 86.1% → 88.5% after removal). See commit `62eda17` for details.

---

## Common Problems

**Dashboard shows "Run `python3 model_stats.py` to generate data"**
→ The dashboard is missing `model_stats.json`. Run the engine as shown in Step 2.

**Dashboard shows no data / blank page**
→ Make sure the web server is running and you're opening `http://localhost:8001/Fractal Sweep Legacy/model_dashboard.html` (not the file directly).

**`python3 model_stats.py` gives a database error**
→ The `candle_science.duckdb` symlink is missing. Recreate with `ln -sf "../Fractal Sweep/candle_science.duckdb" candle_science.duckdb` from inside this folder.

**Port already in use**
→ Change the port: `python3 -m http.server 8002`, then go to `http://localhost:8002/Fractal Sweep Legacy/model_dashboard.html`.
