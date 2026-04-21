# Strategy Insights — 2026-04-21

Analysis of the Fractal Sweep model on the freshly-corrected backtest
(commit `4098487` — F3/F4 applied, same-bar tie = LOSS, 24h coverage).
All figures are `simple_1r` profile (SL = sweep extreme, TP = 1R),
unfiltered baseline unless stated.

## TL;DR

1. **Hour-of-day matters a lot.** The NY RTH block (08:00–16:00 ET)
   delivers 74–81% WR; the overnight 00:00–06:00 block delivers only
   60–68%. Cutting 00:00–06:00 would drop N by ~30% but lift the
   overall EV noticeably.
2. **SMT is a strong filter across every model.** ~+0.30R EV lift on
   average, but at the cost of ~90% of the trade count. Works best as
   a "quality stamp" you consult rather than as a standalone gate.
3. **F3 (Shallow Sweep) + F4 (Closed Back Inside) together give the
   single biggest baseline lift.** 1H_5M goes from 71.8% / +0.44R →
   86.9% / +0.74R on N=816. Pine now defaults these OFF (to match the
   dashboard's historical baseline), but turning them on is a
   data-supported upgrade for live trading.

---

## 1. Hour-of-Day Heatmap (1H_5M · simple_1r · all filters off)

Full table, 24h coverage, sorted by ET hour:

| Hour (ET) | N    | WR     | EV        |
|-----------|------|--------|-----------|
| 00:00     | 50   | 52.0%  | +0.040R   |
| 01:00     | 100  | 60.0%  | +0.200R   |
| 02:00     | 184  | 64.7%  | +0.293R   |
| 03:00     | 280  | 68.6%  | +0.372R   |
| 04:00     | 193  | 67.9%  | +0.357R   |
| 05:00     | 190  | 62.6%  | +0.253R   |
| 06:00     | 205  | 62.0%  | +0.239R   |
| 07:00     | 284  | 64.8%  | +0.296R   |
| **08:00** | 430  | **77.7%** | **+0.554R** |
| **09:00** | 706  | 74.5%  | +0.490R   |
| **10:00** | 330  | **80.6%** | **+0.612R** |
| 11:00     | 204  | 75.5%  | +0.509R   |
| 12:00     | 165  | 78.8%  | +0.576R   |
| **13:00** | 133  | **81.2%** | **+0.624R** |
| 14:00     | 122  | 75.4%  | +0.508R   |
| 15:00     | 158  | 75.3%  | +0.506R   |
| 16:00     | 34   | 79.4%  | +0.588R   |
| 18:00     | 52   | 69.2%  | +0.385R   |
| **19:00** | 37   | 81.1%  | +0.622R   |
| 20:00     | 78   | 76.9%  | +0.538R   |
| 21:00     | 97   | 66.0%  | +0.320R   |
| 22:00     | 75   | 65.3%  | +0.307R   |
| 23:00     | 65   | 64.6%  | +0.292R   |

### Observations

- **Everything in NY RTH (08:00–16:00) clears 75% WR / +0.50R EV.** This
  is where the strategy works best. Largest samples are 08:00 (N=430),
  09:00 (N=706), 10:00 (N=330) — statistically meaningful.
- **00:00–02:00 ET is a graveyard.** 50–184 trades per hour at 52–65%
  WR. 00:00 specifically is barely break-even.
- **Early Asia (02:00–04:00)** is actually decent — 64–69% WR, +0.30R.
  Not as good as RTH but not worthless.
- **London session (03:00–06:00)** is mixed. 03:00 and 04:00 are solid
  (~68% WR), but 05:00 and 06:00 drop back to 62%.
- **13:00 ET is the sweet spot** — 81% WR, +0.62R — likely catching the
  lunch-reversal move that completes by the afternoon session.
- **19:00–20:00 (post-close into Asian pre-open)** is surprisingly
  strong but on low N (~40–80 per hour).
- **21:00 short direction is the worst bucket** — 38.7% WR / −0.23R on
  31 trades. Avoid shorting at that hour.

### Practical filter proposal

A simple hour-of-day filter `hr ∈ [08, 16] ∪ [19, 20]` keeps the best
buckets and drops ~30% of N for a meaningful EV lift. Worth a dashboard
toggle eventually.

---

## 2. SMT Edge Study (all 4 models · simple_1r · no other filters)

SMT = NQ swept its prior HTF extreme but ES did not.

| Model      | without SMT             | with SMT              | Δ WR     | Δ EV     |
|------------|-------------------------|-----------------------|----------|----------|
| 4H_15M     | 306 · 75.5% · +0.51R   | 34 · 91.2% · +0.82R  | +15.7pp  | +0.31R   |
| **1H_5M**  | 3835 · 70.5% · +0.41R  | 337 · 86.7% · +0.73R | +16.2pp  | +0.32R   |
| 1H_3M      | 4173 · 67.7% · +0.35R  | 381 · 81.6% · +0.63R | +13.9pp  | +0.28R   |
| 30M_3M     | 12391 · 66.8% · +0.34R | 940 · 82.3% · +0.65R | +15.5pp  | +0.31R   |

**SMT is consistent:** ~+14–16pp WR / ~+0.30R EV across every model. It
eliminates roughly 90% of the trade count, which is expected — SMT
divergence is rare by design.

### SMT paired with other filters (1H_5M, top 15 by Δ EV)

Shows what SMT adds on top of each base filter combo:

| Base combo                             | without SMT         | with SMT          | Δ EV   |
|----------------------------------------|---------------------|-------------------|--------|
| F4+HOUR_ALIGNED+PRIOR_COUNTER+ENGULF   | N=74 · 68% · +0.35R | N=5 · 100% · +1R  | +0.65R |
| HOUR_ALIGNED+PRIOR_COUNTER+ENGULF      | N=114 · 68% · +0.37R | N=8 · 100% · +1R | +0.63R |
| F4+HOUR_ALIGNED+ENGULF                 | N=142 · 65% · +0.30R | N=12 · 92% · +0.83R | +0.54R |
| HOUR_ALIGNED+ENGULF                    | N=228 · 69% · +0.39R | N=21 · 95% · +0.90R | +0.52R |
| F4+HOUR_ALIGNED+PRIOR_COUNTER          | N=547 · 70% · +0.39R | N=37 · 95% · +0.89R | +0.50R |
| PRIOR_COUNTER+ENGULF                   | N=233 · 70% · +0.39R | N=14 · 93% · +0.86R | +0.47R |
| F4+PRIOR_COUNTER                       | N=1157 · 71% · +0.42R | N=94 · 94% · +0.87R | +0.45R |
| ENGULF only                            | N=489 · 72% · +0.45R | N=39 · 95% · +0.90R | +0.45R |
| F4+ENGULF                              | N=292 · 70% · +0.41R | N=23 · 91% · +0.83R | +0.41R |

**SMT stacks on top of any other filter — no redundancy.** The top 3
combos with SMT hit 100% WR but on tiny samples (N=5, 8). The more
trustworthy combos are ones where SMT still leaves N≥20.

### Practical conclusion

For live trading:
- **Use SMT as a "conviction" gauge, not a gate.** If SMT fires, treat
  the setup as higher-confidence. If it doesn't, the setup still has
  positive EV (70% WR baseline) — just take it normally.
- If you *must* pick a subset: **SMT + F3 + F4** gives N=~100 / 91%+ WR
  across the 11-year window (~9 setups/year — thin but profitable).

---

## 3. Dropping the F3+F4 Default-OFF Decision

We set Pine and dashboard baselines to F3/F4 = OFF to match each other
during the audit. The data now supports reconsidering:

- **F3+F4 alone on 1H_5M:** 86.9% WR / +0.74R / N=816. This is a clean
  live-tradeable sample.
- **Baseline unfiltered on 1H_5M:** 71.8% WR / +0.44R / N=4172.

The cost of F3+F4 is 80% fewer setups. The benefit is ~+15pp WR and
~+0.30R EV per trade. On raw expectancy, F3+F4 baseline generates
`816 × 0.74 = 604R` vs unfiltered's `4172 × 0.44 = 1836R` — **so
unfiltered wins on total expected R**, but F3+F4 wins on quality per
trade.

### What that means for live decision-making

- If you're **bandwidth-constrained** (can only watch a few setups
  per day): **turn F3+F4 ON**. Higher quality trades at the cost of
  frequency.
