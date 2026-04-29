# Amas Quarter Theory — Live TradingView Indicator

**Status:** Design approved 2026-04-26 · Implementation pending
**Owner:** abhi
**Folder:** `Statistic.ally/Amas Quarter Theory/`

## Purpose

Live TradingView Pine v6 indicator that applies bootcamp price-action concepts —
15-minute quarter analysis, 1h doji/line classification, 3h triad line/apex
classification, 05-box bands, midline mechanics — directly on the price chart,
with empirical probability readouts computed from historical NQ/ES 1m data.

## Bootcamp glossary (canonical rules)

### Quarter definitions

Each 1-hour candle is partitioned into four 15-minute quarters anchored to the
hour, NY time:

- **Q1**: minutes :00–:14 (inclusive)
- **Q2**: minutes :15–:29
- **Q3**: minutes :30–:44
- **Q4**: minutes :45–:59

### 3-hour triad blocks

Fixed clock-aligned blocks of three consecutive 1h candles. NY time:

- 00–03, 03–06, 06–09, 09–12, 12–15, 18–21, 21–00
- **15:00 hour is excluded.** No triad covers 15:00–18:00.

Within a triad: **C1** (first hour), **C2** (middle hour), **C3** (third hour).

### Hour classification (live, from quarter behaviour)

- **Line-up hour**: Q1.high < Q2.high < Q3.high < Q4.high AND Q1.low < Q2.low < Q3.low < Q4.low
- **Line-down hour**: monotonic stack down (mirror)
- **Doji hour**: any hour where the four quarters do not respect the monotonic
  stack rule. Choppy hour, no swing forming at the hourly level.

### Triad classification (line vs apex)

- **3h line-up**: C1.high < C2.high < C3.high AND C1.low < C2.low < C3.low
- **3h line-down**: monotonic mirror
- **3h apex-up**: C2 makes the swing high — C1.high < C2.high > C3.high
- **3h apex-down**: C2 makes the swing low — C1.low > C2.low < C3.low
- **3h doji**: anything else (no clean line, no clean apex swing)

In an apex triad, **C2 is also called the apex hour**.

### Quarter extreme classification

- **In-stat extreme**: a high or low that forms in **Q1 or Q4** of an hour.
- **Out-of-stat extreme**: a high or low that forms in **Q2 or Q3**.

Each hour has exactly one high and one low; these are labelled with the
quarter that created them and the in-stat / out-of-stat designation.

### Sweepers and bias shifts

A **sweeper** is any quarter whose price action takes out (strict break of) a
prior quarter's high or low *within the same hour*. Sweepers can occur on any
quarter sequence (Q1→Q2, Q2→Q3, Q3→Q4, or jumps like Q1→Q3).

**Bias shifts:**

- Q2 sweeps Q1 high → upward bias shift for the hour
- Q2 sweeps Q1 low → downward bias shift
- Same logic for Q3, Q4 sweeps of any prior quarter
- Q1→Q2 sweeps are weighted more prominently (initial bias setter)

### Doji-confirmed (mid-hour early read)

When a sweep in one direction is followed later in the hour by a sweep in the
**opposite** direction, the hour is structurally guaranteed not to be a clean
line. The flipping quarter triggers a `doji-confirmed` marker — early read that
the hour is becoming a doji-hour without waiting for hour close.

When the doji-confirmed event occurs inside C2 of a triad, it is also the live
signal that the triad is forming an **apex** rather than a line.

### 05 box and bands

- **05 box**: the price range of the **first 5 one-minute bars** of each hour
  (minutes :00, :01, :02, :03, :04 inclusive). Yields `box_high` and `box_low`.
- **Bands** (anchored at hour open, redrawn each hour, drawn through that hour
  only):
  - `+0.05% band` = `box_high × 1.0005`
  - `+0.10% band` = `box_high × 1.0010`
  - `−0.05% band` = `box_low × 0.9995`
  - `−0.10% band` = `box_low × 0.9990`
- **Visual treatment**: 0.05% bands light dotted; 0.10% bands more prominent
  (heavier dotted, brighter color). Inline `.05%` / `.1%` text labels at the
  right edge of each line.
