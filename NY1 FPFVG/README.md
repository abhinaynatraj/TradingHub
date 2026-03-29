# NY1 Fair Value Gap Model — NY1 FPFVG

This folder contains the **NY1 Fair Value Gap Model** — a backtest that looks for the first Fair Value Gap (FVG) that appears in the opening minutes of the New York trading session (9:31–9:59 AM ET) on NQ futures. It tests how those setups performed over 11+ years of data across multiple entry and exit strategies.

---

## What a Fair Value Gap Is

A Fair Value Gap is a 3-candle pattern where the middle candle moves so far that it leaves a gap — the low of the first candle is above the high of the third candle (for a bullish gap) or vice versa. It represents an area price "skipped" and often returns to fill.

This model focuses on the **very first FVG** that forms after the 9:31 AM ET open, which tends to show the direction institutional activity is pushing in the opening drive.

---

## Files in This Folder

| File | What it does |
|---|---|
| `index.html` | The dashboard — open this in your browser to see the results |
| `ny1_backtest.py` | The backtest engine — runs the analysis and saves results |
| `ny1_results.json` | Pre-computed results — already included, dashboard loads this automatically |
| `export_trades.py` | Optional — exports the full trade log to a formatted Excel file |

---

## Step 1 — Make Sure You've Done the Main Setup

Before using this, make sure you've:
- Installed Python (see the main README in the root folder)
- Installed the required packages:

  **Mac (Terminal):**
  ```
  pip3 install duckdb pandas numpy openpyxl
  ```

  **Windows (Command Prompt):**
  ```
  pip install duckdb pandas numpy openpyxl
  ```

---

## Step 2 — View the Dashboard

The dashboard already has pre-computed results included — you don't need to run anything to see it.

1. Start the web server from the **root of the repo** (the main `Statistic.ally` folder, not this subfolder):

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

2. Open your browser and go to:
   ```
   http://localhost:8001/NY1%20FPFVG/index.html
   ```

   Or navigate there from the hub page at `http://localhost:8001`.

---

## Step 3 (Optional) — Re-Run the Backtest

If you have the database file (`candle_science.duckdb`) and want to regenerate the results:

**Mac:**
```
cd path/to/Statistic.ally/NY1 FPFVG
python3 ny1_backtest.py
```

**Windows:**
```
cd "C:\path\to\Statistic.ally\NY1 FPFVG"
python ny1_backtest.py
```

This overwrites `ny1_results.json` with fresh results.

> **Note:** The database file is not included in the repo because it's very large. The pre-computed `ny1_results.json` is already there, so you don't need the database to view the dashboard.

---

## Step 4 (Optional) — Export Trades to Excel

To get a formatted Excel spreadsheet with all trades, one tab per risk profile:

**Mac:**
```
cd path/to/Statistic.ally/NY1 FPFVG
python3 export_trades.py
```

**Windows:**
```
cd "C:\path\to\Statistic.ally\NY1 FPFVG"
python export_trades.py
```

This creates `ny1_trades.xlsx` in the same folder. Each tab in the spreadsheet corresponds to a different risk profile (different stop/target settings). Winning trades are highlighted green, losing trades red.

---

## The Risk Profiles

The dashboard lets you compare multiple ways to manage the trade via the **Risk Profile** dropdown.

**Structural:**
| Profile | Stop | Target |
|---|---|---|
| Structural | Dynamic (candle low/high) | TP1 0.10% + runner to 16:00 |

**Fixed SL/TP — Top 10 (Weighted Score):**

Ranked by composite score (Sharpe 25%, PF 20%, EV 15%, SQN 15%, MaxDD 10%, RoR 10%, CE 5%) on NY1 data only — no daily classification applied. All use SL=0.03%. Verified non-blown across all 6 timeframes.

| Rank | Profile key | SL | TP | R:R |
|---|---|---|---|---|
| #1 | `sl003_tp008` | 0.03% | 0.08% | 2.67R |
| #2 | `sl003_tp009` | 0.03% | 0.09% | 3.00R |
| #3 | `sl003_tp010` | 0.03% | 0.10% | 3.33R |
| #4 | `sl003_tp011` | 0.03% | 0.11% | 3.67R |
| #5 | `sl003_tp016` | 0.03% | 0.16% | 5.33R |
| #6 | `sl003_tp014` | 0.03% | 0.14% | 4.67R |
| #7 | `sl003_tp012` | 0.03% | 0.12% | 4.00R |
| #8 | `sl003_tp015` | 0.03% | 0.15% | 5.00R |
| #9 | `sl003_tp013` | 0.03% | 0.13% | 4.33R |
| #10 | `sl003_tp017` | 0.03% | 0.17% | 5.67R |

---

## Common Problems

**Dashboard shows no data**
→ Make sure the web server is running and you're opening the URL in a browser (not the file directly from your file system).

**`python3 ny1_backtest.py` gives a database error**
→ The `candle_science.duckdb` database file isn't included in the repo. Use the pre-computed `ny1_results.json` — the dashboard already has it.

**`export_trades.py` says "openpyxl not found"**
→ Run `pip3 install openpyxl` (Mac) or `pip install openpyxl` (Windows).

**Port already in use**
→ Change the port: `python3 -m http.server 8002`, then use `http://localhost:8002/NY1%20FPFVG/index.html`.
