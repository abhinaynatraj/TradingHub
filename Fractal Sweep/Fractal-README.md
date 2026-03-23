# Candle Science · Sweep Model Probability Engine

A statistical backtesting engine for a mechanical **sweep + CISD** trading model built on 15 years of NQ 1-minute futures data. Outputs a probability dashboard with win rate, EV, and profit factor broken down by hour, session, day of week, and timeframe pair.

---

## What the Model Does

The model detects a specific 4-step mechanical setup across four timeframe pairs:

```
1. Prior candle high or low is swept (taken out) during Q1 of the next candle
2. Price returns back inside the prior candle's range within Q1
3. A CISD (Change in State of Delivery) confirms on the lower timeframe
4. Entry = next candle open · Stop = sweep extreme · Target = 2R (1:2 R:R)
```

**CISD definition:** A lower-timeframe candle whose close breaks the prior candle's high (bullish) or low (bearish).

---

## Four Model Variants

| Model Key | Sweep TF | CISD TF | Q1 Window | Typical Risk |
|-----------|----------|---------|-----------|--------------|
| `4H_15M`  | 4 Hour   | 15 Min  | First 1h  | ~28–40 pts   |
| `1H_5M`   | 1 Hour   | 5 Min   | First 15m | ~14–24 pts   |
| `1H_3M`   | 1 Hour   | 3 Min   | First 15m | ~10–20 pts   |
| `30M_3M`  | 30 Min   | 3 Min   | First 8m  | ~8–16 pts    |

All four models run in a single pass and output to one JSON file. The dashboard lets you tab between them and compare at a glance.

---

## Files

```
Fractal Sweep/
├── candle_science.duckdb     ← your existing NQ 1m database
├── model_stats.py            ← detection + statistics engine
├── model_dashboard.html      ← probability dashboard (zero dependencies)
├── model_stats.json          ← generated output (created on first run)
└── README.md                 ← this file
```

---

## Requirements

```bash
pip install duckdb pandas numpy
```

Python 3.9+ recommended. No other dependencies. The dashboard is a single HTML file with no CDN or internet requirement.

---

## Setup

### 1. Verify your DuckDB path

Open `model_stats.py` and confirm the path at the top matches your database location:

```python
DB_PATH  = Path(__file__).parent / 'candle_science.duckdb'
OUT_PATH = Path(__file__).parent / 'model_stats.json'
TABLE    = 'nq_1m'
```

### 2. Run the engine

```bash
cd path/to/TradingHub/Fractal\ Sweep
python3 model_stats.py
```

This runs all four models and prints a comparison table:

```
  Model         Base WR    Base EV    Base PF  →    WR       EV       PF       N    SPD
  4H_15M         49.1%    +0.073R     1.147      56.1%  +0.683R   1.840    2,890   0.88
  1H_5M          50.2%    +0.255R     1.263      55.7%  +0.671R   1.820    3,510   1.82
  1H_3M          49.8%    +0.241R     1.252      55.1%  +0.652R   1.780    4,020   2.24
  30M_3M         49.6%    +0.183R     1.303      49.6%  +0.487R   1.965    2,942   1.18
```

### 3. Start a local server

```bash
python3 -m http.server 8000
```

### 4. Open the dashboard

```
http://localhost:8000/model_dashboard.html
```

The dashboard auto-loads `model_stats.json` from the same folder. You can also load it manually with the **↑ LOAD** button.

---

## CLI Options

```bash
# Run all 4 models (default)
python3 model_stats.py

# Run specific models only
python3 model_stats.py --models 1H_5M 1H_3M

# Use a different instrument
python3 model_stats.py --table es_1m --output es_model_stats.json

# Custom database path
python3 model_stats.py --db /path/to/your.duckdb
```

---

## Refinement Filters

Five quality filters are applied to each setup. The dashboard's **EV Waterfall** panel shows the exact EV improvement each filter contributes:

| Filter | Parameter | What It Removes |
|--------|-----------|-----------------|
| **F1** Prior range floor | ≥ 12 pts (1H), ≥ 30 pts (4H), ≥ 80 pts (1D) | Hours where the prior candle was too compressed to trade |
| **F2** Sweep minimum size | ≥ 10% of prior range | 1-tick wicks — noise, not a real liquidity grab |
| **F3** Sweep maximum cap | ≤ 150% of prior range | Enormous extensions where the market is trending hard, not faking |
| **F4** Close-back required | Close must return inside prior range | Wick-only returns without committed rejection |
| **F5** CISD speed | Within 8 CISD-TF bars of return | Slow structure breaks that belong to a different market move |

