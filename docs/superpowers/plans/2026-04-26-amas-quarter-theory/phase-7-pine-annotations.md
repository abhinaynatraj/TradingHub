# Phase 7 — Pine Annotations, Bands & Midlines

> **Sub-skill:** Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Render all on-chart annotations: quarter dividers, in-stat / out-of-stat extremes, sweepers, bias-shifts, doji-confirmed, hour/triad verdicts, apex-hour highlight, 05-box column, ±0.05/0.10% bands, 1h+3h midlines, midline reactions, band rejections.

**Prereq:** Phase 6 complete.

Each task ends with: load on chart → visually verify → commit.

---

### Task 7.1: Quarter dividers (vertical dotted lines)

- [ ] **Step 1: Append**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 9. RENDERERS — Quarter dividers                                          ║
// ╚══════════════════════════════════════════════════════════════════════════╝

if gQStructOn and gShowQDiv and isFirstBarOfQuarter()
    int q = quarterOfHour()
    color c = T.q_div
    int width = q == 1 ? 1 : 1
    line.new(bar_index, low - syminfo.mintick, bar_index, high + syminfo.mintick,
             xloc=xloc.bar_index, extend=extend.both,
             color=c, style=line.style_dotted, width=q == 1 ? 2 : 1)
```

- [ ] **Step 2: Smoke**

Reload on 15m NQ chart. Should see thin dotted vertical lines at every :15, :30, :45 boundary; a slightly heavier dotted line at every :00 boundary.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render quarter dividers (dotted vertical lines)"
```

---

### Task 7.2: 05-box full-height column

- [ ] **Step 1: Append**

```pinescript
// ── 05-box column ────────────────────────────────────────────────────────
// Full chart-height tinted column spanning :00..:04 of each hour.

if gBoxOn and gShowBoxCol and isFirstBarOfQuarter() and quarterOfHour() == 1
    // Start of a new hour — schedule the box column. We draw it as a box
    // spanning bar_index..bar_index+4 with a very tall vertical extent so it
    // visually occupies the full chart height.
    box.new(left=bar_index, top=high * 10, right=bar_index + 4, bottom=low * 0.1,
            xloc=xloc.bar_index, bgcolor=T.box_tint, border_color=color.new(T.box_tint, 0),
            border_width=1, border_style=line.style_solid)
```

> Pine's `box.new` doesn't natively support "infinite vertical extent"; we approximate by setting `top` very high and `bottom` very low. On most charts this results in a column that fills the visible price area.

- [ ] **Step 2: Smoke** — reload, see a faint column shading the first 5 minutes of each hour.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render 05-box as full-height tinted column"
```

---

### Task 7.3: ±0.05% / ±0.10% bands with inline labels

- [ ] **Step 1: Append**

```pinescript
// ── 05-bands (drawn at hour-close of the :04 minute) ─────────────────────

bandLevels(float boxHi, float boxLo) =>
    [boxHi * 1.0010, boxHi * 1.0005, boxLo * 0.9995, boxLo * 0.9990]

if gBoxOn and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg curH = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : hidx == 3 ? activeTriad.c3 : na
    if not na(curH) and curH.box05Locked and minute(time, NY_TZ) == 4
        [u10, u05, l05, l10] = bandLevels(curH.box05Hi, curH.box05Lo)
        int hourStartBar = curH.anchorBar
        int hourEndBar = bar_index + 55  // approximate: :04 + 55 minutes ≈ :59. Re-extend each new bar.
        if gShowBand10
            line.new(hourStartBar, u10, hourEndBar, u10, xloc=xloc.bar_index,
                     color=T.band_10, style=line.style_dotted, width=2)
            line.new(hourStartBar, l10, hourEndBar, l10, xloc=xloc.bar_index,
                     color=T.band_10, style=line.style_dotted, width=2)
            if gShowBandLbl
                label.new(hourEndBar, u10, ".1%", xloc=xloc.bar_index, color=color.new(T.band_10, 100),
                          textcolor=T.band_10, style=label.style_label_left, size=size.tiny)
                label.new(hourEndBar, l10, ".1%", xloc=xloc.bar_index, color=color.new(T.band_10, 100),
                          textcolor=T.band_10, style=label.style_label_left, size=size.tiny)
        if gShowBand05
            line.new(hourStartBar, u05, hourEndBar, u05, xloc=xloc.bar_index,
                     color=T.band_05, style=line.style_dotted, width=1)
            line.new(hourStartBar, l05, hourEndBar, l05, xloc=xloc.bar_index,
                     color=T.band_05, style=line.style_dotted, width=1)
            if gShowBandLbl
                label.new(hourEndBar, u05, ".05%", xloc=xloc.bar_index, color=color.new(T.band_05, 100),
                          textcolor=T.band_05, style=label.style_label_left, size=size.tiny)
                label.new(hourEndBar, l05, ".05%", xloc=xloc.bar_index, color=color.new(T.band_05, 100),
                          textcolor=T.band_05, style=label.style_label_left, size=size.tiny)
