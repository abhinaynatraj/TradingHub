# Unified Pine Palette — Design

**Date:** 2026-05-06
**Scope:** Styling-only refactor across three Pine indicators that share a TradingView chart.
**Files affected:**
- `Analysis/pine/quarter_theory.pine`
- `Fractal Sweep/pine/fractal_sweep.pine`
- `Fractal Sweep/pine/ttfm+fadi.pine`

**Out of scope:** Logic changes, signal generation, alerts, table layouts, indicator behavior.

## Goal

Make the three indicators look like one developer made them. Today they each ship their own color system, their own theme detection, and their own opacity conventions — when stacked on the same chart they read as three different products.

## Design philosophy

**Semantic, not source-based.** Color encodes meaning (bullish, bearish, warning, reference, accent, structure), not which indicator drew the marker. Indicator identity comes from shape and position — boxes vs lines vs labels vs pills — not hue. A trader's eye learns the meaning of color once and applies it everywhere.

**True mirror palette.** Light and dark modes use the same hue family per role, shifted on the lightness axis: dark = Tailwind 400-500, light = Tailwind 600-700. Visual muscle memory transfers between modes.

**Five opacity tiers.** Every drawing operation picks one of {Ink, Strong, Mid, Soft, Whisper}. No more arbitrary `color.new(c, 87)` vs `color.new(c, 88)`.

**One theme control per indicator.** Same input name, same options, same default in all three files: `gTheme = input.string("Auto", options=["Auto","Dark","Light"], group="🎨 Theme")`.

## Palette tokens

### Role × mode swatch table

| Role | Hue family | Dark mode | Light mode |
|---|---|---|---|
| **Bullish / Long / Up / Confirmed** | emerald | `#34d399` (emerald-400) | `#047857` (emerald-700) |
| **Bearish / Short / Down / Invalidated** | red | `#f87171` (red-400) | `#b91c1c` (red-700) |
| **Warning / Apex / Sweep / Doji-confirmed** | amber | `#fbbf24` (amber-400) | `#b45309` (amber-700) |
| **Information / Reference / CISD / In-stat / P12 / Midnight / Projection** | sky | `#38bdf8` (sky-400) | `#0369a1` (sky-700) |
| **Accent / Sweeper / T-Spot zone** | violet | `#a78bfa` (violet-400) | `#6d28d9` (violet-700) |
| **Structure (boxes, dividers, O/U, MDR-10, midpoints)** | slate | `#cbd5e1` (slate-300) | `#475569` (slate-600) |
| **Ink (text on labels/pills/tables)** | slate extreme | `#f1f5f9` (slate-100) | `#0f172a` (slate-900) |
| **Surface (label/pill/table bg)** | slate inverse-ink | `#1e293b` (slate-800) | `#334155` (slate-700) |

### Opacity tiers

| Tier | Alpha | Used for |
|---|---|---|
| **Ink** | 0 | Text, signal lines, labels — must read |
| **Strong** | 25 | Primary lines, table cell text, borders — should notice |
| **Mid** | 60 | Secondary lines, midlines, pill bgs — available to eye |
| **Soft** | 85 | Range fills, structure boxes — ambient |
| **Whisper** | 95 | Background tints, active-hour wash — barely there |

The chart background detector (`_CHART_IS_LIGHT = mean(chart.bg_color.r, .g, .b) > 127`) is used in "Auto" mode to pick the dark or light palette. "Dark" and "Light" modes force the choice.

## Implementation pattern

Pine has no `import` mechanism, so each indicator gets a copy-pasted **palette block** at the top of the file (right after `indicator(...)` and the theme input). The block is identical across all three files — call it the canonical block.

### Canonical palette block (Pine v6 sketch)

