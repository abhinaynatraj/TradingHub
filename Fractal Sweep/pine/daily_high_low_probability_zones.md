# Daily High/Low Probability Zones (DSP)

Pine v5 indicator — `daily_high_low_probability_zones.pine`

[Source on TradingView](https://www.tradingview.com/script/eLZlBxhi-Daily-High-Low-probability-zones/) · Author: lucymatos · Open-source (MPL 2.0)

## What it does

For the current trading day, projects price levels onto the previous day's range and shades the segments where the day's high and low **historically** form most often. Anchors today's chart with PDH and PDL lines, divides price into 12 equal segments spanning −100% to +200% of the previous day's range, and labels each segment with two empirical probabilities: how often the day's high formed there, and how often the day's low formed there.

Two highlight bands (gold and orange by default) mark the single highest-probability segment for the day's high and the day's low. A right-side table shows the full distribution.

## How to read it

- **PDH / PDL** — yesterday's high and low, drawn as anchor lines for today's session.
- **Inside band (0–100%)** — the previous day's range. Most days print high/low inside this band.
- **Above band (100–200%)** — extension above PDH. Days that broke yesterday's high.
- **Below band (−100–0%)** — extension below PDL. Days that broke yesterday's low.
- **Per-segment label** — `H:N%` is the historical share of days whose high formed in this segment; `L:N%` is the share whose low formed there. The segment with the highest H share is tagged `★H`; highest L share gets `★L`.
- **Gold fill** — top "high formation" segment (where most daily highs land).
- **Orange fill** — top "low formation" segment.
- **Table** — full segment breakdown plus an `OOB` row for days whose high or low landed outside the −100% to +200% window, plus an `n=` row showing the actual sample count after filtering.

## Methodology

Daily H/L are pulled with `request.security(syminfo.tickerid, "1D", ..., lookahead=barmerge.lookahead_off)`. For each day `i` in the lookback window:

1. Take the **prior** day's high and low (day `i+1` from today's perspective). Skip if `priorRange = priorHigh − priorLow ≤ 0`.
2. Compute today's high and low as a percent of that prior range, anchored at PDL = 0%, PDH = 100%:
   - `hPct = (dayHigh − priorLow) / priorRange × 100`
   - `lPct = (dayLow  − priorLow) / priorRange × 100`
3. Bin each into one of 12 equal-width 25%-wide segments spanning `[−100, 200)`. Values outside that window land in `OOB`.
4. Increment that segment's high-count and low-count.

After the loop, segment shares are `count / n × 100` (rounded), where `n` is the count of valid days (those with positive prior range).

The single highest-count segment for highs becomes the gold band; same for lows (orange). If they coincide, only the gold band is drawn.

### Why the −100 to +200 range

A day that opens in the middle of the prior range can run up to ~+100% (PDH) or down to −0% (PDL) without breaking either side. Most expansion days clear PDH or PDL by some fraction of the prior range, so anchoring labels at ±100% beyond the range captures that behavior; ±200% / −100% catches outlier runaway days.

### Bin boundaries

`getSegIdx(pct)` uses half-open intervals `[lo, hi)` for segments 0 through 10, and a closed interval `[lo, hi]` for the final 175–200% segment. So a value of exactly 100% bins into segment 8 (100–125%), not segment 7 (75–100%).

### Minimum sample

Drawing is gated on `n ≥ 5`. With the default lookback of 250 days, `n` is usually close to 250 (every weekday with positive prior range counts). The 5-day floor mostly just guards new symbols / early-history charts.

## Inputs

| Group | Input | Default | Notes |
|---|---|---|---|
| Core | Lookback (days) | 250 | Range 10–500 |
| Visual | PDH/PDL line colour | `#2962FF` | |
| Visual | Inside range colour | `#26A69A` (teal) | Bins 4–7 (0–100%) |
| Visual | Extension above colour | `#5C6BC0` (indigo) | Bins 8–11 (100–200%) |
| Visual | Extension below colour | `#EF5350` (red) | Bins 0–3 (−100–0%) |
| Visual | Label text colour | `#787B86` | |
| Visual | Segment line style | Dashed | Solid / Dotted / Dashed |
| Visual | PDH/PDL line style | Solid | Solid / Dotted / Dashed |
| Visual | Top High% band fill | Gold | Highlights `★H` segment |
| Visual | Top Low% band fill | Orange | Highlights `★L` segment |
| Table | Show probability table | true | |
| Table | Table position | Top Right | 5 positions |
| Table | Table text size | Small | Auto / Tiny / Small / Normal / Large / Huge |

## Implementation notes

- **All rendering on `bar_index == last_bar_index`.** Lines, labels, fills, and the table are emitted only on the final bar — no historical drawings, and no per-bar accumulation. Switching timeframes or replaying with bar replay redraws once the chart settles on the last bar.
- **`xloc.bar_time` for line/label anchoring.** Today's window spans `todayStart = dTimes[0]` to `todayStart + 86_400_000` ms. This means lines and labels project across the calendar day even on intraday timeframes.
- **No alerts.** Pure visualization; the indicator emits no `alert()` calls.
- **Segments 0% and 100% are skipped in the boundary-line loop.** Those edges are already drawn as PDL and PDH respectively, so a separate dashed line at the same level would just thicken those.
- **Top-segment ties broken by index.** If two segments have the same count, the lower-indexed one wins (`>` comparison, not `≥`). For ties between highs and lows on the same segment, the gold band wins — the orange band only draws when `topLowSeg ≠ topHighSeg`.
- **`dHighs`, `dLows`, `dTimes` are arrays returned in one `request.security` call** via the `get_daily()` helper that pushes `lookback + 1` bars of history. Index 0 is today, 1 is yesterday, etc.
- **OOB bucket** captures days where high or low landed outside the −100% to +200% window. Reported as a single percentage in the table — direction (above +200% vs below −100%) is tracked internally but not exposed in the UI.

## Suitability

- **Best fit**: instruments with a regular daily session and meaningful prior-day reference levels (futures with a clear ETH/RTH open, FX majors, large-cap equities).
- **Less useful**: 24/7 instruments where the daily candle is arbitrary (some crypto), or charts where the daily timeframe is unreliable (low-volume tickers, micro-caps).
- **Static, not adaptive**: the segment percentages reflect the trailing 250 (default) days. The indicator does not weight recent days more heavily, doesn't decompose by day of week, and doesn't condition on the prior day's classification (inside/outside, expansion, etc.). For more granular conditioning, a separate downstream study is needed.

## Possible extensions (not implemented)

- Day-of-week stratification — Monday distributions often differ from Thursday/Friday.
- Inside-day vs expansion-day stratification — segment behavior likely diverges depending on whether the prior day broke the day-before's range.
- Confidence intervals — Wilson CI bounds would show whether the gap between top and second-best segment is statistically meaningful at the current sample size.
- Time-of-day labels — most highs and lows form during specific session windows; an additional dimension (hour of high formation) would tell you not just *where* but *when*.
