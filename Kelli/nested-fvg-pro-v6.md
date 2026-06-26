# Nested FVG Pro (v6) — Indicator Reference

**File:** `nested-fvg-pro-v6.pine`
**Pine version:** v6
**Run on:** 1-minute chart (NQ/MNQ futures)
**Source:** Kelli's TradingView indicator (provided 2026-06-26)
**Predecessor:** `nested-fvg.pine` (v5) — same core signal, far simpler exits/reporting

## What it does

Marks and "paper-trades" a nested Fair Value Gap setup: a **1-minute FVG that forms
inside a same-direction 5-minute FVG**, during a Chicago-time session, then manages a
multi-contract position with partial / target / extended-target scale-outs and renders
trade-tracker, hourly-performance, and weekly-summary tables.

It is an **indicator** (not a `strategy`) — all P&L is computed in arrays from
intrabar high/low touches, not from TradingView's broker emulator. It fires `alert()`
JSON payloads suitable for webhook execution (e.g. 3-contract entries, 1-contract
partial/target exits).

## Core signal (unchanged from v5)

- **5-min FVG** built from a manual 3-candle rolling aggregation of 1-min bars
  (`h5_c0/c1/c2`), added on each new 5-min bar within session. Bullish (BISI):
  `l5_c0 > h5_c2`; bearish (SIBI): `h5_c0 < l5_c2`. Min size `fvg5_min_bp` (0.15 bp).
- **1-min FVG**: bullish `low > high[2]`; bearish `high < low[2]`. Min size `fvg1_min_bp`.
- **Nesting**: the 1-min gap must sit within a same-direction 5-min gap ± `proximity_bp`
  (5 bp). First match wins.
- **Mitigation**: a 5-min gap is deleted once price *closes* through its far edge.
- **Cooldown**: 30 bars per direction between signals.
- **Session purge**: at each session open all gaps/state are cleared.

## New in v6 (the substantive changes)

| Area | v5 | v6 |
|---|---|---|
| Position | 1 unit, single exit | **Multi-contract** (`pos_qty`=3): 1 at partial, 1 at target, 1 runner to extended |
| Partial | Booked +pts but **kept full size** (double-count) | **Real scale-out** — closes `qty_part`, books only that leg |
| Stop after partial | n/a | **Break-even** move (`pos_be_at_partial`) |
| Entry | Immediate only | `fvg1_entry`: Immediate / Near Edge / Middle / Far Edge (pullback = **pending limit**, with `invalidate_partial`) |
| Concurrency | Implicit | **Block new trades until open trade closes** (hardcoded) |
| Risk gates | none | Per-trade max-loss ($150 emergency exit), daily-loss-limit ($400), stop-trading-after-hour |
| Time filter | session only | **Trading windows (CT)**: 7–9 PM, 1–2 AM, 6–11 AM, 12–2 PM |
| Default stop/partial | 15 / 15 | **20 / 20** (target still 45, ext 60) |
| Reporting | one table | trade tracker + **hourly "Rating" table** + **weekly summary** + Best Day |
| Outcome states | Win/Loss/Partial | adds `⏳ Win` / `⏳ Partial` (partial-filled, runner still open) |

## Accounting honesty assessment

The v6 **points/dollar P&L is materially more trustworthy than v5.** The old
"partial books points but position stays full size" double-count is **fixed** — each
leg (partial, target, runner, stop) closes a specific contract count and books only
that contract's P&L. The dollar figures on the weekly/trade tables are real.

**Caveats that remain (read before trusting win-rate or "Rating"):**

1. **Win-% still counts partials and BE-scratches as wins.** In the hourly table,
   `hw = hr_wins + hr_partial`, and a runner stopped at break-even after a partial is
   logged as `🔵 Partial` → counted toward "wins." So a 70–100% "Win %" mostly means
   "price moved ~20 pts in favor at some point," not "trade reached full target."
   The **points P&L is the honest column; the Win % is optimistic.**
2. **The hourly "Rating" (⭐ USE / X Cut) is in-sample curve-fitting.** It rates each
   hour on that chart's own realized P&L, so it will always flatter whatever the recent
   sample did. Not a forward-looking edge.
3. **No look-ahead in the live logic.** Signals fire on `barstate.isconfirmed`
   (closed bar); Immediate entries fill at that close and resolve on later bars;
   pullback entries use pending limit fills. (The look-ahead bias found earlier was in
   *our backtest resampler*, since fixed — not in this Pine.)
4. **Indicator P&L assumes perfect intrabar fills** at the exact stop/target/partial
   price with no slippage, no commission, and that both stop and target within one
   bar resolve favorably in the order the code checks (stop-before-target on the
   un-partialed leg, which is conservative).

## Relationship to the backtest study

The repo's `Nested FVG/` backtest validated the **v5** model (1m-in-5m, fixed 15/45,
50% scale-out) and found **no aggregate edge** (all pairings ≈ −0.10R, 95% bootstrap
CIs below zero); one slice (ASIA + LONG) was a forward-test hypothesis only. v6 changes
the **management** (BE at partial, multi-contract, windows, 20/45) but **not the entry
signal**, so the entry's lack of edge is unchanged. Whether v6's *management* turns the
same entries profitable is an open question — that's what the next backtest pass should
measure. See `docs/superpowers/specs/2026-06-05-nested-fvg-validation-verdict.md`.