```

- [ ] **Step 2: Smoke** — reload. Should see four dotted horizontal lines per hour (heavier .1%, lighter .05%), with `.05%` and `.1%` labels at right edge.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render ±0.05/0.10% bands with inline labels"
```

---

### Task 7.4: Band rejection markers

- [ ] **Step 1: Append**

```pinescript
// ── Band rejection markers ───────────────────────────────────────────────
// Wick-and-close: bar.high > band AND bar.close < band → upper rejection.
// 10 takes precedence over 05.

detectBandRejection(float h, float l, float c, float u10, float u05, float l05_, float l10) =>
    string side = "", level = ""
    if h > u10 and c < u10
        side := "upper"
        level := "10"
    else if h > u05 and c < u05
        side := "upper"
        level := "05"
    else if l < l10 and c > l10
        side := "lower"
        level := "10"
    else if l < l05_ and c > l05_
        side := "lower"
        level := "05"
    [side, level]

if gBoxOn and gShowBandRej and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg curH = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : hidx == 3 ? activeTriad.c3 : na
    if not na(curH) and curH.box05Locked and not na(curH.box05Hi)
        [u10, u05, l05_, l10] = bandLevels(curH.box05Hi, curH.box05Lo)
        [side, level] = detectBandRejection(high, low, close, u10, u05, l05_, l10)
        if side != ""
            color cMark = level == "10" ? T.band_10 : T.band_05
            float anchorY = side == "upper" ? high : low
            label.new(bar_index, anchorY, "rej " + level + "%",
                      style=side == "upper" ? label.style_label_down : label.style_label_up,
                      color=color.new(cMark, 80), textcolor=cMark, size=size.tiny)
```

- [ ] **Step 2: Smoke** — chart should show small rejection labels on candles that wick-and-close against the bands.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render band rejection markers (10 takes precedence over 05)"
```

---

### Task 7.5: 1h midline + reaction markers

- [ ] **Step 1: Append**

```pinescript
// ── 1h midline ───────────────────────────────────────────────────────────
// Source: prior hour mid if current hour strictly inside prior; else current.

resolve1hMid(HourAgg cur, HourAgg prior) =>
    float mid = na
    string source = "current"
    if not na(cur) and not na(hourHigh(cur)) and not na(hourLow(cur))
        if not na(prior) and not na(hourHigh(prior)) and not na(hourLow(prior))
            curHi = hourHigh(cur), curLo = hourLow(cur)
            prHi = hourHigh(prior), prLo = hourLow(prior)
            if curLo > prLo and curHi < prHi
                mid := (prHi + prLo) / 2.0
                source := "prior"
            else
                mid := (curHi + curLo) / 2.0
        else
            mid := (hourHigh(cur) + hourLow(cur)) / 2.0
    [mid, source]

// Track prior hour as it closes
var HourAgg priorHour1h = na
var HourAgg priorHour3h_C1 = na
var HourAgg priorHour3h_C2 = na

if isHourClose() and not na(activeTriad)
    int hidx = hourIndexInTriad()
    if hidx == 1
        priorHour3h_C1 := activeTriad.c1
    if hidx == 2
        priorHour3h_C2 := activeTriad.c2

if isHourClose() and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg justClosed = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : activeTriad.c3
    priorHour1h := justClosed

// Draw 1h midline live
if gMidOn and gShowMid1h and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg curH = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : hidx == 3 ? activeTriad.c3 : na
    [mid, _src] = resolve1hMid(curH, priorHour1h)
    if not na(mid)
        line.new(bar_index, mid, bar_index + 1, mid, xloc=xloc.bar_index,
                 color=T.mid_1h, width=gMid1hWidth, style=line.style_solid)

// Midline reaction detection
detectMidReaction(float mid, float h, float l, float c) =>
    string r = ""
    if l < mid and c > mid
        r := "support"
    else if h > mid and c < mid
        r := "reject"
    r

