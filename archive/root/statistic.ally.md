# Statistic.ally — Change Log

---

## NY1 F.P.FVG — Split-Exit Model + PhD-Level Studies
**Date:** 2026-03-28

### Model Changes

#### Exit Rules (ny1_backtest.py)
- **Replaced open-run (no TP) model** with a split-exit model:
  - **50% of position** exits at **TP1 = 0.10%** (10 bps) in the trade's favour
  - **50% runner** moves stop to **breakeven (entry)** once TP1 is hit, then runs to structural stop or 16:00 ET EOD
  - If TP1 is never reached, full position exits at the structural stop (−1R)
- Exit types: `TP1+EOD` (TP1 hit, runner to close) · `TP1+STOP` (TP1 hit, runner to BE) · `STOPPED` (full loss)
- Trades that hit TP1 are marked **WIN**; full stops are marked **LOSS**

#### Constants
```python
TP1_PCT     = 0.001    # 0.10% (10 bps)
TP1_SIZE    = 0.50     # 50% exits at TP1
RUNNER_SIZE = 0.50     # 50% runner at BE
```

#### Results (nq_1m, all history)
| Metric | Value |
|---|---|
| Filled trades | 2,717 |
| TP1 hit rate | 56.0% |
| Avg win (USD) | $127.54 |
| Avg loss (USD) | −$224.37 |

---

### PhD-Level MFE Study

**Backtest** computes `risk_stats.mfe_dist`:
- Moments: mean (0.3798%), median (0.1574%), mode (0.0758%), std (0.5882%), skewness (5.45), kurtosis (68.34)
- Full percentile table p5–p99
- Log-normal fit: μ=−1.7091, σ=1.2126, goodness r=0.9825
- 3-tier natural clusters at p33/p75: Small / Moderate / Large
- **Breakeven trigger analysis**: for 12 reach-rate levels, computes P(positive exit | MFE ≥ X), trades rescued, ΔEV
- **Protect the Queen level**: highest reach_rate trigger where P(positive exit) ≥ 70% (fallback 50%) — prioritizes practical reach over extreme confidence
- Histogram (60 bins, 0→p99) for canvas rendering

**Dashboard** (`renderMFEDistribution`):
1. Stat tiles + frequency histogram + log-normal fit card
2. 3-tier cluster cards
3. Full percentile table + BE trigger analysis table side-by-side
4. Protect the Queen recommendation box (♛)

---

### PhD-Level MAE Study

**Backtest** computes `risk_stats.mae_dist`:
- Moments: mean (0.1698%), median (0.1427%), mode (0.1310%), std (0.1311%), skewness (10.34), kurtosis (258.6)
- Full percentile table p5–p99
- Log-normal fit: μ=−1.9504, σ=0.5907, goodness r=0.9615
- 3-tier natural clusters at p33/p75: Tight / Moderate / Wide
- **SL sweep analysis**: for 12 MAE levels, computes P(false stop — would recover to TP1) and P(genuine loss)
- Key finding: P(false stop) never drops below ~32% at any tested level → structural stop is the natural boundary
- Histogram (60 bins, 0→p99) for canvas rendering

**Dashboard** (`renderMAEAnalysis`):
1. Stat tiles + frequency histogram + log-normal fit card
2. 3-tier cluster cards
3. Full percentile table + SL sweep analysis table side-by-side
4. Stop Loss Insight box (🛡) — confirms tightening SL cuts legitimate winners

---

### Dashboard Updates (index.html)

- **Hero tiles**: "TP1 Rate" (green ≥55%) replaces "EOD Rate"; "Target" shows "TP1 0.10%"
- **Exit rules card**: updated to describe split-exit model
- **Trades table**: WIN (green) / LOSS (red) badges based on TP1 hit
- **Equity curve**: uses `tp1_count` for P&L calculation
- **Section pills**: MFE and MAE sections updated to reflect PhD-level analysis
- **Tab navigation**: single long-scroll page replaced with 5-tab layout (Overview · Performance · MFE Study · MAE Study · Trades); tabs in sticky nav, canvas re-renders on tab switch
- **Trades table TP1 column**: TP1 target price shown for every trade; STOPPED trades include a MFE progress bar toward the 0.10% target

---

## Hub Page — Text Fixes
**Date:** 2026-03-28

- "First Presented FVG" → **"First Presented Fair Value Gap"** (title + subtitle)
- "TP1 (POTQ)" → **"TP1 (PTQ)"** (typo fix)

---

## PTQ / opt_sl Recommendation Logic Fix
**Date:** 2026-04-03

- **PTQ (MFE)**: Changed from "first trigger where p_pos ≥ 0.50" to "highest reach_rate where p_pos ≥ 0.70" (fallback 0.50). JS client-side had a critical iteration-order bug that picked the lowest reach rate instead of highest.
- **opt_sl (MAE)**: Changed from `p_ko × exceed_pct` scoring to "first threshold where p_ko ≥ 0.70" (fallback 0.50). Old metric was meaningless for winner/loser segments (p_ko=0 for winners, p_ko=1 for losers).
- Fixed in both `model_stats.py` (backtest) and `model_dashboard.html` (client-side recent trades).
- Position split updated **80/20 → 50/50** to match current split-exit model
- Subtitle updated: "Fixed % Stop" → **"Structural Stop"**

---

## Data — candle_science.duckdb Updated
**Date:** 2026-03-28

- Fetched differential bars from Databento (GLBX.MDP3, `ohlcv-1m`)
- Inserted **6,900 new rows** each for `nq_1m` and `es_1m`
- Database now current to **2026-03-27 16:59 ET** (was 2026-03-20)