- **Box render**: the 05 box itself is drawn as a **full chart-height tinted
  vertical column** spanning :00–:04 of each hour, *not* a horizontal price
  rectangle. The `box_high` / `box_low` are computed and used for band
  derivation, not drawn as a separate range.

### Band rejection rules

- **Reject from above** (rejection of an upper band): a candle wicks above
  `+0.05%` or `+0.10%` and **closes back below** that level.
- **Reject / support from below** (rejection of a lower band): a candle wicks
  below `−0.05%` or `−0.10%` and **closes back above** that level.

Rejection is candle-anchored (label drawn at the rejecting candle).

### Midline mechanics

The midline of any candle is `(high + low) / 2`.

**1h midline (the active hourly midline drawn through the current hour):**

(Note: "current hour" here means the hour in progress on the chart, not C2 of
a triad. Naming distinct from triad C1/C2/C3 to avoid confusion.)

- If the current hour's running OHLC is **inside the prior hour's range** —
  i.e. `current.low > prior.low AND current.high < prior.high` (strict on both
  sides) — the active midline is the **prior hour's mid**.
- If the current hour has **broken out** of the prior hour's range on either
  side, the active midline is the **current hour's own mid**.
- Equality on either side counts as broken out.

**3h midline (analogous, scaled to the triad level):**

- If the current 3h block is inside the prior 3h block, the active midline is
  the prior 3h block's mid; else current 3h block's mid.

**Midline reaction signals:**

- **Support** (price tags midline from above, holds, bounces back up — wick
  below, close back above) → upward bias for the hour / triad.
- **Reject** (price tags midline from below, fails, falls back down — wick
  above, close back below) → downward bias.
- Each support / reject reaction is candle-anchored with a marker.
- Both 1h and 3h midlines display simultaneously.
- Midline reaction state feeds into the empirical state vector.

## Architecture

### Approach

**Approach A: Pine indicator + offline Python engine** (selected over Approach
B "live webhook" — not feasible in Pine — and Approach C "all-HTML" — would
remove the on-chart-during-trading benefit).

- One Pine v6 indicator file: `pine/quarter_theory.pine`. Self-contained.
- One Python engine that pre-computes empirical probability tables and a
  quarter-pair backtest from `nq_1m` / `es_1m`, emits a Pine code snippet
  containing the tables.
- User pastes the generated snippet into a marked region of the indicator
  source on rebuild cadence (weekly / monthly in practice).

### Project structure

```
Statistic.ally/Amas Quarter Theory/
├── CLAUDE.md                          per-folder guidance
├── README.md                          quickstart + screenshot
├── pine/
│   ├── quarter_theory.pine            indicator (hand-written + paste-region)
│   ├── _generated_tables.pine         machine-generated, gitignored
│   └── _parity_runner.pine            Pine-side parity validator (manual)
├── engine/
│   ├── constants.py                   block defs, quarter defs, instruments
│   ├── db.py                          shared DB load (../Fractal Sweep/candle_science.duckdb)
│   ├── classifier.py                  pure: hour/triad/sweep/midline/05-box logic
│   ├── state_vector.py                state-key builder (parity-critical)
│   ├── empirical.py                   walks history, aggregates P(outcome | state), Wilson CIs
│   ├── strip_order.py                 mutual-information ranking for fallback
│   ├── quarter_pair_backtest.py       backtest every (entry_q, stop_q, direction) per state
│   ├── pine_emit.py                   emits Pine map<string,array<float>> literals
│   ├── build.py                       orchestrator + CLI
│   └── daily_update.py                cron hook into Fractal Sweep/engine/daily_update.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── state_cases.json
│   │   ├── classification_cases.json
│   │   ├── sweep_cases.json
│   │   └── pine_parity_export.json    populated by manual TradingView export
│   ├── test_classifier.py
│   ├── test_state_vector.py           includes Pine parity test
│   ├── test_sweeps.py
│   ├── test_midline.py
│   ├── test_box_05.py
│   ├── test_empirical.py
│   ├── test_quarter_pair.py
│   ├── test_strip_order.py
│   ├── test_pine_emit.py
│   ├── test_determinism.py
│   └── test_db.py
├── docs/
│   ├── spec.md                        canonical rules + glossary (link to this design)
│   └── state_vector.md                versioned schema reference
└── data/                              gitignored caches & build outputs
    ├── empirical_nq.parquet
    ├── empirical_es.parquet
    ├── quarter_pair_nq.parquet
    ├── quarter_pair_es.parquet
    ├── strip_order_v1.json
    ├── build_report.md
    └── last_build.txt
```