if gMidOn and gShowMidReact and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg curH = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : hidx == 3 ? activeTriad.c3 : na
    [mid, _src] = resolve1hMid(curH, priorHour1h)
    if not na(mid)
        r = detectMidReaction(mid, high, low, close)
        if r == "support"
            label.new(bar_index, low, "●", style=label.style_label_up,
                      color=color.new(T.mid_1h, 90), textcolor=T.mid_1h, size=size.tiny)
        else if r == "reject"
            label.new(bar_index, high, "●", style=label.style_label_down,
                      color=color.new(T.mid_1h, 90), textcolor=T.mid_1h, size=size.tiny)
```

- [ ] **Step 2: Smoke** — should see a dashed/solid horizontal line at the active hour's mid, plus dot markers when price wicks-and-closes through it.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render 1h midline + reaction markers"
```

---

### Task 7.6: 3h midline + reactions

- [ ] **Step 1: Append**

```pinescript
// ── 3h midline ───────────────────────────────────────────────────────────
// Source: prior 3h block's mid if current 3h block strictly inside; else current.
// We track the prior triad's high/low at triad-close for use during the next.

var float priorTriadHi = na
var float priorTriadLo = na

if isTriadClose() and not na(activeTriad)
    priorTriadHi := triadHigh(activeTriad)
    priorTriadLo := triadLow(activeTriad)

resolve3hMid(TriadAgg cur) =>
    float mid = na
    string source = "current"
    curHi = na(cur) ? na : triadHigh(cur)
    curLo = na(cur) ? na : triadLow(cur)
    if not na(curHi) and not na(curLo)
        if not na(priorTriadHi) and not na(priorTriadLo) and curLo > priorTriadLo and curHi < priorTriadHi
            mid := (priorTriadHi + priorTriadLo) / 2.0
            source := "prior"
        else
            mid := (curHi + curLo) / 2.0
    [mid, source]

if gMidOn and gShowMid3h and not na(activeTriad)
    [mid, _src] = resolve3hMid(activeTriad)
    if not na(mid)
        line.new(bar_index, mid, bar_index + 1, mid, xloc=xloc.bar_index,
                 color=T.mid_3h, width=gMid3hWidth, style=line.style_solid)
```

- [ ] **Step 2: Smoke** — second horizontal line in a different (lighter) color through the active triad.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render 3h midline (prior-vs-current source resolution)"
```

---

### Task 7.7: In-stat / out-of-stat extreme labels (anchored to candles)

- [ ] **Step 1: Append**

```pinescript
// ── Quarter extreme labels (anchored to the bar that printed the extreme) ─
// Drawn at hour close, anchored to the high_anchor_bar / low_anchor_bar.

if gQStructOn and isHourClose() and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg justClosed = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : activeTriad.c3
    if not na(justClosed) and not na(justClosed.q1) and not na(justClosed.q2) and
       not na(justClosed.q3) and not na(justClosed.q4)
        // Find which quarter holds the hour's high and low
        float hi = hourHigh(justClosed)
        float lo = hourLow(justClosed)
        QuarterAgg qHi = justClosed.q1.high_ == hi ? justClosed.q1 :
                         justClosed.q2.high_ == hi ? justClosed.q2 :
                         justClosed.q3.high_ == hi ? justClosed.q3 :
                         justClosed.q4
        QuarterAgg qLo = justClosed.q1.low_ == lo ? justClosed.q1 :
                         justClosed.q2.low_ == lo ? justClosed.q2 :
                         justClosed.q3.low_ == lo ? justClosed.q3 :
                         justClosed.q4
        bool inStatHi = qHi.qIdx == 1 or qHi.qIdx == 4
        bool inStatLo = qLo.qIdx == 1 or qLo.qIdx == 4

        if (inStatHi and gShowInStat) or (not inStatHi and gShowOutStat)
            string txtHi = "Q" + str.tostring(qHi.qIdx) + " " + (inStatHi ? "in-stat" : "out-of-stat") + " high"
            color cHi = inStatHi ? T.in_stat : T.out_stat
            label.new(qHi.highBar, qHi.high_, txtHi, xloc=xloc.bar_index,
                      style=label.style_label_down, color=color.new(cHi, 85),
                      textcolor=cHi, size=size.tiny)

        if (inStatLo and gShowInStat) or (not inStatLo and gShowOutStat)
            string txtLo = "Q" + str.tostring(qLo.qIdx) + " " + (inStatLo ? "in-stat" : "out-of-stat") + " low"
            color cLo = inStatLo ? T.in_stat : T.out_stat
            label.new(qLo.lowBar, qLo.low_, txtLo, xloc=xloc.bar_index,
                      style=label.style_label_up, color=color.new(cLo, 85),
                      textcolor=cLo, size=size.tiny)
