# Abhi's Fractal Sweep — Pine v5 Indicator

**File:** `fractal_sweep_cisd.pine`
**Version:** v5 | **Last updated:** 2026-03-31

---

## What It Does

Detects fractal sweep + CISD trade setups on NQ/ES futures across 4 auto-detected timeframe combinations. Draws sweep lines, CISD confirmations, R:R boxes, T-Spot zones, and CISD projections when all conditions are met.

---

## Supported Chart Timeframes (auto-detected)

| Chart TF | Sweep TF | CISD TF | Q1 Window (bars) |
|----------|----------|---------|-------------------|
| 1H       | 1D       | 1H      | 14                |
| 15M      | 4H       | 15M     | 4                 |
| 5M       | 1H       | 5M      | 3                 |
| 3M       | 30M      | 3M      | 3                 |

Any other chart TF shows a watermark: "Use 1H / 15M / 5M / 3M chart".

---

## Setup Phases

### Phase 1 — Sweep (Q1 only)
- Price breaks beyond the prior higher-TF candle's high or low within Q1
- Sweep must be between `sweep_min` (0.10%) and `sweep_max` (1.50%) of the prior candle's range
- Sweep line drawn at `anc_hi`/`anc_lo`, anchored to the bar that formed the prior TF high/low
- `sweep_ext` = swing extreme (lowest low for long, highest high for short) — tracked continuously from sweep until fire

### Phase 2 — Return to Range (Q1 only)
- Price must close back inside the prior candle's range within Q1
- `ret_bar` stored for CISD backward scan anchor

### Phase 3 — CISD (can fire after Q1)
- **Backward scan** from the return bar to find the opposing delivery run (consecutive same-polarity candles before the return)
- **CISD level** = open of the FIRST (earliest) candle in that run
- **Fire** when current close crosses through the CISD level
- Dojis (close == open) are skipped, do not break the run
- If sweep + return both completed within Q1, state stays alive for CISD to fire after Q1 (matches backtest behavior)

### Q1 Expiry Rules
- If sweep didn't happen by Q1 end → state reset, no setup
- If sweep happened but return didn't → state reset, drawings deleted
- If sweep + return both completed → state kept alive, CISD can fire after Q1
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
- `Sweep Min %` — minimum sweep penetration (default: 0.10%)
- `Sweep Max %` — maximum sweep penetration (default: 1.50%)
- `Min Risk (pts)` — minimum entry-to-SL distance (default: 3.0)
- `CISD Lookback Bars` — max bars to scan for opposing run (default: 8)
- `RTH Only` — restrict to 07:00–16:00 ET (default: true)

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
| Swing extreme tracking | Q1 bars only (`q1_h[swept_mask].max()`) | Continuous from sweep until fire |
| CISD scan origin | Return bar (backward) | Return bar (backward) — **matched** |
| CISD fire window | 8 CISD-TF bars from return | After Q1 if sweep+return completed — **matched** |
| Entry | Next CISD-TF candle open | Current bar close |

---

## Changelog

- **2026-03-31** — CISD rewritten to scan backward from return bar (match backtest `_find_cisd`)
- **2026-03-31** — Q1 state kept alive if sweep+return both completed (CISD can fire after Q1)
- **2026-03-31** — Added T-Spot zone (log midpoint), C2/C3 labels, T-Spot type classification
- **2026-03-31** — Added CISD series projections (configurable multiples)
- **2026-03-31** — Sweep line anchored to bar that formed prior TF high/low
- **2026-03-31** — SL tracks swing extreme continuously from sweep until fire
- **2026-03-31** — CISD line anchored to the opposing run's candle
- **2026-03-31** — Sweep line redrawn at fire time (survives Q1 cleanup)
- **2026-03-31** — Initial version with auto TF detection, 4 combos, configurable visuals
