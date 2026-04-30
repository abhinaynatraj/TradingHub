# Phase 6 — Pine Indicator Skeleton

> **Sub-skill:** Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Build the Pine indicator's structural backbone: settings (with grouped master toggles), theme resolver, time/structure primitives, running aggregations, classifier, state-vector builder, lookup. No annotations or readouts yet — those come in Phase 7/8. This phase ends with the indicator computing live state on chart, even if it doesn't draw anything beyond debug labels.

**Prereq:** Phases 1–5 complete. `pine/_generated_tables.pine` exists and is non-empty.

**Pine "TDD" note:** Pine cannot be unit-tested locally. Each task ends with: load on TradingView chart, visually verify expected debug output, then commit.

---

### Task 6.1: Settings panel with master toggles

**Files:**
- Modify: `pine/quarter_theory.pine`

- [ ] **Step 1: Replace the skeleton with the full settings + theme resolver framework**

Open `pine/quarter_theory.pine`. Delete its current contents (the Phase 5 skeleton). Replace with:

```pinescript
//@version=6
indicator("Amas Quarter Theory", overlay=true,
         max_labels_count=500, max_lines_count=500, max_boxes_count=500)

// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 1. SETTINGS                                                              ║
// ╚══════════════════════════════════════════════════════════════════════════╝

// ── ⚙ General ─────────────────────────────────────────────────────────────
G_GENERAL = "⚙ General"
gTheme        = input.string("Dark", "Theme",        options=["Dark","Light","Custom"], group=G_GENERAL)
gDataSource   = input.string("Auto", "Empirical data source", options=["Auto","NQ","ES"], group=G_GENERAL)
gTzNote       = input.string("America/New_York", "Time zone (read-only)", options=["America/New_York"], group=G_GENERAL)

// ── 📊 Live Readouts ─────────────────────────────────────────────────────
G_RO = "📊 Live Readouts"
gReadoutsOn   = input.bool(true, "▶ Enable group", group=G_RO)
gShow1h       = input.bool(true, "Show 1h hour readout", group=G_RO)
gShow3h       = input.bool(true, "Show 3h triad readout", group=G_RO)
gActiveStyle  = input.string("Highlighted + LIVE tag", "Active block style",
                              options=["Highlighted","LIVE tag","Highlighted + LIVE tag"], group=G_RO)
gHistDepth    = input.int(20, "History depth (triads)", minval=1, maxval=40, group=G_RO)
gShowN        = input.bool(true, "Show sample count (n)", group=G_RO)
gConfColor    = input.bool(true, "Confidence color on n", group=G_RO)
gShowPath     = input.bool(true, "Show conditional path %", group=G_RO)
gShowQPair    = input.bool(true, "Show quarter-pair recommendation", group=G_RO)

// ── 🕐 Quarter Structure ─────────────────────────────────────────────────
G_QS = "🕐 Quarter Structure"
gQStructOn    = input.bool(true, "▶ Enable group", group=G_QS)
gShowQDiv     = input.bool(true, "Show quarter dividers (vertical dotted)", group=G_QS)
gShowInStat   = input.bool(true, "Show in-stat extreme labels (Q1/Q4)", group=G_QS)
gShowOutStat  = input.bool(true, "Show out-of-stat extreme labels (Q2/Q3)", group=G_QS)
gShowSweepers = input.bool(true, "Show sweeper markers", group=G_QS)
gShowBiasShift= input.bool(true, "Show bias-shift markers", group=G_QS)
gShowDojiConf = input.bool(true, "Show doji-confirmed marker", group=G_QS)

// ── 🕒 Hour & Triad Verdicts ─────────────────────────────────────────────
G_VER = "🕒 Hour & Triad Verdicts"
gVerdictsOn   = input.bool(true, "▶ Enable group", group=G_VER)
gShowHourVerd = input.bool(true, "Show hour close verdict", group=G_VER)
gShowTriadVerd= input.bool(true, "Show triad close verdict", group=G_VER)
gShowApexHr   = input.bool(true, "Show apex-hour highlight", group=G_VER)
gShowOhlcOver = input.bool(true, "Show 3h running OHLC overlay", group=G_VER)

// ── 📐 Midlines ───────────────────────────────────────────────────────────
G_MID = "📐 Midlines"
gMidOn        = input.bool(true, "▶ Enable group", group=G_MID)
gShowMid1h    = input.bool(true, "Show 1h midline", group=G_MID)
gShowMid3h    = input.bool(true, "Show 3h midline", group=G_MID)
gShowMidReact = input.bool(true, "Show midline reaction markers", group=G_MID)
gMid1hWidth   = input.int(1, "1h midline width", minval=1, maxval=4, group=G_MID)
gMid3hWidth   = input.int(1, "3h midline width", minval=1, maxval=4, group=G_MID)

// ── 📦 05 Box & Bands ─────────────────────────────────────────────────────
G_BOX = "📦 05 Box & Bands"
gBoxOn        = input.bool(true, "▶ Enable group", group=G_BOX)
gShowBoxCol   = input.bool(true, "Show 05 box column (full-height tint)", group=G_BOX)
gShowBand05   = input.bool(true, "Show ±0.05% bands", group=G_BOX)
gShowBand10   = input.bool(true, "Show ±0.10% bands", group=G_BOX)
gShowBandRej  = input.bool(true, "Show band rejection markers", group=G_BOX)
gShowBandLbl  = input.bool(true, "Show inline % labels (.05% / .1%)", group=G_BOX)

// ── 🔔 Alerts ─────────────────────────────────────────────────────────────
G_AL = "🔔 Alerts"
gAlertsOn     = input.bool(true, "▶ Enable group", group=G_AL)
gAlertSweep   = input.bool(false, "Alert on sweeper", group=G_AL)
gAlertDoji    = input.bool(true,  "Alert on doji-confirmed", group=G_AL)
gAlertApex    = input.bool(true,  "Alert on apex-confirmed", group=G_AL)
gAlertMid     = input.bool(false, "Alert on midline reaction", group=G_AL)
gAlertBandRej = input.bool(false, "Alert on band rejection", group=G_AL)

// ── 🎨 Custom Colors (only used when Theme = Custom) ─────────────────────
G_COL = "🎨 Custom Colors"
gColInStat    = input.color(color.new(#06b6d4, 0), "In-stat extreme", group=G_COL)
gColOutStat   = input.color(color.new(#f59e0b, 0), "Out-of-stat extreme", group=G_COL)
gColSweeper   = input.color(color.new(#8b5cf6, 0), "Sweeper", group=G_COL)
gColDojiConf  = input.color(color.new(#f59e0b, 0), "Doji-confirmed", group=G_COL)
gColApexHr    = input.color(color.new(#ef4444, 0), "Apex-hour highlight", group=G_COL)
gColLineUp    = input.color(color.new(#10b981, 0), "Line-up readout", group=G_COL)
gColLineDn    = input.color(color.new(#ef4444, 0), "Line-down readout", group=G_COL)
gColApexUp    = input.color(color.new(#3b82f6, 0), "Apex-up readout", group=G_COL)
gColApexDn    = input.color(color.new(#8b5cf6, 0), "Apex-down readout", group=G_COL)
gColDojiRO    = input.color(color.new(#f59e0b, 0), "Doji readout", group=G_COL)
gColMid1h     = input.color(color.new(#f59e0b, 0), "1h midline", group=G_COL)
gColMid3h     = input.color(color.new(#e2eaf4, 0), "3h midline", group=G_COL)
gColBand05    = input.color(color.new(#ffffff, 75), "0.05% band", group=G_COL)
gColBand10    = input.color(color.new(#ffffff, 50), "0.10% band", group=G_COL)
gColBoxTint   = input.color(color.new(#ffffff, 94), "05 box tint", group=G_COL)
gColActiveHr  = input.color(color.new(#06b6d4, 95), "Active hour tint", group=G_COL)
gColActiveTr  = input.color(color.new(#06b6d4, 97), "Active triad tint", group=G_COL)
gColQDiv      = input.color(color.new(#ffffff, 88), "Quarter divider", group=G_COL)
```

