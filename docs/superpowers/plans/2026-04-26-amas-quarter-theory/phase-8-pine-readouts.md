# Phase 8 — Pine Readouts, OHLC Overlay, Alerts, Label Housekeeping

> **Sub-skill:** Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Centered horizontal readouts under each 1h block and 3h triad showing live probabilities; 3h running OHLC + flip-level overlay; tooltips for full state breakdown; alerts; label housekeeping (FIFO under 500 cap).

**Prereq:** Phase 7 complete. Tables loaded in paste-region. Note: empirical lookups still return na until Phase 9 fixes hash parity — readouts will display "—" for probabilities; structure and styling can still be verified.

---

### Task 8.1: 1h block readout (centered horizontally)

- [ ] **Step 1: Append**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 9b. RENDERERS — Block readouts                                           ║
// ╚══════════════════════════════════════════════════════════════════════════╝

// ATR-based vertical offset so the readout sits below the block's price action.
atrOffset() => ta.atr(20) * 2.0

// Format probability as percentage. "—" if na.
fmtP(float p) => na(p) ? "—" : str.tostring(math.round(p * 100)) + "%"

// Format n with confidence color
nColor(float n) =>
    na(n) ? T.readout_text_dim :
      n >= 100 ? T.conf_high :
      n >= 30  ? T.conf_med :
                 T.conf_low

// Build the multi-line text content for an hour readout.
// probs (hour-level): [p_lup, p_ldn, p_doji, n] — in that order.
buildHourReadout(string title, array<float> probs, string hourState, string boxState) =>
    string ln1 = "▸ " + title
    string ln2, ln3
    if na(probs)
        ln2 := "—"
    else
        p_lup = array.get(probs, 0)
        p_ldn = array.get(probs, 1)
        p_doji = array.get(probs, 2)
        ln2 := "L-up " + fmtP(p_lup) + " · L-dn " + fmtP(p_ldn) + " · Doji " + fmtP(p_doji)
        if gShowN
            n = array.get(probs, 3)
            ln2 := ln2 + "  n=" + str.tostring(int(n))
    ln3 := hourState + (boxState != "" ? "  " + boxState : "")
    ln1 + "\n" + ln2 + "\n" + ln3

// Track per-block readout labels for housekeeping.
var array<label> hourReadoutLabels = array.new<label>()
var array<box> hourReadoutBoxes = array.new<box>()

// State strings used by the readout.
var string midhrState = "untouched"
var string mid3hState = "untouched"
var string boxReactState = "none"

// Update midhrState from any reactions emitted on this bar.
if gMidOn and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg curH = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : activeTriad.c3
    [mid, _src] = resolve1hMid(curH, priorHour1h)
    if not na(mid)
        rxn = detectMidReaction(mid, high, low, close)
        if rxn != ""
            midhrState := rxn

// Reset state on hour and triad rollovers
if isFirstBarOfQuarter() and quarterOfHour() == 1
    midhrState := "untouched"
    boxReactState := "none"
if isFirstBarOfQuarter() and quarterOfHour() == 1 and hourIndexInTriad() == 1
    mid3hState := "untouched"

// Update boxReactState from band rejection events on this bar
if gBoxOn and not na(activeTriad)
    int hidx2 = hourIndexInTriad()
    HourAgg curH2 = hidx2 == 1 ? activeTriad.c1 : hidx2 == 2 ? activeTriad.c2 : activeTriad.c3
    if not na(curH2) and curH2.box05Locked and not na(curH2.box05Hi)
        [u10, u05, l05_, l10] = bandLevels(curH2.box05Hi, curH2.box05Lo)
        [side, level] = detectBandRejection(high, low, close, u10, u05, l05_, l10)
        if side != ""
            string token = level + (side == "upper" ? "up_rejected" : "dn_rejected")
            if boxReactState == "none" or boxReactState == token
                boxReactState := token
            else
                boxReactState := "multi"