```

- [ ] **Step 2: Smoke** — at every hour close, see two labels: one above the hour's high (in-stat or out-of-stat), one below the hour's low.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render in-stat / out-of-stat extreme labels"
```

---

### Task 7.8: Sweeper markers + bias-shift arrows

- [ ] **Step 1: Append**

```pinescript
// ── Sweepers (live) ──────────────────────────────────────────────────────
// On every quarter-close bar, check whether THIS quarter swept any prior
// quarter's high/low. If so, draw markers and (if a flip from prior bias)
// emit a doji-confirmed marker.

var int lastSweepBias = 0  // -1 down, 0 none, +1 up — per active hour
var bool dojiConfirmedThisHour = false

if isFirstBarOfQuarter() and quarterOfHour() == 1
    lastSweepBias := 0
    dojiConfirmedThisHour := false

detectSweepsForQuarter(HourAgg h, int byQ) =>
    array<string> events = array.new<string>()
    QuarterAgg byQuarter = byQ == 2 ? h.q2 : byQ == 3 ? h.q3 : h.q4
    if not na(byQuarter)
        for tQ = 1 to byQ - 1
            QuarterAgg targ = tQ == 1 ? h.q1 : tQ == 2 ? h.q2 : h.q3
            if not na(targ)
                if byQuarter.high_ > targ.high_
                    array.push(events, "Q" + str.tostring(byQ) + "→Q" + str.tostring(tQ) + " high")
                if byQuarter.low_ < targ.low_
                    array.push(events, "Q" + str.tostring(byQ) + "→Q" + str.tostring(tQ) + " low")
    events

if gQStructOn and isLastBarOfQuarter() and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg curH = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : activeTriad.c3
    int byQ = quarterOfHour()
    if not na(curH) and byQ >= 2
        events = detectSweepsForQuarter(curH, byQ)
        if array.size(events) > 0 and gShowSweepers
            // Aggregate bias direction
            int newBias = 0
            for i = 0 to array.size(events) - 1
                e = array.get(events, i)
                if str.endswith(e, "high")
                    newBias := 1
                if str.endswith(e, "low") and newBias == 0
                    newBias := -1
                if str.endswith(e, "low") and newBias == 1
                    // mixed in same quarter: flip-y
                    newBias := 0
            if newBias != 0
                if lastSweepBias != 0 and lastSweepBias != newBias
                    dojiConfirmedThisHour := true
                lastSweepBias := newBias

            // Sweeper marker
            label.new(bar_index, newBias > 0 ? high : low,
                      "Q" + str.tostring(byQ) + " sweeper",
                      xloc=xloc.bar_index,
                      style=newBias > 0 ? label.style_label_down : label.style_label_up,
                      color=color.new(T.sweeper, 80), textcolor=T.sweeper, size=size.tiny)

            // Bias-shift arrow (in chart margin via right-extend technique: put at bar_index)
            if gShowBiasShift
                color cArr = newBias > 0 ? T.line_up : T.line_dn
                string arr = newBias > 0 ? "▲" : "▼"
                label.new(bar_index, newBias > 0 ? high : low, arr, xloc=xloc.bar_index,
                          style=newBias > 0 ? label.style_label_left : label.style_label_left,
                          color=color.new(cArr, 100), textcolor=cArr, size=size.small)

// Doji-confirmed marker (drawn when the second-direction sweep happens)
if gShowDojiConf and dojiConfirmedThisHour and isLastBarOfQuarter()
    label.new(bar_index, low, "◆ doji-confirmed", xloc=xloc.bar_index,
              style=label.style_label_up, color=color.new(T.doji_conf, 80),
              textcolor=T.doji_conf, size=size.tiny)
```