- If you're **automated** (like the AMP bridge coming online): **leave
  F3+F4 OFF**. The bot doesn't care about cognitive load; more trades
  at lower per-trade WR still wins total-R.
- If you're **risk-constrained** (daily $500 cap on a $5k account):
  **turn F3+F4 ON**. You can only afford 2 full losers per day; 87% WR
  is safer than 72% WR for staying above the cap.

### Recommendation for the AMP automation

Since you're running 1 MNQ with a hard $500 daily cap on a $5k account,
the **safer move is F3+F4 ON** — fewer setups, higher WR, lower
probability of hitting the cap. The bridge's risk gate already stops
you at 10 trades/day, so fewer setups is fine.

---

## 4. Followups Worth Exploring

1. **Hour-of-day × SMT interaction.** Does SMT during 13:00 ET outperform
   both filters separately? Needs per-trade rows dumped; not yet
   computable from current JSON.
2. **Day-of-week behavior.** Already in `by_dow` — worth a similar
   pass.
3. **Session-open re-entry.** The 08:00 and 19:00 lift hints at
   setups that form within 30m of a session open. A `minutes_since_open`
   grouping might reveal a sharper edge.
4. **Session-tier filter.** Simple `hr ∈ [08, 16] ∪ [19, 20]` gate —
   dashboard could ship this as a one-click "RTH + late US" toggle.

## Source

Data: `model_stats.json` regenerated 2026-04-21 (commit `4098487`).
Engine: `engine/model_stats.py` post-F3/F4-apply + tie-rule fixes.
Inputs: 4,172 trades (1H_5M simple_1r unfiltered), 11+ years coverage,
24h Globex data.
