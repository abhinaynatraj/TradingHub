# Fractal Sweep

This folder hosts three backtesting engines over 11+ years of NQ/ES 1-minute futures data, sharing a single `candle_science.duckdb`.

| Engine | What it does | Dashboard |
|---|---|---|
| **Fixed Constant** | Doctrine-compliant locked-anchor MAE/MFE study — one rep per HTF block, no filters | `model_dashboard_fixed_constant.html` (primary, linked from hub) |
| **TTFM** | TTrades Fractal Model — T-Spot touch setups across 6 variants | `model_dashboard_ttfm.html` |
| **Original Sweep + CISD** | Prior-candle sweep → return → CISD confirmation (F1 intact) | *(dashboard lives in `Fractal Sweep Legacy/`)* |

---

## Setup

Install Python (see the root README) and the required packages.

**Mac:**
```
pip3 install duckdb pandas numpy
```

**Windows:**
```
pip install duckdb pandas numpy
```

---

## View the Dashboards

The hub page at `http://localhost:8001` links to **Fixed Constant**. Other dashboards open by direct URL.

Start the web server from the **repo root** (not this subfolder):

```
cd path/to/Statistic.ally
python3 -m http.server 8001
```

Then open:

- Fixed Constant: `http://localhost:8001/Fractal Sweep/model_dashboard_fixed_constant.html`
- TTFM: `http://localhost:8001/Fractal Sweep/model_dashboard_ttfm.html`

The Fixed Constant JSON is large (>100 MB) and is **gitignored**. If the dashboard says "Run the engine," generate it once:

```
cd "path/to/Statistic.ally/Fractal Sweep"
python3 model_stats_fixed_constant.py
```

`model_stats.json` and `model_stats_ttfm.json` are pre-computed and committed, so their dashboards load immediately.

---

## Re-Run a Backtest

Only needed if you have `candle_science.duckdb` and want fresh results.

```
python3 model_stats_fixed_constant.py           # Fixed Constant, ~20s
python3 model_stats_ttfm.py                     # TTFM
python3 model_stats.py                          # Original sweep+CISD
```

All three accept `--table es_1m` and `--models <keys>`:

```
python3 model_stats.py --models 1H_5M 1H_3M --table es_1m
```

> **Database note:** `candle_science.duckdb` (~550 MB) is not in the repo. `Fractal Sweep Legacy/` symlinks to this folder's copy. Without the DB, use the committed JSON.

---

## Keep Data Current (Optional)

With a Databento API key:

```
python3 daily_update.py
```

To schedule it, see `install_cron.sh`.

---

## Models by Engine

**Fixed Constant** (3 models — `15M_1M` deliberately excluded):
| Key | HTF | Chart TF |
|---|---|---|
| `30M_3M` | 30-min | 3-min |
| `1H_5M` | 1-hour | 5-min |
| `4H_15M` | 4-hour | 15-min |

**TTFM** (4 models):
| Key | HTF | Chart TF |
|---|---|---|
| `15M_1M` | 15-min | 1-min |
| `30M_3M` | 30-min | 3-min |
| `1H_5M` | 1-hour | 5-min |
| `4H_15M` | 4-hour | 15-min |

**Original Sweep + CISD** (4 models):
| Key | Sweep TF | CISD TF |
|---|---|---|
| `4H_15M` | 4-hour | 15-min |
| `1H_5M` | 1-hour | 5-min |
| `1H_3M` | 1-hour | 3-min |
| `30M_3M` | 30-min | 3-min |

---

## Common Problems

**Dashboard shows no data**
→ Web server not running, or you're opening the HTML file directly. Serve from the repo root and use `http://localhost:8001/...`.

**"Run the engine" fallback on Fixed Constant**
→ `model_stats_fixed_constant.json` is gitignored. Run `python3 model_stats_fixed_constant.py` once.

**Database error on re-run**
→ `candle_science.duckdb` isn't in the repo. Use the committed JSON, or point the script at your own copy.

**Port already in use**
→ Change it: `python3 -m http.server 8002` and adjust URLs.