```pine
// ╔══ 🎨 PALETTE — unified across quarter_theory / fractal_sweep / ttfm+fadi ══╗
// IMPORTANT: keep this block in sync across all three files.
// Update procedure: edit one, copy verbatim to the other two.

G_THEME = "🎨 Theme"
gTheme  = input.string("Auto", "Theme", options=["Auto","Dark","Light"], group=G_THEME,
                       tooltip="Auto reads chart bg brightness; Dark/Light forces the palette.")

// Mode resolution — single source of truth.
bool _AUTO_IS_LIGHT = (color.r(chart.bg_color) + color.g(chart.bg_color) + color.b(chart.bg_color)) / 3.0 > 127
bool IS_LIGHT_MODE  = gTheme == "Light" or (gTheme == "Auto" and _AUTO_IS_LIGHT)

// ── Role × mode tokens ───────────────────────────────────────────────────────
color P_LONG_BASE   = IS_LIGHT_MODE ? #047857 : #34d399
color P_SHORT_BASE  = IS_LIGHT_MODE ? #b91c1c : #f87171
color P_WARN_BASE   = IS_LIGHT_MODE ? #b45309 : #fbbf24
color P_INFO_BASE   = IS_LIGHT_MODE ? #0369a1 : #38bdf8
color P_ACCENT_BASE = IS_LIGHT_MODE ? #6d28d9 : #a78bfa
color P_STRUCT_BASE = IS_LIGHT_MODE ? #475569 : #cbd5e1
color P_INK         = IS_LIGHT_MODE ? #0f172a : #f1f5f9
color P_SURFACE     = IS_LIGHT_MODE ? #334155 : #1e293b

// ── Tier helpers — apply opacity to any base color ───────────────────────────
tier_ink(color c)     => color.new(c, 0)
tier_strong(color c)  => color.new(c, 25)
tier_mid(color c)     => color.new(c, 60)
tier_soft(color c)    => color.new(c, 85)
tier_whisper(color c) => color.new(c, 95)

// ── Composite resolvers — use these in drawing code ──────────────────────────
// Pattern: pal_<role>_<tier>().
pal_long_ink()       => tier_ink(P_LONG_BASE)
pal_long_strong()    => tier_strong(P_LONG_BASE)
pal_long_mid()       => tier_mid(P_LONG_BASE)
pal_long_soft()      => tier_soft(P_LONG_BASE)
// (same pattern for short, warn, info, accent, struct)
pal_ink()            => P_INK
pal_surface()        => P_SURFACE
pal_surface_strong() => tier_strong(P_SURFACE)
```

The full block defines all 30 composite resolvers (6 roles × 5 tiers) plus the 2 ink/surface helpers. Drawing code then reads:

```pine
// Before:
color SWEEP_RED_COLOR = gTheme == "Light" ? color.new(#dc2626, 0) : color.new(#ef4444, 0)
line.set_color(hlLine, SWEEP_RED_COLOR)

// After:
line.set_color(hlLine, pal_short_ink())
```

## Per-file mapping

This section enumerates how the existing per-file colors map to the unified tokens. Logic stays identical — only the right-hand side of color assignments changes.

### `quarter_theory.pine`

**Removed inputs** (palette becomes the source of truth):
- The entire `Theme` UDT and `resolveTheme()` function — replaced by direct token reads.
- `gTheme` "Custom" option (drop the third option, keep "Auto"/"Dark"/"Light").
- `🎨 Custom Colors` group (`gColInStat`, `gColOutStat`, `gColSweeper`, `gColDojiConf`, `gColApexHr`, `gColLineUp`, `gColLineDn`, `gColApexUp`, `gColApexDn`, `gColDojiRO`, `gColMid1h`, `gColMid3h`, `gColBand05`, `gColBand10`, `gColBoxTint`, `gColActiveHr`, `gColActiveTr`, `gColQDiv`) — all 18 inputs deleted.
- `gColHourOpenBox`, `gColQ1Bg`, `gColQ2Bg`, `gColQ3Bg`, `gColQ4Bg` — replaced by palette tokens.
- `gSessP12Color`, `gSessOUColor`, `gSessMDRColor`, `gSessMidnightCol`, `gSessSDColor` — deleted.
- `gSessBoxColor`, `g930BoxColor`, `g930LineColor`, `g930CandleColor` — deleted.
- `gTblBgColor`, `gTblTextColor`, `gTblHdrColor`, `gTblLongColor`, `gTblShortColor`, `gTblTrueColor`, `gTblFalseColor`, `gTblBrokenColor` — deleted.

**Role assignments:**

