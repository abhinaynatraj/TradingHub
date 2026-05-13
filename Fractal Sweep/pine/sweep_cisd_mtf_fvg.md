# Sweep · CISD · FVG · Key Levels (npg) — Indicator Notes

Source: [sweep_cisd_mtf_fvg.pine](sweep_cisd_mtf_fvg.pine) · TradingView page: https://www.tradingview.com/script/nxEwfrqF-Sweep-CISD-MTF-FVG-Key-Levels/
License: MPL-2.0 · Author: © npg · Pine v6 · Indicator (overlay)

## What it does

Single-script implementation of the **HTF-sweep → return-to-range → CISD → projection** workflow (Fearing / TTFM vocabulary), with MTF FVGs and a full key-levels suite layered on top. It draws synthetic HTF candles in chart's future space and detects sweep + reversal setups on those HTF candles, then resolves the entry trigger on the LTF chart timeframe.

This is the closest off-the-shelf indicator to the model that the [engine/model_stats.py](../engine/model_stats.py) backtester implements, but the **CISD definition differs** (see [Mismatch vs. Fractal Sweep engine](#mismatch-vs-fractal-sweep-engine) below).

## Core mechanics (from source)

### HTF auto-pairing
LTF chart → HTF default ([line 198–214](sweep_cisd_mtf_fvg.pine#L198-L214)):
| Chart TF | HTF |
|---|---|
| 1m  | 15m |
| 3m  | 30m |
| 5m  | 1h  |
| 15m | 4h  |
| 30m / 1h | 1D |
| 4h / 8h | 1W |
| 1D | 1M |

Custom mode lets you override.

### Wick Lick (sweep) detection
For the **last closed HTF candle** (`last_closed`) vs. the prior one (`prev_closed`) ([line 1106 / 1148](sweep_cisd_mtf_fvg.pine#L1106)):

- **Bearish Wick Lick:** `last.high > prev.high AND last.close < prev.high` — and it must NOT also be a full sweep of the prior low closing back inside (excludes ambiguous double-sweeps).
- **Bullish Wick Lick:** `last.low < prev.low AND last.close > prev.low` (mirrored).

The drawn zone is **from the log-midpoint of the sweep candle down to its close** (bearish), not the candle body — the script uses `calculateLogMidpoint` ([line 917](sweep_cisd_mtf_fvg.pine#L917)) which biases the midpoint toward the dominant wick when wicks exceed the body.

Only one Wick Lick can fire per HTF candle (`tspot_created` lockout per `last_htf_candle_bar`).

### Silver filter
Fires when ([line 1124](sweep_cisd_mtf_fvg.pine#L1124)):
- `candleOfDay == 5` (Friday in 4H bucket terms — the script uses `floor(hour/4)+1`), OR
- `candleOfDay == 4` AND `hour ≥ 13 ET` (late Thursday afternoon),
- AND the sweep candle closed beyond **both** prior candles' opposing extremes (aggressive close).

This is a **late-week distribution-window quality filter** — the author's "premium" tag, mapped to weekly profile timing.

### CISD detection ([line 658–723](sweep_cisd_mtf_fvg.pine#L658-L723))
Pure source logic — different from how Fearing teaches CISD verbally:

1. Find the bar holding the swept extreme (`c2_bar` = bar where last_closed's high/low printed).
2. Walk back from c2_bar collecting an **unbroken series of opposing-direction candles** (max 20 bars). For a bearish setup, the series consists of *bullish* candles.
3. Track `series_high` / `series_low` across that series (body or wick depending on `usebody_for_confirmation`).
4. From c2_bar forward, the **first close that breaks beyond the series' opposing extreme** = CISD fire. For bearish: first close > series_high.

Output: a horizontal CISD line from start-of-series to break-bar at the relevant extreme.

### Projections
After CISD fires ([line 704–723](sweep_cisd_mtf_fvg.pine#L704-L723)):
- `series_range = series_high − series_low`
- `proj_price = break_price ± (series_range × multiple)` — multiples are user input, default `0.5, 1.0, 1.5, 2.0`.
- Drawn as horizontal lines extending right; latest set tracks current bar if `extend_latest_projections` is on.

These are NOT 1R/2R off the entry — they are multiples of the **opposing-candle series range** that produced the CISD.

### TTFM labels
On each Wick Lick fire ([line 1136–1140](sweep_cisd_mtf_fvg.pine#L1136-L1140)):
- **C2** label on the sweep candle (the one that took the prior high/low)
- **C3** label on the close-back candle (where price re-entered the range)
- These match the Fearing/TTFM C1–C5 candle-counting taxonomy.

### MTF FVGs ([line 5 / SECTION 5](sweep_cisd_mtf_fvg.pine#L350))
Two independent timeframes (default 5m + 1h), each tracking bullish and bearish FVGs as boxes that auto-delete when traded through (full mitigation, not 50%).

### Key Levels
4H H/L, prior D/W/M, Asia (6pm–2am ET), London (2am–8am ET), HOD/LOD, and three opens (6pm Globex, 8am futures, 9:30am RTH). All session math is `America/New_York`. Daily reset on the 6pm Globex bar via `isAsiaSession() and not isAsiaSession()[1]`.

### HTF Bias (info table) ([line 788–816](sweep_cisd_mtf_fvg.pine#L788-L816))
Compares `last_closed` vs. `prev_closed`:
- Closed beyond prior high → **Bullish**; closed beyond prior low → **Bearish**
- Swept high but closed inside → **Bearish** (rejection)
- Swept low but closed inside → **Bullish**
- Double-sweep: longer wick wins

## Inputs at a glance

| Group | Setting | Default | Notes |
|---|---|---|---|
| HTF Candle | HTF Mode | Auto | Auto-pair table above |
| HTF Candle | Max Display | 4 | History candles drawn |
| HTF Candle | Use Actual Day Change | false | Use when daily HTF detection is glitchy |
| Wick Licks | Bias filter | None | Bullish-only / Bearish-only / both |
| Wick Licks | Use Body for Confirmation | true | Tightens CISD threshold |
| Wick Licks | Show Only Latest | true | Reduces clutter |
| Wick Licks | Show Silver Wick Lick | true | Late-week quality tag |
| CISD | Projection Levels | `0.5,1.0,1.5,2.0` | Multiples of CISD series range |
| MTF FVG | TF1 / TF2 | 5m / 1h | Independent gap tracking |
| Key Levels | (toggles per group) | mostly on | Each group has own color/style |

## On-chart elements

| Element | Meaning |
|---|---|
| HTF candle cluster (right of chart) | Synthetic HTF candles in future space, with countdown to next close |
| Trace lines (dotted) | OHLC of each HTF candle echoed back to its origin bar |
| Wick Lick zone (rectangle) | From log-midpoint of sweep candle to its close, extending across HTF candle's expected duration |
| Midline + close line | The two key prices inside the zone |
| Silver T-Spot label | Late-week premium-quality tag |
| C2 / C3 labels | Sweep candle / close-back candle (TTFM taxonomy) |
| CISD line (solid blue) | Drawn at series extreme from start-of-series to break-bar |
| Projection lines (dotted) | Multiples of CISD series range, with `0.5` / `1.0` / etc. labels |
| FVG boxes | MTF gaps from TF1/TF2, auto-mitigate on trade-through |
| HTF FVG / Volume Imbalance | Within the synthetic HTF cluster |
| Sweep lines (chart) | Prior HTF high/low pierced and closed back inside |
| Key level lines (PDH/PWL/Asia/etc.) | Persistent S/R from sessions and prior periods |
| Info table | Current TF, HTF, countdown, bias |

## How to use it (workflow)

The author's intent is a single-zone-at-a-time HTF setup tracked through to LTF confirmation:

1. **Wait for a Wick Lick zone** to print on the latest HTF candle. Direction filter helps if you have a daily/weekly bias.
2. **Check confluence** — does the zone overlap a Key Level (PDH, Asia high, RTH open)? Stack matters more than the zone alone.
3. **Watch the LTF for CISD** — price interacts with the zone, then a closing break of the opposing series triggers the CISD line and projections.
4. **Use Silver as a quality filter**, not as a separate signal — when Silver fires, weekly distribution context is in your favor.
5. **Targets = projections.** The `1.0` and `2.0` multiples are the natural pause/reversal areas. Place stops above the Wick Lick zone (bearish) or below (bullish).
6. **MTF FVGs as confluence**, not entries. A 1H FVG inside an active Wick Lick zone is a pre-entry magnet.

## Recommended chart pairings

For your 5m / 15m / 1h execution work:
- **5m chart** → Auto-pairs to 1H HTF. Use TF1=5m, TF2=1H for FVGs.
- **15m chart** → Auto-pairs to 4H HTF. Use TF1=15m, TF2=1H or TF2=4H.
- **1H chart** → Auto-pairs to Daily HTF. Use TF1=1H, TF2=4H.

The Auto pairing matches what you'd want for Fearing-style execution.

## Mismatch vs. Fractal Sweep engine

The npg script and [engine/model_stats.py](../engine/model_stats.py) overlap conceptually but **define CISD differently**:

| | Fractal Sweep engine | npg indicator |
|---|---|---|
| Sweep | Prior HTF candle's high or low broken | Prior HTF candle's high or low broken AND closed back inside (full Wick Lick definition) |
| Trigger | Prior LTF bar engulfed (CISD per the engine's definition in `engine/model_stats.py`) | First close that breaks the **opposing-candle series extreme** preceding the sweep candle |
| Anchor window | Sweep + return + CISD must all complete within the same HTF window | Same per-HTF lockout via `tspot_created` / `last_htf_candle_bar` |
| Targets | 1R off entry (`simple_1r`) | Multiples of CISD series range projected from break-price |
| Quality filter | F3 (shallow sweep) + F4 (closed back inside) + SMT (NQ/ES divergence) | Silver (late-week timing) + bias filter |

**Implication:** the npg indicator is a *related but not identical* model. Setups it shows will overlap with engine-detected setups but will not be 1:1. If you want to validate npg setups against the engine's stats, you'd need to either:
- Re-implement npg's CISD definition in the engine and rerun, or
- Treat npg as a **discretionary visual tool** and rely on the engine numbers for sizing/EV decisions.

The Silver filter is interesting — it's a **late-week timing filter** that the engine doesn't currently model. Could be worth adding as `passes_silver` alongside F3/F4/SMT to test for marginal edge.

## Practical fit with your existing stack

- Pair this with [pine/fractal_sweep.pine](fractal_sweep.pine) on the same chart: npg gives you HTF Wick Lick zones + key levels; your indicator gives you the engine-aligned sweep+CISD entries.
- The HTF candle cluster + Key Levels are the most uniquely useful pieces — your existing indicator doesn't render those.
- The Silver concept is the standout idea worth borrowing for the engine.
