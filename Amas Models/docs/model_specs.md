# Amas Models — Formal Specs

This document is the contract between the Amas mentorship materials and every line of engine code in `engine/models/`. Each model below has its rules formalized to a level the engine can implement without interpretation.

**Companion docs:**
- Source-by-source summary: [`source_index.md`](source_index.md)
- Engine design and correctness invariants: [`../../docs/superpowers/specs/2026-04-26-amas-models-design.md`](../../docs/superpowers/specs/2026-04-26-amas-models-design.md)

**Reading status:** All 24 source files read. 8 PDF pairs (Mentorships 1–4, 6, 7, 8) + 8 transcripts. Transcripts 1, 2, 3, 4, 6, 7, 8 duplicate their corresponding Mentorship long PDFs (verified by spot-check). Transcript 5 is unique — a back-testing walkthrough call with no PDF equivalent. Note: there is no "Mentorship 5" PDF; the numbering jumps from 4 to 6.

---

## Glossary

_Every term the mentor uses, defined once. Models reference glossary terms instead of redefining them. Each entry cites the first source where the term is introduced or best defined._

- **H1 candle** — A 1-hour candle. Per the mentor: "every 59 and 59 seconds, the H1 candle will close. Boom. New one will open." (M1 PDF 35:02). The framework tracks H1 closes and trades the *transition* between one H1 close and the next H1 open.
- **Draw / Draw on liquidity / Target** — The price level the mentor expects price to "be drawn to" within the next H1 window. For Continuation, it's the prior H1's already-formed high (long) or low (short). For Reversal, it's the opposite extreme of the swept range. (M1 PDF 24:10, "I know price will most likely go towards this high")
- **Continuation pattern** — H1 candle closes *above* the previous H1's high (bullish) or *below* the previous H1's low (bearish). Mentor's claim: "80% chance of seeing a candle close on the H1 and see open high into that H1 candle here." (M1 PDF 01:29)
- **Reversal pattern** — H1 candle *sweeps* the previous H1's high or low (price wicks past it) but *closes back inside* the prior H1's range. After a high sweep that closes back inside, the *low* of the prior H1 becomes the draw; symmetrically for low sweeps. (M1 PDF 23:50, "we swept previous candles low, close back inside the range. So, what do I know? I know this high is going to be taken up 80% of the time.")
- **Sweep / Liquidity sweep** — Price wicks beyond a high or low without closing past it. The wick takes out resting orders ("liquidity") sitting at that level.
- **Macro / Macro window** — The mentor's term for specific 20-minute windows where macros (algorithmic moves) tend to fire. The H1-internal macro is the **last 10 + first 10 minutes around an hourly close** (`:50–:10`). There are also session-specific macros (e.g., `:50–:10` of the 9 AM hour = `08:50–09:10` ET, called "9:50–10:10 macro"). (M1 PDF 03:43, M1 PDF 1:00:03)
- **First 10 / Last 10** — Shorthand for the two halves of the H1-internal macro window: last 10 minutes of the prior H1 (`:50–:00`) and first 10 minutes of the new H1 (`:00–:10`). (M1 PDF 07:02, "the first portion of the macros to the last 10 minutes of the hour, okay? Which means that it's from 50 to 0 first.")
- **":42 timing rule"** — The high or low you are *targeting* must have been *formed* at or after minute :42 of the source H1 candle. Highs/lows formed before :42 are typically rejected by the mentor as low-probability. (M1 PDF 49:26, "you always want the high or the low you're trying to target to be formed after 42.")
- **CISD** — _(not used by Amas mentor; this is Fractal Sweep terminology — see cross-cutting concepts.)_
- **Order Block (OB)** — An M1 candlestick pattern: price breaks structure (high/low/higher-high), and the *zone* of the candle that broke structure is the order block. A bullish OB forms after price breaks structure to the upside; a bearish OB after a break to the downside. The mentor enters in this zone on the pullback. (M1 PDF 26:18, M2 PDF 1:03:48)
- **Breaker Block** — A *failed* order block: an order block that gets violated (price closes through it) and then re-tests it from the opposite side. "When you disrespect a bullish order block, it turns into a bearish breaker." (M1 PDF 29:21)
- **Inversion FVG / Inversion for Value Gap** — A Fair Value Gap that gets traded through and then re-tests in the opposite role: a bearish FVG that's broken above becomes bullish support on retest. (M1 PDF 29:31, "this is my favorite entry model and by far the best in trading.")
- **Fair Value Gap (FVG) / Value Gap** — A 3-candle imbalance where the middle candle's body fully crosses the gap between the high of bar 1 and the low of bar 3 (bullish) or vice versa.
- **Market Structure Shift (MSS) / Break of Structure (BOS)** — A change in trend on a small timeframe: price makes a lower-low after a high (bearish MSS) or higher-high after a low (bullish MSS). The mentor uses this on M1 to time entries.
- **Fake Market Structure Shift** — When M1 makes an MSS that the mentor expects to fail because the higher-timeframe (H1) bias is opposite. He waits for this fake shift and trades against it. (M1 PDF 17:11)
- **Opposite structure** — On the H1, when there is an obvious S/R level (prior order block, FVG, big wick) inside the H1 candle's range that would *resist* the draw move. Mentor scratches setups where opposite structure is "blatant"; takes them when it's mild and the M1 setup is otherwise strong. (M1 PDF 38:16, M2 PDF 51:55)
- **Rejection of HTF liquidity** — When the H1 wick has *already* taken out a higher-timeframe (H4 or daily) high/low. The mentor avoids fading that — he interprets the prior wick as having already swept the liquidity, so the move into the prior H1 high is less likely to repeat. (M1 PDF 37:08)
- **Aggressive candle / Volume in the body** — A signed close where the H1 body (open→close) is large relative to the wick(s). Mentor avoids dojis and slim-body H1s; he wants "the body to have volume in it." (M1 PDF 47:18)
- **Distribution candle** — An H1 candle whose extreme (the low for a bearish candle, the high for a bullish candle) is formed *late* in the candle's lifetime. For a bearish distribution candle: opens, makes the high, distributes downward, makes the low near the close (OHLC sequence: open-high-low-close). The low is "unprotected" — there's not enough remaining time in the candle for buyers to step in and form a defensible OB. **Tradeable.** (M3 transcript 08:05, 11:24)
- **Pullback candle** — An H1 candle whose extreme is formed *early* in the candle's lifetime. For a bearish pullback candle: opens, makes the low quickly, then retraces high, then closes back lower (OHLC sequence: open-low-high-close). The low is "protected" — there's been enough time in the candle for buyers to defensively load up at the low, forming a high-probability OB that resists being swept. **NOT tradeable** by the mentor. (M3 transcript 09:11, 09:36)
- **Protected vs Unprotected low/high** — The same idea as Distribution vs Pullback, framed from the structure side: an unprotected low (in a bearish candle) is the kind formed near the close; a protected low is formed early and "had time to be defended." The :42 rule operationalizes the boundary. (M3 transcript 10:36)
- **Displacement** — A large H1 candle (in points) whose body and volume substantially exceed the prior N candles. Indicates strong directional conviction; mentor sometimes overrides his other rules when displacement is extreme ("I will never disrespect the rule of 42... but if the volume is huge enough I will hold past 1R"). (M3 transcript 26:31, 27:17)
- **V-signature** — An M1 entry pattern: a 3-bar sequence where bar 1 makes a low, bar 2 wicks lower (sweep), bar 3 closes back up sharply. Forms a "V" shape. Mentor prefers this entry over waiting for an OB-then-pullback when displacement is present. (M3 transcript 1:11:28)
- **5-criteria validation list (M3 explicit)** — The mentor enumerates the criteria for an A+ trade in a single drill (M3 03:06): (1) no rejection of higher timeframe liquidity; (2) no opposite structure; (3) no lunch macro; (4) no big wicks (i.e., big volume candle, aggressive body); (5) low/high formed after :42 (i.e., distribution not pullback); (6) no SMTs. He counts these as "5 criteria" but actually lists 6–7. The engine treats each as a separate `passes_*` flag.
- **A+ setup** — Mentor's tag for a setup that meets *all* validation criteria: no opposite structure, no HTF liquidity rejection, aggressive H1 body, target high/low formed after :42, M1 has a clean OB / Breaker / Inversion-FVG, and timing is tight to the H1 close. (M2 PDF 11:15, M2 PDF 18:18)
- **SMT / NQ-ES Divergence** — When NQ takes out its target liquidity but ES does not, OR ES does and NQ doesn't. The mentor uses SMT both for entry confirmation (when no clean sweep exists) and for stop-management ("SMT is a reason why you should either put your stops to break even or get the fuck out"). (M1 PDF 1:07:23, M2 PDF 07:39)
- **Drop / Jaw / Slope** — Casual mentor synonyms for the prior H1's high (or low) — i.e., the draw. ("This slope has 80% chance of being taken out.")
- **PDR / PDA / PDA rate** — Premium-Discount Region / Premium-Discount Array. ICT-derived terminology for the price zone where a setup is valid. Mentor uses "PDR" loosely to mean "pullback zone for entry."

