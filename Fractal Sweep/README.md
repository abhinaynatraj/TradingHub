# Fractal Sweep Model — Fractal Sweep

This folder contains the **Fractal Sweep Model** — a backtest that scans 11+ years of 1-minute NQ/ES futures data looking for a specific price action setup: a sweep of a prior candle's high or low, followed by a structural shift (CISD). The results are displayed in an interactive dashboard.

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
| `model_stats.json` | Pre-computed results — already included, dashboard loads this automatically |
| `daily_update.py` | Optional — fetches new bar data from Databento to keep the database current |

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

## Step 2 — View the Dashboard

The dashboard already has pre-computed results included — you don't need to run anything to see it.

1. Start the web server from the **root of the repo** (the main `TradingHub` folder, not this subfolder):

   **Mac:**
   ```
   cd path/to/TradingHub
   python3 -m http.server 8001
   ```

   **Windows:**
   ```
   cd C:\path\to\TradingHub
   python -m http.server 8001
   ```

2. Open your browser and go to:
   ```
   http://localhost:8001/Fractal Sweep/model_dashboard.html
   ```

   Or navigate there from the hub page at `http://localhost:8001`.

---

## Step 3 (Optional) — Re-Run the Backtest

If you have the database file (`candle_science.duckdb`) and want to regenerate the results:

**Mac:**
```
cd path/to/TradingHub/Fractal Sweep
python3 model_stats.py
```

**Windows:**
```
cd C:\path\to\TradingHub\Fractal Sweep
python model_stats.py
```

This will overwrite `model_stats.json` with fresh results. You can also run just specific models:

```
python3 model_stats.py --models 1H_5M 1H_3M
```

> **Note:** The database file (`candle_science.duckdb`) is not included in the repo because it's very large. The pre-computed `model_stats.json` is already there, so you don't need the database to view the dashboard.

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

## Common Problems

**Dashboard shows no data**
→ Make sure the web server is running and you're opening `http://localhost:8001/Fractal Sweep/model_dashboard.html` (not the file directly).

**`python3 model_stats.py` gives a database error**
→ The `candle_science.duckdb` database file isn't included in the repo. The pre-computed `model_stats.json` is already there — you don't need to re-run the backtest.

**Port already in use**
→ Change the port: `python3 -m http.server 8002`, then go to `http://localhost:8002/Fractal Sweep/model_dashboard.html`.
