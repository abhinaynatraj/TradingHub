# Abhi's Live Price Action

A TradingView Pine v6 overlay indicator that visualizes bootcamp price-action
structure on intraday futures charts. Designed for live, in-session reading on
the **1-minute timeframe** (some features extend to 5m). All time logic uses
**America/New_York**.

---

## What it draws

### Hour structure
- **Hour box** — a clear-bordered rectangle spanning the active hour's range (high to low), expanding live as the hour develops. Quarter dividers at `:15`, `:30`, `:45` are drawn inside the box.
- **Hour open line** — a horizontal line at the hour's open price, labeled `XXam Open` / `XXpm Open` centered above. Only the current and previous hour's open lines are kept visible.
- **Hour high/low marker** — at hour close, a horizontal line is drawn from the candle that printed the hour's extreme through `:59` of the next hour, picking whichever extreme (high or low) is closer to the close. Same "current + previous hour only" retention.
- **Per-quarter background tints** — Q1 / Q2 / Q3 / Q4 each get an independent background color (Q3 defaults to a faint cyan wash, others clear). Fully user-configurable.

### Hour close summary pill
At each hour close a single pill is rendered above the hour box, showing only the most-recent hour. It can list any of:
- `• Q# In Stat High` / `Out of Stat High` — the quarter that holds the hour's high (in-stat = Q1/Q4, out-of-stat = Q2/Q3). Tag fires only when a *different* quarter's low broke below the holder's low (i.e., the hour expanded past the holder's range — otherwise the high is "trivial" and gets no tag).
- `• Q# In Stat Low` / `Out of Stat Low` — symmetric rule for the hour's low.
- `• Doji Hour` — the hour's quarter sequence isn't strictly monotonic up or down (i.e., not a clean line-up or line-down).

### Triad structure (3-hour blocks)
Active triad blocks are: `00–03`, `03–06`, `06–09`, `09–12`, `12–15`, `18–21`, `21–00` ET. The **3-pm hour (15:00–15:59) renders as a standalone hour** outside any triad — it gets the hour-level features but no triad-level overlays.

- **3h midline** — a thin solid line at the running mid of the triad's range (or the prior triad's range if the current triad is contained inside it). Right edge clamped to the triad's last bar.
- **Apex hour highlight** — at triad close, if the triad classifies as `apex-up` or `apex-down`, the middle hour (C2) gets a faint red/wine fill plus a `• Apex Hour` label centered above it.
- **Triad close verdict** — `line-up triad` / `line-down triad` / `apex-up triad` / `apex-down triad` label below the triad's low.

### 0.5% box + bands (Q1-only)
Drawn only during the first 15 minutes (`:00`–`:14`) of each tracked hour:
- **05 box** — a tinted column anchored to the high/low of minutes `:00`–`:04` (locks at `:04`).
- **±0.05% / ±0.10% bands** — dotted horizontal lines at fixed % offsets from the 05-box high/low, extending through `:14`.
- **Band rejection markers** — `rej 10` label printed when price pierces and closes back inside the 0.10% band. First rejection per (level, side) per hour only.

### 1h midline
Solid line at the hour's running mid (or the prior hour's mid if contained), updated live. Optional reaction markers on midline support/reject.

### Doji-confirmed marker
When a quarter's close *flips the hour's bias* (e.g. Q4 takes a prior quarter's low after Q2/Q3 had set an upward bias), a black horizontal line is drawn from the broken extreme to the breaking candle, with a red `✕` at the line's mid. Only the first flip per hour gets a marker.

---

## Settings

Settings are organized into groups:

- **⚙ General** — Theme (Dark / Light / Custom), reserved data-source picker.
- **📊 Live Readouts** — Toggle 1h / 3h tint boxes (off by default; tints clear).
- **🕐 Quarter Structure** — Master toggle, quarter dividers, in-stat / out-of-stat tags, sweepers, doji-confirmed, per-quarter tints + colors.
- **🕒 Hour & Triad Verdicts** — Hour close pill, triad verdict, apex-hour highlight.
- **📐 Midlines** — 1h / 3h line toggles + widths, midline reaction markers.
- **📦 05 Box & Bands** — 05 box column, ±0.05% / ±0.10% bands, rejection markers, inline `.05%` / `.1%` labels.
- **🔔 Alerts** — Per-event alert toggles (sweeper, doji, apex, midline, band rejection).
- **🎨 Custom Colors** — Manual palette, only used when Theme = Custom.

---

## Theme behavior

The indicator has three theme modes (`Dark` / `Light` / `Custom`), but contrast-sensitive elements (hour-box border, quarter dividers, hour-open / H/L marker text) **auto-detect the actual TradingView chart background brightness** rather than relying on the theme input. So those stay readable even if the indicator theme doesn't match the chart skin.

---

## Definitions

| Term | Meaning |
|---|---|
| **Quarter (Q1–Q4)** | A 15-minute bucket within the hour: Q1 = `:00–:14`, Q2 = `:15–:29`, Q3 = `:30–:44`, Q4 = `:45–:59`. |
| **In-stat extreme** | The hour's high or low is held by Q1 or Q4. |
| **Out-of-stat extreme** | The hour's high or low is held by Q2 or Q3. |
| **Line-up hour** | `Q1.high < Q2.high < Q3.high < Q4.high` AND `Q1.low < Q2.low < Q3.low < Q4.low` (strictly monotonic). |
| **Line-down hour** | Symmetric, strictly descending. |
| **Doji hour** | Anything that isn't line-up or line-down (i.e., the quarter sequence isn't strictly monotonic). |
| **Doji-confirmed** | A bias flip *within* the hour: a later quarter takes out the opposite side of an earlier-set bias. Distinct from "Doji hour" — a hour can classify doji without the bias actually flipping. |
| **Apex-up triad** | `C1.high < C2.high > C3.high` (C2 is the apex). |
| **Apex-down triad** | `C1.low > C2.low < C3.low` (C2 is the apex). |
| **05 box** | Range of the first 5 minutes of the hour (locks at `:04`). |
| **Bands** | `±0.05%` and `±0.10%` offsets from the 05-box high/low. |

---

## Timeframe support

- **1m chart** — full feature set.
- **5m chart** — hour/triad tints render; per-bar features that need 1m granularity (quarter dividers, live extreme lines, hour-open/H/L markers, doji-confirmed) are gated off.
- **Other timeframes** — most features are silently skipped; the script doesn't error out.

---

## Performance

Designed to stay under TradingView's drawing-object caps (`max_labels_count=500`, `max_lines_count=500`, `max_boxes_count=500`):
- Live drawings (hour box, midlines, extreme lines, active hour tint) **mutate in place** every bar via `box.set_*` / `line.set_*` instead of recreate-and-delete cycles.
- Hour-open and H/L markers retain only the **current + previous** hour's pair; older drawings are explicitly deleted.
- Per-bar `hour()` / `minute()` calls are cached once per bar.
- Theme-derived colors are pre-resolved to script-level constants at load time, not recomputed per bar.

---

## Schema version

`v1` — visual-only build. Empirical probability readouts (live conditional path %, sample-count `n`, confidence color) are **reserved** in the settings UI but display `—` placeholders in this build. Wired in when the empirical pipeline (`engine/build.py`) lands.