---

## Cross-cutting concepts

_Rules, filters, and definitions that apply to multiple models._

### Anchor and time

- **Anchor unit:** the H1 candle. All detection logic is keyed off the H1 close timestamp.
- **Timezone:** all timestamps in `America/New_York`. The mentor explicitly clocks his 9:50/10:10/11:10/etc. macros in NY time (M1 PDF 1:00:08 references the 9:50–10:10 window as primary).
- **Macro windows (preferred trading times):** the mentor ranks NY macros by his preference. From M1 PDF 1:01:41:
  1. **`09:50–10:10`** — best
  2. `10:50–11:10`
  3. `08:50–09:10`
  4. `12:50–13:10` ("good but hard")
  5. `13:50–14:10` ("the one I have a love-hate relationship with")
  6. `14:50–15:10`
  7. **`11:50–12:10` — explicitly avoid** ("no liquidity at all")
- **Outside macros:** trades fired outside `:50–:10` are **lower probability** but not strictly rejected. Mentor: "everything that is not immediate is lower probability. I would probably not take that." (M1 PDF 22:33)
- **":42 timing rule":** for any setup, the H1 high (long) or low (short) being targeted must have been formed at or after minute `:42` of its source H1 candle. Highs/lows formed earlier in the candle are anti-edge — they correspond to "open low, low formed early, push up, close" style distributions where the mentor's model decays. (M1 PDF 49:26, 50:38, 51:11, 51:53)

### Risk and sizing

- **Per-trade risk:** $400 USD on NQ mini ($20/pt) — implies max 20-point stop (per design spec). For wider stops (the mentor cites 32-handle stops as the boundary), switch to micros — the engine treats this as the same setup with the same R; only dollar size changes.
- **Stop placement:** at the nearest *trade-invalidation* level — typically the swing high above (for shorts) / swing low below (for longs) of the M1 entry pattern. "If price goes there, it will be invalidating your trade." (M1 PDF 1:15:02)
- **Target:** **1R (1:1)** is the headline. Mentor: "Target a one-to-one. Most of the time, it will be either 1 to 1 or 0.9 to 1, close to negative RR most of the time." (M1 PDF 15:58). On A+ setups he sometimes "swings" for 2R+, but the engine's default is `simple_1r`.
- **MAX_RISK_PTS = 20.0** — risk gate (design spec).
- **MIN_RISK_PTS = None** — no lower floor (design spec).

### Confluences (filters that apply across models)

Each becomes a `passes_<key>: bool` flag on every trade row.

