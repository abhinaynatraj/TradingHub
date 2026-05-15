# Amas + Fearing Filter Candidates — Design

**Date:** 2026-05-11
**Project:** Fractal Sweep
**Status:** Design (Phase 1 = chips; Phase 2 = engine-only diagnostic survey)

---

## Motivation

Fractal Sweep currently exposes three runtime filters (F3 Shallow Sweep, F4 Closed Back Inside, SMT NQ-ES Divergence). SMT is the dominant edge (+7.8% WR), F3 is moderate (+3.4% WR), F4 is noise alone. A deep study of two mentorship corpora — **Amas + Bootcamp** (7 PDFs, 8 call transcripts) and **Fearing** (15 lesson transcripts) — surfaced two filter candidates that target the model's two weakest spots:

- **":42 rule" (Amas)** — the prior HTF candle's swept extreme must form *late* in the candle (last ~30%). Distinguishes "distribution" candles whose extremes are unprotected from "pullback" candles whose extremes are protected.
- **CISD PD location (Fearing)** — the CISD bar's close must sit in the *premium half* (shorts) or *discount half* (longs) of the prior HTF range. Refines F4's binary in-range check with a continuous price-location score.

These are orthogonal to existing filters, mechanically computable from data we already have, and each is the central concept of its source.

The remaining candidates (8 more) are added as **diagnostic-only flags** for engine-side measurement, matching the precedent set by the FVG confluence study (`2026-04-26-supporting-fvg-confluence-design.md`).

## Non-goals

