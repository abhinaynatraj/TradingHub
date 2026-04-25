# Fractal Sweep — Statistically Validated Sweep-CISD Setup

Fractal Sweep detects a specific, **repeatable** higher-timeframe liquidity event: prior candle's high or low gets swept → price returns inside the range → a CISD (Change in State of Delivery) confirmation fires in the opposing direction. Entry is the next bar's open. Exit is 1R at the sweep extreme.

This isn't a discretionary tool. The logic mirrors an engine that has been backtested on **15 years of 1-minute NQ data (~15,000 resolved trades)** and published to a live dashboard. Every setup you see on the chart is the same setup the engine records.

---

## How a Setup Forms

**Phase 1 — Sweep:** Price trades beyond the prior HTF candle's high (short-sided) or low (long-sided) within the current period.

**Phase 2 — Return:** Price re-enters the prior candle's range.

**Phase 3 — CISD:** The engine scans backward from the return bar for the consecutive opposing delivery run (bearish run for longs, bullish run for shorts). The CISD level is the open of the earliest candle in that run. When the current bar's close crosses through the CISD level, the setup fires.

**Entry:** Next bar's open (no in-bar fills, no limit orders).

---

## Timeframe Combinations

The indicator auto-detects your chart TF and applies the correct sweep/CISD pair:

| Chart TF | Sweep TF | CISD TF | Validated |
|---|---|---|---|
| 5M | 1H | 5M | ✓ |
| 3M | 30M | 3M | ✓ |

Both combos map directly to the backtested engine variants. Other chart timeframes are inactive — the indicator does not draw signals.

---

## What You'll See on the Chart

- **Sweep level** (amber dashed) — the prior HTF high/low that got swept
- **CISD level** (blue solid) — the trigger price
- **Entry line** (white/slate) — next bar's open
- **Risk zone** (red shaded) — SL at the sweep extreme or the CISD level (configurable)
- **Reward zone** (cyan shaded) — 1R target by default, user-tunable
- **50% midpoint lines** (slate dashed) — "Move to BE" and "Take Partial" management markers
- **T-Spot zone** (violet, optional) — the logarithmic midpoint of the sweep candle with ProTrend / Normal / Expansive classification
- **C2 / C3 labels** (optional) — structural reference points
- **CISD projections** (optional) — 0.5R / 1.0R / 1.5R / 2.0R multiples of the CISD series range
- **SMT label** — green "SMT" / grey "NO SMT" showing whether ES swept its corresponding level

---

## SMT Divergence (NQ × ES)

When trading NQ, the indicator fetches ES at the same sweep TF and checks whether ES reached its corresponding high/low when NQ did. If NQ swept but ES did **not**, the setup is tagged "SMT" — interpreted as smart-money divergence. The backtest engine shows this tag carries a materially higher win rate (1H/5M model: ~90% WR with SMT vs ~84% baseline).

You can point SMT at any correlated symbol via the `ES Symbol` input (`ES1!` by default).

---

## Over-Risk Detection

If the structural SL distance exceeds your configured max risk (default 112.5 pts for MNQ @ $225 / $2 per point), the setup is drawn in orange with an **OVER RISK** label instead of firing normally. This matches the backtest's max-risk gate so you don't take trades the engine rejects.

---

## Configurable Colors

Every drawn element has its own color input under the **Colors** group — ten in total. Defaults are chosen to avoid collision with standard green/red candles:

- Sweep = amber · CISD = blue · SL = red · TP = cyan · T-Spot = violet
- Midpoint = slate · Over-risk = orange · Projection = slate · Debug = navy

Works cleanly on dark, light, or themed charts. Customise to taste.

---

## Inputs Summary

**Filters** — min/max risk in points, CISD lookback bars, SL anchor (Sweep Extreme or CISD Level)
**SMT Divergence** — on/off toggle, symbol override
**R:R Box** — bar width, R:R target (default 1.0 matches the backtest's `simple_1r` profile)
**Sweep / CISD Line** — line style, label text, label position
**T-Spot Zone** — optional overlay with C2/C3 labels, type classification, projection levels
**R:R Labels** — position, colors
**Display** — debug toggle, max setups to keep on chart (1–20), 50% midpoint lines toggle
**Colors** — full 10-element palette

---

## Alerts

Fires on bar close with a structured message including direction, symbol, entry instructions, SL level, TF combo, and SMT status. Ready for webhook forwarding to autotrading platforms.

Example: `LONG NQ1! | Enter @ next open | SL 24012.25 | 1H/5M | SMT`

---

## Intended Use

- **Live confirmation** of backtest-validated setups — if it doesn't appear here, the backtest doesn't count it
- **Journaling** — keep N past setups visible (`Max Setups`) with full annotations
- **Chart education** — the T-Spot zone, C2/C3 labels, and projection levels make the structural logic visible

This is a filter, not a crystal ball. Use it to identify high-quality setups the engine has already priced — then decide for yourself whether the current market conditions warrant trading them.

---

*Built alongside the [Statistic.ally backtest dashboards](https://github.com/abhinaynatraj/Statistic.ally) — 15 years of NQ data, MAE/MFE excursion studies, SL/TP variant analysis, regime comparison. Every parameter you see here is grounded in that dataset.*
