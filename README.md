# Statistic.ally

A personal trading research hub for NQ and ES futures. Multiple statistical backtesting models run against 11+ years of 1-minute bar data, each with an interactive dashboard you open in a browser.

> **No trading experience required to view the dashboards.** You only need to install Python and run two commands to get everything working locally.

---

## What's Inside

| Folder | What it does |
|---|---|
| `Fractal Sweep/` | **Fixed Constant + TTFM + original sweep+CISD engines** — doctrine-compliant locked-anchor backtests (Fixed Constant is the primary dashboard linked from the hub) |
| `Fractal Sweep Legacy/` | **Sweep + CISD model** — the original sweep-of-prior-high/low setup with CISD confirmation, risk profiles, equity tracking. Still actively maintained as a separate strategy. |
| `TTrades Fractal Model Analysis/` | **TTrades Fractal Model** — T-Spot zone entry backtest based on sweep + zone-touch mechanic |

The root `index.html` is a **hub page** that links to all the dashboards from one place.

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
git clone https://github.com/abhinaynatraj/Statistic.ally.git
cd Statistic.ally
```

---

## Step 2 — Install the Required Python Packages

These are free libraries Python needs to process the data.

### Mac

Open Terminal, navigate to the folder you downloaded, then run:
```
cd path/to/Statistic.ally
pip3 install duckdb pandas numpy openpyxl
```

Replace `path/to/Statistic.ally` with the actual location — for example if you put it on your Desktop:
```
cd ~/Desktop/Statistic.ally
pip3 install duckdb pandas numpy openpyxl
```

### Windows

Open Command Prompt, then run:
```
cd C:\Users\YourName\Desktop\Statistic.ally
pip install duckdb pandas numpy openpyxl
```

Replace `C:\Users\YourName\Desktop\Statistic.ally` with wherever you saved the folder.

---

## Step 3 — Start the Local Web Server

The dashboards need to be served over a local web address (they use `fetch()` to load data files, which doesn't work when you just double-click the HTML file).

This command starts a tiny built-in web server — it's completely local, nothing goes to the internet.

### Mac

```
cd path/to/Statistic.ally
python3 -m http.server 8001
```

### Windows

```
cd C:\path\to\Statistic.ally
python -m http.server 8001
```

Leave this terminal window open while you're using the dashboards.

---

## Step 4 — Open the Hub

Open your web browser (Chrome, Firefox, Safari, Edge — any of them) and go to:

```
http://localhost:8001
```

You'll see the **Statistic.ally** hub page, which links the Fractal Sweep Fixed Constant dashboard. The TTFM, sweep+CISD, and Legacy dashboards open from their respective folders via direct URL.

> **Tip:** Bookmark `http://localhost:8001` so you can come back to it easily.

---

## About the Data

Most dashboards load from pre-computed JSON files that are included in this repo (`ttfm_results.json`, `model_stats.json`, etc.). Two exceptions:

- **`Fractal Sweep/model_stats_fixed_constant.json`** — the Fixed Constant results file exceeds GitHub's 100 MB per-file limit, so it's gitignored. Run `python3 Fractal\ Sweep/model_stats_fixed_constant.py` once locally to generate it (~20 seconds). The dashboard shows a "Run the engine" fallback if it's missing.
- **`Fractal Sweep Legacy/model_stats.json`** — same story. Run `python3 Fractal\ Sweep\ Legacy/model_stats.py` once to generate.

If you want to re-run the other backtests to update with newer data, see the README inside each project folder.

---

## Folder Structure

```
Statistic.ally/
├── index.html                                ← Hub page (open this in browser)
├── Fractal Sweep/                            [Fixed Constant · TTFM · sweep+CISD]
│   ├── model_dashboard_fixed_constant.html   ← Fixed Constant dashboard (primary)
│   ├── model_dashboard_ttfm.html             ← TTFM dashboard
│   ├── model_stats_fixed_constant.py         ← Fixed Constant engine
│   ├── model_stats_ttfm.py                   ← TTFM engine
│   ├── model_stats.py                        ← Original sweep+CISD engine
│   ├── candle_science.duckdb                 ← Shared DB (gitignored, ~550 MB)
│   └── daily_update.py                       ← Fetches new bar data
├── Fractal Sweep Legacy/                     [Sweep + CISD]
│   ├── model_dashboard.html                  ← Legacy sweep+CISD dashboard
│   ├── model_stats.py                        ← Legacy engine (F1 filter removed)
│   ├── candle_science.duckdb                 ← Symlink to ../Fractal Sweep/candle_science.duckdb
│   ├── LEGACY_NOTE.md                        ← Change history since snapshot
│   └── tests/                                ← pytest suite
└── TTrades Fractal Model Analysis/
    ├── index.html                            ← TTrades dashboard
    ├── ttfm_backtest.py                      ← Backtest engine
    └── ttfm_results.json                     ← Pre-computed results
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
