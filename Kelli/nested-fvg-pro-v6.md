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

**Caveats:**

1. ~~Win-% counts partials and BE-scratches as wins.~~ **FIXED (2026-06-26).** This
   file now reports honest stats: **"Win %" counts only full-target wins**; partials
   and break-even scratches are shown in their own `Part/BE` column (hourly table) and
   `P` bucket (trade/weekly tables), never as wins. The hourly **"Rating"** is now
   driven by realized P&L, not the (formerly inflated) win-rate, so an hour full of
   break-even scratches is no longer flattered into "** USE **". See the backtest study
   below: the old definition showed ~50% WR; the honest target-hit rate is ~17%.
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

## Backtest study (v6 IS the model)

`Nested FVG/v6_model/v6_model.py` is a faithful port of THIS indicator at its default
settings (Immediate entry, 3-contract scale-out 1/1/1, BE-at-partial, 20/45/20/60,
trading windows, block-while-open, DLL/per-trade limits). Run on ~12y of NQ 1m bars:

| Metric | Value |
|---|---|
| Trades | 16,888 |
| **Win % as v6 tables showed it** (partials + BE as wins) | **50.1%** |
| **Win % honest** (full target reached only) | **16.8%** |
| Real expectancy per trade (MNQ $2/pt) | **−$2.44** |
| Total | **−$41,241** |
| Buckets | 2,765 target-win · 385 partial · 5,082 BE-scratch · 8,188 loss · 468 expired |
| Every trading window | negative (−$0.32 to −$5.10 / trade) |

**Conclusion:** the v6 *management* (BE-at-partial, scale-out, windows) does NOT rescue
the entry. The "50% win rate" was real arithmetic that counted ~5,500 break-even
scratches as wins; only **1 in 6** trades reaches the actual target, and long-run
expectancy is **negative in every window**. Live green weeks are variance on a
negative-EV system, not edge. The honest-stats modification above makes the live tables
report the 17% figure instead of the 50% one. Full result: `v6_model/v6_result.json`;
prior v5 study: `docs/superpowers/specs/2026-06-05-nested-fvg-validation-verdict.md`.