- [ ] **Step 2: Manual smoke test**

Open `pine/quarter_theory.pine` in TradingView's Pine editor. Click "Save" / "Add to chart". The indicator should appear in the indicators list and load on a chart with no errors. Settings panel should show all 8 groups with their toggles.

**Visual checklist:**
- All 8 group headers (icons render correctly).
- Each group has its master toggle row + child toggles.
- Theme dropdown shows Dark/Light/Custom.
- Empirical data source dropdown shows Auto/NQ/ES.
- No "compilation error" messages.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add Pine settings panel with 8 grouped sections"
```

---

### Task 6.2: Theme resolver

- [ ] **Step 1: Append theme resolver to `pine/quarter_theory.pine`**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 2. THEME RESOLVER                                                        ║
// ╚══════════════════════════════════════════════════════════════════════════╝
// Single source of truth for colors. Switch on gTheme; Custom uses g* inputs.

type Theme
    color in_stat
    color out_stat
    color sweeper
    color doji_conf
    color apex_hour
    color line_up
    color line_dn
    color apex_up
    color apex_dn
    color doji
    color mid_1h
    color mid_3h
    color band_05
    color band_10
    color box_tint
    color active_hr
    color active_triad
    color q_div
    color readout_bg
    color readout_border
    color readout_text
    color readout_text_dim
    color readout_active_accent
    color conf_high
    color conf_med
    color conf_low

resolveTheme() =>
    if gTheme == "Dark"
        Theme.new(
          in_stat              = color.new(#06b6d4, 0),
          out_stat             = color.new(#f59e0b, 0),
          sweeper              = color.new(#8b5cf6, 0),
          doji_conf            = color.new(#f59e0b, 0),
          apex_hour            = color.new(#ef4444, 0),
          line_up              = color.new(#10b981, 0),
          line_dn              = color.new(#ef4444, 0),
          apex_up              = color.new(#3b82f6, 0),
          apex_dn              = color.new(#8b5cf6, 0),
          doji                 = color.new(#f59e0b, 0),
          mid_1h               = color.new(#f59e0b, 0),
          mid_3h               = color.new(#e2eaf4, 0),
          band_05              = color.new(#ffffff, 75),
          band_10              = color.new(#ffffff, 50),
          box_tint             = color.new(#ffffff, 94),
          active_hr            = color.new(#06b6d4, 95),
          active_triad         = color.new(#06b6d4, 97),
          q_div                = color.new(#ffffff, 88),
          readout_bg           = color.new(#111827, 15),
          readout_border       = color.new(#ffffff, 90),
          readout_text         = color.new(#e2eaf4, 0),
          readout_text_dim     = color.new(#8ba4bc, 0),
          readout_active_accent= color.new(#06b6d4, 65),
          conf_high            = color.new(#10b981, 0),
          conf_med             = color.new(#f59e0b, 0),
          conf_low             = color.new(#ef4444, 0))
    else if gTheme == "Light"
        Theme.new(
          in_stat              = color.new(#0891b2, 0),
          out_stat             = color.new(#d97706, 0),
          sweeper              = color.new(#7c3aed, 0),
          doji_conf            = color.new(#d97706, 0),
          apex_hour            = color.new(#dc2626, 0),
          line_up              = color.new(#059669, 0),
          line_dn              = color.new(#dc2626, 0),
          apex_up              = color.new(#2563eb, 0),
          apex_dn              = color.new(#7c3aed, 0),
          doji                 = color.new(#d97706, 0),
          mid_1h               = color.new(#d97706, 0),
          mid_3h               = color.new(#1f2937, 0),
          band_05              = color.new(#000000, 75),
          band_10              = color.new(#000000, 45),
          box_tint             = color.new(#000000, 94),
          active_hr            = color.new(#0891b2, 94),
          active_triad         = color.new(#0891b2, 97),
          q_div                = color.new(#000000, 85),
          readout_bg           = color.new(#ffffff, 8),
          readout_border       = color.new(#000000, 90),
          readout_text         = color.new(#0f172a, 0),
          readout_text_dim     = color.new(#475569, 0),
          readout_active_accent= color.new(#0891b2, 55),
          conf_high            = color.new(#059669, 0),
          conf_med             = color.new(#d97706, 0),
          conf_low             = color.new(#dc2626, 0))
    else
        Theme.new(
          in_stat              = gColInStat,
          out_stat             = gColOutStat,
          sweeper              = gColSweeper,
          doji_conf            = gColDojiConf,
          apex_hour            = gColApexHr,
          line_up              = gColLineUp,
          line_dn              = gColLineDn,
          apex_up              = gColApexUp,
          apex_dn              = gColApexDn,
          doji                 = gColDojiRO,
          mid_1h               = gColMid1h,
          mid_3h               = gColMid3h,
          band_05              = gColBand05,
          band_10              = gColBand10,
          box_tint             = gColBoxTint,
          active_hr            = gColActiveHr,
          active_triad         = gColActiveTr,
          q_div                = gColQDiv,
          readout_bg           = color.new(#111827, 15),
          readout_border       = color.new(#ffffff, 90),
          readout_text         = color.new(#e2eaf4, 0),
          readout_text_dim     = color.new(#8ba4bc, 0),
          readout_active_accent= color.new(#06b6d4, 65),
          conf_high            = color.new(#10b981, 0),
          conf_med             = color.new(#f59e0b, 0),
          conf_low             = color.new(#ef4444, 0))

var Theme T = resolveTheme()
T := resolveTheme()  // re-resolve on every bar in case user toggled theme
```