| Existing concept | New token |
|---|---|
| In-stat extreme (Q1/Q4 high/low) | `pal_info_ink()` |
| Out-of-stat extreme (Q2/Q3 high/low) | `pal_warn_ink()` |
| Sweeper marker | `pal_accent_ink()` |
| Doji-confirmed marker / line | `pal_warn_ink()` |
| Apex hour bg | `pal_warn_whisper()` |
| Apex hour border | `pal_warn_soft()` |
| Apex hour label bg | `pal_warn_mid()` |
| Line-up triad verdict | `pal_long_ink()` |
| Line-down triad verdict | `pal_short_ink()` |
| Apex-up triad verdict | `pal_info_ink()` |
| Apex-down triad verdict | `pal_accent_ink()` |
| Doji triad readout | `pal_accent_ink()` |
| 1h midline | `pal_warn_ink()` |
| 1h midline label bg | `pal_warn_soft()` |
| 3h midline | `pal_info_mid()` |
| ±0.05% / ±0.10% bands | `pal_struct_mid()` |
| 05 box tint | `pal_info_whisper()` |
| 05 box border | `pal_info_soft()` |
| Active hour tint | `pal_struct_whisper()` |
| Active triad tint | `pal_struct_soft()` |
| Quarter divider | `pal_struct_soft()` |
| Q1/Q2/Q4 background | clear (na color) |
| Q3 background | `pal_struct_whisper()` |
| Hour box bg | clear (na color) |
| Hour box border / quarter divider line | `pal_struct_strong()` |
| Hour-open color | `pal_warn_ink()` |
| Hour-open label bg | `pal_warn_soft()` |
| H/L mark color | `pal_ink()` |
| H/L mark label bg | `pal_surface()` |
| Sweep red (sweep recolor on high) | `pal_short_ink()` |
| Sweep green (sweep recolor on low) | `pal_long_ink()` |
| Doji line color | `pal_ink()` |
| Pill bg | `pal_surface()` |
| Pill border | `pal_surface_strong()` |
| Pill text | `pal_ink()` |
| 9:30 box fill | `pal_struct_soft()` |
| 9:30 quartile lines | `pal_struct_mid()` |
| 9:30 candle highlight | `pal_warn_mid()` |
| Session box bg | `pal_struct_soft()` |
| Session box border | `pal_struct_mid()` |
| Session midline | `pal_struct_mid()` |
| P12 high / mid / low lines | `pal_info_ink()` (high/low), `pal_info_mid()` (mid) |
| P12 labels | bg=`pal_info_soft()`, text=`pal_info_ink()` |
| Midnight line | `pal_info_strong()` |
| Midnight label | bg=`pal_info_soft()`, text=`pal_info_ink()` |
| O/U lines (4 sessions) | `pal_struct_strong()` |
| O/U labels | bg=`pal_struct_soft()`, text=`pal_struct_ink()` |
| MDR-10 H/L lines | `pal_struct_strong()` |
| MDR-10 labels | bg=`pal_struct_soft()`, text=`pal_struct_ink()` |
| Asia fib projections (whole) | `pal_warn_strong()` |
| Asia fib projections (half) | `pal_warn_soft()` |
| Asia fib labels | bg=`pal_warn_soft()`, text=`pal_warn_ink()` |
| Table bg | `pal_surface()` |
| Table text | `pal_ink()` |
| Table header text | `pal_struct_ink()` |
| Long table cell | `pal_long_ink()` |
| Short table cell | `pal_short_ink()` |
| True cell | `pal_long_ink()` |
| False cell | `pal_short_ink()` |
| Broken cell | `pal_short_ink()` |

### `fractal_sweep.pine`

**Removed inputs:**
- `c_sweep_c`, `c_cisd_c`, `c_sl_c`, `c_tp_c`, `c_tspot_c`, `c_mid_c`, `c_overrisk_c`, `c_proj_c`, `c_dbg_c` — all custom-mode pickers deleted.
- `proj_color` — deleted.
- `rr_entry_col`, `rr_risk_col_c`, `rr_risk_border_c`, `rr_rew_col_c`, `rr_rew_border_c`, `rr_lbl_tp_col`, `rr_lbl_sl_col`, `rr_lbl_en_col` — deleted.
- The existing `_light` / `_dark` ternaries throughout — replaced by palette tokens.
- The "Custom" theme branch (if any) — deleted.

**Role assignments:**

