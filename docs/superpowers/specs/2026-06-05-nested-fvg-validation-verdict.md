# Nested FVG — Validation Verdict

**Date:** 2026-06-05
**Branch:** `feat/nested-fvg-backtest`
**Verdict:** ❌ **No tradeable edge as specified.** One regime-stable slice is a hypothesis to forward-test, not a validated edge.

## TL;DR

The Nested FVG model (`Kelli/nested-fvg.pine`) was backtested on NQ 1-minute data
(2014–2026) across three nesting scales. An initial run showed a promising "edge
gradient" (5m_30m at +0.087R, PF 1.19). **A correctness audit found that result was
entirely a look-ahead bias artifact.** After fixing the bias, all three pairings are
confidently negative. A four-dimension statistical validation confirms it.

## The look-ahead bias (the headline)

`resample()` stamped each higher-timeframe bar with its **start** timestamp, and
`find_fvgs` used that stamp. So a 5m/15m/30m FVG — which is only confirmed at the
**close** of its 3rd candle — was treated as "known" at that candle's **open**.
Entry (`sig_idx + 1`) then fired up to 1–4 minutes early on the LTF side and up to
14–29 minutes early on the HTF side, using price data that had not yet occurred to
both detect the signal and place the fill.

This also explained the "edge gradient": the **coarser the timeframe, the more future
information leaked**, so 5m_30m looked best precisely because it cheated most.

### The fix
- `find_fvgs` stamps FVGs at confirmation-**close** (`ts_close_ns`) for resampled
  series; native 1m gets a synthesized close-ts.
- Entry = first 1m bar at/after the FVG's close (no double-skip).
- Mitigation and nesting use close-times; HTF host must confirm *strictly before* the signal.
- Data-gap guards: skip stale signals straddling a gap; expiry bounded to a 22h
  horizon so it can't latch a later day's 16:00.
- 34 unit tests pass, including dedicated look-ahead regression tests.

### Impact of the fix

| Pairing | Biased (wrong) | De-biased (correct) |
|---|---|---|
| 1m_5m  | EV −0.065, PF 0.88 | **EV −0.105, PF 0.81** |
| 3m_15m | EV +0.018, PF 1.04 | **EV −0.112, PF 0.80** |
| 5m_30m | EV +0.087, PF 1.19 | **EV −0.099, PF 0.82** |

The entire apparent edge — and the gradient — was leakage.

## Four-dimension validation (on de-biased data)

Engine: `validation/run_validation.py` → `data/validation.json` (Validation tab in dashboard).

1. **Walk-forward (yearly OOS).** No parameters are fit, so every year is OOS by
   construction. 1m_5m is positive in only **1 of 13 years**, with a steady decay
   from −0.37R (2014) toward ~0 (recent). Negative and structural, not noisy.

2. **Day-blocked bootstrap (2000 draws).** 95% CIs on settled EV are **entirely below
   zero** for all three pairings (1m_5m [−0.115, −0.094]; 3m_15m [−0.128, −0.097];
   5m_30m [−0.120, −0.079]). This is *confidently* negative, not noise straddling zero.

3. **Sensitivity.**
   - Outlier leave-one-day-out: removing the best/worst single day does not flip the verdict.
   - **Exit-param sweep is an APPROXIMATION** re-derived from stored MAE/MFE; it ignores
     intrabar order. Its high EV at wide stops (e.g. +0.81R at stop=25) is an **artifact**,
     not a tradeable parameter — flagged in the data and the dashboard.
   - Gap-size sensitivity: EV improves as the minimum LTF gap grows (−0.099 → −0.053 at
     median → ~+0.006 at the 90th percentile), but only on a small, shrinking subsample.

4. **Per-slice scan (Bonferroni).** Of ~36 session×direction×SMT cells, **one** survives
   correction: **ASIA + LONG + no-SMT on 1m_5m**, EV +0.052R, and positive in **9
   consecutive years (2018–2026)** after being negative 2014–2017 (PF 1.06–1.49,
   ~1,200 trades/year).

## On the one surviving slice

This is the only genuinely interesting result, and it must be framed honestly:

- It is **not** multiple-testing noise in the usual sense — 9 straight positive years
  with stable sample sizes is a real regime pattern, plausibly a post-2017 shift in
  NQ overnight (Asia-session) behavior.
- **But** it is one slice discovered by scanning ~36 cells. Bonferroni was applied
  per-pairing, so across all three the family is ~3× larger. This is the textbook
  garden-of-forking-paths setup.

**Status: a hypothesis, not an edge.** The correct next step — if pursued — is to
*lock the rule* (1m_5m, ASIA session, LONG only, no SMT, with the de-biased engine) and
**forward-test it on data not used in this scan** (e.g. paper-trade forward, or hold out
2025–2026 and confirm). It is not deployable on the strength of an in-sample scan.

## Relationship to prior models

The de-biased no-edge result is **consistent with the rest of the repo**: FVG confluence
tested non-additive in Fractal Sweep (redundant with SMT) and Inversion-FVG was dropped
in Amas v1 (19% vs 68% draw-hit). The bare FVG primitive has now underperformed in three
independent studies. The Nested FVG twist (nesting geometry + session + fixed R/R) did not
rescue it in aggregate.

## What's in the repo

- `engine/` — de-biased detection + simulation + orchestrator (34 unit tests + smoke test).
- `validation/run_validation.py` — the four-dimension analysis → `data/validation.json`.
- `dashboard.html` — 6 tabs incl. the **Validation** tab (verdict banner, bootstrap CI,
  walk-forward, slice scan with the honest survivor callout).
- Design spec: `2026-06-01-nested-fvg-backtest-design.md`. Plan: `../plans/2026-06-01-...`.