- [ ] **Step 2: Manual smoke test**

Reload indicator. Toggle Theme between Dark/Light/Custom in settings — no compile errors. Custom should expose individual color inputs.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add theme resolver with Dark/Light/Custom palettes"
```

---

### Task 6.3: Embedded empirical tables (paste-region wired up)

- [ ] **Step 1: Append the paste-region sentinels and a temporary lookup helper**

Append to `pine/quarter_theory.pine`:

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 3. EMBEDDED EMPIRICAL TABLES                                             ║
// ╚══════════════════════════════════════════════════════════════════════════╝

// ── PASTE-REGION-START ───────────────────────────────────────────────────
// (auto-generated by engine/build.py — do not edit by hand)
// (last updated: <pending first paste>)

// Empty shells so the variables exist before we have generated content.
var map<string, array<float>> EMPIRICAL_NQ_TRIAD = map.new<string, array<float>>()
var map<string, array<float>> EMPIRICAL_NQ_HOUR  = map.new<string, array<float>>()
var map<string, array<float>> QPAIR_NQ           = map.new<string, array<float>>()
var map<string, string>       QPAIR_NQ_LABELS    = map.new<string, string>()
var map<string, array<float>> EMPIRICAL_ES_TRIAD = map.new<string, array<float>>()
var map<string, array<float>> EMPIRICAL_ES_HOUR  = map.new<string, array<float>>()
var map<string, array<float>> QPAIR_ES           = map.new<string, array<float>>()
var map<string, string>       QPAIR_ES_LABELS    = map.new<string, string>()

// ── PASTE-REGION-END ─────────────────────────────────────────────────────
```