| Existing concept | New token |
|---|---|
| Sweep level line | `pal_warn_strong()` |
| CISD level line | `pal_info_ink()` |
| Stop loss / risk zone fill | `pal_short_soft()` |
| Stop loss / risk zone border | `pal_short_mid()` |
| Take profit / reward zone fill | `pal_info_soft()` |
| Take profit / reward zone border | `pal_info_mid()` |
| T-Spot zone fill | `pal_accent_soft()` |
| T-Spot zone border | `pal_accent_mid()` |
| Midpoint line | `pal_struct_strong()` |
| Over-risk warning | `pal_warn_ink()` |
| CISD projection line | `pal_struct_mid()` |
| Entry pill bg | `pal_struct_mid()` |
| Entry pill text | `pal_ink()` |
| TP pill bg | `pal_info_strong()` |
| TP pill text | `pal_ink()` |
| SL pill bg | `pal_short_strong()` |
| SL pill text | `pal_ink()` |
| Long marker (▲) | `pal_long_ink()` |
| Short marker (▼) | `pal_short_ink()` |
| SMT confirmation pill | bg=`pal_long_soft()` (long) / `pal_short_soft()` (short), text=`pal_ink()` |
| NO-SMT pill | bg=`pal_struct_soft()`, text=`pal_ink()` |
| Scoreboard bg | `pal_surface()` |
| Scoreboard alt-row bg | `pal_surface_strong()` |
| Scoreboard text | `pal_ink()` |
| Scoreboard header text | `pal_struct_ink()` |

### `ttfm+fadi.pine`

**Removed inputs:**
- `_TEMPLATE_COLOR_user`, `_table_border_user`, `_table_text_user`, `_table_frame_user`, `_htf_label_color_user`, `_htf_timer_color_user`, `_tspot_sweep_label_user`, `_cisd_color_user`, `_htf_line_color_user` — all themed-input pickers replaced with direct palette reads.
- `themeInk()`, `themeLblBg()`, `themeSwpTxt()`, `themeCisd()` helpers — deleted (palette block replaces them).
- "Custom" theme option — deleted.
- Bull/bear sage/coral inputs — replaced with palette tokens (this is a real visual change to HTF candles).

**Role assignments:**

| Existing concept | New token |
|---|---|
| Bull body / border / wick | `pal_long_strong()` (body), `pal_long_mid()` (border/wick) |
| Bear body / border / wick | `pal_short_strong()` (body), `pal_short_mid()` (border/wick) |
| Template line color | `pal_ink()` |
| HTF label text | `pal_ink()` |
| HTF timer text | `pal_ink()` |
| Table bg | `pal_surface()` |
| Table border | `pal_struct_strong()` |
| Table text | `pal_ink()` |
| Table frame | `pal_struct_mid()` |
| FVG fill | `pal_struct_soft()` |
| Volume imbalance fill | `pal_warn_mid()` |
| Trace lines (O / C / H / L) | `pal_struct_mid()` |
| Generic label bg | `pal_surface()` |
| HTF line color | `pal_ink()` |
| T-Spot sweep label text | `pal_ink()` |
| CISD line | `pal_info_ink()` |
| Projection line | `pal_struct_mid()` |

## What stays user-configurable

A small set of inputs survive because they're chrome that has no semantic role:

- `quarter_theory.pine`: nothing — all palette inputs deleted.
- `fractal_sweep.pine`: nothing — all palette inputs deleted.
- `ttfm+fadi.pine`: nothing — all palette inputs deleted.

If a user wants different colors, the answer is "edit the palette block at the top of the file" — and that's intentional. The whole point is one source of truth.

## Migration & rollout

Order of work (one indicator at a time, smallest first to validate the palette block before the bigger files):

1. **`fractal_sweep.pine`** — paste the palette block, replace color assignments, verify visually on a chart.
2. **`ttfm+fadi.pine`** — same pattern. Validate that bull/bear emerald/red doesn't break HTF candle readability.
3. **`quarter_theory.pine`** — biggest file, most palette surface area. Do this last so the pattern is proven.

After each file:
- TradingView "Add to chart" must succeed (no compile errors).
- Visual smoke test: open the chart in dark mode, verify all signals render. Toggle to light mode, verify mirror palette holds.
- Toggle `gTheme` between Auto/Dark/Light — confirm the palette switches correctly.

## Non-goals

- No logic changes. Signal generation, alert wiring, table cell logic, retention queues — untouched.
- No new features. The 9:30 box still draws the same way; the session anchor lines still extend the same way; the sweep detector still fires the same way.
- No performance work. Palette resolution is one-time at script init, no per-bar overhead.

## Risks

- **HTF candle bull/bear color change in ttfm+fadi**: sage/coral → emerald/red is a visible aesthetic shift. User should preview before committing.
- **Loss of per-user color customization**: removing 30+ input pickers is intentional but is a one-way change. Users who had personalized palettes will need to re-customize via palette-block edits.
- **Palette-block drift**: the canonical block lives in three files. Future edits must be applied to all three. Mitigation: a comment header at the top of each block flags this and names the canonical update procedure.
