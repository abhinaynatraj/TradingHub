# TradingHub

A personal trading research hub for NQ and ES futures. Multiple statistical backtesting models run against 11+ years of 1-minute bar data, each with an interactive dashboard you open in a browser.

> **No trading experience required to view the dashboards.** You only need to install Python and run two commands to get everything working locally.

---

## What's Inside

| Folder | What it does |
|---|---|
| `Fractal Sweep/` | **Sweep + CISD model** — sweep-of-prior-high/low setup with CISD confirmation, 3 runtime-toggleable filters (F3, F4, SMT), 25 risk profiles, equity tracking. Engine and Pine indicator are aligned (same setup logic). |
| `Amas Models/` | **Amas continuation models** — H1 continuation backtests (`h1_continuation`, `h1_continuation_m5`) |
| `NPG Sweep/` | **NPG (Novel Price Generation) sweep** — multi-pairing sweep model (`1H_5M`, `4H_15M`, `D_1H`) with per-pairing parquet outputs |
| `Analysis/` | **Hourly Analysis** — quarter theory + breakout studies; dashboard reads parquets directly via DuckDB-WASM |
| `TTrades Fractal Model Analysis/` | **TTrades Fractal Model** — T-Spot zone entry backtest based on sweep + zone-touch mechanic |

The root `index.html` is a **hub page** that links to all dashboards.

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
git clone https://github.com/silviyaguzen/TradingHub.git
cd TradingHub
```

---

## Step 2 — Install the Required Python Packages

These are free libraries Python needs to process the data. All dependencies are listed in `requirements.txt` at the repo root.

### Mac

Open Terminal, navigate to the folder you downloaded, then run:
```
cd path/to/TradingHub
pip3 install -r requirements.txt
```

Replace `path/to/TradingHub` with the actual location — for example if you put it on your Desktop:
```
cd ~/Desktop/TradingHub
pip3 install -r requirements.txt
```

### Windows

Open Command Prompt, then run:
```
cd C:\Users\YourName\Desktop\TradingHub
pip install -r requirements.txt
```

Replace `C:\Users\YourName\Desktop\TradingHub` with wherever you saved the folder.

---

## Step 3 — Start the Local Web Server

The dashboards need to be served over a local web address (they use `fetch()` to load data files, which doesn't work when you just double-click the HTML file).

`server.py` is a small local-only Python server. It serves the static dashboards AND exposes the `/data`, `/trades`, and `/recalc` endpoints the Fractal Sweep dashboard uses to slice JSON aggregates and stream parquet trade rows on demand. Nothing leaves your machine.

### Mac

```
cd path/to/TradingHub
python3 server.py
```

### Windows

```
cd C:\path\to\TradingHub
python server.py
```

Leave this terminal window open while you're using the dashboards.

> The plain `python3 -m http.server 8001` works for static-only dashboards (Hourly Analysis, NPG Sweep) but is **not enough for Fractal Sweep** — that dashboard relies on `server.py`'s slicing endpoints. Just use `server.py` for everything.

---

## Step 4 — Open the Hub

Open your web browser (Chrome, Firefox, Safari, Edge — any of them) and go to:

```
http://localhost:8001
```

You'll see the **TradingHub** hub page, which links the Fractal Sweep dashboard. Other dashboards (e.g. TTrades) open from their respective folders via direct URL.

> **Tip:** Bookmark `http://localhost:8001` so you can come back to it easily.

---

## About the Data

Most data files are **gitignored** and need to be generated locally before the dashboards have anything to show. The good news: each engine is one Python command.

| Dashboard | Data files | Generate with |
|---|---|---|
| **Fractal Sweep** | `model_stats.json` (~56 MB) + `model_stats.parquet` (~78 MB) | `python3 "Fractal Sweep/engine/model_stats.py"` |
| **Amas Models** | `Amas Models/model_stats.json` (~2.6 MB) | `python3 "Amas Models/engine/model_stats.py"` |
| **NPG Sweep** | `NPG Sweep/npg_stats.json` + `NPG Sweep/data/trades_*.parquet` | `python3 "NPG Sweep/engine/npg_stats.py"` |
| **Hourly Analysis** | `Analysis/data/**/*.parquet` + `Analysis/data/manifest.json` | `python3 "Analysis/engine/run_all.py"` |
| **TTrades** | `ttfm_results.json` (committed to the repo, ~3 MB) | — |

Fractal Sweep's JSON contains aggregate stats only; trade rows live in the parquet sidecar and are fetched on demand by the dashboard via `server.py`'s `/trades` endpoint. NPG Sweep and Hourly Analysis use the same parquet-first pattern — their dashboards load parquets directly into DuckDB-WASM in the browser.

Re-run any backtest with newer data — see the README inside each project folder.

---

## Folder Structure

```
TradingHub/
├── index.html                                ← Hub page (open this in browser)
├── server.py                                 ← Local server: serves dashboards + /data, /trades, /recalc
├── Fractal Sweep/                            [Sweep + CISD]
│   ├── model_dashboard.html                  ← Dashboard with 3 runtime filter chips (F3, F4, SMT)
│   ├── model_stats.json                      ← Aggregate stats (gitignored, ~56 MB)
│   ├── model_stats.parquet                   ← Trade rows (gitignored, ~78 MB) — served via /trades
│   ├── candle_science.duckdb                 ← Shared DB (gitignored, ~550 MB)
│   ├── engine/                               ← Python backtest code
│   │   ├── model_stats.py                    ← Backtest engine (engine ↔ indicator aligned)
│   │   ├── daily_update.py                   ← Fetches new bars from Databento
│   │   └── …                                 ← master_backtester, sltp_analyzer, recalc, install_cron
│   ├── pine/                                 ← TradingView scripts + snapshots
│   ├── data/                                 ← Raw Databento .dbn dumps (gitignored)
│   ├── docs/                                 ← Indicator description, analysis write-ups
│   ├── tests/                                ← pytest suite (drift gate, trades-endpoint tests, etc.)
│   └── LEGACY_NOTE.md                        ← Earlier-era history
├── Amas Models/
│   ├── model_dashboard.html                  ← Amas dashboard
│   ├── model_stats.json                      ← Engine output (gitignored, ~2.6 MB)
│   └── engine/model_stats.py                 ← Continuation backtest
├── NPG Sweep/
│   ├── npg_dashboard.html                    ← NPG dashboard (DuckDB-WASM, reads parquets directly)
│   ├── npg_stats.json                        ← Manifest + summary (gitignored)
│   ├── data/trades_*.parquet                 ← Per-pairing trade rows
│   └── engine/npg_stats.py                   ← NPG backtest
├── Analysis/                                 [Hourly Analysis]
│   ├── dashboard/index.html                  ← DuckDB-WASM dashboard
│   ├── data/{breakout,quarters,strategy}/    ← Per-study parquet outputs
│   └── engine/run_all.py                     ← Quarter + breakout study runner
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
→ Make sure `server.py` is running (`python3 server.py`) and you're going to `http://localhost:8001` (not opening the HTML file directly). The plain `http.server` won't serve Fractal Sweep's `/data` and `/trades` endpoints.

**"pip3 is not recognized"** (Windows)
→ Use `pip` instead of `pip3`, or try `python -m pip install -r requirements.txt`.

**Port already in use**
→ `server.py` hardcodes port 8001. Either stop the other process or edit the `port = 8001` line at the bottom of `server.py`.

**Recalculate button returns stale data**
→ Fixed in the slim-JSON migration — `server.py` now invalidates its in-memory parquet cache when `model_stats.parquet`'s mtime changes. If you somehow still see stale data, restart `server.py`.