- [ ] **Step 2: Now paste the Phase 5 build output**

```bash
cd "Statistic.ally/Amas Quarter Theory"
cat pine/_generated_tables.pine
```

In TradingView's Pine editor, replace the lines between PASTE-REGION-START and PASTE-REGION-END with the contents of `pine/_generated_tables.pine`. Save.

If no `_generated_tables.pine` exists yet, run:

```bash
python3 engine/build.py --symbol NQ --since 2024-01-02 --until 2024-04-01
```

- [ ] **Step 3: Smoke test**

Reload indicator. Should compile without errors. The maps now hold real probabilities even though nothing is rendered yet.

- [ ] **Step 4: Commit (the indicator file with paste-region structure; the pasted tables themselves are gitignored as `_generated_tables.pine`)**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): wire paste-region with empty map shells"
```

---

### Task 6.4: Time/structure primitives in Pine

- [ ] **Step 1: Append**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 4. TIME / STRUCTURE PRIMITIVES                                           ║
// ╚══════════════════════════════════════════════════════════════════════════╝

NY_TZ = "America/New_York"

// Returns Q1=1..Q4=4 from the bar's NY-time minute.
quarterOfHour() =>
    int m = minute(time, NY_TZ)
    m / 15 + 1

// Returns "00-03"|"03-06"|...|"21-00" or na if hour is in 15:00-18:00 excluded gap.
blockId() =>
    int h = hour(time, NY_TZ)
    string b = na
    if h < 3
        b := "00-03"
    else if h < 6
        b := "03-06"
    else if h < 9
        b := "06-09"
    else if h < 12
        b := "09-12"
    else if h < 15
        b := "12-15"
    else if h >= 18 and h < 21
        b := "18-21"
    else if h >= 21
        b := "21-00"
    // else 15..17 → b stays na
    b

// Returns 1, 2, 3 (C1, C2, C3) within the active triad, or na in the gap.
hourIndexInTriad() =>
    int h = hour(time, NY_TZ)
    string b = blockId()
    int idx = na
    if not na(b)
        startH = str.tonumber(str.substring(b, 0, 2))
        idx := h - int(startH) + 1
    idx

// True iff this is the FIRST bar of a new quarter (the :00, :15, :30, or :45 minute bar)
isFirstBarOfQuarter() =>
    int m = minute(time, NY_TZ)
    m == 0 or m == 15 or m == 30 or m == 45

// True iff this is the last bar of a quarter (minute 14, 29, 44, 59)
isLastBarOfQuarter() =>
    int m = minute(time, NY_TZ)
    m == 14 or m == 29 or m == 44 or m == 59

// True iff this bar is part of the 05 box (minutes 0..4)
isBoxBar() =>
    int m = minute(time, NY_TZ)
    m <= 4

// Hour-close detection (this bar is the last bar of the hour)
isHourClose() =>
    minute(time, NY_TZ) == 59

// Triad-close (this bar is the last bar of C3 of the triad)
isTriadClose() =>
    isHourClose() and hourIndexInTriad() == 3
```