### Pine indicator internal structure

```
1.  Settings (8 grouped sections, each with a master toggle except General/Custom)
2.  Theme resolver (Dark / Light / Custom → unified color struct)
3.  Embedded empirical tables (PASTE-REGION sentinels)
4.  Time / structure primitives (NY tz, quarter-of-hour, triad-block-id, exclusion)
5.  Running aggregations (QuarterAgg, HourAgg, TriadAgg)
6.  Classifiers (pure logic, parity-mirrored from engine/classifier.py)
7.  State-vector builder (parity-mirrored from engine/state_vector.py)
8.  Probability lookup with hierarchical fallback
9.  Renderers (split per concern: quarter annotations, hour finalize, triad
    finalize, 05 box & bands, midlines, block readouts, OHLC overlay,
    tooltips)
10. Alerts
11. Label housekeeping (FIFO pruning to stay under Pine's 500-element caps)
```

### Data flow per bar

1. Update running aggregations (quarter / hour / triad / 05-box).
2. Detect events on this bar (sweeps, bias shifts, doji-confirmed, midline
   reactions, band rejections).
3. Classify current state (hour class, triad class, midline source).
4. Build state vector → key string.
5. Look up empirical probabilities (hierarchical fallback if `n < 30`).
6. Fire alerts for newly-flagged events (gated by user toggles).
7. Render: update active block readouts in-place; draw new annotations on
   confirmed bars only (avoid repaint flicker); prune oldest labels.

### Decision points (where probabilities re-evaluate)

1. Quarter close (every :15, :30, :45, :00)
2. Sweep event mid-quarter
3. Midline reaction confirmed
4. Band rejection confirmed
5. Hour close
6. Triad close
7. 05-box close (at :04 of every hour)

## State-vector schema (v1)

The contract between Python engine and Pine indicator. Byte-identical key
strings on both sides; pinned by parity tests.

### Triad key

```
v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up|c2q=Q3|
   c2vh=above|c2vl=above|c2sw_c1h=Y|c2sw_c1l=N|c2_inside=N|
   midhr=support|mid3h=untouched|box_react=10up_rejected
```

| Field | Values | Meaning |
|---|---|---|
| `v1` | literal | schema version (mismatch → fail-loud at lookup time) |
| `sym` | NQ / ES | instrument |
| `tf` | triad / hour | which timeframe key is for |
| `block` | 00-03 / 03-06 / 06-09 / 09-12 / 12-15 / 18-21 / 21-00 | NY-time 3h block |
| `c1cls` | line-up / line-dn / doji | C1 hour's quarter-stack classification |
| `c2q` | Q1 / Q2 / Q3 / Q4 / closed | which quarter C2 is currently in |
| `c2vh` | above / inside / below / na | C2 running high vs C1 high |
| `c2vl` | above / inside / below / na | C2 running low vs C1 low |
| `c2sw_c1h` | Y / N | C2 ever took out C1's high (persistent flag) |
| `c2sw_c1l` | Y / N | C2 ever took out C1's low |
| `c2_inside` | Y / N | C2 currently inside C1 range (both sides) |
| `midhr` | support / reject / untouched | active 1h midline reaction state |
| `mid3h` | support / reject / untouched | active 3h midline reaction state |
| `box_react` | none / 5up_rejected / 5dn_rejected / 10up_rejected / 10dn_rejected / multi | most-recent meaningful band reaction in current hour |

### Hour key