- **`passes_macro_010` (key: `MACRO`)** — entry timestamp falls within `:50–:10` of any hour. Always-on baseline expectation per mentor; surfaced as toggleable to measure standalone edge.
- **`passes_top3_macros` (key: `MACRO_TOP3`)** — entry within one of the 3 best windows: `08:50–09:10`, `09:50–10:10`, `10:50–11:10`.
- **`passes_avoid_lunch` (key: `NO_LUNCH`)** — entry NOT within `11:50–12:10` (the explicitly-avoided window). Independent of `MACRO_TOP3` so we can measure it standalone.
- **`passes_target_after_42` (key: `T42`)** — the prior H1's high/low being targeted was formed at minute ≥42 of its candle. Computed by scanning the prior H1's 1m bars for the high/low timestamp.
- **`passes_no_opposite_struct_h1` (key: `NO_OS`)** — the H1 candle whose close triggers the setup has no large opposite-structure feature inside it (large opposite-side wick > a threshold of the body, or a clean opposite OB on the H1). _Initial threshold TBD; see Open Questions._
- **`passes_no_htf_rejection` (key: `NO_HTF_REJ`)** — the H1 wick (in the trade direction) has not already taken out an H4 or daily high/low. _Implementation: requires H4 and daily series — derived by resampling 1m bars._
- **`passes_aggressive_body` (key: `AGG_BODY`)** — the H1 body (`abs(close - open)`) is at least N% of the candle range (`high - low`). _Initial threshold: body ≥ 60% of range._
- **`passes_distribution_candle` (key: `DIST`)** — the H1 candle is a *distribution* candle (extreme formed late, ≥:42), not a *pullback* candle (extreme formed early, <:42). Implementation: scan the H1's 1m bars; find the timestamp of the candle's relevant extreme (low for bearish, high for bullish); flag passes if `extreme_minute >= 42`. This is *the same signal* as `passes_target_after_42` for the *self*-candle (the just-closed H1). For the prior H1 (the candle whose draw is being targeted), the analogous flag is `passes_target_after_42` already defined above. **Two separate flags with different semantics:** `T42` is about the prior H1 (the draw); `DIST` is about the just-closed H1 (the source). Both must pass for full A+. (M3 transcript 03:06–05:06, 09:36, 10:36, 14:51)
- **`passes_smt` (key: `SMT`)** — at the moment of detection, NQ swept its draw level but ES did NOT (for shorts looking for re-test; symmetric for longs). Same primitive used by Fractal Sweep.
- **`passes_within_5m_structure` (key: `5M_OK`)** — entry distance to the draw is below an "in M5 structure" threshold. Per Transcript 5 (~02:23, ~47:30): when the distance from entry to draw exceeds ~40 NQ points, the mentor calls it "5-minute structure" and explicitly avoids it because stop-loss placement becomes unreliable. _Initial threshold: `abs(entry_price - draw_price) ≤ 40.0`._
- **`passes_target_after_50` (key: `T50`)** — STRICTER variant of `T42` for Model 3 only. The targeted high/low must have been formed at `≥ :50` of its source candle (last 10 minutes). Mentor (M6 transcript 35:38): "If you want to play the model 3 for the reversal, it needs to be clear. You need the high or low to be put in at 50 and after." Models 1 and 2 still use `T42`; only Model 3 escalates to `T50`.

The first three (`MACRO`, `MACRO_TOP3`, `NO_LUNCH`) are time-of-day based. The next four are H1-feature based. `SMT` requires both instruments loaded.

### Direction and validation

- **Continuation trade direction:** same direction as the H1 close (close > prior_high → long; close < prior_low → short).
- **Reversal trade direction:** opposite the wick direction (sweep prior high then close back inside → short; sweep prior low then close back inside → long).
- **Validation criteria** (mentor lists 4, M1 PDF 36:30 onward; these become the H1-feature filters listed above):
  1. **No rejection of HTF liquidity** in the wick direction. → `passes_no_htf_rejection`.
  2. **No opposite structure** inside the H1 candle. → `passes_no_opposite_struct_h1`.
  3. **No lunch trades** (`11:50–12:10`). → `passes_avoid_lunch`.
  4. **Aggressive candle closure** with volume in the body (no doji). → `passes_aggressive_body`.
- **Discard:** if these criteria are violated, the mentor "scratches the trade" — but his decision is judgmental ("opposite structure could still work"). The engine surfaces all setups and lets each filter combo measure its standalone edge.

### Trade construction (used by both Continuation and Reversal)

The setup that fires after H1 close (or pre-positions before close) is identical in mechanics:

1. **Anchor:** the H1 candle that just closed at time T.
2. **Pattern check:** Continuation or Reversal pattern (defined per-model).
3. **Validation gates:** all four validation criteria evaluated; setup is *recorded* regardless, with `passes_*` flags.
4. **Direction:** derived per-pattern (see above).
5. **Draw:** the prior H1's relevant extreme (Continuation: prior H1's same-direction extreme; Reversal: prior H1's opposite extreme).
6. **M1 entry trigger:** the first of OB / Breaker / Inversion-FVG to form on M1 in the macro window after T (`T+0:00–T+0:10`) AND/OR before T (`T-0:10–T+0:00`, the "pre-close entry").
7. **Entry price:** the high/low of the M1 trigger pattern, on the pullback into it (the mentor uses limit orders at the pattern's edge).
8. **Stop loss:** the structural high/low immediately beyond the trigger pattern (for shorts, the swing high that the trigger broke; for longs, the swing low).
9. **Take profit:** **1R** (`simple_1r` profile) — fixed at `entry + 1 * abs(entry - SL)` for longs, mirrored for shorts.
10. **Invalidation:** if the draw is hit before the 1R, that's a TP. If SL is hit, SL. If neither resolves within `OUTCOME_MAX_BARS` (1440 minutes), `EXPIRED`.

### Pre-close vs post-close entries — Model 1 vs Model 2

The mentor (M4 transcript 08:17–11:21) labels these explicitly:

- **Model 1 (positioning *before* H1 close):** during `T-0:10–T:00` (last-10 macro, minutes :50–:59), if M1 already shows the OB/Breaker/Inversion pattern AND we project the H1 will close in the right pattern, enter early. The H1 candle is "still fluctuating" at entry.
- **Model 2 (positioning *after* H1 close):** during `T:00–T+0:10` (first-10 macro), wait for the H1 to actually close in the pattern, then look for the M1 trigger on the *new* H1 candle (which is forming). Mentor: "Model 2 is you wait. So open low, high right here formed after 42... And this candle will close. So most likely the high is going to be formed at like 55, 56-ish." (M4 transcript 10:19–10:32) — ambiguous read; he means *the next candle's* high forms at :55–:56 of *its* hour, which is Model 1 of the *next* hour. So Model 1 and Model 2 are essentially the same pattern at offset hours.

**Mentor's explicit guidance on choosing:** when there is opposite structure on the H1, prefer Model 2 ("safer"). When the H1 setup is clean (no opposite structure, big body, late extreme), Model 1 is acceptable — the front-running entry captures more R. (M4 transcript 12:19–13:31)

Mentor on safety: "the closer you are from the close, the more chances you have to win. That's 100%." (M2 PDF 09:15) "My trades, the time that I would take a trade basically, the most premature is like 52, 53." (M2 PDF 03:29)

**Engine treatment:** for v1, fire the setup at the H1 close as a Model-2-equivalent post-close entry. Adding Model 1 (pre-close entry) requires forecasting the H1 close from an incomplete bar, which is complex and pattern-dependent — defer to a later phase or as an explicit `entry_mode: 'model_1' | 'model_2'` parameter once Model 2 baseline is measured. (Open Questions #2)

### Power of Three (M4)

**Power of Three** is the mentor's framing of the 3-phase H1 candle structure (M4 transcript 22:11–27:09):

1. **Setup phase (`:00–:42` of H1):** the candle establishes its initial direction, often opposite the eventual close direction (the "fake" move).
2. **Manipulation phase (`:42–:55` of H1):** the candle reaches its extreme on the side that *will be swept*. This is when the `:42` rule says the high/low forms.
3. **Distribution phase (`:55–:59:59` of H1):** the candle resolves toward its close direction, often closing strongly outside its first-half range (Continuation) or closing back inside the prior H1's range (Reversal).

The :42 rule formalizes the boundary between phases 1 and 2. Distribution candles (per M3) are candles where the extreme falls in phase 2. Pullback candles are those where the extreme falls in phase 1.

**Power of Three on the new H1 (M4 22:11–27:09):** the same logic applies to the next candle. After T (the close of the prior H1), the new H1 forms its own 3-phase structure. The mentor uses an M1 IFVG/OB/Breaker pattern *on the new H1* targeting the prior H1's draw as a high-probability entry. He calls this confirmation "the flip" — when the new H1's price closes back above its own opening price after a fake move down (for a long setup), the low of the new H1 is "officially formed" and can be used as the stop level.

**Engine treatment:** Power of Three is a meta-concept that doesn't add a new filter; it confirms the existing :42 rule and Distribution-vs-Pullback flag. The "flip" pattern (M4 24:36) — new H1 closes back above its open after a fake move — is a candidate for a `passes_h1_flip` confluence flag in a later iteration; deferred for v1.

---

## Source map

_For each of the 24 source files, 1 line on which models it informs. Detailed summaries live in [`source_index.md`](source_index.md)._

(Will be populated as files are read; current entries below.)

- **Mentorship1-H1 Candle Trading Guide.pdf** (summary): introduces both Continuation and Reversal at high level; defines macros, OB/Breaker/FVG entries, ~80% draw probability claim, validation criteria.
- **Mentorship1-H1 Candle Trading Guide (1).pdf** (full transcript): same content, more detail and examples; introduces the `:42` timing rule and the 7 macro window rankings.
- **Mentorship2-H1 Model & Risk.pdf** (full transcript): no new model; deep-dives Q&A on edge cases ("when do I take a trade with opposite structure?"), risk management ("don't trade far from the close, take 7-6-5 minutes from close"), and the "tracking H1, not M1" principle.

---

# Models

## Model: H1 Continuation

### Source citations
- Mentorship 1 PDF (summary) p.1 ("Continuation pattern indicates H1 candle closing above the previous candle's high. Post-close outcome probability of taking out the upwick is 80%.")
- Mentorship 1 (1).pdf [transcript] timestamps 00:52, 01:11, 01:29, 03:06, 13:04 (bearish), 21:02
- Mentorship 2.pdf [transcript] 33:00, 33:39, 34:21, 36:51, 43:11, 44:04

### Plain-English description
After an H1 candle closes outside the prior H1's range (above the prior high → bullish; below the prior low → bearish), the mentor expects the *prior H1's same-side extreme* to be retested ("popped") within the next H1 window with ~80% probability. The trade enters on a pullback to an M1 OB/Breaker/Inversion-FVG inside the macro window around the close, targets 1R, stop above (short) / below (long) the M1 swing.

### Anchor / setup timeframe
H1 (1-hour candle, NY tz). The setup fires at H1 close at time `T`.

### Detection rules (all must be true)
1. The just-closed H1 candle's close is strictly outside the prior H1's range:
   - Bullish continuation: `H1[T].close > H1[T-1h].high`
   - Bearish continuation: `H1[T].close < H1[T-1h].low`
2. The prior H1 (`H1[T-1h]`) exists (i.e., not the first candle in the series).
3. The prior H1's relevant extreme (for the draw) is a strictly defined level: prior H1's high (bullish) or low (bearish).
4. After the close at T, the M1 bars in the post-close macro window (`T:00 – T+0:10`) contain at least one Order Block / Breaker / Inversion-FVG pattern in the trade direction. _Pattern detectors detailed below._
5. The trigger M1 pattern's invalidation level (its swing high for shorts, swing low for longs) is at most `MAX_RISK_PTS = 20.0` points from the entry price. Setups exceeding the gate are excluded entirely (not just flagged).

### Entry trigger
The first M1 Order Block / Breaker / Inversion-FVG pattern in the trade direction that forms within `[T:00, T+0:10]` and provides a pullback entry. Entry is at the pattern's edge on the pullback (limit-order semantics).

For v1, the engine operationalizes "pattern formed" as:
- **Order Block:** a 1-candle (M1) opposite-color candle that gets immediately broken by structure (a higher high after it for bullish trades; lower low for bearish). Entry = the OB candle's open (for bullish OB) or close (for bearish OB) — TBD; see Open Questions #3.
- **Breaker:** a *failed* opposite-direction OB. Detection: the M1 forms an OB in the opposite direction, then closes through it; the broken OB level becomes the trigger. Entry = the broken OB's edge.
- **Inversion FVG:** a 3-bar M1 FVG that gets traded through; on retest from the opposite side, entry at the gap edge.

Of the three, mentor prefers Inversion FVG ("by far the best in trading", M1 PDF 29:31). For v1, all three are detected and an `entry_pattern: str` field on the trade row records which one fired. A model variant restricting to Inversion-FVG only is a Phase 5 filter experiment.

### Stop loss
- **Bullish:** the swing low of the M1 trigger pattern (i.e., the lowest low of the M1 bars from the macro start through the entry bar).
- **Bearish:** the swing high of the M1 trigger pattern (highest high in the same window).

In code: stop = `min(M1 lows in [T:00, entry_ts])` for longs; mirrored for shorts. _Refinement TBD; see Open Questions #4._

### Take profit / exit
**1R** (`simple_1r` profile):
- Bullish: `tp = entry + (entry - sl)`
- Bearish: `tp = entry - (sl - entry)`

The mentor's "draw" (prior H1 extreme) is the *aspirational* target but the booked exit is 1R, which empirically tends to land at or near the draw given typical M1 entry distances.

### Direction logic
- `H1[T].close > H1[T-1h].high` → long
- `H1[T].close < H1[T-1h].low` → short

A single anchor produces at most one direction (the close is either above the prior high or below the prior low; both being true is impossible).

### Invalidation / discard
- If no qualifying M1 trigger fires within the post-close macro window `[T:00, T+0:10]`, the setup is discarded (no trade row).
- If a trigger fires but the implied risk exceeds `MAX_RISK_PTS`, the setup is discarded.
- After entry, standard outcome resolution: TP, SL, or EXPIRED at `OUTCOME_MAX_BARS`.

### Confluences / filters mentioned
All cross-cutting filters apply (computed as `passes_<key>` flags on each trade row):
- `passes_macro_010` — by definition of the entry window, this is always True for v1 setups. (Useful when comparing against later expansions.)
- `passes_top3_macros`
- `passes_avoid_lunch`
- `passes_target_after_42`
- `passes_no_opposite_struct_h1`
- `passes_no_htf_rejection`
- `passes_aggressive_body`
- `passes_distribution_candle`
- `passes_within_5m_structure`
- `passes_smt`

Plus a model-specific flag:
- `passes_pattern_inversion_fvg` — entry was via Inversion-FVG specifically (mentor's stated favorite).

### Open questions / ambiguities
1. **OB entry price exact location.** The mentor describes the OB but doesn't pin the entry to a specific price (open vs close vs midpoint of the OB candle). Source quote: "you would enter on the order block ... stop loss above this candle's low" (M1 PDF 55:10). For v1, conservative interpretation: entry = OB candle's open (worse fill, more realistic for a limit order).
2. **Pre-close entry.** Mentor describes positioning before H1 close (M1 PDF 21:25, M2 PDF 03:29). Engine v1 fires only at post-close; pre-close is deferred.
3. **OB swing-detection on M1.** Defining "the M1 swing high/low after pattern" requires picking a lookback. For v1, use the macro-window low/high (`min(M1[T:00..entry_ts].low)` for longs); revisit if results are noisy.
4. **Aggressive body threshold.** Mentor uses "aggressive" qualitatively. Initial: body ≥ 60% of range. To be parameter-swept.
5. **Opposite structure threshold.** Same — initial heuristic: a body-sized opposite wick on the H1 (wick on the *opposite* side ≥ 50% of the body) is "opposite structure." To be refined.
6. **HTF rejection definition.** Mentor uses H4 and daily liquidity. Initial: H1 close-direction wick takes out the recent H4 high/low (within last 24 H4 bars). To be refined.
7. **":42" exact semantics.** "High formed after :42" — is that the timestamp of the bar that contains the high price, the *bar's start* time, or the *bar's close*? For v1, use the start-time of the 1m bar that contains the H1's high price.
8. **OB rule fired on micro-breaks** — the loose formal OB definition caught one-tick "structural breaks" with tiny-body candles, patterns the mentor would never call OBs. Tightened in 2026-04-26 to require `min_body_ratio ≥ 0.5` (OB candle's body ≥ 50% of its range) and `min_break_displacement_pts ≥ 1.0` (NQ point) on the breaking bar. Both parameters are in `engine/models/h1_continuation.py` constants and can be parameter-swept in Phase 4.
9. **Inversion-FVG dropped from v1 entry triggers** — the formal INV_FVG definition produced 19% draw-hit on 12y NQ data while tightened OB produced 68%. INV_FVG was actively dragging down the overall WR. The primitive remains in `engine/m1_patterns.py` but is excluded from the H1 Continuation candidate list for v1. Likely the formal definition doesn't match the mentor's intent for "best in trading" pattern; needs re-formalization in Phase 4+.

### Backtest results

**Run date:** 2026-04-26
**Data:** NQ 1-minute, 2014-08-31 → 2026-04-24 (~12 years)
**Configuration:** Tightened OB (`min_body_ratio=0.5, min_break_displacement_pts=1.0`); INV_FVG dropped; Breaker kept (n=17 over 12y, contributes negligibly)

#### Baseline (no filter chips active)
- **N**: 774 trades (~65/year)
- **1R Win Rate**: 68.6% [Wilson 95% CI: 65.2%, 71.8%]
- **Draw-hit rate** (the mentor's actual edge claim, ~80%): **67.1%**
- **EV**: +0.372R per trade
- **Profit factor**: 2.19
- **Year-by-year**: stable. 13/13 years above 50% 1R-WR. Range 58% (2021) to 88% (2014, n=8). Two years above 80% 1R-WR (2014, 2017).

#### Best filter combo (most picky)
Filters: `aggressive_body + avoid_lunch + distribution_candle + no_opposite_struct_h1 + within_5m_structure`
- **N**: 115 trades (~10/year)
- **1R Win Rate**: 72.2%
- **Draw-hit rate**: **76.5%** (within 3.5 pp of mentor's 80% claim, Wilson 95% CI lower bound ~68%)
- **EV**: +0.443R per trade

#### Notable breakdowns
- **Long vs Short**: roughly symmetric. Long n=421 WR 68.5%, Short n=353 WR 68.8% — no directional bias detected.
- **Pattern**: 97.8% Order Block (n=757, 68.0% draw-hit), 2.2% Breaker (n=17, 23.5% draw-hit — small sample noise).
- **Risk distribution**: median 2.75 NQ pts, p25 1.0, p75 5.5. Mean 4.0 pts. The MAX_RISK_PTS=20 gate is rarely binding.
- **Expired trades**: 0 (all trades resolved within OUTCOME_MAX_BARS=1440).

#### Walk-forward
_Not yet computed; deferred to Phase 5._

---

## Model: H1 Reversal

### Source citations
- Mentorship 1 PDF (summary) p.1 ("After H1 sweeps prior high and closes back inside range...")
- Mentorship 1 (1).pdf [transcript] 23:50, 38:30, 43:50 (mentor calls Reversal "best model in my opinion"), 44:13 (continuation reversal = bearish)
- Mentorship 2.pdf [transcript] 43:50–44:32, 35:54

### Plain-English description
After an H1 candle wicks past the prior H1's high (bearish reversal) or low (bullish reversal) but closes back inside the prior H1's range, the mentor expects the *opposite* extreme of the prior H1 to be the draw within the next H1 window. Same M1 trigger structure as Continuation, opposite direction logic.

### Anchor / setup timeframe
H1 (NY tz). Setup fires at H1 close at T.

### Detection rules (all must be true)
1. The just-closed H1 candle's wick swept the prior H1's range AND the close is back inside the prior H1's range:
   - Bearish reversal: `H1[T].high > H1[T-1h].high` AND `H1[T].close ≤ H1[T-1h].high`
   - Bullish reversal: `H1[T].low < H1[T-1h].low` AND `H1[T].close ≥ H1[T-1h].low`
2. The prior H1 exists.
3. The draw is the prior H1's *opposite* extreme:
   - Bearish reversal: target = `H1[T-1h].low`
   - Bullish reversal: target = `H1[T-1h].high`
4. M1 trigger criteria identical to Continuation (Order Block / Breaker / Inversion-FVG in the trade direction within `[T:00, T+0:10]`).
5. Risk gate: trigger's invalidation ≤ `MAX_RISK_PTS = 20.0`.

### Entry trigger / Stop loss / Take profit
Identical to Continuation, with mirrored direction.

### Direction logic
- Bearish reversal (high swept, close back inside) → short
- Bullish reversal (low swept, close back inside) → long

A single anchor produces at most one direction. (If both rules fire — e.g., close is exactly equal to a prior extreme — that's a degenerate case; tie-break: classify as Continuation if close strictly outside prior range, else Reversal.)

### Invalidation / discard
Same as Continuation.

### Confluences / filters
Same as Continuation, with the same `passes_<key>` flags.

### Open questions / ambiguities
1. **"Close back inside" — strict or weak inequality?** Mentor's language "close back inside the range" is ambiguous on whether `close == prior_high` counts. For v1, use weak inequality (`close ≤ prior_high` for bearish reversal, `close ≥ prior_low` for bullish reversal). I.e., closing exactly at the prior extreme is a reversal, not a continuation.
2. **Reversal vs Continuation tie-break.** Same anchor cannot produce both, by construction (close cannot simultaneously be strictly above prior high and ≤ prior high). But what if the H1 sweeps both prior high AND prior low (engulfing wicks)? Source is silent. For v1: classify by which side the close falls — if close > prior_high → Continuation bull; if close < prior_low → Continuation bear; if close inside range AND wick swept high → bearish reversal; if close inside range AND wick swept low → bullish reversal; if both wicks swept and close inside range → ambiguous, use **wick-magnitude tie-break**: assign to the side with the larger wick. This is the only rule the mentor doesn't directly specify; flagged as TBD.
3. **All other ambiguities** from Continuation (entry-price-on-OB, aggressive-body threshold, etc.) apply identically.

### Backtest results
_(filled in during Phase 4)_

---

## Model: H1 Reversal — Model 3 (DCA-aggressive, range-bound markets)

### Source citations
- Mentorship 6.pdf [summary] p.1–2 (introduces Model 3)
- Mentorship 6 (1).pdf [transcript] 28:50–32:27 (Model 3 thesis), 41:54–48:53 (DCA mechanics), 50:54 ("first con sweep low, second con DCA"), 35:38 (`:50+` requirement)
- Mentorship 7.pdf [summary] (Models 3 & 4 in trending markets)
- Mentorship 8 (1).pdf [transcript] 1:01:46 ("Model 3 and 4 are literally the same in this case")

### Plain-English description
Same H1 Reversal pattern as Model 2 (sweep prior H1's low/high, close back inside range), but the *entry mechanics* are different. Used in trending market conditions where Models 1/2 don't pick up because price never pulls back. Light initial position inside the OB+FVG zone immediately after the close, then DCA on the first internal pullback ("turtle soup") to reach full size.

### Anchor / setup timeframe
H1 (NY tz). Setup fires at H1 close at T, same as Models 1 and 2.

### Detection rules (all must be true)
1. The just-closed H1 is a *Reversal* pattern (per Model 2's Detection rule 1):
   - Bearish reversal: `H1[T].high > H1[T-1h].high` AND `H1[T].close ≤ H1[T-1h].high`
   - Bullish reversal: `H1[T].low < H1[T-1h].low` AND `H1[T].close ≥ H1[T-1h].low`
2. **STRICTER timing:** the prior H1's targeted extreme (the draw) must have been formed at minute `≥ :50` of its source candle. (`passes_target_after_50` flag.) Less-strict `:42+` setups go to Models 1/2.
3. The new H1 (the one forming after T) shows an Order Block AND a Fair Value Gap aligned in the trade direction within `[T:00, T+0:10]`. Mentor: "you enter inside an order block slash fair value gap. The best thing is when you have both." (M6 transcript 29:28)
4. Trade direction: opposite the wick direction (bearish reversal → short; bullish reversal → long).
5. Risk gate (initial entry): `risk_pts ≤ MAX_RISK_PTS`.

### Entry trigger and DCA mechanics
This model has **two positions**:
- **First (initial) position:** ~50% of normal size, entered market or limit at the first OB+FVG zone inside the post-close macro `[T:00, T+0:10]`. Mentor: "five micros. Boom. I'm in five micros. That's good." (M6 transcript 43:43)
- **Second (DCA) position:** ~50% of normal size, limit order at the first internal pullback (the "turtle soup" / sweep of the first internal low for longs, first internal high for shorts) within the same H1 window. If the pullback never comes, the trade rides on the first position only.

Mental stop loss on first position: looser than usual ("wider stop loss because if it goes deeper to soup, the second entry will catch the better price"). Hard stop = below the prior H1's low (for longs) / above the prior H1's high (for shorts) — the *invalidation* level for the whole reversal pattern.

### Stop loss
- **First position only (no DCA fill):** structural — below the M1 trigger pattern's swing low (long) / above its swing high (short). Same as Model 2.
- **Combined position (DCA filled):** the prior H1's invalidation extreme (the level whose breach invalidates the reversal pattern entirely). For longs: prior H1's low. For shorts: prior H1's high.
- Effective combined-position risk = average entry minus invalidation level. Mentor describes this as "around 1:1 RR" once both positions fill (M6 transcript 44:29).

### Take profit / exit
- **First position:** **0.6R** (mentor: "the first initial position would be around 0.6 RR" — M6 transcript 44:29).
- **Second position:** **1.0–2.0R** (mentor: "the second one would be around 1 to 2").
- The model's combined R is roughly **1R** per unit risked when both fill, or **0.6R** when only the first fills.

### Direction logic
Same as H1 Reversal (Model 2):
- Bearish reversal (high swept, close back inside) → short
- Bullish reversal (low swept, close back inside) → long

### Invalidation / discard
- If neither OB nor FVG forms in the post-close macro, no first position is taken; setup is discarded.
- If the prior H1's invalidation extreme is breached before either TP, full position is stopped out at 1R combined loss (the invalidation level is the combined stop).
- Standard `EXPIRED` resolution at `OUTCOME_MAX_BARS`.

### Confluences / filters
All cross-cutting filters apply, plus:
- `passes_target_after_50` (REPLACES `passes_target_after_42`; Model 3 requires the stricter `:50+` rule)
- `passes_within_5m_structure` (entry distance ≤ 40 pts to draw)
- `passes_pattern_ob_and_fvg_aligned` — Model 3 only fires when *both* an OB AND an FVG form in the trade direction (vs. Model 2 which accepts any of OB/Breaker/Inversion-FVG)

### Open questions / ambiguities
1. **DCA outcome resolution.** The shared outcome resolver in `engine/outcomes.py` handles single-position trades. Model 3 has TWO positions with different TP levels. Engine v1 will treat the trade row as a single combined position with the average entry and the combined stop, computing R against that. The 0.6R first-position TP becomes a tag on the trade row (`first_pos_resolved: bool`) for analysis, not a separate trade. Each Model 3 setup → ONE trade row.
2. **Internal pullback definition.** Mentor says "first internal low" but doesn't pin the threshold. Initial: the first M1 bar after entry whose low is below the entry by at least N points (N = trigger pattern's height × 0.5). To be parameter-swept.
3. **OB+FVG alignment definition.** "Aligned" likely means the OB's zone overlaps the FVG's zone in price space. Initial: OB body intersects FVG body.

### Backtest results
_(filled in during Phase 4)_

---

## Model: H1 Reversal — Model 4 (below-sweep continuation, trending markets)

### Source citations
- Mentorship 6.pdf [summary] p.1
- Mentorship 7.pdf [summary] ("wait for a sweep of the most recent low and enter below that low to capture a rapid rally")
- Mentorship 7 (1).pdf [transcript] (description of Model 4 mechanics)

### Plain-English description
Same H1 Reversal pattern as Models 2/3, but enter *below* the most recent internal low (for longs) or *above* the most recent internal high (for shorts). The thesis: in strongly trending markets, price will not pause to form an OB or FVG inside the macro — it will rip from a sweep directly through the draw in a single big M1 candle. Model 4 catches that one-candle rally by positioning *at* the sweep extreme rather than waiting for confirmation.

### Anchor / setup timeframe
H1 (NY tz). Setup fires at H1 close at T.

### Detection rules (all must be true)
1. Same Reversal pattern detection as Model 3 (rule 1).
2. Same `passes_target_after_50` requirement as Model 3.
3. The **most recent internal extreme** in the new H1's `[T:00, T+0:10]` window has been swept and price is back inside that extreme (for longs: most recent M1 low has been violated then closed back above it).
4. No OB or FVG required (this is the differentiator from Model 3 — pure stop-hunt entry).
5. Risk gate: `risk_pts ≤ MAX_RISK_PTS`.

### Entry trigger
Limit order at the swept extreme — the price level at the moment the M1 swept it. Mentor (M7 summary): "enter below that low to capture a rapid rally by one large candle."

### Stop loss
Wider than Models 1/2/3 by design: ~`1.0–1.5×` the trigger height below (for longs) the swept extreme. Mentor describes Model 4 as a "stop hunt" entry — the swept extreme is the invalidation; the stop is past it by a buffer.

### Take profit / exit
**1R**, but the mentor notes Model 4 trades "tend to fly" toward the draw in a single candle, so a trailing-stop overlay (move stop to break-even after `0.5R` reached) is mentioned but not formalized. Engine v1 ships standard `simple_1r`.

### Direction logic
Same as Reversal: bearish reversal → short, bullish reversal → long.

### Invalidation / discard
- If no recent internal extreme exists to sweep within `[T:00, T+0:10]`, setup is discarded.
- Same `EXPIRED` resolution.

### Confluences / filters
Same as Model 3, except:
- Mentor specifically mentions Model 4 fires in **trending markets** (sustained directional moves with shallow pullbacks). A `regime_trending: bool` flag could be added by measuring the prior N H1 candles' close-direction streak. Initial: trailing 3 of last 5 H1 candles closed in the same direction. Marked TBD #3.

### Open questions / ambiguities
1. **"Most recent" internal extreme.** Mentor uses gestural language; engine needs a precise rule. Initial: the lowest low (for longs) of the M1 bars in `[T:00, swept_ts]` where `swept_ts` is the M1 timestamp at which price swept that low.
2. **Stop buffer.** Mentor says "wider" without specifying. Initial: stop = swept extreme ± 0.25 × prior H1's range.
3. **Regime-trending detection.** Marked above.

### Backtest results
_(filled in during Phase 4)_

---

## M15 timeframe variants

Per Mentorship 7 (PDF + transcript) and Mentorship 8 (transcript 1:12:08): "**15 minute models. There is no model one and two. It's only model three and four.**" The M15 timeframe supports Models 3 and 4 *only*; Models 1 and 2 do not transfer to M15.

### M15 anchor unit
A 15-minute candle, NY tz. Anchors floor to `:00`, `:15`, `:30`, `:45` of each hour.

### M15 timing rule (analogue of `:42+`)
Per Mentorship 7 summary: M15 highs/lows formed in the **last 6 minutes** of the M15 candle are "unprotected" (the M15 analogue of the H1 `:42+` rule). For each M15 anchor, the equivalent thresholds are:
- M15 candle covering `:00–:15` → high/low must be formed at `≥ :09`
- M15 candle covering `:15–:30` → `≥ :24`
- M15 candle covering `:30–:45` → `≥ :39`
- M15 candle covering `:45–:00` → **DO NOT TRADE** (mentor: "avoid the last M15 because the hourly close holds more power")

This is `passes_target_after_m15_last_6` flag.

### M15 hourly-trend dominance
Per M7 summary: "never trade an M15 reversal that opposes the hourly close direction because the hourly candle will likely invalidate the M15 setup." This becomes `passes_h1_aligned: bool` — the H1 candle currently containing the M15 anchor must close in the SAME direction as the M15 trade direction.

### Model 3 — M15 variant
Same detection logic as H1 Model 3, with:
- Anchor = M15 candle (instead of H1)
- Draw = the prior M15's opposite extreme (instead of prior H1's)
- Timing rule = `:09`/`:24`/`:39` (instead of `:50`)
- M15 anchor at `:45` is dropped entirely
- New filter: `passes_h1_aligned`

### Model 4 — M15 variant
Same as Model 4 with the M15 substitutions above.

### Engine treatment
Each model is a separate registration in the engine `MODELS` registry:
- `h1_continuation` (Model 1+2 entry merged for v1)
- `h1_reversal` (Model 1+2 entry merged for v1)
- `h1_reversal_m3` (Model 3 H1)
- `h1_reversal_m4` (Model 4 H1)
- `m15_reversal_m3` (Model 3 M15)
- `m15_reversal_m4` (Model 4 M15)

For v1, only `h1_continuation` is implemented (Phase 3 candidate). The other 5 are Phase 4+ work. The cross-cutting concepts and filters are shared so they generalize cleanly.

---

## Empirical timing observations (Transcript 5)

In the back-testing walkthrough call (Transcript 5), the mentor repeatedly observed that highs and lows in the NQ data are concentrated at specific minute marks within H1 candles:

- **`:46`** — most common low/high formation minute; mentor remarks on it across multiple trade examples ("46 again. Oh my god, that's a month. What's happening that the lows are always firmed at 46?")
- **`:51`** — second most common
- **`:57`** — frequently appears, especially for opposite-direction extremes
- **`:42`** — the threshold itself; the rule is `≥ :42`, but `:42` exactly is rarer than `:46`/`:51`/`:57`

These minute marks are *empirical*, not rules. They support the mentor's claim that the `:42+` rule was derived from "5,000 backtested trades" (M3 14:51).

**Engine treatment:** the engine should *measure* these distributions for each model rather than gate on them. A `extreme_minute: int` field on each trade row enables the dashboard to surface these distributions empirically. If the engine confirms `:46`/`:51`/`:57` clustering on the live 12y dataset, that's strong corroboration of the mentor's framework. If it doesn't, that's a real finding (either the framework is data-dependent or the Toronto/NY tz handling has a systemic offset — bug check).

This is an analysis output, not a filter.

---

## Two-contract DCA technique (Transcript 5)

A **risk management tactic** applicable to ALL models, not a model itself. Per Transcript 5 (~3:01, ~5:25, ~6:25):

- Enter the trade in **two halves**: 1 contract at market (immediate fill), 1 contract via limit order at a structural pullback below entry.
- If the limit fills, average entry is better and combined RR is closer to 1:1.
- If the limit doesn't fill, the trade rides on 1 contract only (smaller win).
- This converts setups with marginal RR (~0.6) into effective ~0.95–1.0 RR setups, at the cost of accepting larger drawdown if the trade fails.

**Engine treatment:** v1 ships single-contract `simple_1r` only. The 2-contract DCA can be added as an additional risk profile in a later phase (`split_dca_1r` or similar). It's orthogonal to model selection.

---

## Phase 3 candidate — CONFIRMED

**Phase 3 implements `h1_continuation` (Model 2 entry timing — post-close).**

Justification:
1. Mentor explicitly says: "I really want you guys to understand everything about the H-1 continuation first because it's a little bit, like, it's the same." (M4 transcript 52:34) and "we will master this continuation setup, and when we're done with that, we'll master the reversal" (M1 PDF 1:19:14).
2. Continuation has fewer ambiguities than Reversal: no two-sided sweep edge case, no DCA mechanic, no `:50+` stricter timing.
3. Model 2 (post-close entry) is simpler than Model 1 (pre-close entry) because the H1 candle is fully closed at decision time — no forecasting required.
4. Model 2 H1 Continuation produces the largest sample size of all variants (mentor notes Continuation is more frequent than Reversal in his lived experience), giving Phase 3 statistical power to validate the architecture.
5. Once Model 2 H1 Continuation is end-to-end, Reversal is a near-mirror (different direction logic, same machinery), Model 1 adds the pre-close timing dimension, Model 3 adds DCA, Model 4 adds wider stops, and M15 variants are anchor-timeframe substitutions. All Phase 4 work is replication on a proven base.

The full v1 model registration:
```
MODELS = {
    "h1_continuation": ModelDefinition(
        key="h1_continuation",
        label="H1 Continuation (Model 2 entry)",
        detect=h1_continuation.detect_setups,
        filters=[
            Filter("MACRO", "Macro window :50–:10", default=True),
            Filter("MACRO_TOP3", "Top-3 macro hours", default=False),
            Filter("NO_LUNCH", "Avoid 12:50–13:10", default=False),
            Filter("T42", "Draw formed after :42", default=False),
            Filter("NO_OS", "No opposite structure", default=False),
            Filter("NO_HTF_REJ", "No HTF rejection", default=False),
            Filter("AGG_BODY", "Aggressive H1 body", default=False),
            Filter("DIST", "Distribution candle (vs pullback)", default=False),
            Filter("5M_OK", "Within M5 structure (≤40 pts to draw)", default=False),
            Filter("SMT", "NQ-ES divergence", default=False),
        ],
        spec_anchor="model-h1-continuation",
    ),
}
```

---

## Per-model template (reference, do not edit)

```
## Model: <name>

### Source citations
- Mentorship 6-H1 Reversal Models.pdf p.4–7
- 1st Call Mentorship 2025.txt L1240–1380

### Plain-English description
2–4 sentences.

### Anchor / setup timeframe
e.g., "H1 candle that closes between 09:30 and 16:00 ET"

### Detection rules (all must be true)
1. Numbered list. Each rule is one boolean condition expressed in OHLC values, prior bars, time, or other models' state.
2. Vague terms are translated to a numeric threshold or flagged TBD with the source quote.

### Entry trigger
Exact bar/condition that fires the trade.

### Stop loss
Defined price relative to a specific bar's high/low.

### Take profit / exit
Either fixed R or a defined condition.

### Direction logic
How long vs short is determined.

### Invalidation / discard
When the setup is dropped before resolution.

### Confluences / filters mentioned
Each becomes a togglable dashboard chip, computed as a `passes_<key>: bool` flag on every trade row.

### Open questions / ambiguities
Numbered list with source quote.

### Backtest results (filled in during Phase 4)
- Baseline (no filters): WR, EV, PF, N, period
- With recommended filter combo: WR, EV, PF, N
- Notable regime breaks
- Walk-forward: train EV vs test EV, overfitting score
```