// Render hour readout each bar (active block) — recreate label in place to update text.
var label activeHourReadout = na
var box   activeHourReadoutBox = na

if gReadoutsOn and gShow1h and not na(activeTriad)
    int hidx3 = hourIndexInTriad()
    HourAgg curH3 = hidx3 == 1 ? activeTriad.c1 : hidx3 == 2 ? activeTriad.c2 : activeTriad.c3
    if not na(curH3) and not na(hourLow(curH3))
        // Build state-key for hour
        // (Hour-state-key construction — placeholder until full builder in 6.7 covers hours)
        string hourTitle = "HOUR " + str.tostring(hour(time, NY_TZ)) + ":00 · Q" + str.tostring(quarterOfHour()) + " forming"
        string hourStateText = "midhr=" + midhrState + (boxReactState != "none" ? "  box=" + boxReactState : "")
        // Hour-level lookup will return na for now (no hour-key builder yet); show "—"
        array<float> hprobs = na
        string text = buildHourReadout(hourTitle, hprobs, hourStateText, "")
        float yPos = hourLow(curH3) - atrOffset()
        // Center bar = anchor + 30 minutes (30 bars on 1m chart, 2 bars on 15m chart)
        int centerBar = curH3.anchorBar + (timeframe.in_seconds("") <= 60 ? 30 : 2)

        if not na(activeHourReadout)
            label.delete(activeHourReadout)
            box.delete(activeHourReadoutBox)
        activeHourReadoutBox := box.new(centerBar - 5, yPos + atrOffset()/2, centerBar + 5, yPos - atrOffset()/2,
                                        xloc=xloc.bar_index,
                                        bgcolor=T.readout_bg, border_color=T.readout_active_accent, border_width=2)
        activeHourReadout := label.new(centerBar, yPos, text, xloc=xloc.bar_index,
                                       style=label.style_label_center, color=color.new(T.readout_bg, 100),
                                       textcolor=T.readout_text, size=size.small)
```

- [ ] **Step 2: Smoke** — under the active hour, see a 3-line readout with title + probabilities + state.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render 1h hour readout (centered, ATR-offset)"
```

---

### Task 8.2: 3h triad readout

- [ ] **Step 1: Append**