- [ ] **Step 2: Smoke test — temporarily add a debug label**

Append (TEMPORARILY — we'll remove before commit):

```pinescript
if barstate.islast
    debug = "Q=" + str.tostring(quarterOfHour()) + " block=" + (na(blockId()) ? "GAP" : blockId()) + " hidx=" + str.tostring(hourIndexInTriad())
    label.new(bar_index, high, debug, style=label.style_label_down)
```

Reload on a chart in NY hours. Verify the label shows correct quarter/block/hour-index.

- [ ] **Step 3: Remove the debug label, save, commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add Pine time/structure primitives (quarter/block/hour-index)"
```

---

### Task 6.5: Running aggregations (Quarter, Hour, Triad)

- [ ] **Step 1: Append**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 5. RUNNING AGGREGATIONS                                                  ║
// ╚══════════════════════════════════════════════════════════════════════════╝

type QuarterAgg
    int    qIdx
    int    anchorBar
    float  open_  = na
    float  close_ = na
    float  high_  = na
    float  low_   = na
    int    highBar = na
    int    lowBar  = na
    int    barCount = 0

quarterUpdate(QuarterAgg q, float o, float h, float l, float c) =>
    if q.barCount == 0
        q.open_ := o
    q.close_ := c
    if na(q.high_) or h > q.high_
        q.high_   := h
        q.highBar := bar_index
    if na(q.low_) or l < q.low_
        q.low_   := l
        q.lowBar := bar_index
    q.barCount += 1

type HourAgg
    int       anchorBar
    QuarterAgg q1 = na
    QuarterAgg q2 = na
    QuarterAgg q3 = na
    QuarterAgg q4 = na
    float     box05Hi = na
    float     box05Lo = na
    bool      box05Locked = false

hourHigh(HourAgg h) =>
    float hi = na
    if not na(h.q1) and (na(hi) or h.q1.high_ > hi)
        hi := h.q1.high_
    if not na(h.q2) and (na(hi) or h.q2.high_ > hi)
        hi := h.q2.high_
    if not na(h.q3) and (na(hi) or h.q3.high_ > hi)
        hi := h.q3.high_
    if not na(h.q4) and (na(hi) or h.q4.high_ > hi)
        hi := h.q4.high_
    hi

hourLow(HourAgg h) =>
    float lo = na
    if not na(h.q1) and (na(lo) or h.q1.low_ < lo)
        lo := h.q1.low_
    if not na(h.q2) and (na(lo) or h.q2.low_ < lo)
        lo := h.q2.low_
    if not na(h.q3) and (na(lo) or h.q3.low_ < lo)
        lo := h.q3.low_
    if not na(h.q4) and (na(lo) or h.q4.low_ < lo)
        lo := h.q4.low_
    lo

hourMid(HourAgg h) =>
    hi = hourHigh(h)
    lo = hourLow(h)
    na(hi) or na(lo) ? na : (hi + lo) / 2.0

type TriadAgg
    string  blockId
    int     anchorBar
    HourAgg c1 = na
    HourAgg c2 = na
    HourAgg c3 = na

triadHigh(TriadAgg t) =>
    float hi = na
    h1 = na(t.c1) ? na : hourHigh(t.c1)
    h2 = na(t.c2) ? na : hourHigh(t.c2)
    h3 = na(t.c3) ? na : hourHigh(t.c3)
    if not na(h1)
        hi := h1
    if not na(h2) and (na(hi) or h2 > hi)
        hi := h2
    if not na(h3) and (na(hi) or h3 > hi)
        hi := h3
    hi

triadLow(TriadAgg t) =>
    float lo = na
    l1 = na(t.c1) ? na : hourLow(t.c1)
    l2 = na(t.c2) ? na : hourLow(t.c2)
    l3 = na(t.c3) ? na : hourLow(t.c3)
    if not na(l1)
        lo := l1
    if not na(l2) and (na(lo) or l2 < lo)
        lo := l2
    if not na(l3) and (na(lo) or l3 < lo)
        lo := l3
    lo

// ── Bar-by-bar update of running state ───────────────────────────────────
// One TriadAgg per active 3h block. Reset at start of new block.

var TriadAgg activeTriad = na

if isFirstBarOfQuarter() and quarterOfHour() == 1 and hourIndexInTriad() == 1
    activeTriad := TriadAgg.new(blockId = blockId(), anchorBar = bar_index)

if not na(activeTriad)
    int hidx = hourIndexInTriad()
    if not na(hidx)
        // Lazily create the hour and quarter on first bar of each
        if hidx == 1 and na(activeTriad.c1)
            activeTriad.c1 := HourAgg.new(anchorBar = bar_index)
        if hidx == 2 and na(activeTriad.c2)
            activeTriad.c2 := HourAgg.new(anchorBar = bar_index)
        if hidx == 3 and na(activeTriad.c3)
            activeTriad.c3 := HourAgg.new(anchorBar = bar_index)

        HourAgg curHour = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : activeTriad.c3
        int qi = quarterOfHour()
        if qi == 1 and na(curHour.q1)
            curHour.q1 := QuarterAgg.new(qIdx = 1, anchorBar = bar_index)
        if qi == 2 and na(curHour.q2)
            curHour.q2 := QuarterAgg.new(qIdx = 2, anchorBar = bar_index)
        if qi == 3 and na(curHour.q3)
            curHour.q3 := QuarterAgg.new(qIdx = 3, anchorBar = bar_index)
        if qi == 4 and na(curHour.q4)
            curHour.q4 := QuarterAgg.new(qIdx = 4, anchorBar = bar_index)
        QuarterAgg curQ = qi == 1 ? curHour.q1 : qi == 2 ? curHour.q2 : qi == 3 ? curHour.q3 : curHour.q4

        quarterUpdate(curQ, open, high, low, close)

        // 05-box accumulation
        if isBoxBar()
            curHour.box05Hi := na(curHour.box05Hi) ? high : math.max(curHour.box05Hi, high)
            curHour.box05Lo := na(curHour.box05Lo) ? low  : math.min(curHour.box05Lo, low)
            if minute(time, NY_TZ) == 4
                curHour.box05Locked := true
```

- [ ] **Step 2: Smoke test with debug label**

Add temporarily:

```pinescript
if barstate.islast and not na(activeTriad)
    h = na(activeTriad.c2) ? "?" : (na(activeTriad.c2.q4) ? "?" : str.tostring(activeTriad.c2.q4.high_, format.mintick))
    label.new(bar_index, high, "C2.Q4 high: " + h, style=label.style_label_down)
```

Reload on NQ chart. Should show a sensible high price for the most recent C2.Q4 in view.

- [ ] **Step 3: Remove debug label, commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add Pine running aggregations (quarter/hour/triad)"
```

---

### Task 6.6: Pine classifier (parity-mirrored from Python)

- [ ] **Step 1: Append**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 6. CLASSIFIERS                                                           ║
// ╚══════════════════════════════════════════════════════════════════════════╝

// classify_hour mirrors engine/classifier.py:classify_hour with strict comparisons.
classifyHour(HourAgg h) =>
    string cls = "pending"
    if not na(h.q1) and not na(h.q2) and not na(h.q3) and not na(h.q4)
        h1 = h.q1.high_, h2 = h.q2.high_, h3 = h.q3.high_, h4 = h.q4.high_
        l1 = h.q1.low_,  l2 = h.q2.low_,  l3 = h.q3.low_,  l4 = h.q4.low_
        if h1 < h2 and h2 < h3 and h3 < h4 and l1 < l2 and l2 < l3 and l3 < l4
            cls := "line-up"
        else if h1 > h2 and h2 > h3 and h3 > h4 and l1 > l2 and l2 > l3 and l3 > l4
            cls := "line-down"
        else
            cls := "doji"
    cls

classifyTriad(TriadAgg t) =>
    string cls = "pending"
    if not na(t.c1) and not na(t.c2) and not na(t.c3)
        h1 = hourHigh(t.c1), h2 = hourHigh(t.c2), h3 = hourHigh(t.c3)
        l1 = hourLow(t.c1),  l2 = hourLow(t.c2),  l3 = hourLow(t.c3)
        if not na(h1) and not na(h2) and not na(h3) and not na(l1) and not na(l2) and not na(l3)
            if h1 < h2 and h2 < h3 and l1 < l2 and l2 < l3
                cls := "line-up"
            else if h1 > h2 and h2 > h3 and l1 > l2 and l2 > l3
                cls := "line-down"
            else if h1 < h2 and h2 > h3
                cls := "apex-up"
            else if l1 > l2 and l2 < l3
                cls := "apex-down"
            else
                cls := "doji"
    cls
```

- [ ] **Step 2: Smoke debug**

```pinescript
if barstate.islast and not na(activeTriad)
    label.new(bar_index, high, "triad: " + classifyTriad(activeTriad) + " hour: " + (na(activeTriad.c2) ? "-" : classifyHour(activeTriad.c2)),
              style=label.style_label_down)
```

Verify classifications are sensible against your eye on the chart.

- [ ] **Step 3: Remove debug, commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add Pine classifier (parity-mirrored from Python)"
```

---

### Task 6.7: State-vector builder + canonical_hash

- [ ] **Step 1: Append**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 7. STATE-VECTOR BUILDER                                                  ║
// ╚══════════════════════════════════════════════════════════════════════════╝

SCHEMA_VERSION = "v1"

ynStr(bool b) => b ? "Y" : "N"

// Resolve sym from chart symbol, gated by user override.
resolveSym() =>
    string s = "NQ"
    if gDataSource == "NQ"
        s := "NQ"
    else if gDataSource == "ES"
        s := "ES"
    else
        // Auto: detect from syminfo.ticker (NQH2024, ESM2024, NQ1!, etc.)
        t = syminfo.ticker
        s := str.startswith(t, "ES") ? "ES" : "NQ"
    s

// Build the triad state-key.
buildTriadKey(TriadAgg t, string midhrState, string mid3hState, string boxReactState) =>
    string sym = resolveSym()
    string block = na(t) ? "00-03" : t.blockId
    string c1cls = na(t) or na(t.c1) ? "doji" : classifyHour(t.c1)
    if c1cls == "pending"
        c1cls := "doji"
    int hidx = hourIndexInTriad()
    string c2q = "Q1"
    if hidx == 2
        int qi = quarterOfHour()
        c2q := "Q" + str.tostring(qi)
        if isHourClose()
            c2q := "closed"
    else if hidx >= 3
        c2q := "closed"

    string c2vh = "na", c2vl = "na"
    bool c2sw_c1h = false, c2sw_c1l = false, c2_inside = false
    if hidx >= 2 and not na(t.c1) and not na(t.c2)
        c1hi = hourHigh(t.c1), c1lo = hourLow(t.c1)
        c2hi = hourHigh(t.c2), c2lo = hourLow(t.c2)
        if not na(c1hi) and not na(c2hi)
            c2sw_c1h := c2hi > c1hi
            c2sw_c1l := c2lo < c1lo
            c2_inside := (c2hi < c1hi) and (c2lo > c1lo)
            c2vh := c2hi > c1hi ? "above" : (c2hi < c1hi ? "below" : "inside")
            c2vl := c2lo > c1lo ? "above" : (c2lo < c1lo ? "below" : "inside")

    SCHEMA_VERSION + "|sym=" + sym + "|tf=triad|block=" + block + "|c1cls=" + c1cls + "|c2q=" + c2q +
      "|c2vh=" + c2vh + "|c2vl=" + c2vl +
      "|c2sw_c1h=" + ynStr(c2sw_c1h) + "|c2sw_c1l=" + ynStr(c2sw_c1l) +
      "|c2_inside=" + ynStr(c2_inside) +
      "|midhr=" + midhrState + "|mid3h=" + mid3hState + "|box_react=" + boxReactState

// canonical_hash: byte-level emulation of low-64-bit SHA-256 → base36.
// Pine has no built-in SHA. We use a stable polynomial rolling hash
// over UTF-8 bytes. Python side uses SHA-256[:8]. The two will produce
// DIFFERENT hashes — so the Python pine_emit must be updated to use
// the same polynomial hash. This is handled in Phase 9 parity.
//
// Placeholder: simple polynomial hash. Will be replaced in Phase 9 with
// the parity-validated implementation.
canonicalHash(string s) =>
    int h = 0
    for i = 0 to str.length(s) - 1
        c = str.charat(s, i)
        codes = str.tonumber(str.format("{0,number,###}", c))  // crude codepoint
        h := (h * 131 + (na(codes) ? 0 : int(codes))) % 100000000000
    // Convert to base36
    string digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    string out = ""
    int n = h
    while n > 0
        d = n % 36
        out := str.substring(digits, d, d + 1) + out
        n := n / 36
    out == "" ? "0" : out
```

> **Note:** the placeholder `canonicalHash` does NOT match the Python SHA-256 hash. **Phase 9 fixes this** by replacing both Python and Pine hashes with the same polynomial hash so they agree. Until Phase 9, lookups will return na and the indicator will display "n/a" probabilities — that's expected.

- [ ] **Step 2: Smoke test**

```pinescript
if barstate.islast and not na(activeTriad)
    k = buildTriadKey(activeTriad, "untouched", "untouched", "none")
    label.new(bar_index, high, k, style=label.style_label_down, size=size.tiny)
```

Verify the state-key string looks sensible (correct format, all fields present).

- [ ] **Step 3: Remove debug, commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add Pine state-vector builder (hash deferred to Phase 9)"
```

---

### Task 6.8: Probability lookup with hierarchical fallback (Pine side)

- [ ] **Step 1: Append**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 8. PROBABILITY LOOKUP                                                    ║
// ╚══════════════════════════════════════════════════════════════════════════╝

// Look up a key in the appropriate triad map. Returns array<float> or na.
lookupTriadProbs(string key) =>
    sym = resolveSym()
    h = canonicalHash(key)
    map<string, array<float>> m = sym == "NQ" ? EMPIRICAL_NQ_TRIAD : EMPIRICAL_ES_TRIAD
    map.contains(m, h) ? map.get(m, h) : na

lookupHourProbs(string key) =>
    sym = resolveSym()
    h = canonicalHash(key)
    map<string, array<float>> m = sym == "NQ" ? EMPIRICAL_NQ_HOUR : EMPIRICAL_ES_HOUR
    map.contains(m, h) ? map.get(m, h) : na

lookupQpair(string key) =>
    sym = resolveSym()
    h = canonicalHash(key)
    map<string, array<float>> m = sym == "NQ" ? QPAIR_NQ : QPAIR_ES
    map<string, string>       lbl = sym == "NQ" ? QPAIR_NQ_LABELS : QPAIR_ES_LABELS
    [map.contains(m, h) ? map.get(m, h) : na,
     map.contains(lbl, h) ? map.get(lbl, h) : ""]

// Hierarchical fallback: if n < 30, strip the rightmost "|<field>=<val>" segment
// of the key and retry. Strip order is the v1 lexicographic order of fields
// (will be replaced with MI-based order in Phase 9 once parity is in).
stripLastField(string key) =>
    int idx = str.lastindexof(key, "|")
    idx > 0 ? str.substring(key, 0, idx) : key

lookupTriadProbsWithFallback(string startKey) =>
    string k = startKey
    array<float> result = na
    int stripped = 0
    for i = 0 to 8
        result := lookupTriadProbs(k)
        if not na(result) and array.get(result, array.size(result) - 1) >= 30
            break
        k := stripLastField(k)
        stripped += 1
        if str.length(k) < 20  // sanity floor — don't strip past version|sym
            break
    [result, stripped]
```

- [ ] **Step 2: Smoke test (this WILL show "n/a" until Phase 9 fixes hash parity)**

```pinescript
if barstate.islast and not na(activeTriad)
    k = buildTriadKey(activeTriad, "untouched", "untouched", "none")
    [probs, stripped] = lookupTriadProbsWithFallback(k)
    msg = na(probs) ? "no match" : "n=" + str.tostring(array.get(probs, array.size(probs) - 1)) + " stripped=" + str.tostring(stripped)
    label.new(bar_index, high, msg, style=label.style_label_down, size=size.tiny)
```

Expect "no match" — this is fine until Phase 9.

- [ ] **Step 3: Remove debug, commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add Pine probability lookup with hierarchical fallback"
```

---

### Phase 6 smoke test

- [ ] **The indicator loads on a chart with no compile errors.**

- [ ] **Settings panel shows all 8 groups with master toggles.**

- [ ] **Theme switch (Dark/Light/Custom) doesn't break compilation.**

- [ ] **Embedded paste-region is wired up (`EMPIRICAL_NQ_TRIAD` etc. exist as variables).**

- [ ] **Pine classifier and state-vector builder produce sensible strings (verified via temporary debug labels in tasks above).**

- [ ] **Lookups currently return "no match" — parity fix is in Phase 9. This is OK.**

**End of Phase 6.** Move to [Phase 7 — Pine annotations + bands + midlines](phase-7-pine-annotations.md).
