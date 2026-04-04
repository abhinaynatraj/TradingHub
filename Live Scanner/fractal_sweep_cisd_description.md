# Abhi's Fractal Sweep — Pine v5 Indicator

**File:** `fractal_sweep_cisd.pine`
**Version:** v5 | **Last updated:** 2026-04-04

---

## What It Does

Detects fractal sweep + CISD trade setups on NQ/ES futures across 4 auto-detected timeframe combinations. Draws sweep lines, CISD confirmations, R:R boxes, T-Spot zones, and CISD projections when all conditions are met.

---

## Supported Chart Timeframes (auto-detected)

| Chart TF | Sweep TF | CISD TF | Q1 Window (bars) |
|----------|----------|---------|-------------------|
| 1H       | 1D       | 1H      | 6                 |
| 15M      | 4H       | 15M     | 4                 |
| 5M       | 1H       | 5M      | 3                 |
| 3M       | 30M/1H   | 3M      | 5                 |

Any other chart TF shows a watermark: "Use 1H / 15M / 5M / 3M chart".

---

## Setup Phases

### Phase 1 — Sweep
- Price breaks beyond the prior higher-TF candle's high or low
- Sweep detected throughout the HTF period; tagged Q1 (red) vs non-Q1 (orange)
- Sweep must be ≤ `sweep_max` (50%) of the prior candle's range
- Prior candle range must be ≥ `min_range` (12 pts default)
- `sweep_ext` = swing extreme (lowest low for long, highest high for short) — locked at detection time

### Phase 2 — Return to Range
- Price must close back inside the prior candle's range
- Can happen anytime after sweep within the HTF period (no window deadline)
- `ret_bar` stored for CISD backward scan anchor

### Phase 3 — CISD
- **Backward scan** from the return bar to find the opposing delivery run (consecutive same-polarity candles before the return)
- **CISD level** = open of the FIRST (earliest) candle in that run
- **Fire** when current close crosses through the CISD level
- Dojis (close == open) are skipped, do not break the run
- No bar limit on CISD formation — can fire anytime after return within the HTF period
- Lookback default: 100 bars (effectively unlimited)

### Validity Filters
- Risk (entry to SL) must be ≥ `min_risk` (3 pts) and ≤ `max_risk` (112.5 pts)
- New anchor period always resets everything

---

## Visual Elements (drawn on fire)

| Element | Description | Anchor |
|---------|-------------|--------|
| **Sweep line** (red) | Prior TF high/low level | Bar that formed the prior TF high/low → r_end |
| **SL line** (red) | Swing extreme (wick tip) | Sweep extreme bar → r_end |
| **CISD line** (blue) | Opposing run's open level | CISD candle bar → r_end |
| **Entry line** (white) | Close at fire time | Fire bar → r_end |
| **R:R box** | Risk (red fill) + reward (teal fill) | Fire bar → r_end |
| **TP/Entry/SL labels** | Price + pts info | Right or left of box |

### T-Spot Zone (TTFM concepts)
| Element | Description |
|---------|-------------|
| **T-Spot box** | Log midpoint to close of sweep candle (conviction zone) |
| **Midline** (dotted) | Log midpoint level through the zone |
| **C2 label** | At the swept level (prior TF high/low) |
| **C3 label** | At the CISD confirmation level |
| **T-Spot type** | ProTrend (<0.30), Normal (0.30–0.80), Expansive (>0.80) — based on sweep_pct |

### CISD Projections
- Measures the CISD opposing run's range (series high - series low)
- Projects configurable multiples from the break point (default: 0.5, 1.0, 1.5, 2.0)
- Dotted gray lines with level labels

### CISD Preview (while waiting)
- Dashed line at the current expected CISD level during Q1
- Updates each bar as the opposing run evolves
- Deleted when CISD fires or Q1 expires

---

## Input Groups

### Filters (G2)
- `Sweep Max %` — maximum sweep penetration (default: 50%)
- `Min Risk (pts)` — minimum entry-to-SL distance (default: 3.0)
- `Max Risk (pts)` — maximum entry-to-SL distance (default: 112.5, MNQ $225 ÷ $2/pt)
- `Min Prior Range (pts)` — reject tiny prior candles (default: 12.0)
- `CISD Lookback Bars` — max bars to scan for opposing run (default: 100, effectively unlimited)

### R:R Box (G3)
- `Box Width (bars)` — how far right the box extends (default: 20)
- `R:R Target` — reward multiple (default: 1.0)
- Fill/border colors for risk and reward zones
- Entry line color

### Sweep Line (G4)
- Line style (Dotted/Dashed/Solid)
- Label text (default: "Sweep of", TF appended automatically)
- Label position (Left/Right)

### CISD Line (G5)
- Line style, label text, label position

### T-Spot Zone (G7)
- Show/hide T-Spot zone, C2/C3 labels, T-Spot type, CISD projections
- Zone transparency
- Projection levels (comma-separated)
- Projection color

### R:R Labels (G6)
- Label position (Left/Right)
- TP/SL/Entry label colors

---

## Security Calls

All 4 higher-TF periods pre-declared with literal strings (Pine v5 requirement):
- `"1D"` — high[1], low[1], time
- `"240"` — high[1], low[1], time
- `"60"` — high[1], low[1], time
- `"30"` — high[1], low[1], time

Correct values selected via ternary on `timeframe.period`. Uses `lookahead=barmerge.lookahead_on` for prior candle data.

---

## Alerts

Fires `alert.freq_once_per_bar_close` with format:
```
LONG NQ | Entry 24025.25 | SL 23974.50 | TP 24076.00 | Risk 50.8 pts | 1H/5M
```

---

## Key Differences from Backtest (model_stats.py)

| Aspect | Backtest | Pine |
|--------|----------|------|
| Sweep extreme tracking | Locked at Q1 detection | Locked at detection — **matched** |
| CISD bar limit | None (unlimited) | 100 bars (effectively unlimited) — **matched** |
| CISD scan origin | Return bar (backward) | Return bar (backward) — **matched** |
| Min range filter | Per-model (8-30 pts) | Single input (12 pts default) |
| Max risk filter | 112.5 pts | 112.5 pts — **matched** |
| Non-Q1 sweeps | Not detected | Detected (orange color) — indicator is more permissive |
| Entry | Next CISD-TF candle open | Current bar close |
| Split exit / runner | 90/10 split with BE stop | Single exit (all-in/all-out) |

---

## Changelog

- **2026-04-04** — Removed CISD bar limit (was 8→32 bars, now 100 = unlimited)
- **2026-04-04** — Removed ret_window deadline — CISD can form anytime after sweep within HTF period
- **2026-04-04** — Added max_risk input (112.5 pts MNQ default) to validity gate
- **2026-04-04** — Added min_range input (12 pts default) — rejects tiny prior candle ranges
- **2026-04-04** — Fixed 3M Q1 window: 3→5 bars (15 min, matches 1H_3M backtest)
- **2026-04-04** — Sweep extreme locked at detection time (no continuous deepening)
- **2026-03-31** — CISD rewritten to scan backward from return bar (match backtest `_find_cisd`)
- **2026-03-31** — Q1 state kept alive if sweep+return both completed (CISD can fire after Q1)
- **2026-03-31** — Added T-Spot zone (log midpoint), C2/C3 labels, T-Spot type classification
- **2026-03-31** — Added CISD series projections (configurable multiples)
- **2026-03-31** — Sweep line anchored to bar that formed prior TF high/low
- **2026-03-31** — Initial version with auto TF detection, 4 combos, configurable visuals