Filters are applied cumulatively. The unfiltered baseline is always tracked so you can see the full before/after comparison.

---

## Dashboard Panels

| Panel | What It Shows |
|-------|---------------|
| **Compare Bar** | WR / EV / PF / Setups-per-day for all 4 models side by side |
| **Win Rate by Hour** | LONG vs SHORT grouped bars with 33.3% breakeven line |
| **By Session** | NY1 (08:30–11:30) vs NY2 (11:30–16:00) |
| **By Day of Week** | Mon–Fri edge breakdown |
| **Direction Summary** | LONG vs SHORT with WR, EV, PF, count |
| **Hour × Day Heatmap** | Color-coded win rate grid — identifies your best time slots |
| **Best / Worst Setups** | Top and bottom combos ranked by EV (min 6 occurrences) |
| **EV Waterfall** | Per-filter EV improvement from baseline to refined |
| **R Distribution** | Histogram of all outcomes: -2R / partial / 2R / 3R+ |
| **Win Rate by Year** | Regime stability check across 15 years |
| **Risk Distribution** | P25 / Median / Mean / P75 / P90 stop sizes |

All panels are interactive — hover any bar, dot, or cell for detail.

---

## Output JSON Schema

`model_stats.json` is a top-level object keyed by model (`4H_15M`, `1H_5M`, `1H_3M`, `30M_3M`). Each model contains:

```json
{
  "1H_5M": {
    "meta": {
      "model_key", "model_label", "instrument", "date_range",
      "trading_days", "total_raw", "total_wl", "total_expired",
      "win_rate", "ev_per_trade", "profit_factor", "avg_risk_pts",
      "setups_per_day_ny", "risk_breakeven_wr", "rr_target",
      "risk_median", "risk_p25", "risk_p75", "risk_p90"
    },
    "by_hour":      [ { hr, direction, n, wins, wr, ev, pf, avg_risk_pts, hr_label } ],
    "by_session":   [ { session, direction, n, wins, wr, ev, pf } ],
    "by_dow":       [ { dow, dow_name, direction, n, wins, wr, ev, pf } ],
    "heatmap":      [ { hr, dow, dow_name, wr, ev, n } ],
    "top_combos":   [ { hr, dow, dow_name, direction, label, n, wins, wr, ev, pf, avg_risk_pts } ],
    "worst_combos": [ ... same ... ],
    "by_year":      [ { yr, n, wins, wr, ev } ],
    "r_hist":       [ { bucket, n } ],
    "dir_summary":  [ { direction, n, wins, wr, ev, pf, avg_risk_pts } ],
    "risk_dist":    { mean, median, p25, p75, p90, max },
    "filter_impact":[ { label, n, wr, ev, pf, removed } ]
  }
}
```

---

## Key Constants (model_stats.py)

```python
RR               = 2.0     # 1:2 risk-reward target
MIN_RISK_PTS     = 3.0     # minimum valid stop in points
OUTCOME_MAX_BARS = 360     # max 1m bars forward to scan for outcome (~6h)
SWEEP_MIN_PCT    = 0.10    # sweep must be >= 10% of prior range
SWEEP_MAX_PCT    = 1.50    # sweep must be <= 150% of prior range
CISD_FAST_BARS   = 8       # CISD must form within 8 CISD-TF bars of return
```

---

## Notes

- **Timestamps** in DuckDB are stored as `TIMESTAMP WITH TIME ZONE`. All date/time extraction uses `timezone('America/New_York', timestamp)` to ensure correct ET alignment.
- **Expired setups** (neither target nor stop hit within the scan window) are excluded from win rate and EV calculations but counted in the output.
- **Profit Factor** = (total winning R) ÷ (total losing R). Above 1.5 is generally considered strong; above 2.0 is excellent.
- **Breakeven win rate** at 1:2 R:R = 33.3%. Any win rate above this is positive EV.
- All models use the RTH 07:00–16:00 ET window for both sweep detection and outcome resolution.
