# NPG Engine — Spec Notes

## Source of truth
- Pine: `../Fractal Sweep/pine/sweep_cisd_mtf_fvg.pine`
- Author: © npg, MPL-2.0
- Indicator analysis: `../Fractal Sweep/pine/sweep_cisd_mtf_fvg.md`

## Engine ↔ indicator alignment

| Aspect | Indicator | Engine |
|---|---|---|
| Wick Lick | `last.h > prev.h AND last.c < prev.h` (bearish), with double-sweep exclusion | Same. `wick_lick.detect_wick_licks` |
| CISD series | Walk back from c2 collecting opposing candles, max 20 bars | Same. `cisd_npg.find_cisd_npg`, max_series=20 |
| CISD body confirmation | `usebody_for_confirmation` toggle (default True) | Same. `body_confirm` arg, default True |
| CISD anchor lockout | One per HTF via `tspot_created` | One per HTF via `seen_anchors` set in orchestrator |
| Projections | `0.5, 1.0, 1.5, 2.0` × series_range from break_price | Same. `MULTIPLIERS` constant; break_price = series_low (SHORT) / series_high (LONG) per Pine line 707 |
| Silver | `candleOfDay==5 OR (==4 AND hour≥13)` + aggressive close | Same. `filters.is_silver` |
| Same-bar TP/SL tie | (not in indicator — visual) | SL wins (matches Fractal Sweep convention) |

## Phase 1 limitations
- No key-level confluence filter (PDH/PDL/Asia/etc.) — phase 2
- No MTF FVG flags — phase 2
- No HTML dashboard — phase 2
- Raw `_trades` array is included in JSON (large file). Phase 2 will split.

## Notes from Phase 1 implementation

- CISD direction was initially inverted in the engine plan; corrected in commit `5fd6ab9` (Task 12.5). For SHORT setups, CISD fires when close < series_low (bears break the bullish opposing-candle series); for LONG, close > series_high. Matches Pine source lines 681–696 with the caller convention from lines 1135 (bearish WL → is_bullish=false) and 1177 (bullish WL → is_bullish=true).
- break_price for projections also needed to be the structural CISD level, not entry (matches Pine line 707).
