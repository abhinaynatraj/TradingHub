# Supporting FVG Confluence — Design

**Date:** 2026-04-26
**Project:** Fractal Sweep
**Status:** Design (engine-only first; dashboard exposure deferred)

---

## Motivation

Fractal Sweep currently sits at ~50–55% WR baseline on `simple_1r`, with the
strongest known edge coming from the SMT (NQ-ES Divergence) filter (+7.8% WR,
+0.150R EV). We want to test whether requiring a **supporting LTF FVG behind
entry** adds edge — the intuition being that a sweep which prints a clean
displacement-driven FVG on the way back into range gives the CISD a piece of
structure to lean on, while a sweep with no such gap is "thinner."

Original sketch: *"H1 low sweep into 15 / 5 min BISI + CISD."*

This is a hypothesis, not a known edge. The point of this spec is to compute
the flags cheaply, look at the numbers, and then decide what to expose.

## Non-goals

- No dashboard chip wiring in this iteration. Engine + JSON output only.
- No Pine indicator changes.
- No removal or modification of F3, F4, or SMT.
- No continuous distance-to-FVG feature (`dist_to_fvg_top` etc.). Binary flags
  only. We can layer continuous features on later if there's edge to refine.
- No cross-anchor FVGs. The "everything happens within one anchor HTF window"
  invariant aligned in 2026-04-24 is preserved.

## Definitions

### Supporting FVG (geometry C from brainstorm)

A **supporting FVG** for a trade is an unfilled same-side LTF FVG that the
trade can fall back into before stop. We compute two geometric tightness
levels per timeframe:

- **Strict** — FVG body fully between the sweep extreme (SL level) and the
  entry price. Trade literally has a gap to fall into before stop.
- **Loose** — FVG top below entry (for longs; mirror for shorts), anywhere in
  the anchor HTF window. Includes strict as a subset.

For a LONG trade (sweep of prior HTF low):

- Bullish FVG at LTF index `i`: `low[i] > high[i-2]`
- Strict requires: `sweep_extreme ≤ high[i-2]` AND `low[i] ≤ entry_price`
  (entire body inside the SL→entry band)
- Loose requires: `low[i] ≤ entry_price` (top of gap below entry)

SHORT trade is the mirror: bearish FVG `high[i] < low[i-2]`, geometry inverted.

### "Unfilled at entry"

An FVG is unfilled at entry if **no candle between FVG formation (bar `i`) and
entry has wicked into the gap.** For a bullish FVG with body `[high[i-2], low[i]]`:
unfilled iff for all bars `j` in `(i, entry_idx)`, `low[j] > high[i-2]` (no
LTF wick has dipped into the upper edge of the gap). Mirror for bearish.

We track this once per FVG by scanning forward from formation and breaking on
first fill. Trades that occur after fill see the FVG as filled.

### Two timeframes scanned

- **CISD-TF FVGs** — 5M for `1H_5M`, 3M for `30M_3M`. Already resampled in
  the engine.
- **1M FVGs** — raw 1-minute bars from `m1_arrs`. Already loaded.

Both scans are restricted to the **current anchor HTF window** (sweep_anchor
window), consistent with the rest of the engine.

## Trade Row Fields (added)

Four new boolean fields per trade row:

| Field | TF | Geometry |
|---|---|---|
| `passes_fvg_cisd_strict` | CISD-TF | Body fully between sweep extreme and entry |
| `passes_fvg_cisd_loose`  | CISD-TF | Top below entry |
| `passes_fvg_1m_strict`   | 1M | Body fully between sweep extreme and entry |
| `passes_fvg_1m_loose`    | 1M | Top below entry |

Invariant: `strict ⇒ loose` per TF. Asserted in tests and at engine boundary.

The CISD-TF and 1M flags are independent — a trade can have a 1M FVG without
a CISD-TF FVG and vice versa.

## Aggregation Output

A new `fvg_summary` block in `build_model_stats` output (one per model ×
profile, alongside `smt_summary`). Structured the same way `smt_summary` is —
each leaf runs through the existing `agg()` and produces
`{n, wins, wr, ev, pf, avg_risk_pts, avg_rr, avg_mae, avg_mfe, avg_mae_hr, avg_mfe_hr}`:

```
fvg_summary: {
  cisd_strict, cisd_loose, no_cisd_fvg,
  m1_strict,   m1_loose,   no_m1_fvg,
  any_strict,  any_loose,                          # OR across both TFs
  cisd_strict_smt, m1_strict_smt, any_strict_smt   # confluence with SMT
}
```

`any_strict` = `passes_fvg_cisd_strict OR passes_fvg_1m_strict`. Same for
loose. `any_strict_smt` is `any_strict AND smt`. The SMT-confluence keys exist
because SMT is the strongest existing filter; the marginal edge of FVG over
SMT-alone is the real test.

## Implementation Surface