- [ ] **Step 2: Smoke** — when Q2/Q3/Q4 sweeps a prior quarter, see a sweeper label; when bias flips within an hour, see the doji-confirmed marker.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render sweepers, bias-shift arrows, doji-confirmed"
```

---

### Task 7.9: Hour & triad close verdicts; apex-hour highlight

- [ ] **Step 1: Append**

```pinescript
// ── Hour close verdict ───────────────────────────────────────────────────
if gVerdictsOn and gShowHourVerd and isHourClose() and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg justClosed = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : activeTriad.c3
    if not na(justClosed)
        cls = classifyHour(justClosed)
        color c = cls == "line-up" ? T.line_up :
                  cls == "line-down" ? T.line_dn :
                  T.doji
        // Find Q4 anchor bar
        QuarterAgg q4 = justClosed.q4
        if not na(q4)
            label.new(bar_index, hourLow(justClosed), cls + " hour", xloc=xloc.bar_index,
                      style=label.style_label_up, color=color.new(c, 85),
                      textcolor=c, size=size.small)

// ── Triad close verdict ──────────────────────────────────────────────────
if gVerdictsOn and gShowTriadVerd and isTriadClose() and not na(activeTriad)
    cls = classifyTriad(activeTriad)
    color c = cls == "line-up" ? T.line_up :
              cls == "line-down" ? T.line_dn :
              cls == "apex-up" ? T.apex_up :
              cls == "apex-down" ? T.apex_dn :
              T.doji
    label.new(bar_index, triadLow(activeTriad), cls + " triad", xloc=xloc.bar_index,
              style=label.style_label_up, color=color.new(c, 80),
              textcolor=c, size=size.normal)

    // Apex-hour highlight: if apex-up or apex-down, highlight C2 of triad
    if gShowApexHr and (cls == "apex-up" or cls == "apex-down") and not na(activeTriad.c2)
        int c2Q1Bar = na(activeTriad.c2.q1) ? activeTriad.c2.anchorBar : activeTriad.c2.q1.anchorBar
        int c2Q4Bar = na(activeTriad.c2.q4) ? bar_index : activeTriad.c2.q4.anchorBar + 14
        box.new(c2Q1Bar, hourHigh(activeTriad.c2), c2Q4Bar, hourLow(activeTriad.c2),
                xloc=xloc.bar_index, bgcolor=color.new(T.apex_hour, 92),
                border_color=color.new(T.apex_hour, 70), border_width=1)
        // Apex-hour label anchored to Q4 of C2
        label.new(c2Q4Bar, hourLow(activeTriad.c2), "apex hour", xloc=xloc.bar_index,
                  style=label.style_label_up, color=color.new(T.apex_hour, 80),
                  textcolor=T.apex_hour, size=size.small)
```

- [ ] **Step 2: Smoke** — at hour close, see "line-up hour" / "doji hour" / etc. labels; at triad close, see triad verdict; on apex triads, see C2 highlighted with overlay box.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render hour/triad verdicts and apex-hour highlight"
```

---

### Task 7.10: Active block tints (active hour, active triad)

- [ ] **Step 1: Append**

```pinescript
// ── Active hour & triad tints ────────────────────────────────────────────
// Drawn live; the box is recreated on every bar to follow price action.

var box activeHourTint = na
var box activeTriadTint = na

if gReadoutsOn and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg curH = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : activeTriad.c3
    if not na(curH)
        // Active hour tint: from anchor bar to current bar, full chart height
        if not na(activeHourTint)
            box.delete(activeHourTint)
        activeHourTint := box.new(curH.anchorBar, high * 5, bar_index, low * 0.2,
                                  xloc=xloc.bar_index, bgcolor=T.active_hr,
                                  border_color=color.new(T.active_hr, 100), border_width=0)
    // Active triad tint
    if not na(activeTriadTint)
        box.delete(activeTriadTint)
    activeTriadTint := box.new(activeTriad.anchorBar, high * 5, bar_index, low * 0.2,
                               xloc=xloc.bar_index, bgcolor=T.active_triad,
                               border_color=color.new(T.active_triad, 100), border_width=0)
```

- [ ] **Step 2: Smoke** — active hour gets a faint tint; active triad gets a slightly different (fainter) tint underneath.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render active hour and active triad tints"
```

---

### Phase 7 smoke test

- [ ] **All annotations render correctly on a 15m NQ chart in NY hours.**

- [ ] **Toggle each settings group's master toggle off → relevant annotations disappear.**

- [ ] **Switch theme to Light → colors invert tastefully.**

- [ ] **No "max_labels_count exceeded" or "max_lines_count exceeded" errors.** (If you see them, label housekeeping in Phase 8 will fix it.)

**End of Phase 7.** Move to [Phase 8 — Pine readouts + theming polish + alerts](phase-8-pine-readouts.md).