```pinescript
buildTriadReadout(string title, string stateLine, array<float> probs, string qpairLabel, array<float> qpairData) =>
    string l1 = "▸ " + title
    string l2 = stateLine
    string l3
    if na(probs)
        l3 := "—"
    else
        p_lup = array.get(probs, 0), p_ldn = array.get(probs, 1)
        p_aup = array.get(probs, 2), p_adn = array.get(probs, 3), p_doji = array.get(probs, 4)
        l3 := "L-up " + fmtP(p_lup) + " · A-up " + fmtP(p_aup) + " · Doji " + fmtP(p_doji) +
              " · L-dn " + fmtP(p_ldn) + " · A-dn " + fmtP(p_adn)
        if gShowN
            n = array.get(probs, 5)
            l3 := l3 + "  n=" + str.tostring(int(n))
    string l4 = ""
    if gShowQPair and qpairLabel != "" and not na(qpairData)
        wr = array.get(qpairData, 0), ev = array.get(qpairData, 1), n = array.get(qpairData, 2)
        l4 := "🎯 " + qpairLabel + " · WR " + fmtP(wr) + " · EV " + str.tostring(ev, "+#.##") + "R · n=" + str.tostring(int(n))
    string text = l1 + "\n" + l2 + "\n" + l3
    if l4 != ""
        text := text + "\n" + l4
    text

var label activeTriadReadout = na
var box activeTriadReadoutBox = na

if gReadoutsOn and gShow3h and not na(activeTriad)
    string triadTitle = "TRIAD " + activeTriad.blockId + " · C" + str.tostring(hourIndexInTriad()) + " forming · " + classifyTriad(activeTriad) + " tracking"
    string stateLine = "mid3h=" + mid3hState + " · midhr=" + midhrState
    string triadKey = buildTriadKey(activeTriad, midhrState, mid3hState, boxReactState)
    [tprobs, _stripped] = lookupTriadProbsWithFallback(triadKey)
    // QPair uses a coarser key: v1|sym=...|tf=qpair|block=...|c1cls=...|dq=<global decision quarter>
    int dq = (hourIndexInTriad() - 1) * 4 + quarterOfHour()
    string c1clsKey = na(activeTriad.c1) ? "doji" : (classifyHour(activeTriad.c1) == "pending" ? "doji" : classifyHour(activeTriad.c1))
    string qpairKey = "v1|sym=" + resolveSym() + "|tf=qpair|block=" + activeTriad.blockId +
                      "|c1cls=" + c1clsKey + "|dq=" + str.tostring(dq)
    [qpData, qpLabel] = lookupQpair(qpairKey)

    string txt = buildTriadReadout(triadTitle, stateLine, tprobs, qpLabel, qpData)

    // Position: below the triad's lowest price, with extra ATR offset to clear hour readout
    float lowestHourReadoutY = hourLow(activeTriad.c1)  // approximation
    if not na(activeTriad.c2)
        l2 = hourLow(activeTriad.c2)
        if not na(l2) and l2 < lowestHourReadoutY
            lowestHourReadoutY := l2
    float yPos = lowestHourReadoutY - atrOffset() * 2.5
    int centerBar = activeTriad.anchorBar + (timeframe.in_seconds("") <= 60 ? 90 : 6)  // mid of triad

    if not na(activeTriadReadout)
        label.delete(activeTriadReadout)
        box.delete(activeTriadReadoutBox)
    activeTriadReadoutBox := box.new(centerBar - 8, yPos + atrOffset(), centerBar + 8, yPos - atrOffset(),
                                     xloc=xloc.bar_index,
                                     bgcolor=T.readout_bg, border_color=T.readout_active_accent, border_width=2)
    activeTriadReadout := label.new(centerBar, yPos, txt, xloc=xloc.bar_index,
                                    style=label.style_label_center, color=color.new(T.readout_bg, 100),
                                    textcolor=T.readout_text, size=size.small,
                                    tooltip="Full state-key: " + triadKey)
```

- [ ] **Step 2: Smoke** — see a fuller readout below the active triad with title, state, all 5 probabilities, and (when available) a quarter-pair recommendation.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render 3h triad readout with qpair recommendation"
```

---

### Task 8.3: 3h running OHLC + flip-level overlay (A-4)

- [ ] **Step 1: Append**

```pinescript
// ── Running 3h OHLC overlay (small, near the triad readout) ──────────────
// Shows: current C1.h, C1.l, C2.h, C2.l, C3.h, C3.l plus the level needed
// for the next bar to flip line/apex.

flipLevels(TriadAgg t) =>
    // For line-up: need C3.high > C2.high AND C3.low > C2.low. Whichever is higher reachable.
    // For apex-up: need C2 to be the swing high. We surface "C3 needs to close < C2.high to confirm apex-up"
    // For simplicity v1, surface ONE level: the threshold C3 must clear/break.
    string txt = "—"
    if not na(t.c1) and not na(t.c2)
        h1 = hourHigh(t.c1), h2 = hourHigh(t.c2)
        l1 = hourLow(t.c1),  l2 = hourLow(t.c2)
        cls = classifyTriad(t)
        if cls == "pending"
            // C3 still forming
            txt := "C3 line-up: needs > " + str.tostring(h2, format.mintick) +
                   " · apex-up: needs < " + str.tostring(h2, format.mintick)
    txt