```
v1|sym=NQ|tf=hour|block=09-12|hour_idx=2|q=Q3|
   q1cls=in-stat-high|q2cls=swept-q1-low|
   sweep_set=Q2_swept_Q1_low|midhr=support|box_react=05dn_rejected
```

| Field | Values | Meaning |
|---|---|---|
| `hour_idx` | 1 / 2 / 3 | which hour of the triad (C1, C2, C3) |
| `q` | Q1 / Q2 / Q3 / Q4 / closed | current quarter |
| `qNcls` | in-stat-high / in-stat-low / out-stat-high / out-stat-low / inside | per-quarter extreme classification |
| `sweep_set` | comma-joined sweep events (sorted) | full sweep set for the hour |

### Compact encoding

Human-readable keys are too large for Pine's 1 MB source budget at full
cardinality × fallback levels. Both Python and Pine compute a stable hash of
the canonical key string (base36 of a 64-bit hash). Pine map keys are the
hash, not the human form. Hash function and canonical-form rules pinned in
`docs/state_vector.md`.

### Hierarchical fallback

Lookup tries the full key first; if `n < 30`, strip the least-informative
field per `data/strip_order_v1.json` (computed from mutual information of each
field with the eventual outcome) and try again. Repeat until match found or
root reached. Display:

- Matched key's `n`
- `*` flag if any fallback occurred (with strip count)
- Confidence color reflects the **matched** `n`

Strip order is baked into both Python (when emitting fallback levels into the
Pine table) and Pine (when keying lookups). Versioned with the schema.

## Empirical engine

`engine/empirical.py` walks every historical triad in `nq_1m` and `es_1m`:

1. At each decision point, build the live state vector (causal — uses only
   bars ≤ T).
2. Record `(state_key, eventual_outcome)`.
3. After full pass, group by state-key, compute empirical probabilities and
   Wilson 95% CIs.
4. Emit fallback levels per key per `strip_order_v1.json`.

Output schema (parquet): `state_key | outcome | p | ci_lo | ci_hi | n`.

`engine/pine_emit.py` translates this into Pine map literals:

```pinescript
var map<string, array<float>> EMPIRICAL_NQ = map.new<string, array<float>>()
if barstate.isfirst
    map.put(EMPIRICAL_NQ, "abc123", array.from(0.41, 0.05, 0.38, 0.02, 0.14, 312.0))
    // ...
```

Triad map values are 6-element arrays: `[p_lup, p_ldn, p_aup, p_adn, p_doji, n]`.
Hour map values are 4-element arrays: `[p_lup, p_ldn, p_doji, n]`.

### Source-size budget

Hard limit: `_generated_tables.pine` ≤ 900 KB (10% headroom under Pine's
1 MB). `engine/build.py` asserts this and fails loud if exceeded.

Mitigations available if needed:

1. Compact key encoding via base36 hash (default; included from v1).
2. Quantize probabilities to 1 decimal place.
3. Drop low-`n` keys below the fallback threshold.
4. Split into per-block tables (only if 1–3 insufficient).

### Symbol-aware tables

NQ and ES tables built independently from their respective 1m data.
`Empirical data source = Auto` selects by chart symbol. Force NQ / Force ES
overrides available. Charts of other symbols → `SCHEMA NOT CALIBRATED`
readout, no probabilities shown.

## Quarter-pair backtest (B-6 add-on)

For every state vector, surface the historically best quarter-pair entry/stop
combo as a trade idea on the readout.

### Trade definition

```python
@dataclass
class TradeDef:
    entry_q: int           # 1..12 (Q1 of C1 = 1, Q4 of C3 = 12)
    stop_q: int            # any quarter < entry_q (must be a closed quarter)
    direction: Literal["long", "short"]
```

### Restrictions (v1 scope)

- Decision points: **quarter-close boundaries only** for the backtest (not
  mid-quarter sweeps / reactions). Trade ideas don't change mid-quarter.