- No removal or modification of F3, F4, SMT, or any existing field.
- No Pine indicator changes in this iteration.
- No new filter promoted to a chip beyond the two named above.
- No new continuous-feature exposure on the dashboard for Phase-2 diagnostics — they live in JSON summaries only.
- No FX, bond, news-calendar, or volume-profile data sources (we don't have them).

## Phase 1 — Two new dashboard chips

Two new boolean flags become row fields and join F3/F4/SMT in `compute_filter_variants()` and the dashboard chip bar.

### Flag 1: `passes_p42` — Late-Extreme rule (Amas)

**Rule.** For each trade, the swept extreme of the prior HTF candle must have been printed in the **last 30% of that candle's window** (by minute).

- Long trade (sweep of prior HTF low): find the minute, within the prior HTF candle's time window, at which the low was printed.
- Short trade (sweep of prior HTF high): same for the high.
- For 1H pair: pass iff `extreme_minute_offset >= 42` (i.e., printed at XX:42 or later within an XX:00–YY:00 candle).
- For 30M pair: pass iff `extreme_minute_offset >= 21` (same 70% fractional position within a 30-minute candle).

**Computation.** During the existing prior-candle scan, the engine already loads 1-minute bars covering the HTF window. Add one extra step: locate the index of the prior-candle extreme on the 1-minute axis, derive its minute-of-bar offset, and compare to the per-TF threshold.

Source: Amas Mentorship 1 §49:13 ("the magic number… the deal breaker"); Mentorship 3 ("low/high created after or at 42"); Mentorship 4, 6, 7. Repeated across every PDF/transcript.

### Flag 2: `passes_pd_cisd` — CISD Premium/Discount location (Fearing)

**Rule.** The CISD bar's close must sit in the half of the prior HTF range that aligns with trade direction.

Let `r = (cisd_close - prior_low) / (prior_high - prior_low)`.

- Long (sweep of prior low): pass iff `r <= 0.50` (discount half).
- Short (sweep of prior high): pass iff `r >= 0.50` (premium half).

**Computation.** `cisd_close` and prior-HTF `high`/`low` are already on the trade row. Add one arithmetic line.

Source: Fearing transcript 11 ("premium CISD lecture") — the entire ~7,000-word lecture is about this concept. Quote: *"basic premium and discount of price entering on discount of your expansion leg will usually involve stop loss being hit at some point in time before take profit gets mitigated."*

### Continuous companions (row fields, not chips)

Both chips are derived from continuous scores. We store the score on each row so the dashboard can later test stricter thresholds without re-running the engine:

- `prior_extreme_minute_pct` — fractional position of the swept extreme within the prior HTF candle (0.0–1.0).
- `cisd_pd_pct` — CISD bar close as fraction of prior range (0.0–1.0).

The chips threshold at 0.70 and 0.50 respectively. The dashboard could later add a slider that re-derives `passes_p42` / `passes_pd_cisd` at any threshold from the continuous fields.

### Filter combination explosion

Existing `compute_filter_variants()` enumerates 2³ = 8 combinations of (F3, F4, SMT). Adding two chips brings this to 2⁵ = 32 combinations per model × profile. Still trivial.

### Dashboard wiring

The chip bar in `model_dashboard.html` adds two chips after SMT, in the same visual style:

| Chip | Title attribute | Default |
|---|---|---|
| Late Extreme (:42) | "Swept extreme formed in last 30% of prior HTF candle" | OFF |
| CISD in PD | "CISD bar closed in premium (shorts) / discount (longs) of prior range" | OFF |

`smt_summary` already shows WR/EV/PF split by SMT on/off. Add `p42_summary` and `pd_cisd_summary` to the JSON output in the same shape so the dashboard can render single-filter stats on the chip bar without recomputation.

## Phase 2 — Diagnostic-only flags (engine measurement, no chips)

Eight additional flags are added to each trade row and exposed via per-flag summaries (`candidate_filter_summary` block in JSON). They follow the same pattern as `passes_fvg_*` from the 2026-04-26 FVG study: row data + JSON summary, no chip wiring, no `compute_filter_variants()` participation.

The criterion to promote any of these to a chip in a future iteration is the standing one: **+3% WR standalone, or +1% WR conditional on SMT.**

### Phase-2 flags (in priority order)

| # | Field | Source | Computation summary |
|---|---|---|---|
| 1 | `smt_quarter_transition` | Fearing | Map sweep timestamp and HTF-candle timestamp to quarter of relevant cycle (weekly cycle for 1H, 90-min for 30M); TRUE iff the swept HTF candle belongs to Q2 or Q3 and the sweep occurs in Q3 or Q4 of the same cycle (Q2→Q3 or Q3→Q4 transition). |
| 2 | `displacement_score` (numeric) | Amas | `prior_range / median(prior 10 HTF ranges)`. Continuous; no threshold on the row. Diagnostic summary thresholds at ≥1.5. |
| 3 | `passes_macro_window` | Both | Entry timestamp (NY) falls inside a macro window. Initial set: `08:50–09:10`, `09:50–10:10`, `10:50–11:10`, `13:50–14:10`, `14:50–15:10`. Blacklists lunch (11:10–12:50) by construction. |
| 4 | `passes_three_candle_cisd` | Fearing | Three consecutive HTF bars C1/C2/C3. TRUE iff (a) C2 wick breaches C1 extreme in trade direction, (b) C2 body closes back inside C1 range, (c) C3 closes through C2 open in trade direction. |
| 5 | `unmet_opposing_level` | Fearing | At sweep time, prior day's opposing extreme (PDL for shorts, PDH for longs) has not been touched since previous session close. Also computed for prior week (`unmet_opposing_pwk`). |
| 6 | `aggressive_body_frac` (numeric) | Amas | Body / range of prior HTF candle. Diagnostic threshold ≥0.55. |
| 7 | `passes_two_bar_smt` | Fearing | On the LTF (5M / 3M), the sweep bar and the bar immediately preceding it show directional divergence vs ES: NQ makes a HH/LL on the pair while ES does not. |
| 8 | `passes_sweep_in_10` | Amas | Sweep timestamp's minute-of-hour in `{0..10} ∪ {50..59}`. |

Numeric fields (`displacement_score`, `aggressive_body_frac`, `prior_extreme_minute_pct`, `cisd_pd_pct`) are stored as floats. Boolean flags are stored as `bool`. Memory cost is negligible (~10 extra columns × ~50K rows).

### Per-flag summary block

Each Phase-2 flag emits a JSON sub-block in `candidate_filter_summary`:

```json
"candidate_filter_summary": {
  "smt_quarter_transition": {
    "on":  {"n": ..., "wr": ..., "ev": ..., "pf": ...},
    "off": {"n": ..., "wr": ..., "ev": ..., "pf": ...},
    "delta_wr": ..., "delta_ev": ...
  },
  "displacement_score_ge_1.5": { ... },
  "passes_macro_hour": { ... },
  ...
}
```

Threshold-based summaries (`displacement_score`, `aggressive_body_frac`) are computed at one canonical threshold to start. A second threshold can be added later if early results suggest a different cutoff.

### Conditional-on-SMT companion summaries

Because SMT already dominates, the more interesting question for each Phase-2 candidate is "does it add edge *on top of* SMT?". Each summary additionally emits an `smt_on` sub-block, mirroring the precedent in `fvg_summary`:

```json
"smt_quarter_transition": {
  "all_trades": { ...as above... },
  "smt_on": { ...same stats but restricted to SMT=true rows... }
}
```

This is the same shape as `fvg_summary` already produces.

### Deferred (not implemented this iteration)

These were considered and explicitly deferred until Phase-2 results justify them. Encoded here so we don't re-litigate later:

- PSP at sweep (3-bar pivot with directional candle divergence vs ES)
- DFR cracking correlation (Asia / NY-premarket session defining range, NQ vs ES box-cross)
- Devil's Mark side (session-open candle wick asymmetry)
- True-Open side (CISD close relative to NY 00:00 + Sunday 18:00 opens)
- Small opposing wick on prior HTF candle
- Open-reclaim stricter F4 (CISD close beyond prior HTF open, not just inside range)
- 1-minute sweep-bar volume spike (rolling-median × k)
- Three-candle engulfing continuation (prior-prior HTF chain)

If any Phase-2 flag clears the promotion bar, the corresponding deferred concept gets reconsidered in the same family.

## Architecture

### Files touched

| File | Change |
|---|---|
| `engine/model_stats.py` | Add `compute_p42_flag`, `compute_pd_cisd_flag`, and Phase-2 helpers. Extend `base_row` with new fields. Extend `compute_filter_variants()` from 3-filter to 5-filter (32 combos). Add `p42_summary`, `pd_cisd_summary`, `candidate_filter_summary` to JSON. |
| `model_dashboard.html` | Add two chips after SMT. Wire up filter masks in the JS aggregator. Update precomputed-combos table to show 32 rows. No Phase-2 UI. |
| `tests/` | Unit tests for the two new chip computations; smoke test on `candidate_filter_summary` block shape. |

No changes to: `pine/`, `daily_update.py`, DB schema, `master_backtester.py`, `recalc.py`, `sltp_analyzer.py`.

### Compute-once, reuse pattern

`prior_extreme_minute_pct` is per-prior-candle and can be computed once per HTF bar (cached on the prior-candle scan), not per-trade. `cisd_pd_pct` is a single arithmetic per trade. Phase-2 quarter mapping is a stateless function on timestamp. Phase-2 rolling-median displacement is precomputed per HTF bar.

Engine runtime should not measurably increase — all new computation is O(1) per row except `displacement_score` which is O(N) per HTF bar with N=10.

### Backward compatibility

- All existing JSON keys preserved.
- All existing chip behaviors preserved.
- The 32-combo table replaces the 8-combo table in `filter_variants`; consumers iterate, so no consumer code breaks.
- New row fields are additive; downstream summaries that don't know about them ignore them.

## Risks and unknowns

1. **Sample-size collapse with 5 chips.** 32 combos over 1,711 trades (1H_5M best combo's current N) means some combos will have N < 50. The dashboard already handles small-N gracefully (shows `n` per row), but the "best combo" recommendation needs a minimum-N gate. Use N ≥ 200 as a floor for combo recommendation.
2. **`:42` rule may correlate with F3.** A late-formed extreme of a "displacement" candle is more likely to be a shallow sweep on the next bar. Measure the correlation; if F3 ∧ p42 is essentially F3 alone, drop p42 from the chip bar.
3. **PD location may correlate with F4.** F4 = "close in range" — a tight band of `r` values just inside the boundary. PD = "close in correct half" — a broader region. Should be substantially orthogonal but worth verifying.
4. **30M:21-minute threshold is a fractional-position guess.** The Amas rule is specifically `>= 42` minutes for H1. The 30M analogue (`>= 21`) preserves the 70% fractional position. If Phase-1 numbers underwhelm on 30M but work on 1H, try threshold = 18 (60%) and 24 (80%) as variants.

## Testing strategy

1. Run `python3 engine/model_stats.py` → confirm both new chips are populated on every row and the summary blocks render.
2. Spot-check 10 rows manually: re-derive `prior_extreme_minute_pct` and `cisd_pd_pct` by hand from the source DB rows. Confirm match.
3. Inspect the 32-combo table for sane monotonicity (adding a real filter shouldn't *decrease* WR with statistically meaningful N).
4. Inspect `candidate_filter_summary` for the eight Phase-2 flags. Note which clear the +3%-standalone or +1%-over-SMT bar. Those are the next-iteration chip candidates.
5. Existing test suite (`pytest tests/ -q`) must continue to pass — 215 currently passing.

## Success criteria

**Phase 1 success:**
- Both new chips wired and toggleable in the dashboard.
- Per-chip standalone WR/EV delta visible in the chip bar badges (existing UI pattern).
- 32-combo table renders, sortable by EV.

**Phase 2 success (separate from Phase 1):**
- `candidate_filter_summary` block written to JSON with all 8 flags.
- At least one Phase-2 flag clears the +3%-standalone or +1%-conditional-on-SMT bar.

If no Phase-2 flag clears the bar, we've cheaply ruled out 8 candidates and the next iteration moves to the 8 deferred concepts.

## Source paths (study artifacts)

- Amas material: [Mentorships/Amas + Bootcamp](/Users/abhi/Projects/Mentorships/Amas + Bootcamp) — 7 PDFs + 8 NoteGPT transcripts.
- Fearing material: [Mentorships/Fearing/transcripts/txt/](/Users/abhi/Projects/Mentorships/Fearing/transcripts/txt/) — 15 auto-caption transcripts (~40K words).
- Most-referenced Fearing transcript for this design: `11 - 05   fearing premium cisd lecture.txt`.
