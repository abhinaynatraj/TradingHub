# TTrades Fractal Model Analysis

This folder contains the **TTrades Fractal Model** — a backtest based on a price action technique where a sweep of a prior candle's extreme creates a "T-Spot" zone, and entering on a touch of that zone is the trade. The model tests this mechanic across 11+ years of NQ futures data.

---

## What This Model Does

The setup works like this:
1. Price sweeps the high or low of a prior candle on the 1-hour chart
2. That sweep creates a zone called the **T-Spot** (defined by the body of the sweep candle)
3. If price returns and touches that zone later in the same day, that's the entry
4. The stop goes above/below the sweep extreme; target is a fixed reward-to-risk multiple

This model backtests how often those zone touches led to profitable trades across different filter conditions.

---

## Files in This Folder

| File | What it does |
|---|---|
| `index.html` | The dashboard — open this in your browser to see the results |
| `ttfm_backtest.py` | The backtest engine — runs the analysis and saves results |
| `ttfm_results.json` | Pre-computed results — already included, dashboard loads this automatically |

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
   http://localhost:8001/TTrades%20Fractal%20Model%20Analysis/index.html
   ```

   Or navigate there from the hub page at `http://localhost:8001`.

---

## Step 3 (Optional) — Re-Run the Backtest

If you have the database file (`candle_science.duckdb`) and want to regenerate the results:

**Mac:**
```
cd "path/to/TradingHub/TTrades Fractal Model Analysis"
python3 ttfm_backtest.py
```

**Windows:**
```
cd "C:\path\to\TradingHub\TTrades Fractal Model Analysis"
python ttfm_backtest.py
```

This overwrites `ttfm_results.json` with fresh results.

You can also customize the backtest with options:

```
python3 ttfm_backtest.py --htf 240 --rr 1.5
python3 ttfm_backtest.py --min-risk 3 --max-hold 120
```

| Option | What it does | Default |
|---|---|---|
| `--htf` | Higher timeframe in minutes (e.g. 60 = 1 hour) | 60 |
| `--rr` | Reward-to-risk ratio target | 2.0 |
| `--min-risk` | Minimum setup size in points | 5.0 |
| `--max-hold` | Maximum bars to hold before expiry | 240 |

> **Note:** The database file is not included in the repo because it's very large. The pre-computed `ttfm_results.json` is already there, so you don't need the database to view the dashboard.

---

## The 6 Model Variants

The model has 6 variants based on setup type and direction:

| Variant | Direction | Setup Type |
|---|---|---|
| Normal Bull | Long | Standard T-Spot touch |
| Normal Bear | Short | Standard T-Spot touch |
| Expansive Bull | Long | Wider zone (more room) |
| Expansive Bear | Short | Wider zone |
| ProTrend Bull | Long | With-trend only |
| ProTrend Bear | Short | With-trend only |

---

## Common Problems

**Dashboard shows no data**
→ Make sure the web server is running and you're opening the URL in a browser (not the file directly from your file system).

**`python3 ttfm_backtest.py` gives a database error**
→ The `candle_science.duckdb` database file isn't included in the repo. Use the pre-computed `ttfm_results.json` — the dashboard already has it.

**Port already in use**
→ Change the port: `python3 -m http.server 8002`, then use `http://localhost:8002/TTrades%20Fractal%20Model%20Analysis/index.html`.

**URL doesn't load in browser**
→ The spaces in the folder name need to be typed as `%20` in the browser URL bar, or just navigate from the hub page at `http://localhost:8001`.