if gVerdictsOn and gShowOhlcOver and not na(activeTriad)
    string ohlc = "C1 " + str.tostring(hourHigh(activeTriad.c1), format.mintick) + "/" + str.tostring(hourLow(activeTriad.c1), format.mintick) +
                  " | C2 " + (na(activeTriad.c2) ? "-" : str.tostring(hourHigh(activeTriad.c2), format.mintick) + "/" + str.tostring(hourLow(activeTriad.c2), format.mintick)) +
                  " | C3 " + (na(activeTriad.c3) ? "(forming)" : str.tostring(hourHigh(activeTriad.c3), format.mintick) + "/" + str.tostring(hourLow(activeTriad.c3), format.mintick))
    string flip = flipLevels(activeTriad)

    // Place small overlay near top-right of price area
    var label ohlcOverlay = na
    if not na(ohlcOverlay)
        label.delete(ohlcOverlay)
    ohlcOverlay := label.new(bar_index, high * 1.0005, ohlc + "\n" + flip,
                             xloc=xloc.bar_index, style=label.style_label_left,
                             color=color.new(T.readout_bg, 30),
                             textcolor=T.readout_text_dim, size=size.tiny)
```

- [ ] **Step 2: Smoke** — small text label near the top-right showing C1/C2/C3 OHLC and the flip-level threshold.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): render 3h running OHLC + flip-level overlay"
```

---

### Task 8.4: Alerts

- [ ] **Step 1: Append**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 10. ALERTS                                                               ║
// ╚══════════════════════════════════════════════════════════════════════════╝

// We track which events fired this bar to fire alerts once.
var bool alertSweeperFiredThisBar = false
var bool alertDojiFiredThisBar = false
var bool alertApexFiredThisBar = false

if barstate.isnew
    alertSweeperFiredThisBar := false
    alertDojiFiredThisBar := false
    alertApexFiredThisBar := false

// Sweeper alert
if gAlertsOn and gAlertSweep and not alertSweeperFiredThisBar and isLastBarOfQuarter() and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg curH = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : activeTriad.c3
    int byQ = quarterOfHour()
    if not na(curH) and byQ >= 2
        events = detectSweepsForQuarter(curH, byQ)
        if array.size(events) > 0
            alert("Quarter Theory: sweeper Q" + str.tostring(byQ), alert.freq_once_per_bar)
            alertSweeperFiredThisBar := true

// Doji-confirmed alert
if gAlertsOn and gAlertDoji and not alertDojiFiredThisBar and dojiConfirmedThisHour and isLastBarOfQuarter()
    alert("Quarter Theory: doji-confirmed in current hour", alert.freq_once_per_bar)
    alertDojiFiredThisBar := true

// Apex-confirmed alert (at triad close)
if gAlertsOn and gAlertApex and not alertApexFiredThisBar and isTriadClose() and not na(activeTriad)
    cls = classifyTriad(activeTriad)
    if cls == "apex-up" or cls == "apex-down"
        alert("Quarter Theory: " + cls + " confirmed for triad " + activeTriad.blockId, alert.freq_once_per_bar)
        alertApexFiredThisBar := true

// Midline reaction alert
if gAlertsOn and gAlertMid and not na(activeTriad)
    int hidx = hourIndexInTriad()
    HourAgg curH = hidx == 1 ? activeTriad.c1 : hidx == 2 ? activeTriad.c2 : activeTriad.c3
    [mid, _src] = resolve1hMid(curH, priorHour1h)
    if not na(mid)
        rxn = detectMidReaction(mid, high, low, close)
        if rxn != ""
            alert("Quarter Theory: midline " + rxn, alert.freq_once_per_bar)

// Band rejection alert
if gAlertsOn and gAlertBandRej and not na(activeTriad)
    int hidx2 = hourIndexInTriad()
    HourAgg curH2 = hidx2 == 1 ? activeTriad.c1 : hidx2 == 2 ? activeTriad.c2 : activeTriad.c3
    if not na(curH2) and curH2.box05Locked and not na(curH2.box05Hi)
        [u10, u05, l05_, l10] = bandLevels(curH2.box05Hi, curH2.box05Lo)
        [side, level] = detectBandRejection(high, low, close, u10, u05, l05_, l10)
        if side != ""
            alert("Quarter Theory: " + level + "% band " + side + " rejection", alert.freq_once_per_bar)