All changes confined to `engine/model_stats.py` and `tests/`.

### `engine/model_stats.py`

1. New helper near `find_cisd`:
   ```python
   def find_supporting_fvgs(
       arrs,                       # tuple of (opens, highs, lows, closes, ts_ns)
       window_start_idx, window_end_idx,
       sweep_extreme, entry_price, direction,
       entry_idx,                  # index in this TF at/before which entry occurred
   ) -> tuple[bool, bool]:         # (strict, loose)
   ```
   Scans `[window_start_idx, entry_idx)` for 3-bar FVGs of correct polarity,
   verifies unfilled-at-entry, returns the two booleans. Vectorisable over the
   small windows involved; correctness over speed for v1.

2. Inside `detect_setups_base`, for each setup that reaches the entry phase,
   call `find_supporting_fvgs` twice — once on `c_arrs` (CISD-TF) and once on
   `m1_arrs` (1M) — and write the four resulting flags onto the row.

3. Inside `build_model_stats`, after `smt_summary` is built, build
   `fvg_summary` using the same helpers (`agg`, group masks).

4. JSON output adds `fvg_summary` per model × profile.

### `tests/`

Unit tests for `find_supporting_fvgs` covering:

- Bullish FVG strictly between SL and entry → strict True, loose True
- Bullish FVG below entry but extending below SL → strict False, loose True
- Bullish FVG above entry → strict False, loose False
- Bullish FVG that gets wicked into before entry → strict False, loose False
- Wrong-side (bearish FVG on a long trade) → both False
- No 3-bar gap in window → both False
- Mirror cases for SHORT trades

Engine-boundary invariant test: for the full backtest output,
`passes_fvg_*_strict ⇒ passes_fvg_*_loose` element-wise per TF.

Existing tests continue to pass unchanged — adding flags doesn't move
`outcome`, `r`, or any of the existing aggregates.

## Decision Criterion (after first run)

Promote a flag to a dashboard chip in a follow-up iteration if **either**:

1. **Standalone edge** — WR delta ≥ +3% over the ~50% baseline AND N ≥ 500
   over 12y on at least one model, OR
2. **Stacks with SMT** — `*_smt` block shows ≥ +1% WR over `smt`-alone with
   N ≥ 200 over 12y on at least one model.

Lower bars than F3 (which sat at +3.4%) are not interesting in isolation.

If neither geometry nor TF clears the bar on either model, we leave the flags
in the trade rows for future reference (they're cheap) but skip the dashboard
work.

## Risks & Open Questions

- **Sparsity, especially on `30M_3M` strict.** Strict requires the gap to fit
  inside the SL→entry band, which is bounded by `MIN_RISK_PTS = 3.0`. On 3M
  CISD-TF this may be very rare. Loose is the fallback if strict has N < 200.
- **Sample bias from the unfilled requirement.** A sweep that retraces deeply
  before CISD will have wicked through any nearby FVG, killing the flag. This
  is by design (the gap really does need to be there at entry) but it means
  FVG presence is correlated with momentum sweeps, not deep retracements.
  Worth keeping in mind when reading numbers.
- **Correlation with SMT.** A clean SMT divergence often comes from
  displacement, which often produces an FVG. The marginal edge over SMT-alone
  (`*_smt` blocks) is the real test, not the standalone number.
- **1M noise floor.** 1M FVGs are common, including from low-volume one-tick
  imbalances. Loose 1M may be near-100% prevalence and provide no
  discrimination. We expect strict 1M to be the more interesting cell.

## File-by-file Change Summary

| File | Change |
|---|---|
| `engine/model_stats.py` | Add `find_supporting_fvgs` helper; call twice in `detect_setups_base`; add four flag fields to trade rows; add `fvg_summary` block to `build_model_stats`. |
| `tests/test_<new>.py` | Unit tests for `find_supporting_fvgs` plus the strict-implies-loose invariant. |
| `model_stats.json` | Auto-regenerated; gains `fvg_summary` block per model × profile. |
| `engine/CLAUDE.md`, `PIPELINE.md`, `.claude/rules/fractal-sweep.md` | Document the four new fields and `fvg_summary` after the engine run lands and we know whether to expose them. |

No changes to:

- `model_dashboard.html` (deferred)
- `pine/` (deferred)
- `daily_update.py` (no schema migration; flags appear automatically on next
  full engine run)
- `engine/sltp_analyzer.py`, `master_backtester.py`, `recalc.py` (no
  consumption of the new fields yet)

## Out of Scope (explicit)

- Dashboard chip wiring
- Pine indicator FVG drawing
- Continuous `dist_to_fvg_top` / `fvg_size_r` features
- Cross-anchor FVGs
- Combining FVG with F3/F4 in the SMT-confluence aggregates (we only test
  against SMT-alone; F3/F4 confluence is a follow-up if FVG clears the
  decision criterion)