- Stop quarter must be **closed** at entry time (no same-quarter stops).
- Entry trigger: **close of the entry quarter**. (Adding "break of prior
  high" doubles table; defer to v2.)
- Target: **fixed at 2R** (R = entry-to-stop distance). Structural targets
  defer to v2.

### Aggregation

For every (state_key, pair) combination, record `wr`, `n`, `avg_r`, `ev`.
Filter to **top-1 by EV per state with `n ≥ 30`**. Quantize WR / EV / R to 1
decimal place. Drop pairs with > 0.9 outcome correlation to a higher-EV pair
(coverage dedup).

Embedded as second Pine map: `QPAIR_NQ` / `QPAIR_ES`. Same symbol-aware
auto-selection as the empirical map; charts of unsupported symbols hide the
quarter-pair line entirely.

### Display

Third line of the triad readout, when a recommendation exists for the active
state:

```
🎯 Long Q3-C2 / stop Q2-C2 low
   WR 64% · EV +0.8R · n=48
```

Boxed with accent-color border, distinct visual style from probability lines.
Toggleable via `Show quarter-pair recommendation` in `📊 Live Readouts` group.

### Correctness invariants (mirrors Amas Models)

- Same-bar tie → SL.
- `OUTCOME_MAX_BARS = 1440` (1 trading day). Expired excluded from WR/EV.
- Trade dedup by `(triad_id, pair, decision_point)`.
- Causal sampling (state-key uses bars ≤ entry only).
- Wilson CI on every WR.
- Determinism (byte-reproducible).

## Live readouts

### Placement

Centered horizontally under each 1h block and each 3h block, below price action.

- **1h readout** for each hour: drop `2 × ATR(20)` below the lowest low of the
  hour's four quarters.
- **3h triad readout**: drop another `2 × ATR(20)` below the lowest 1h
  readout in the triad.
- Spans the triad horizontally (centered on the triad midpoint, not under any
  single hour).

### Active vs completed

- **Active block** (forming live): bordered box with accent-color border,
  `▸ LIVE` prefix on first line, brighter colors. Updates in-place
  (`label.set_text`) on every bar.
- **Completed blocks**: borderless or 1px-faint border, no LIVE prefix, dim
  text. Frozen at hour-close / triad-close, never updated again.

### History depth

Default 20 most-recent triads (~60 hours) on chart. Toggle to 1–40 via
settings. Pruned FIFO to stay under Pine's 500-label cap.

### 1h readout content

```
HOUR 10:00 · Q3 forming
L-up 12 · L-dn 28 · Doji 60 · n=187
sweeper Q2 · 05-box 21041–21048
```

### 3h readout content

```
TRIAD 09–12 · C2 forming · line-up tracking
L-up 41 · A-up 38 · Doji 14 · L-dn 5 · A-dn 2 · n=312
🎯 Long Q3-C2 / stop Q2-C2 low · WR 64% · EV +0.8R · n=48
P(C3 high > C2 high | now) = 71%   ← conditional path %
```

### Confidence color on `n`

- `n ≥ 100` → green
- `30 ≤ n < 100` → amber
- `n < 30` → red (and fallback `*` flag)

### Tooltip on hover (C-11)

Every readout label and event annotation gets a `tooltip` with:

- Full state-vector key (decoded human-readable form)
- Full sweep history for the hour / triad
- Full midline reaction history
- All band rejection events
- Sample size and CI bounds for each probability

## On-chart annotations

### Quarter dividers

Vertical dotted lines at :15, :30, :45 (per hour). Slightly heavier divider at
:00 hour boundaries. Color from theme palette.

### Per-candle event annotations

- **In-stat extreme** (Q1/Q4 high or low): label anchored to the candle that
  printed the extreme. Example text: `Q1 in-stat high` (above candle, arrow
  down) or `Q4 in-stat low` (below candle, arrow up). Color: in-stat extreme.
- **Out-of-stat extreme** (Q2/Q3): same treatment, different color (out-of-stat).
- **Sweeper marker**: small triangle/arrow at the swept-from extreme, with a
  thin dotted line connecting to the sweeper's wick. Color: sweeper.
- **Bias-shift markers**: small green up-arrow or red down-arrow in chart
  margin (right-side of the bar). Q1→Q2 sweeps styled more prominently.
- **Doji-confirmed**: amber `◆` glyph at the flipping quarter's open. Distinct
  from the hour-close `doji-hour` verdict.

### Hour-close verdicts (anchored to Q4)

- `line-up hour` / `line-down hour` / `doji-hour` label below the Q4 candle of
  the hour.

### Triad-close verdicts (anchored to Q4 of C3)

- `line triad` / `apex triad` / `doji triad` label below Q4 of C3.

### Apex-hour highlight

When a triad classifies as apex, the C2 hour is highlighted with a label
anchored to Q4 of C2 reading `apex hour`, plus a subtle background tint
overlay across all four quarters of C2 in the `apex_hour` color. Triggers at
triad close (when C3 finalizes the apex classification).

### 3h block running OHLC overlay (A-4)

Small floating overlay near the active 3h block's readout showing live OHLC of
the developing block plus the price level needed to flip line/apex
classification (e.g. "C3 needs > 21,140 to confirm line-up").

### Midlines (horizontal lines)

- 1h midline drawn through the active hour, color `midline_1h` (amber default).
- 3h midline drawn through the active triad, color `midline_3h` (light gray
  default), distinguishable from 1h.
- Midline source resolved per the inside-bar rule (Section 6: prior or current
  candle's mid).

### Midline reaction markers

Small filled circle (4px) at the reacting candle's wick-tip, in
`midline_reaction` color, with optional thin connecting line back to the
midline.

### 05 box & bands

- **05 box**: full chart-height tinted vertical column spanning :00–:04 of
  each hour. Subtle 1px darker top/bottom border. Color: `box_05_tint`.
- **±0.05% bands**: light dotted horizontal lines, drawn through that hour
  only.
- **±0.10% bands**: heavier dotted, more prominent.
- Inline `.05%` / `.1%` text labels at the right edge.
- **Band rejection markers**: anchored to the rejecting candle. The rejected
  band's segment-during-that-hour brightens for 2 bars after rejection.

## Settings

### General (no master toggle)

- Theme: Dark / Light / Custom
- Empirical data source: Auto / Force NQ / Force ES
- Time zone: America/New_York (read-only)

### 📊 Live Readouts (master toggle)

- Show 1h hour readout
- Show 3h triad readout
- Active block style: Highlighted / LIVE tag / Both
- History depth (triads): 1–40 (default 20)
- Show sample count (n)
- Confidence color on n
- Show conditional path %
- Show quarter-pair recommendation (also gated by the group master toggle)

### 🕐 Quarter Structure (master toggle)

- Show quarter dividers
- Show in-stat extreme labels
- Show out-of-stat extreme labels
- Show sweeper markers
- Show bias-shift markers
- Show doji-confirmed marker

### 🕒 Hour & Triad Verdicts (master toggle)

- Show hour close verdict
- Show triad close verdict
- Show apex-hour highlight
- Show 3h running OHLC overlay

### 📐 Midlines (master toggle)

- Show 1h midline
- Show 3h midline
- Show midline reaction markers
- 1h midline width
- 3h midline width

### 📦 05 Box & Bands (master toggle)

- Show 05 box column
- Show ±0.05% bands
- Show ±0.10% bands
- Show band rejection markers
- Show inline % labels

### 🔔 Alerts (master toggle)

- Alert on sweeper
- Alert on doji-confirmed (default ON)
- Alert on apex-confirmed (default ON)
- Alert on midline reaction
- Alert on band rejection

### 🎨 Custom Colors (no master; gated behind Theme = Custom)

Individual color inputs for each annotation, readout, midline, band, tint
(see Theming section below for the full list).

## Theming

Two built-in palettes, plus Custom. Mirrors the cyan-accent system from Amas
Models / Statistic.ally hub.

### Dark Mode (default)

```
active_hour_tint        rgba(6,182,212,0.05)
active_triad_tint       rgba(6,182,212,0.03)
completed_hour_tint     rgba(255,255,255,0.015)
box_05_tint             rgba(255,255,255,0.06)
active_block_outline    rgba(6,182,212,0.35)

quarter_divider         rgba(255,255,255,0.12)
quarter_divider_hour    rgba(255,255,255,0.20)

in_stat_extreme         #06b6d4  (cyan)
out_stat_extreme        #f59e0b  (amber)
sweeper                 #8b5cf6  (purple)
bias_shift_up           rgba(16,185,129,0.7)
bias_shift_down         rgba(239,68,68,0.7)
doji_confirmed          #f59e0b
apex_hour               #ef4444
line_hour_up            #10b981
line_hour_down          #ef4444
midline_reaction        #f59e0b

midline_1h              #f59e0b  (1px solid)
midline_3h              #e2eaf4  (1px solid)

band_05                 rgba(255,255,255,0.25)
band_10                 rgba(255,255,255,0.50)

readout_bg              rgba(17,24,39,0.85)
readout_border          rgba(255,255,255,0.10)
readout_text            #e2eaf4
readout_text_dim        #8ba4bc
readout_active_accent   #06b6d4
prob_line_up            #10b981
prob_line_down          #ef4444
prob_apex_up            #3b82f6
prob_apex_down          #8b5cf6
prob_doji               #f59e0b
conf_high               #10b981  (n ≥ 100)
conf_med                #f59e0b  (30 ≤ n < 100)
conf_low                #ef4444  (n < 30)
qpair_box               rgba(6,182,212,0.10)
```

### Light Mode

```
active_hour_tint        rgba(8,145,178,0.06)
active_triad_tint       rgba(8,145,178,0.03)
completed_hour_tint     rgba(0,0,0,0.015)
box_05_tint             rgba(0,0,0,0.06)
active_block_outline    rgba(8,145,178,0.45)

quarter_divider         rgba(0,0,0,0.15)
quarter_divider_hour    rgba(0,0,0,0.25)

in_stat_extreme         #0891b2
out_stat_extreme        #d97706
sweeper                 #7c3aed
bias_shift_up           rgba(5,150,105,0.7)
bias_shift_down         rgba(220,38,38,0.7)
doji_confirmed          #d97706
apex_hour               #dc2626
line_hour_up            #059669
line_hour_down          #dc2626
midline_reaction        #d97706

midline_1h              #d97706
midline_3h              #1f2937

band_05                 rgba(0,0,0,0.25)
band_10                 rgba(0,0,0,0.55)

readout_bg              rgba(255,255,255,0.92)
readout_border          rgba(0,0,0,0.10)
readout_text            #0f172a
readout_text_dim        #475569
readout_active_accent   #0891b2
prob_line_up            #059669
prob_line_down          #dc2626
prob_apex_up            #2563eb
prob_apex_down          #7c3aed
prob_doji               #d97706
conf_high               #059669
conf_med                #d97706
conf_low                #dc2626
qpair_box               rgba(8,145,178,0.10)
```

### Layout & polish details

- Readouts use `box.new` (background + border) with stacked `label.new` lines
  inside (each line independently colorable).
- Active block "glow" simulated with two overlapping translucent boxes (outer
  larger and fainter).
- 05-box column gets a 1px-darker top and bottom border.
- Typography (Pine-limited): readout headers `size.small` bold; readout body
  `size.tiny` mono; per-candle event labels `size.tiny` normal; inline band %
  labels `size.tiny` mono.
- Repaint avoidance: event annotations drawn only on `barstate.isconfirmed`;
  readout text updated in-place via `label.set_text` (safe intra-bar).

## Correctness invariants (non-negotiable)

Mirrors `Amas Models/CLAUDE.md` — same standard.

- **A. Causal sampling**: state-vector at decision-point T uses only bars
  with `ts ≤ T`. Lookahead-leak test pinned via synthetic anomaly bar.
- **B. Pine ↔ Python parity**: `state_vector` and `classifier` produce
  byte-identical output for the same input. Pinned by fixture-based test.
- **C. Hour & triad classification parity**: same parity test for
  `classify_hour` / `classify_triad`. Includes ties, zero-range bars,
  exact-equal extremes.
- **D. Sweep detection**: strict break, equality does not trigger.
- **E. 05-box arithmetic**: 5 minute bars at :00–:04 inclusive. Bands at
  exactly `box × 1.0005`, `box × 1.0010`, etc. Pinned to the digit.
- **F. Midline source resolution**: inside-bar test is strict on both sides
  (`> AND <`). Equality counts as broken-out.
- **G. Quarter-pair backtest fidelity**: same-bar tie → SL,
  OUTCOME_MAX_BARS=1440, expired excluded, trade dedup by tuple.
- **H. Wilson CI on every WR / probability**. `n` always visible.
- **I. Determinism**: `engine/build.py` byte-reproducible.
- **J. Source-size budget**: `_generated_tables.pine` ≤ 900 KB. Asserted in
  `build.py` itself.
- **K. Fallback monotonicity**: never strips back to a more-specific key.
- **L. Data quality on every load**: monotonic timestamps, no duplicates,
  OHLC sanity, no RTH gaps, schema match.

## Build & deploy workflow

### One-time build

```bash
cd Statistic.ally/Amas\ Quarter\ Theory/
python3 engine/build.py            # builds tables, emits _generated_tables.pine
python3 -m pytest tests/ -q        # runs full suite
```

`build.py` outputs paste instructions on success.

### Pine paste

`pine/quarter_theory.pine` has sentinel comments:

```pinescript
// PASTE-REGION-START
// (auto-generated — do not edit by hand)
// (last updated: 2026-04-26 by build.py)
// ... map.put() calls ...
// PASTE-REGION-END
```

User opens both files, replaces region, saves.

### Pine parity validation (manual, after every rebuild)

1. `engine/build.py` regenerates `tests/fixtures/state_cases.json`.
2. User opens `pine/_parity_runner.pine` in TradingView (separate from main
   indicator), adds to a chart. The runner outputs a multi-line label with
   computed state-keys.
3. User copies output, saves as `tests/fixtures/pine_parity_export.json`.
4. Run `python3 -m pytest tests/test_state_vector.py::test_pine_parity -v`.

If parity fails, the empirical lookup is silently wrong — build is unusable
until fixed.

### Daily refresh (cron)

Hook into existing `Fractal Sweep/engine/daily_update.py`:

```python
if (REPO_ROOT / "Amas Quarter Theory" / "engine" / "daily_update.py").exists():
    subprocess.run(
        ["python3", "engine/daily_update.py"],
        cwd=REPO_ROOT / "Amas Quarter Theory",
        check=False,
    )
```

`Amas Quarter Theory/engine/daily_update.py` calls `build.py`, writes
`data/last_build.txt` with status. **Manual paste still required** — no way
around this without server infrastructure. In practice user re-pastes
weekly / monthly.

### Schema versioning

`SCHEMA_VERSION = "v1"` constant on both sides. Mismatch detected at lookup
time → readout shows `SCHEMA MISMATCH — REBUILD` instead of probabilities,
fail-loud. Bumping requires: update both, rebuild table, re-paste, re-validate
parity.

## v2 deferred

- **D-12: Companion HTML dashboard** — Pine webhooks JSON → richer panels
  (heatmaps of states by time-of-day, full conditional-distribution charts).
  Lives at `Statistic.ally/Amas Quarter Theory/dashboard/` (or merged into
  hub). Reuses the same engine output.

## v1 explicitly skipped

- A-1 (daily / 4h triad layer), A-2 (liquidity sweep history), A-3 (NY session
  tint), C-9 (replay mode), C-10 (state export).

## References

- `Statistic.ally/CLAUDE.md` — repo conventions.
- `Statistic.ally/Amas Models/CLAUDE.md` — sibling engine pattern,
  correctness invariants standard, stats helpers (`Wilson CI`, `EV`,
  `OUTCOME_MAX_BARS=1440`).
- `Statistic.ally/Fractal Sweep/engine/daily_update.py` — cron entry point.
- Reference image (user-supplied) showing target visual treatment of
  quarter dividers, 05 box column, midlines, and dotted bands.
