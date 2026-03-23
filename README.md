# Edgeful Research Lab

A personal trading research hub for NQ and ES futures. Three statistical backtesting models run against 11+ years of 1-minute bar data, each with an interactive dashboard you open in a browser.

> **No trading experience required to view the dashboards.** You only need to install Python and run two commands to get everything working locally.

---

## What's Inside

| Folder | What it does |
|---|---|
| `CandleScience/` | **Fractal Sweep Model** — detects sweep + structure break setups across four timeframe combinations |
| `NY1 FPFVG/` | **NY1 Fair Value Gap Model** — first presented FVG in the 9:31–9:59 ET opening window on NQ 1-minute |
| `TTrades Fractal Model Analysis/` | **TTrades Fractal Model** — T-Spot zone entry backtest based on sweep + zone-touch mechanic |

The root `index.html` is a **hub page** that links to all three dashboards from one place.

---

## Before You Start — Install Python

Python is a free programming language. These projects use it to process data and produce the files the dashboards read.

### Mac

1. Open **Terminal** (press `Cmd + Space`, type "Terminal", hit Enter)
2. Type this and press Enter:
   ```
   python3 --version
   ```
3. If you see something like `Python 3.9.x` or higher — you already have it. Skip to **Step 2** below.
4. If not, go to [python.org/downloads](https://www.python.org/downloads/) and download the latest version for Mac. Run the installer and follow the prompts.

### Windows

1. Open **Command Prompt** (press `Windows key`, type "cmd", hit Enter)
2. Type this and press Enter:
   ```
   python --version
   ```
3. If you see `Python 3.9.x` or higher — you already have it. Skip to **Step 2** below.
4. If not, go to [python.org/downloads](https://www.python.org/downloads/) and download the latest version for Windows. **During installation, check the box that says "Add Python to PATH"** — this is important.

---

## Step 1 — Download This Repo

### Option A — Download as ZIP (easiest, no Git needed)

1. Click the green **Code** button at the top of this page
2. Click **Download ZIP**
3. Unzip the folder somewhere easy to find, like your Desktop

### Option B — Clone with Git

If you have Git installed:
```
git clone https://github.com/abhinaynatraj/TradingHub.git
cd TradingHub
```

---

## Step 2 — Install the Required Python Packages

These are free libraries Python needs to process the data.

### Mac

Open Terminal, navigate to the folder you downloaded, then run:
```
cd path/to/TradingHub
pip3 install duckdb pandas numpy openpyxl
```

Replace `path/to/TradingHub` with the actual location — for example if you put it on your Desktop:
```
cd ~/Desktop/TradingHub
pip3 install duckdb pandas numpy openpyxl
```

### Windows

Open Command Prompt, then run:
```
cd C:\Users\YourName\Desktop\TradingHub
pip install duckdb pandas numpy openpyxl
```

Replace `C:\Users\YourName\Desktop\TradingHub` with wherever you saved the folder.

---

## Step 3 — Start the Local Web Server

The dashboards need to be served over a local web address (they use `fetch()` to load data files, which doesn't work when you just double-click the HTML file).

This command starts a tiny built-in web server — it's completely local, nothing goes to the internet.

### Mac

```
cd path/to/TradingHub
python3 -m http.server 8001
```

### Windows

```
cd C:\path\to\TradingHub
python -m http.server 8001
```

Leave this terminal window open while you're using the dashboards.

---

## Step 4 — Open the Hub

Open your web browser (Chrome, Firefox, Safari, Edge — any of them) and go to:

```
http://localhost:8001
```

You'll see the **Edgeful Research Lab** hub page with links to all three dashboards.

> **Tip:** Bookmark `http://localhost:8001` so you can come back to it easily.

---

## About the Data

The dashboards load from pre-computed JSON files that are already included in this repo (`model_stats.json`, `ny1_results.json`, `ttfm_results.json`). You don't need to do anything special — the dashboards will work immediately with the data that's already there.

If you want to re-run the backtests yourself (to update with newer data), see the README inside each project folder.

---

## Folder Structure

```
TradingHub/
├── index.html                          ← Hub page (open this in browser)
├── mae_mfe_guide.html                  ← MAE/MFE reference guide
├── CandleScience/
│   ├── model_dashboard.html            ← Sweep model dashboard
│   ├── model_stats.py                  ← Backtest engine
│   ├── model_stats.json                ← Pre-computed results (loaded by dashboard)
│   └── daily_update.py                 ← Fetches new data (optional)
├── NY1 FPFVG/
│   ├── index.html                      ← NY1 FVG dashboard
│   ├── ny1_backtest.py                 ← Backtest engine
│   ├── ny1_results.json                ← Pre-computed results
│   └── export_trades.py                ← Exports trade log to Excel
└── TTrades Fractal Model Analysis/
    ├── index.html                      ← TTrades dashboard
    ├── ttfm_backtest.py                ← Backtest engine
    └── ttfm_results.json               ← Pre-computed results
```

---

## Common Problems

**"python3 is not recognized"** (Windows)
→ Python wasn't added to PATH during installation. Reinstall Python and check "Add Python to PATH".

**Dashboard shows no data / blank page**
→ Make sure the web server is running (`python3 -m http.server 8001`) and you're going to `http://localhost:8001` (not opening the HTML file directly).

**"pip3 is not recognized"** (Windows)
→ Use `pip` instead of `pip3`, or try `python -m pip install duckdb pandas numpy openpyxl`.

**Port already in use**
→ Change the port number: `python3 -m http.server 8002`, then go to `http://localhost:8002`.