```

- [ ] **Step 2: Smoke** — load on chart, right-click → "Add alert on Amas Quarter Theory" → confirm alert dialog.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add alerts (sweeper, doji-confirmed, apex, midline, band rejection)"
```

---

### Task 8.5: Label housekeeping (FIFO under 500 cap)

- [ ] **Step 1: Append**

```pinescript
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 11. LABEL HOUSEKEEPING                                                   ║
// ╚══════════════════════════════════════════════════════════════════════════╝
// Pine caps at 500 labels/lines/boxes per script. With ~10 events per hour ×
// 3 hours per triad × 20 triad history = 600+ events potentially. We track
// all created labels in a FIFO and prune oldest when exceeding the budget.
//
// SIMPLIFICATION: max_labels_count=500 is set in the indicator() declaration.
// Pine itself FIFOs the oldest labels automatically when this cap is hit. So
// this section is mostly defensive; we just ensure history_depth bounds the
// number of READOUT labels we keep (since those are most context-dependent).

// Track readout labels per block; on triad close, if we exceed history_depth
// triads of completed readouts, delete the oldest.
var array<label> completedTriadReadouts = array.new<label>()
var array<box> completedTriadReadoutBoxes = array.new<box>()

if isTriadClose() and not na(activeTriad) and not na(activeTriadReadout)
    array.push(completedTriadReadouts, activeTriadReadout)
    array.push(completedTriadReadoutBoxes, activeTriadReadoutBox)
    activeTriadReadout := na
    activeTriadReadoutBox := na

    while array.size(completedTriadReadouts) > gHistDepth
        oldLabel = array.shift(completedTriadReadouts)
        oldBox = array.shift(completedTriadReadoutBoxes)
        if not na(oldLabel)
            label.delete(oldLabel)
        if not na(oldBox)
            box.delete(oldBox)
```

- [ ] **Step 2: Smoke** — load on a chart that goes back several days; verify only the last `gHistDepth` triads' readouts are kept.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): label housekeeping (FIFO under history_depth)"
```

---

### Task 8.6: Tooltips on annotations (C-11)

- [ ] **Step 1: Adjust existing label.new() calls** in `pine/quarter_theory.pine` to include a `tooltip=` parameter where useful. Examples:

For sweepers, change:
```pinescript
label.new(bar_index, newBias > 0 ? high : low, "Q" + str.tostring(byQ) + " sweeper", ...)
```
To:
```pinescript
string tipText = "Sweeps:\n"
for i = 0 to array.size(events) - 1
    tipText := tipText + "  " + array.get(events, i) + "\n"
label.new(bar_index, newBias > 0 ? high : low, "Q" + str.tostring(byQ) + " sweeper",
          ..., tooltip=tipText)
```

For triad readout: already includes the state-key in tooltip from Task 8.2.

For hour readout: add `tooltip="State key: " + (hour state key)` once the hour state-key builder is added (deferred to Phase 9 alongside parity work).

- [ ] **Step 2: Smoke** — hover any label, see the tooltip expand.

- [ ] **Step 3: Commit.**

```bash
git add pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add tooltips to event annotations and readouts"
```

---

### Phase 8 smoke test

- [ ] **Active hour readout shows under each forming hour with title/probs/state.**

- [ ] **Active triad readout shows under each forming triad with all 5 probabilities + qpair recommendation (when present).**

- [ ] **Probabilities currently display "—" because hash parity isn't fixed yet — Phase 9 fixes this.**

- [ ] **OHLC overlay shows top-right of active triad.**

- [ ] **Alerts can be created via TradingView's alert dialog.**

- [ ] **No "max_labels_count exceeded" errors after scrolling through several days of history.**

- [ ] **Tooltips work on hover.**

**End of Phase 8.** Move to [Phase 9 — Parity validation + cron + polish](phase-9-parity-polish.md).
