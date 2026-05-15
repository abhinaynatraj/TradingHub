# NPG Engine — Phase 1 Findings

Run date: 2026-05-02
Data: NQ 1m + ES 1m. DB: `../Fractal Sweep/candle_science.duckdb` (~4.04M NQ bars, ~4.08M ES bars).
Engine: `engine/npg_stats.py` v1.0
Branch: `npg-engine-phase1`

## Executive summary

Across all three HTF/LTF pairings, the NPG model produces a strong baseline edge: 85.9% / 88.6% / 90.7% reach-1.0× rates on `1H_5M`, `4H_15M`, and `D_1H` respectively, with composite EV of +0.182R / +0.225R / +0.311R and PF of 2.25 / 2.89 / 6.72. Edge increases monotonically as you move up the HTF — fewer setups, but each one is cleaner and reaches further. The Silver late-week timing filter is the standout: on 1H_5M it lifts EV from +0.182R → +0.347R (and to +0.359R when combined with SMT) at a cost of ~97% of trade volume. Silver-tagged setups are rare (508 of 15,148 on 1H_5M, ~3.4%) but consistently exceptional across all three pairings.

Compared to the existing Fractal Sweep engine (~50% WR / +0.182R EV / N=1,711 over 12y on 1H_5M with F3+F4+SMT), NPG fires roughly 9× more frequently on the same TF (15,148 vs 1,711) at a much higher reach-1.0× rate (85.9% vs 50% — though the metrics aren't apples-to-apples; see "Comparison" below). The composite EV per trade matches exactly at +0.182R, but NPG's higher firing rate translates to substantially higher annual R if executed mechanically.

## Headline numbers

| Pairing | Profile | N | WR | EV | PF |
|---|---|---|---|---|---|
| 1H_5M | series_multi | 15,148 | 85.9% | +0.182R | 2.25 |
| 1H_5M | raw_measure | 15,148 | 96.5% | 0.000R | 0.00 |
| 4H_15M | series_multi | 4,077 | 88.6% | +0.225R | 2.89 |
| 4H_15M | raw_measure | 4,077 | 95.0% | 0.000R | 0.00 |
| D_1H | series_multi | 668 | 90.7% | +0.311R | 6.72 |
| D_1H | raw_measure | 668 | 91.8% | 0.000R | 0.00 |

WR semantics: for `series_multi`, "WR" = % of trades that reached at least 1.0× projection before SL hit. For `raw_measure`, WR = % reach-1.0× (no SL enforcement; PF/EV are 0 by design — see Profile semantics).

## Reach rates

### series_multi (with SL = sweep extreme)

| Pairing | 0.5× | 1.0× | 1.5× | 2.0× |
|---|---|---|---|---|
| 1H_5M | 94.7% | 85.9% | 77.3% | 70.2% |
| 4H_15M | 95.3% | 88.6% | 80.9% | 73.5% |
| D_1H | 96.7% | 90.7% | 82.9% | 76.3% |

### raw_measure (no SL — pure MAE/MFE walk)

| Pairing | 0.5× | 1.0× | 1.5× | 2.0× |
|---|---|---|---|---|
| 1H_5M | 99.0% | 96.5% | 93.6% | 90.3% |
| 4H_15M | 98.2% | 95.0% | 90.8% | 86.1% |
| D_1H | 97.3% | 91.8% | 84.0% | 77.7% |

The raw_measure rates show the natural reach distribution without SL clipping. Differences from series_multi rates indicate how often setups hit a target *and* would have survived an SL stop. The gap is largest on 1H_5M (≈4.3pp at 1.0×, ≈20.1pp at 2.0×) — meaning on intraday TF a meaningful share of setups reach the target only after first wicking through the sweep extreme. On D_1H the gap collapses (≈1.1pp at 1.0×, ≈1.4pp at 2.0×), so daily setups that reach a target almost always do so without first stopping out.

Reach rates are monotonically non-increasing across thresholds for every pairing in both profiles — sanity check passes.

Average MAE/MFE (points, raw_measure):

| Pairing | avg_mae | avg_mfe |
|---|---|---|
| 1H_5M | 107.3 | 122.1 |
| 4H_15M | 84.9 | 116.5 |
| D_1H | 35.8 | 103.6 |

D_1H has dramatically lower MAE per trade — daily setups give back far less before resolving.

## Filter combinations

### 1H_5M / series_multi (sorted by EV)

| Combo | N | WR | EV |
|---|---|---|---|
| silver+smt | 274 | 96.4% | +0.359R |
| silver | 508 | 96.5% | +0.347R |
| smt | 7,870 | 86.3% | +0.185R |
| NONE | 15,148 | 85.9% | +0.182R |

### 4H_15M / series_multi

| Combo | N | WR | EV |
|---|---|---|---|
| silver+smt | 11 | 100.0% | +0.432R |
| silver | 41 | 100.0% | +0.408R |
| NONE | 4,077 | 88.6% | +0.225R |
| smt | 795 | 88.7% | +0.221R |

### D_1H / series_multi

| Combo | N | WR | EV |
|---|---|---|---|
| silver | 61 | 96.7% | +0.422R |
| silver+smt | 7 | 100.0% | +0.400R |
| NONE | 668 | 90.7% | +0.311R |
| smt | 102 | 88.2% | +0.261R |

Caveat: `silver+smt` on 4H_15M (N=11) and D_1H (N=7) are too small to be statistically meaningful — they're shown for completeness but should not drive decisions. The Silver-only and baseline rows are the load-bearing reads on those higher TFs.

## Direction breakdown (1H_5M/series_multi)

| Direction | N | WR | EV |
|---|---|---|---|
| LONG | 7,441 | 86.5% | +0.195R |
| SHORT | 7,707 | 85.4% | +0.170R |

LONG outperforms SHORT by ~+0.025R EV at near-equal volume — small but consistent direction bias, likely a long-term equity drift artifact.

## Session breakdown (1H_5M/series_multi)

| Session | N | WR | EV |
|---|---|---|---|
| ASIA | 4,671 | 85.0% | +0.170R |
| LONDON | 4,126 | 86.1% | +0.184R |
| NY | 6,018 | 87.0% | +0.197R |
| OTHER | 333 | 79.3% | +0.067R |

NY > LONDON > ASIA in both WR and EV, with `OTHER` (off-session) substantially worse — a candidate for an outright session filter in Phase 2.

## Profile semantics

- **`series_multi`** (primary): 4 partial exits at 0.5×/1.0×/1.5×/2.0× of opposing-series range from break_price. SL = sweep extreme (1× base risk). Same-bar TP/SL ties: SL wins. Composite R per trade = sum over hit levels of (0.25 × R_at_level) − (remaining_legs × 0.25 × 1R if SL hit).
- **`raw_measure`** (measurement only): no SL enforcement, walks the full session window (up to 1440 1m bars). Records MAE/MFE and per-projection reach. By design, `composite_r=0` for every trade → `agg.ev` and `agg.pf` are 0/0 in the JSON. Use `reach_rates` and `avg_mae`/`avg_mfe` for analysis, NOT EV/PF.

## Comparison vs. Fractal Sweep engine

The two engines are not directly comparable on WR — Fractal Sweep WR = % winners hitting a single 1R TP, while NPG `series_multi` "WR" = % of trades reaching the 1.0× series-range projection before SL (and the trade can keep running after for additional partials at 1.5× / 2.0×). Reaching 1.0× in NPG is a less-strict bar than winning a fixed 1R trade in Fractal Sweep, which explains the much higher headline WR (85.9% vs ~50%). Composite EV is the metric to compare across engines.

On 1H_5M, NPG baseline EV (+0.182R) matches the Fractal Sweep best-combo F3+F4+SMT EV (+0.182R) exactly. But the trade volumes are very different: NPG fires 15,148 trades over the same 12y period (~1,260/yr) vs. Fractal Sweep's 1,711 (~143/yr) — a ~9× ratio. Two reasons: (1) NPG's CISD definition is broader (opposing-candle series vs. single-bar engulf), and (2) NPG carries no setup-quality filters (F3/F4) at baseline. Both engines use identical risk gates (`MIN_RISK_PTS=3.0` / `MAX_RISK_PTS=112.5`) and the same SMT logic.

SMT carries far less marginal edge in NPG than in Fractal Sweep. In Fractal Sweep, SMT is the strongest single filter (+7.8% WR, +0.150R EV). In NPG/1H_5M, SMT alone moves EV +0.182R → +0.185R and WR +85.9% → +86.3% — barely above noise. This is plausibly because NPG's series-range projections are already calibrated to the move's natural extension (so divergence vs. ES adds little once you've already conditioned on a strong CISD break), whereas Fractal Sweep's flat 1R target is much more sensitive to whether the move has follow-through. SMT may be largely redundant with the Wick Lick + CISD signal in this engine.

Silver, by contrast, is highly load-bearing here. It has no Fractal Sweep analog and is responsible for the majority of the filter-stack edge in NPG. Worth back-porting to Fractal Sweep as a Phase 2 experiment.

## Phase 1 takeaways

- **Silver is the killer feature.** On 1H_5M it lifts EV from +0.182R → +0.347R (almost 2× the per-trade edge) at the cost of ~96.6% of trade volume. Effect is consistent across all three pairings (always the top-EV combo by Silver-only or Silver+SMT). N gets thin on higher TFs (41 silver on 4H_15M, 61 on D_1H), but the directional read is unambiguous.
- **EV scales monotonically with HTF.** 1H_5M → 4H_15M → D_1H goes +0.182R → +0.225R → +0.311R, with PF 2.25 → 2.89 → 6.72. Higher TFs trade less but each trade is much cleaner — D_1H avg MAE is only 35.8pts vs 107.3pts on 1H_5M.
- **Reach rates degrade gracefully.** Even at 2.0× projection, 1H_5M still hits 70.2% in series_multi (and 90.3% if you remove the SL constraint). Whatever target multiple you pick, the distribution supports it.
- **SMT is near-noise in NPG.** Unlike Fractal Sweep where SMT is the single biggest filter, here it adds ~+0.003R EV / +0.4pp WR on 1H_5M. The series-range projection appears to already encode most of what SMT was capturing in the flat-1R-target world.
- **NY session > LONDON > ASIA, and `OTHER` is meaningfully worse** (+0.197R / +0.184R / +0.170R / +0.067R EV). A simple `session != OTHER` filter would clean ~2% of low-quality trades for free.
- **LONG has a small but consistent edge over SHORT** on 1H_5M (+0.195R vs +0.170R). Worth tracking but not actionable on its own.

## Phase 2 candidates

- Key-level confluence filter (Wick Lick zone overlapping PDH/PDL/Asia/RTH open) — biggest potential edge addition; probably the best place to spend the next research week.
- MTF FVG confluence flags
- HTML dashboard mirroring `model_dashboard.html` — make filter combinations interactive; especially valuable given how strong Silver-only is.
- Cross-model comparison: which NPG setups also pass Fractal Sweep's CISD definition? (overlap analysis)
- Silver back-port to Fractal Sweep engine (test as new filter alongside F3/F4/SMT) — Silver has no FS analog and shows large edge here; obvious thing to try.
- Walk-forward / regime analysis on NPG setups (do the +0.31R EV on D_1H and the Silver edge persist year-over-year, or is it concentrated in a few regimes?)
- Session filter (`session != OTHER`, or RTH-only) to drop low-liquidity overnight noise.
- Investigate why SMT is near-noise here vs. strongest-single-filter in Fractal Sweep — is series_multi already absorbing the divergence signal?

## Silver back-port to Fractal Sweep — Phase 2 result

Silver was ported into the Fractal Sweep engine in Phase 2 (commit on `npg-dashboard-phase2` branch). The Phase 1 finding generalised — and then some.

**Marginal edge alongside the F3+F4+SMT baseline (1H_5M, ~12y NQ):**

| Combo | N | WR | EV | PF |
|---|---|---|---|---|
| F3+F4+SMT (baseline) | 1,715 | 59.0% | +0.180R | 1.44 |
| F3+F4+SMT+Silver | 59 | 76.3% | +0.525R | 3.21 |

ΔWR: **+17.26pp** · ΔEV: **+0.345R**

Verdict: **PASSES** the +1%WR / +0.05R-EV gate by a wide margin.

Silver dominates every filter combination on the Fractal Sweep engine — the top 8 EV combos out of 16 all include Silver. Even Silver alone (286 trades, +0.622R EV, PF 4.30) crushes the previous best F3+F4+SMT combo (+0.180R EV, PF 1.44). The catch: trade volume drops dramatically (286 → 59 with the full F3+F4+SMT+Silver stack — roughly 5/year). Silver is a quality filter, not a sole strategy, but it's a remarkably strong one.

Two implications:
1. **Silver's edge is real and not specific to NPG's CISD definition.** It works on FS's single-bar engulf CISD too, which means the "late-week + aggressive close" gate is capturing something about market microstructure (likely weekly-cycle distribution timing) that's orthogonal to the CISD spec.
2. **Silver belongs in the Fractal Sweep dashboard's chip set** alongside F3/F4/SMT. Done in Task 14.

Top-EV combos (1H_5M, simple_1r profile):

| Rank | Combo | N | WR | EV | PF |
|---|---|---|---|---|---|
| 1 | F3 + Silver | 233 | 82.0% | +0.639R | 4.55 |
| 2 | Silver | 286 | 81.1% | +0.622R | 4.30 |
| 3 | F3+F4+Silver | 161 | 80.1% | +0.602R | 4.03 |
| 4 | F4+Silver | 190 | 79.5% | +0.589R | 3.87 |
| 5 | F3+SMT+Silver | 73 | 78.1% | +0.562R | 3.56 |
| 6 | F3+F4+SMT+Silver | 59 | 76.3% | +0.525R | 3.21 |
| 7 | SMT+Silver | 78 | 75.6% | +0.513R | 3.10 |
| 8 | F4+SMT+Silver | 62 | 74.2% | +0.484R | 2.88 |
| 9 | F3+F4+SMT (no Silver) | 1,715 | 59.0% | +0.180R | 1.44 |
