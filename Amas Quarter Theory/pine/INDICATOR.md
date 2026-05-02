# Abhi's Live Price Action

- **Quarter structure** — 15m quarters per hour with optional dividers, per-quarter background tints, and a 5-bar hour-open box (:00–:04).
- **Hour & triad verdicts** — closed-hour pills tag in-stat / out-of-stat extremes plus doji/line/apex classification; closed-triad pills tag line-up / line-down / apex-up / apex-down with apex-hour highlight.
- **Sweepers, bias-shifts & doji-confirmed markers** — flag the candle that takes out a prior quarter's extreme; doji-confirmed line + ✕ when the breaking quarter flips the hour's prior bias.
- **Live H/L markers** — horizontal lines at the candle holding the hour's running high/low; closed-hour H/L marker recolors red/green on sweep+reclose.
- **1h & 3h midlines** — running midline per hour and per triad with the prior-range containment rule; reaction markers on support/reject.
- **05 box & ±0.05% / ±0.10% bands** — 5-bar opening range box anchors percentage bands across Q1 with first-rejection markers.
- **9:30 range box** — RTH session box (9:30 → 16:00) with .25/.5/.75 quartile lines and right-axis price tags; distinct candle-only highlight on the 9:30 bar.
- **Session anchors (Asia / London / NY1 / NY2)** — fixed-window range boxes + midlines, P12 high/mid/low (18:00–06:00), midnight horizontal anchor with 🦉 label.
- **Day-level anchors** — O/U lines at each session close, MDR-10 high/low off today's 18:00 open (rolling 10-day average range), and Asia fib projections (−1, −1.5, −2, −2.5 above the high; +1.5, +2, +2.5 below the low) all extending to 17:00 with right-edge labels.
- **Session status table** — 4-column (ASN/LDN/NY1/NY2) × 3-row (Direction / Session / Model Status) tracker with ▲/▼ markers on the breaking candle for each session's locked H/L.
