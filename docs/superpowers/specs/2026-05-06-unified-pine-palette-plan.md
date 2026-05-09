# Unified Pine Palette — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor three Pine indicators (`fractal_sweep.pine`, `ttfm+fadi.pine`, `quarter_theory.pine`) onto a single shared semantic palette and 5-tier opacity system, so they read as one product when stacked on the same TradingView chart.

**Architecture:** Each file gets a copy-pasted "canonical palette block" at the top defining base colors (8 roles × 2 modes) and tier helpers (5 opacity tiers). All existing color-related inputs and theme helpers are deleted. Every drawing call is rewritten to use `pal_<role>_<tier>()` accessors. Logic untouched.

**Tech Stack:** Pine Script v6 (no imports — palette block is copy-pasted; sync enforced by comment header).

**Spec reference:** [`docs/superpowers/specs/2026-05-06-unified-pine-palette-design.md`](2026-05-06-unified-pine-palette-design.md)

---

## File Structure

| File | Role | Color sites today |
|---|---|---|
| `Fractal Sweep/pine/fractal_sweep.pine` | Indicator A — sweep + CISD entries, R:R zones, scoreboard | 89 (`color.new` + `input.color`) |
| `Fractal Sweep/pine/ttfm+fadi.pine` | Indicator B — HTF candle template, FVG, T-Spot sweeps, projections | 67 |
| `Analysis/pine/quarter_theory.pine` | Indicator C — quarter structure, hour pills, session anchors, fib | 163 |

The plan modifies these three files only. It also writes one reference file (`docs/superpowers/specs/2026-05-06-unified-pine-palette-block.pine`) holding the canonical palette block as a non-executable reference snippet — that file is the source of truth when the three blocks need to stay in sync.

## Verification model

Pine has no headless test harness. Verification is **manual in TradingView** at the end of every phase:

1. **Compile check** — paste the modified file into TradingView's Pine editor → "Add to chart". Expected: no compile errors, indicator loads.
2. **Visual smoke** — confirm core signals render (specific checks listed per phase).
3. **Mode toggle** — flip `gTheme` between Auto / Dark / Light. Confirm palette switches; no inputs throw.
4. **Stack with the others** — once all three are migrated, load all three on the same chart and confirm they look like one product (no clashing hues, consistent pill style, consistent line opacity).

Each phase has a checkpoint where the engineer pauses and the user runs the manual checks. Do not proceed to the next phase until the user confirms.

## Phase ordering

1. **Phase 0** — write the canonical palette block reference file
2. **Phase 1** — `fractal_sweep.pine` (smallest active file, validates the block)
3. **Phase 2** — `ttfm+fadi.pine` (medium, includes the visible bull/bear hue change)
4. **Phase 3** — `quarter_theory.pine` (largest surface area)
5. **Phase 4** — final cross-indicator visual review

Smaller-first ordering means any palette-block bug surfaces on the easier file first.

---

## Phase 0 — Canonical palette block reference

### Task 0.1: Write the palette block reference file

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-unified-pine-palette-block.pine`

This file is non-executable (it has no `//@version` or `indicator(...)` line). It exists only so future edits to the palette block have a single source of truth — when the canonical block changes, update this file first, then copy verbatim to the three indicators.

- [ ] **Step 1: Create the reference file with the full palette block**

Write the following content to `docs/superpowers/specs/2026-05-06-unified-pine-palette-block.pine`:

```pine
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 🎨 CANONICAL PALETTE BLOCK — REFERENCE COPY                              ║
// ║ Source of truth: this file. When this block changes, copy verbatim into: ║
// ║   - Analysis/pine/quarter_theory.pine                                    ║
// ║   - Fractal Sweep/pine/fractal_sweep.pine                                ║
// ║   - Fractal Sweep/pine/ttfm+fadi.pine                                    ║
// ║ Spec: docs/superpowers/specs/2026-05-06-unified-pine-palette-design.md   ║
// ╚══════════════════════════════════════════════════════════════════════════╝

// ── Theme input ──────────────────────────────────────────────────────────────
var string G_THEME = "🎨 Theme"
gTheme = input.string("Auto", "Theme",
                      options=["Auto", "Dark", "Light"],
                      group=G_THEME,
                      tooltip="Auto reads chart bg brightness; Dark/Light forces the palette.")

// ── Mode resolution (single source of truth) ─────────────────────────────────
// `chart.bg_color` returns the actual chart background; mean(r,g,b) > 127 = light.
bool _AUTO_IS_LIGHT = (color.r(chart.bg_color) + color.g(chart.bg_color) + color.b(chart.bg_color)) / 3.0 > 127
bool IS_LIGHT_MODE  = gTheme == "Light" or (gTheme == "Auto" and _AUTO_IS_LIGHT)

// ── Role base colors (ink-tier, alpha 0) ─────────────────────────────────────
// Dark mode = Tailwind 400-500; Light mode = Tailwind 600-700. True mirror.
color P_LONG_BASE   = IS_LIGHT_MODE ? #047857 : #34d399  // emerald
color P_SHORT_BASE  = IS_LIGHT_MODE ? #b91c1c : #f87171  // red
color P_WARN_BASE   = IS_LIGHT_MODE ? #b45309 : #fbbf24  // amber
color P_INFO_BASE   = IS_LIGHT_MODE ? #0369a1 : #38bdf8  // sky
color P_ACCENT_BASE = IS_LIGHT_MODE ? #6d28d9 : #a78bfa  // violet
color P_STRUCT_BASE = IS_LIGHT_MODE ? #475569 : #cbd5e1  // slate
color P_INK         = IS_LIGHT_MODE ? #0f172a : #f1f5f9  // slate extreme (label/table text)
color P_SURFACE     = IS_LIGHT_MODE ? #334155 : #1e293b  // slate inverse-ink (pill/table bg)

// ── Tier helpers — apply opacity to any base color ───────────────────────────
tier_ink(color c)     => color.new(c, 0)
tier_strong(color c)  => color.new(c, 25)
tier_mid(color c)     => color.new(c, 60)
tier_soft(color c)    => color.new(c, 85)
tier_whisper(color c) => color.new(c, 95)

// ── Composite resolvers — drawing code reads only these ──────────────────────
pal_long_ink()       => tier_ink(P_LONG_BASE)
pal_long_strong()    => tier_strong(P_LONG_BASE)
pal_long_mid()       => tier_mid(P_LONG_BASE)
pal_long_soft()      => tier_soft(P_LONG_BASE)
pal_long_whisper()   => tier_whisper(P_LONG_BASE)

pal_short_ink()      => tier_ink(P_SHORT_BASE)
pal_short_strong()   => tier_strong(P_SHORT_BASE)
pal_short_mid()      => tier_mid(P_SHORT_BASE)
pal_short_soft()     => tier_soft(P_SHORT_BASE)
pal_short_whisper()  => tier_whisper(P_SHORT_BASE)

pal_warn_ink()       => tier_ink(P_WARN_BASE)
pal_warn_strong()    => tier_strong(P_WARN_BASE)
pal_warn_mid()       => tier_mid(P_WARN_BASE)
pal_warn_soft()      => tier_soft(P_WARN_BASE)
pal_warn_whisper()   => tier_whisper(P_WARN_BASE)

pal_info_ink()       => tier_ink(P_INFO_BASE)
pal_info_strong()    => tier_strong(P_INFO_BASE)
pal_info_mid()       => tier_mid(P_INFO_BASE)
pal_info_soft()      => tier_soft(P_INFO_BASE)
pal_info_whisper()   => tier_whisper(P_INFO_BASE)

pal_accent_ink()     => tier_ink(P_ACCENT_BASE)
pal_accent_strong()  => tier_strong(P_ACCENT_BASE)
pal_accent_mid()     => tier_mid(P_ACCENT_BASE)
pal_accent_soft()    => tier_soft(P_ACCENT_BASE)
pal_accent_whisper() => tier_whisper(P_ACCENT_BASE)

pal_struct_ink()     => tier_ink(P_STRUCT_BASE)
pal_struct_strong()  => tier_strong(P_STRUCT_BASE)
pal_struct_mid()     => tier_mid(P_STRUCT_BASE)
pal_struct_soft()    => tier_soft(P_STRUCT_BASE)
pal_struct_whisper() => tier_whisper(P_STRUCT_BASE)

pal_ink()            => P_INK
pal_surface()        => P_SURFACE
pal_surface_strong() => tier_strong(P_SURFACE)
pal_surface_soft()   => tier_soft(P_SURFACE)
// ╚══════════════════════════════════════════════════════════════════════════╝
```

- [ ] **Step 2: Commit the reference file**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add docs/superpowers/specs/2026-05-06-unified-pine-palette-block.pine
git commit -m "docs(pine): add canonical palette block reference"
```

Expected: one new file committed; nothing else modified.

---

## Phase 1 — `fractal_sweep.pine`

This is the validation phase. If the palette block has any Pine v6 syntax issue, it surfaces here before we copy it twice more.

**Files:**
- Modify: `Fractal Sweep/pine/fractal_sweep.pine`

### Task 1.1: Insert palette block, delete old style inputs

**What this task does:** Replaces lines 56-113 (the entire `// ── 5. STYLE ──` group, `c_*_c` custom inputs, `_light`/`_dark` ternaries, `c_sweep`/`c_cisd`/etc. resolvers, `rr_*_col` resolvers, `c_rr_lbl_text`, `c_size_bg`) with the canonical palette block plus the few non-color style inputs that survive (`rr_extend`, `sweep_style_inp`, `cisd_style_inp`, `sweep_text`, `cisd_text`, label-position inputs). Keeps all logic helpers from line 115 onward.

- [ ] **Step 1: Read the current style section**

Run: `sed -n '56,115p' "Fractal Sweep/pine/fractal_sweep.pine"`

Expected: see lines starting `// ── 5. STYLE ──` through the end of `c_size_bg = ...`. This is the section being replaced.

- [ ] **Step 2: Replace lines 56-113 with the new block**

Use the Edit tool. The exact `old_string` is the block from line 56 (`// ── 5. STYLE ──`) through line 113 (`c_size_bg      = _light ? ...`). The `new_string` is:

```pine
// ── 5. STYLE (non-color) ──────────────────────────────────────────────────────
var string G_STYLE = "Style"
rr_extend       = input.int(20,    "R:R Box Width (bars)",    group=G_STYLE, minval=5, maxval=100)
sweep_style_inp = input.string("Dotted", "Sweep Line Style",  options=["Dotted", "Dashed", "Solid"],  group=G_STYLE)
cisd_style_inp  = input.string("Dotted", "CISD Line Style",   options=["Dotted", "Dashed", "Solid"],  group=G_STYLE)
sweep_text      = input.string("Sweep of", "Sweep Label Text",group=G_STYLE, tooltip="TF is appended automatically.")
cisd_text       = input.string("CISD",     "CISD Label Text", group=G_STYLE, tooltip="TF is appended automatically.")
sweep_lbl_pos   = input.string("Right", "Sweep Label Position", options=["Left", "Right"],  group=G_STYLE)
cisd_lbl_pos    = input.string("Right", "CISD Label Position",  options=["Left", "Right"],  group=G_STYLE)
rr_lbl_pos      = input.string("Right", "R:R Pill Position",    options=["Left", "Right"],  group=G_STYLE)

// ── 6. PALETTE — keep in sync with palette-block reference ────────────────────
// Source of truth: docs/superpowers/specs/2026-05-06-unified-pine-palette-block.pine
// When that file changes, copy verbatim into the block below.
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║ 🎨 CANONICAL PALETTE BLOCK                                                ║
// ╚══════════════════════════════════════════════════════════════════════════╝
var string G_THEME = "🎨 Theme"
gTheme = input.string("Auto", "Theme",
                      options=["Auto", "Dark", "Light"],
                      group=G_THEME,
                      tooltip="Auto reads chart bg brightness; Dark/Light forces the palette.")

bool _AUTO_IS_LIGHT = (color.r(chart.bg_color) + color.g(chart.bg_color) + color.b(chart.bg_color)) / 3.0 > 127
bool IS_LIGHT_MODE  = gTheme == "Light" or (gTheme == "Auto" and _AUTO_IS_LIGHT)

color P_LONG_BASE   = IS_LIGHT_MODE ? #047857 : #34d399
color P_SHORT_BASE  = IS_LIGHT_MODE ? #b91c1c : #f87171
color P_WARN_BASE   = IS_LIGHT_MODE ? #b45309 : #fbbf24
color P_INFO_BASE   = IS_LIGHT_MODE ? #0369a1 : #38bdf8
color P_ACCENT_BASE = IS_LIGHT_MODE ? #6d28d9 : #a78bfa
color P_STRUCT_BASE = IS_LIGHT_MODE ? #475569 : #cbd5e1
color P_INK         = IS_LIGHT_MODE ? #0f172a : #f1f5f9
color P_SURFACE     = IS_LIGHT_MODE ? #334155 : #1e293b

tier_ink(color c)     => color.new(c, 0)
tier_strong(color c)  => color.new(c, 25)
tier_mid(color c)     => color.new(c, 60)
tier_soft(color c)    => color.new(c, 85)
tier_whisper(color c) => color.new(c, 95)

pal_long_ink()       => tier_ink(P_LONG_BASE)
pal_long_strong()    => tier_strong(P_LONG_BASE)
pal_long_mid()       => tier_mid(P_LONG_BASE)
pal_long_soft()      => tier_soft(P_LONG_BASE)
pal_long_whisper()   => tier_whisper(P_LONG_BASE)
pal_short_ink()      => tier_ink(P_SHORT_BASE)
pal_short_strong()   => tier_strong(P_SHORT_BASE)
pal_short_mid()      => tier_mid(P_SHORT_BASE)
pal_short_soft()     => tier_soft(P_SHORT_BASE)
pal_short_whisper()  => tier_whisper(P_SHORT_BASE)
pal_warn_ink()       => tier_ink(P_WARN_BASE)
pal_warn_strong()    => tier_strong(P_WARN_BASE)
pal_warn_mid()       => tier_mid(P_WARN_BASE)
pal_warn_soft()      => tier_soft(P_WARN_BASE)
pal_warn_whisper()   => tier_whisper(P_WARN_BASE)
pal_info_ink()       => tier_ink(P_INFO_BASE)
pal_info_strong()    => tier_strong(P_INFO_BASE)
pal_info_mid()       => tier_mid(P_INFO_BASE)
pal_info_soft()      => tier_soft(P_INFO_BASE)
pal_info_whisper()   => tier_whisper(P_INFO_BASE)
pal_accent_ink()     => tier_ink(P_ACCENT_BASE)
pal_accent_strong()  => tier_strong(P_ACCENT_BASE)
pal_accent_mid()     => tier_mid(P_ACCENT_BASE)
pal_accent_soft()    => tier_soft(P_ACCENT_BASE)
pal_accent_whisper() => tier_whisper(P_ACCENT_BASE)
pal_struct_ink()     => tier_ink(P_STRUCT_BASE)
pal_struct_strong()  => tier_strong(P_STRUCT_BASE)
pal_struct_mid()     => tier_mid(P_STRUCT_BASE)
pal_struct_soft()    => tier_soft(P_STRUCT_BASE)
pal_struct_whisper() => tier_whisper(P_STRUCT_BASE)
pal_ink()            => P_INK
pal_surface()        => P_SURFACE
pal_surface_strong() => tier_strong(P_SURFACE)
pal_surface_soft()   => tier_soft(P_SURFACE)
// ╚══════════════════════════════════════════════════════════════════════════╝
```

- [ ] **Step 3: Confirm the file still parses by running grep on residue**

Run: `grep -nE "_light|_dark|c_sweep_c|c_cisd_c|c_sl_c|c_tp_c|c_tspot_c|c_mid_c|c_overrisk_c|c_proj_c|c_dbg_c|rr_entry_col|rr_risk_col_c|rr_risk_border_c|rr_rew_col_c|rr_rew_border_c|rr_lbl_tp_col|rr_lbl_sl_col|rr_lbl_en_col|c_rr_lbl_text|c_size_bg|color_mode" "Fractal Sweep/pine/fractal_sweep.pine"`

Expected: zero matches inside the file's top-of-file inputs/resolvers section. (Some matches will still appear in the body — those are usage sites we replace in Task 1.2.)

If matches DO appear in the new block region (lines 56-130-ish), the Edit failed and you need to re-apply.

- [ ] **Step 4: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Fractal Sweep/pine/fractal_sweep.pine"
git commit -m "refactor(fractal_sweep): replace style/theme inputs with canonical palette block"
```

### Task 1.2: Rewrite all color usage sites in body

**What this task does:** Replaces every `color.new(c_X, N)` and `c_X` reference in the body of `fractal_sweep.pine` with the appropriate `pal_*()` call. Logic untouched. The mapping table is the spec's "Per-file mapping → fractal_sweep.pine" section.

- [ ] **Step 1: Replace sweep level references**

`c_sweep` was amber. Spec maps it to `pal_warn_*`.

In `Fractal Sweep/pine/fractal_sweep.pine`:

| Old | New |
|---|---|
| `color.new(c_sweep, 25)` | `pal_warn_strong()` |
| `color.new(c_sweep, 100)` | `na` (label color=na means no pill) — but check usage; if it's a label background, use `pal_warn_soft()`. Read each call site. |
| `c_sweep` (bare, used as textcolor) | `pal_warn_ink()` |

Walk the file with: `grep -n "c_sweep" "Fractal Sweep/pine/fractal_sweep.pine"`

For each match (lines ~450, 451, 454, 455, 507, 508, 521, 522, 1171, 1323, 1484):
- If used as `color.new(c_sweep, 25)` → replace with `pal_warn_strong()`
- If used as `color.new(c_sweep, 100)` (these are label `color=` args meaning transparent bg) → replace with `pal_warn_soft()` (legible pill bg)
- If used as `color.new(c_sweep, 25)` for a label `textcolor=` → replace with `pal_warn_strong()`
- If used as bare `c_sweep` for `textcolor=` → replace with `pal_warn_ink()`

Use the Edit tool, one occurrence at a time. Do not use `replace_all`.

- [ ] **Step 2: Replace CISD level references**

`c_cisd` was blue → spec maps to `pal_info_*`. Walk lines 643, 644, 653, 654, 1166, 1318:

| Old | New |
|---|---|
| `color.new(c_cisd, 50)` | `pal_info_mid()` |
| `color.new(c_cisd, 100)` (label color) | `pal_info_soft()` |
| `c_cisd` (textcolor) | `pal_info_ink()` |

- [ ] **Step 3: Replace stop loss / risk-zone references**

`c_sl`, `rr_risk_col`, `rr_risk_border`, `rr_lbl_sl_col` all map to `pal_short_*`.

Walk lines 1493, 1497, 1573, 1577, plus lines that reference `rr_risk_col` or `rr_risk_border` directly.

| Old | New |
|---|---|
| `rr_risk_col` (bg fill) | `pal_short_soft()` |
| `rr_risk_border` | `pal_short_mid()` |
| `color.new(c_sl, 60)` (border) | `pal_short_mid()` |
| `color.new(c_sl, 92)` (over-risk fill) | `pal_short_soft()` |
| `color.new(c_sl, 30)` (SL pill bg) | `pal_short_strong()` |
| `rr_lbl_sl_col` (pill bg) | `pal_short_strong()` |

- [ ] **Step 4: Replace take-profit / reward-zone references**

`c_tp`, `rr_rew_col`, `rr_rew_border`, `rr_lbl_tp_col` map to `pal_info_*`.

Walk lines 1494, 1498, 1574, 1578, plus `rr_rew_col` / `rr_rew_border` references.

| Old | New |
|---|---|
| `rr_rew_col` | `pal_info_soft()` |
| `rr_rew_border` | `pal_info_mid()` |
| `color.new(c_tp, 60)` | `pal_info_mid()` |
| `color.new(c_tp, 92)` | `pal_info_soft()` |
| `color.new(c_tp, 30)` | `pal_info_strong()` |
| `rr_lbl_tp_col` | `pal_info_strong()` |

- [ ] **Step 5: Replace T-Spot references**

`c_tspot` maps to `pal_accent_*`. Walk lines 1234, 1237, 1238, 1241, 1382, 1385, 1386, 1389:

| Old | New |
|---|---|
| `color.new(c_tspot, tspot_transp)` (box bgcolor) | `pal_accent_soft()` |
| `color.new(c_tspot, tspot_transp + 5)` (border) | `pal_accent_mid()` |
| `color.new(c_tspot, 100)` (label color) | `pal_accent_soft()` |
| `c_tspot` (textcolor) | `pal_accent_ink()` |

Note: this loses the `tspot_transp` user input. That's intentional — spec removes user-configurable color tuning. If you want to preserve the input, that's a deviation worth flagging to the user before committing.

- [ ] **Step 6: Replace midpoint and projection references**

`c_mid` (midline) → `pal_struct_strong()`. `c_proj` and `proj_color` → `pal_struct_mid()`. Walk lines 1225, 1228, 1229, 1261, 1373, 1376, 1377, 1409:

| Old | New |
|---|---|
| `color.new(c_mid, 30)` | `pal_struct_strong()` |
| `color.new(_mid_col, 100)` | `pal_struct_soft()` |
| `_mid_col` (textcolor) | `pal_struct_strong()` |
| `color.new(proj_color, 100)` | `pal_struct_soft()` |
| `proj_color` (textcolor) | `pal_struct_mid()` |

- [ ] **Step 7: Replace over-risk references**

`c_overrisk` → `pal_warn_*`. Walk lines 1476, 1484, 1487, 1496, 1499, 1556, 1564, 1567, 1576, 1579:

| Old | New |
|---|---|
| `color.new(c_overrisk, 30)` | `pal_warn_strong()` |
| `color.new(c_overrisk, 40)` | `pal_warn_strong()` |
| `color.new(c_overrisk, 100)` | `pal_warn_soft()` |
| `color.new(c_overrisk, 10)` | `pal_warn_ink()` |

- [ ] **Step 8: Replace entry pill, R:R label text, SIZE badge**

| Old | New |
|---|---|
| `rr_entry_col` (entry line) | `pal_struct_strong()` |
| `rr_lbl_en_col` (entry pill bg) | `pal_struct_mid()` |
| `c_rr_lbl_text` (label textcolor) | `pal_ink()` |
| `c_size_bg` (SIZE badge bg) | `pal_struct_soft()` |

Walk all references to these names with `grep -n` and replace.

- [ ] **Step 9: Replace scoreboard colors**

The scoreboard section (around lines 791-797) builds its own local `_sb_*` colors with `_dark` ternaries. Replace:

| Old | New |
|---|---|
| `_sb_bg = _dark ? color.new(#0f172a, 0) : color.new(c_dbg, 0)` | `_sb_bg = pal_surface()` |
| `_sb_alt = _dark ? color.new(#334155, 0) : color.new(#1e293b, 0)` | `_sb_alt = pal_surface_strong()` |
| `_sb_text = color.white` | `_sb_text = pal_ink()` |
| `_sb_muted = _dark ? #e2e8f0 : #cbd5e1` | `_sb_muted = pal_struct_ink()` |
| `_sb_tp = _dark ? #34d399 : #10b981` | `_sb_tp = pal_long_ink()` |
| `_sb_sl = _dark ? #f87171 : #ef4444` | `_sb_sl = pal_short_ink()` |
| `_sb_frame = _dark ? #64748b : #475569` | `_sb_frame = pal_struct_strong()` |

Also replace `bgcolor=_sb_bg` and `border_color=color.new(_sb_frame, 0)` accordingly — those are already correct after the substitution above.

- [ ] **Step 10: Replace SMT / NO-SMT pill colors**

Walk lines 1264, 1266, 1412, 1414:

| Old | New |
|---|---|
| `color.new(color.green, 10)` (SMT long pill bg) | `pal_long_soft()` |
| `color.new(color.red, 10)` (SMT short pill bg) | `pal_short_soft()` |
| `color.new(color.gray, 40)` (NO-SMT pill bg) | `pal_struct_soft()` |
| `c_rr_lbl_text` (already covered in Step 8) | `pal_ink()` |

- [ ] **Step 11: Replace debug label**

Line 707: `color=color.new(c_dbg, 20), textcolor=color.white`

Replace:
- `color.new(c_dbg, 20)` → `pal_surface_strong()`
- `color.white` → `pal_ink()`

- [ ] **Step 12: Replace mark-resolve label color**

Line 1011: `color=_mark_col, textcolor=color.white`

`_mark_col` is set conditionally further up in the file. Find its definition with `grep -n "_mark_col" "Fractal Sweep/pine/fractal_sweep.pine"` and:
- If `_mark_col = color.X` for SL hit → use `pal_short_strong()`
- If `_mark_col = color.X` for TP hit → use `pal_info_strong()`
- `textcolor=color.white` → `pal_ink()`

- [ ] **Step 13: Run final residue check**

Run: `grep -nE "color\.new\(c_|c_sweep[^_]|c_cisd[^_]|c_sl[^_]|c_tp[^_]|c_tspot[^_]|c_mid[^_]|c_overrisk[^_]|c_proj[^_]|c_dbg[^_]|c_rr_lbl_text|c_size_bg|rr_entry_col|rr_risk_col|rr_risk_border|rr_rew_col|rr_rew_border|rr_lbl_tp_col|rr_lbl_sl_col|rr_lbl_en_col|proj_color|_light\b|_dark\b" "Fractal Sweep/pine/fractal_sweep.pine"`

Expected: zero matches. If any remain, address them — they're usage sites missed in Steps 1-12.

- [ ] **Step 14: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Fractal Sweep/pine/fractal_sweep.pine"
git commit -m "refactor(fractal_sweep): rewrite all color sites onto unified palette tokens"
```

### Task 1.3: TradingView verification (manual — user runs)

- [ ] **Step 1: User compiles in TradingView**

Pause execution and ask the user to:
1. Open `Fractal Sweep/pine/fractal_sweep.pine` in TradingView's Pine Editor
2. Click "Add to chart"
3. Confirm: no compile errors, indicator loads.

If compile errors appear, the engineer reads the error, identifies the offending line, fixes, and re-runs. Common causes:
- A `pal_*()` call that doesn't exist (typo) → check the canonical block has it defined
- A bare `c_*` reference left behind → grep again

- [ ] **Step 2: User does visual smoke check**

User loads a 5m NQ chart with the indicator and confirms:
1. **Sweep line + label render in amber** (any swept HTF level visible)
2. **CISD line + label render in sky blue** (any active CISD level)
3. **R:R box renders** with red SL zone, sky TP zone
4. **Entry/SL/TP pills** are visible with correct colors
5. **Scoreboard table** renders in slate/ink (top-right by default)
6. **Toggle gTheme**: Auto → Dark → Light. Each switch should swap the palette without errors. Light mode shades darker; Dark mode shades brighter.

User reports back. Do NOT proceed to Phase 2 until user confirms.

---

## Phase 2 — `ttfm+fadi.pine`

This phase has the visible bull/bear hue change (sage/coral → emerald/red) flagged as a risk in the spec.

**Files:**
- Modify: `Fractal Sweep/pine/ttfm+fadi.pine`

### Task 2.1: Insert palette block, delete theme helpers

**What this task does:** Replaces lines 20-50 (the `🎨 Theme` group + `themeInk` / `themeLblBg` / `themeSwpTxt` / `themeCisd` helpers) with the canonical palette block. Keeps the rest of the file's input structure (HTF candle group, table group, etc.).

- [ ] **Step 1: Read current theme section**

Run: `sed -n '20,55p' "Fractal Sweep/pine/ttfm+fadi.pine"`

Expected: see `// ── 🎨 Theme ──` through the four `themeXxx(...)` helper definitions. This is the section being replaced.

- [ ] **Step 2: Replace lines 20-50 with the canonical palette block**

Use Edit. The new block is identical to Phase 1's palette block (verbatim copy from `docs/superpowers/specs/2026-05-06-unified-pine-palette-block.pine`). Paste the same block content used in Phase 1 Task 1.1 Step 1 (with the comment header pointing at the reference file).

- [ ] **Step 3: Search-and-replace all `themeXxx(...)` call sites**

Run: `grep -n "theme[ILSC][a-z]*\(" "Fractal Sweep/pine/ttfm+fadi.pine"`

Expected: 8-10 matches at lines like 53 (`themeInk(_TEMPLATE_COLOR_user)`), 279, 283, 291, 293, 297, 322, 326, 336, 349.

For each, replace with the appropriate `pal_*()` call per the spec's per-file mapping. Examples:

| Old | New |
|---|---|
| `themeInk(_TEMPLATE_COLOR_user)` | `pal_ink()` |
| `themeInk(input.color(color.black, "", inline='HTFlabel', ...))` | `pal_ink()` (input deleted) |
| `themeLblBg(input.color(color.new(#eaeaea, 10), "", inline='label', ...))` | `pal_surface()` |
| `themeSwpTxt(input.color(color.white, ...))` | `pal_ink()` |
| `themeCisd(_cisd_color_user)` | `pal_info_ink()` |

The corresponding `_X_user = input.color(...)` lines feeding each `themeXxx(...)` are also deleted in this same pass — they're now unused.

- [ ] **Step 4: Replace bull/bear body inputs (visible change — confirm with user)**

Lines 266-271 currently set `settings.bull_body`, `settings.bear_body`, `settings.bull_border`, `settings.bear_border`, `settings.bull_wick`, `settings.bear_wick` from sage/coral input pickers.

Per spec, replace with palette tokens:

```pine
settings.bull_body   := pal_long_strong()
settings.bear_body   := pal_short_strong()
settings.bull_border := pal_long_mid()
settings.bear_border := pal_short_mid()
settings.bull_wick   := pal_long_mid()
settings.bear_wick   := pal_short_mid()
```

Delete the corresponding `input.color(...)` calls on lines 266-271.

⚠ **Visible change**: HTF candles will switch from sage/coral to emerald/red. Spec calls this an acceptable risk. If the user reacts negatively after Step 6 below, revert this step only.

- [ ] **Step 5: Replace remaining color sites**

Per spec mapping table:

| Concept | Lines | Old | New |
|---|---|---|---|
| FVG fill | 301 | `input.color(color.new(color.gray, 80), ...)` | `pal_struct_soft()` |
| VI fill | 304 | `input.color(color.new(color.orange, 50), ...)` | `pal_warn_mid()` |
| Trace lines (O/C/H/L) | 307, 310, 313, 316 | `input.color(color.new(color.gray, 50), ...)` | `pal_struct_mid()` |
| Generic label bg | 322 | `themeLblBg(...)` | `pal_surface()` |
| HTF line color | 326 | `themeInk(...)` | `pal_ink()` |
| T-Spot sweep label text | 336 | `themeSwpTxt(...)` | `pal_ink()` |
| CISD line | 349 | `themeCisd(...)` | `pal_info_ink()` |
| Projection color | 352 | `input.color(color.gray, ...)` | `pal_struct_mid()` |
| Table bg | 289 | `input.color(color.new(color.gray, 100), ...)` | `pal_surface()` |
| Table border | 291 | `themeInk(...)` | `pal_struct_strong()` |
| Table text | 293 | `themeInk(...)` | `pal_ink()` |
| Table frame | 297 | `themeInk(...)` | `pal_struct_mid()` |

Each of these replaces both the `_X_user = input.color(...)` line (deleted) and the assignment line (rewritten to use the palette helper).

Walk the file's full input section (roughly lines 250-360) for any remaining `input.color(...)` calls. If any are color-only chrome (not surviving per spec), delete the input and route the variable to the palette token.

- [ ] **Step 6: Run residue check**

Run: `grep -nE "themeInk|themeLblBg|themeSwpTxt|themeCisd|_TEMPLATE_COLOR_user|_table_border_user|_table_text_user|_table_frame_user|_htf_label_color_user|_htf_timer_color_user|_tspot_sweep_label_user|_cisd_color_user|_htf_line_color_user|input\.color" "Fractal Sweep/pine/ttfm+fadi.pine"`

Expected: zero matches. (`input.color` may legitimately remain only if there's a chrome input we're keeping — but per spec there are none.)

- [ ] **Step 7: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Fractal Sweep/pine/ttfm+fadi.pine"
git commit -m "refactor(ttfm+fadi): replace theme helpers with canonical palette block"
```

### Task 2.2: TradingView verification

- [ ] **Step 1: User compiles**

Same pattern as Phase 1 Task 1.3. User loads `ttfm+fadi.pine` in Pine Editor → "Add to chart". Compile passes.

- [ ] **Step 2: User does visual smoke check**

On a 5m NQ chart:
1. **HTF candles render in emerald (bull) / red (bear)** — flag if user wants the sage/coral aesthetic back
2. **FVG fills render** in slate at soft opacity
3. **VI fills render** in amber at mid opacity
4. **HTF label / timer text render** in ink (slate-100 dark, slate-900 light)
5. **Trace lines (O/C/H/L)** render in slate-mid
6. **CISD line** in sky-ink
7. **Projection lines** in slate-mid
8. **Table** renders in surface bg / ink text
9. **Toggle gTheme**: Auto → Dark → Light. Mirror palette holds.

User reports back. Do NOT proceed to Phase 3 until user confirms.

---

## Phase 3 — `quarter_theory.pine`

Largest surface area. The file already has a `Theme` UDT and a runtime `_CHART_IS_LIGHT` detector that overlap with the canonical palette block — both get deleted.

**Files:**
- Modify: `Analysis/pine/quarter_theory.pine`

### Task 3.1: Replace existing theme system with palette block

**What this task does:** Deletes the `🎨 Custom Colors` group (lines ~138-156), the `Theme` UDT and `resolveTheme()` function (lines ~165-289), the `_CHART_IS_LIGHT` block + scattered theme-aware constants in the renderer section (lines ~613-665), and inserts the canonical palette block in their place. Also drops the "Custom" option from `gTheme`.

- [ ] **Step 1: Drop "Custom" from gTheme input**

Edit line 16 (`gTheme = input.string("Dark", ...)` to use `["Auto", "Dark", "Light"]` and default to `"Auto"`. Use Edit:

`old_string`: `gTheme        = input.string("Dark", "Theme",        options=["Dark","Light","Custom"], group=G_GENERAL)`

`new_string`: (this input is deleted entirely — the canonical block has its own `gTheme` declaration in the `🎨 Theme` group)

Note: the existing `gTheme` lives in the `⚙ General` group; the canonical block creates a new one in `🎨 Theme`. Delete the General-group instance.

- [ ] **Step 2: Delete the `🎨 Custom Colors` input group**

Find the group with `grep -n "Custom Colors" "Analysis/pine/quarter_theory.pine"` (around line 138).

Delete all 18 inputs in that group: `gColInStat`, `gColOutStat`, `gColSweeper`, `gColDojiConf`, `gColApexHr`, `gColLineUp`, `gColLineDn`, `gColApexUp`, `gColApexDn`, `gColDojiRO`, `gColMid1h`, `gColMid3h`, `gColBand05`, `gColBand10`, `gColBoxTint`, `gColActiveHr`, `gColActiveTr`, `gColQDiv`, plus the `G_COL = ...` group declaration.

- [ ] **Step 3: Delete the `Theme` UDT and `resolveTheme()` function**

Find with `grep -n "type Theme\|resolveTheme\|^var Theme T" "Analysis/pine/quarter_theory.pine"` (around lines 165-289).

Delete the entire UDT definition, the `resolveTheme()` function body, and the `var Theme T = na / T := resolveTheme()` lines. Replace nothing — the canonical block (inserted in Step 5) provides everything that referenced `T.X`.

- [ ] **Step 4: Delete the `_CHART_IS_LIGHT` block + theme-aware constants**

Find with `grep -n "_CHART_IS_LIGHT\|HOUR_BOX_BG\|HOUR_BOX_BORDER\|HOUR_DIV_LINE\|HOUR_OPEN_COLOR\|HL_MARK_COLOR\|SWEEP_RED_COLOR\|SWEEP_GREEN_COLOR\|DOJI_LINE_COLOR\|IN_STAT_BG\|OUT_STAT_BG\|ACTIVE_TRIAD_BORDER\|BOX_05_BORDER\|ACTIVE_HR_BG\|BAND_05_BG\|BAND_10_BG\|APEX_HOUR_BG\|APEX_HOUR_BORDER\|APEX_HOUR_LABEL_BG\|MID_1H_BG\|MID_3H_LINE\|HOUR_OPEN_LABEL_BG\|HL_MARK_LABEL_BG\|RED_TRANSPARENT\|PILL_BG\|PILL_BORDER\|PILL_TEXT\|SESS_P12_LINE\|SESS_OU_LINE\|SESS_MDR_LINE\|SESS_MIDNIGHT_LINE\|SESS_SD_LINE\|Q[1-4]_BG_BORDER" "Analysis/pine/quarter_theory.pine" | head -50`

These are all the theme-derived `color CONST_NAME = ...` declarations in the renderer section (around lines 613-665). They become palette accessor calls or get deleted (when the value was just bookkeeping the canonical block now handles).

Two substitution strategies — pick whichever is faster:

**Option A (smaller diff):** Keep the constant names. Rewrite each RHS to call a palette accessor. e.g.:

```pine
color SWEEP_RED_COLOR = pal_short_ink()
color SWEEP_GREEN_COLOR = pal_long_ink()
color DOJI_LINE_COLOR = pal_ink()
color IN_STAT_BG = pal_info_soft()
// ... etc
```

This minimizes the body diff (no need to touch the 100+ usage sites).

**Option B (cleaner):** Delete the constants, replace every usage in the body with the palette call directly. Larger diff, but eliminates the redundant indirection.

Recommend **Option A** for this phase — smaller diff, lower risk of mistakes. We can collapse the indirection in a later cleanup if desired.

Concrete mappings (per spec):

| Old constant | New RHS |
|---|---|
| `HOUR_BOX_BG` | `na` (was clear by default) |
| `HOUR_BOX_BORDER` | `pal_struct_strong()` |
| `HOUR_DIV_LINE` | `pal_struct_strong()` |
| `HOUR_OPEN_COLOR` | `pal_warn_ink()` |
| `HL_MARK_COLOR` | `pal_ink()` |
| `SWEEP_RED_COLOR` | `pal_short_ink()` |
| `SWEEP_GREEN_COLOR` | `pal_long_ink()` |
| `DOJI_LINE_COLOR` | `pal_ink()` |
| `IN_STAT_BG` | `pal_info_soft()` |
| `OUT_STAT_BG` | `pal_warn_soft()` |
| `ACTIVE_TRIAD_BORDER` | `pal_struct_mid()` |
| `BOX_05_BORDER` | `pal_info_soft()` |
| `ACTIVE_HR_BG` | `pal_struct_whisper()` |
| `ACTIVE_HR_BORDER` | `na` (was clear by default) |
| `BAND_05_BG` | `pal_struct_mid()` |
| `BAND_10_BG` | `pal_struct_mid()` |
| `APEX_HOUR_BG` | `pal_warn_whisper()` |
| `APEX_HOUR_BORDER` | `pal_warn_soft()` |
| `APEX_HOUR_LABEL_BG` | `pal_warn_mid()` |
| `MID_1H_BG` | `pal_warn_soft()` |
| `MID_3H_LINE` | `pal_info_mid()` |
| `HOUR_OPEN_LABEL_BG` | `pal_warn_soft()` |
| `HL_MARK_LABEL_BG` | `pal_surface()` |
| `RED_TRANSPARENT` | leave as-is (it's a transparent placeholder; not a semantic color) |
| `PILL_BG` | `pal_surface()` |
| `PILL_BORDER` | `pal_surface_strong()` |
| `PILL_TEXT` | `pal_ink()` |
| `SESS_P12_LINE` | `pal_info_ink()` |
| `SESS_OU_LINE` | `pal_struct_strong()` |
| `SESS_MDR_LINE` | `pal_struct_strong()` |
| `SESS_MIDNIGHT_LINE` | `pal_info_strong()` |
| `SESS_SD_LINE` | `pal_warn_strong()` |
| `Q1_BG_BORDER` | `na` |
| `Q2_BG_BORDER` | `na` |
| `Q3_BG_BORDER` | `na` |
| `Q4_BG_BORDER` | `na` |

- [ ] **Step 5: Insert canonical palette block**

Insert the canonical palette block (verbatim from `docs/superpowers/specs/2026-05-06-unified-pine-palette-block.pine`) at the top of the file, right after the `indicator(...)` declaration and before the existing `// ── ⚙ General ──` settings block.

The block defines `gTheme` itself, so any earlier `gTheme` reference must come AFTER the block (it does — the block is at the very top, all other code follows).

- [ ] **Step 6: Replace `T.X` references in the body**

The deleted `Theme` UDT was accessed as `T.in_stat`, `T.out_stat`, `T.sweeper`, etc. throughout the body.

Run: `grep -n "T\.\(in_stat\|out_stat\|sweeper\|doji_conf\|apex_hour\|line_up\|line_dn\|apex_up\|apex_dn\|doji\|mid_1h\|mid_3h\|band_05\|band_10\|box_tint\|active_hr\|active_triad\|q_div\|readout_bg\|readout_border\|readout_text\|readout_text_dim\|readout_active_accent\|conf_high\|conf_med\|conf_low\)" "Analysis/pine/quarter_theory.pine"`

Replace each per the spec mapping. Examples:

| Old | New |
|---|---|
| `T.in_stat` | `pal_info_ink()` |
| `T.out_stat` | `pal_warn_ink()` |
| `T.sweeper` | `pal_accent_ink()` |
| `T.doji_conf` | `pal_warn_ink()` |
| `T.apex_hour` | `pal_warn_ink()` |
| `T.line_up` | `pal_long_ink()` |
| `T.line_dn` | `pal_short_ink()` |
| `T.apex_up` | `pal_info_ink()` |
| `T.apex_dn` | `pal_accent_ink()` |
| `T.doji` | `pal_accent_ink()` |
| `T.mid_1h` | `pal_warn_ink()` |
| `T.mid_3h` | `pal_info_mid()` |
| `T.band_05` | `pal_struct_mid()` |
| `T.band_10` | `pal_struct_mid()` |
| `T.box_tint` | `pal_info_whisper()` |
| `T.active_hr` | `pal_struct_whisper()` |
| `T.active_triad` | `pal_struct_soft()` |
| `T.q_div` | `pal_struct_soft()` |
| `T.readout_bg` | `pal_surface()` |
| `T.readout_border` | `pal_surface_strong()` |
| `T.readout_text` | `pal_ink()` |
| `T.readout_text_dim` | `pal_struct_ink()` |
| `T.readout_active_accent` | `pal_accent_strong()` |
| `T.conf_high` | `pal_long_ink()` |
| `T.conf_med` | `pal_warn_ink()` |
| `T.conf_low` | `pal_short_ink()` |

Some of these are passed to `color.new(T.X, NN)` — the new accessor already returns a tinted color, so wrap considerations matter:

- If old code was `color.new(T.X, 0)` → use `pal_*_ink()`
- If old code was `color.new(T.X, 80)` → use `pal_*_soft()`
- If old code was `color.new(T.X, 95)` → use `pal_*_whisper()`
- If old code was `color.new(T.X, NN)` for some other NN → snap NN to the closest tier (Strong=25, Mid=60, Soft=85) and use that tier accessor

- [ ] **Step 7: Replace session-anchor input pickers**

Around line 84-109 the file has `gSessBoxColor`, `gSessP12Color`, `gSessMidnightCol`, `gSessOUColor`, `gSessMDRColor`, `gSessSDColor`, `g930BoxColor`, `g930LineColor`, `g930CandleColor`, `gColHourOpenBox`, `gColQ1Bg`, `gColQ2Bg`, `gColQ3Bg`, `gColQ4Bg` inputs.

Per spec, all are deleted. Wherever they're used in the body, replace with palette calls:

| Old | New |
|---|---|
| `gSessBoxColor` | `pal_struct_soft()` |
| `gSessP12Color` (all variants) | `pal_info_ink()` (high/low) or `pal_info_mid()` (mid) — depends on call site |
| `gSessMidnightCol` | `pal_info_strong()` |
| `gSessOUColor` | `pal_struct_strong()` |
| `gSessMDRColor` | `pal_struct_strong()` |
| `gSessSDColor` | `pal_warn_strong()` (whole) or `pal_warn_soft()` (half) — depends on call site |
| `g930BoxColor` | `pal_struct_soft()` |
| `g930LineColor` | `pal_struct_mid()` |
| `g930CandleColor` | `pal_warn_mid()` |
| `gColHourOpenBox` | `pal_struct_soft()` |
| `gColQ1Bg`, `gColQ2Bg`, `gColQ4Bg` | `na` (clear) |
| `gColQ3Bg` | `pal_struct_whisper()` |

The lines where `color.new(gSessXColor, NN)` were used inside helpers (e.g., `color p12LabelBg = color.new(gSessP12Color, 80)`) snap to the tier accessor (`pal_info_soft()` for alpha 80).

- [ ] **Step 8: Replace table inputs and color literals**

The table colors (`gTblBgColor`, `gTblTextColor`, `gTblHdrColor`, `gTblLongColor`, `gTblShortColor`, `gTblTrueColor`, `gTblFalseColor`, `gTblBrokenColor`) are defined around line 126-133. Per spec, all deleted. Replace usages:

| Old | New |
|---|---|
| `gTblBgColor` | `pal_surface()` |
| `gTblTextColor` | `pal_ink()` |
| `gTblHdrColor` | `pal_struct_ink()` |
| `gTblLongColor` | `pal_long_ink()` |
| `gTblShortColor` | `pal_short_ink()` |
| `gTblTrueColor` | `pal_long_ink()` |
| `gTblFalseColor` | `pal_short_ink()` |
| `gTblBrokenColor` | `pal_short_ink()` |

- [ ] **Step 9: Run final residue check**

Run: `grep -nE "T\.(in_stat|out_stat|sweeper|doji_conf|apex_hour|line_up|line_dn|apex_up|apex_dn|doji|mid_1h|mid_3h|band_05|band_10|box_tint|active_hr|active_triad|q_div|readout_bg|readout_border|readout_text|readout_text_dim|readout_active_accent|conf_high|conf_med|conf_low)|gColInStat|gColOutStat|gColSweeper|gColDojiConf|gColApexHr|gColLineUp|gColLineDn|gColApexUp|gColApexDn|gColDojiRO|gColMid1h|gColMid3h|gColBand05|gColBand10|gColBoxTint|gColActiveHr|gColActiveTr|gColQDiv|gColHourOpenBox|gColQ[1-4]Bg|gSessBoxColor|gSessP12Color|gSessMidnightCol|gSessOUColor|gSessMDRColor|gSessSDColor|g930BoxColor|g930LineColor|g930CandleColor|gTblBgColor|gTblTextColor|gTblHdrColor|gTblLongColor|gTblShortColor|gTblTrueColor|gTblFalseColor|gTblBrokenColor|resolveTheme|_CHART_IS_LIGHT|type Theme" "Analysis/pine/quarter_theory.pine"</br>

Expected: zero matches. Each match is either a definition that wasn't deleted or a usage site that wasn't migrated.

- [ ] **Step 10: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add "Analysis/pine/quarter_theory.pine"
git commit -m "refactor(quarter_theory): replace theme UDT and custom-color inputs with canonical palette block"
```

### Task 3.2: TradingView verification

- [ ] **Step 1: User compiles**

Same pattern. User loads `quarter_theory.pine` in Pine Editor → "Add to chart". Compile passes.

- [ ] **Step 2: User does extensive visual smoke check**

This file has the most rendering surface area. On a 1m NQ chart:
1. **Hour box + quarter dividers** render in slate-strong borders
2. **Per-quarter background tints** — Q1/Q2/Q4 clear, Q3 in slate-whisper
3. **05-box** renders in info-whisper bg with info-soft border
4. **±0.05% / ±0.10% bands** render in struct-mid lines, struct-mid label bg
5. **In-stat / out-of-stat extreme labels** — info-ink for in-stat, warn-ink for out-of-stat
6. **Sweeper labels** in accent-ink
7. **Doji-confirmed line** in ink, with red ✕ for failed confirmation
8. **Apex hour box** in warn-whisper bg, warn-soft border, warn-mid label bg
9. **1h midline** in warn-ink, **3h midline** in info-mid
10. **Hour-open label** in warn-ink
11. **Live H/L marker line** in ink
12. **Hour close summary pill** in surface bg / ink text
13. **9:30 box** in struct-soft fill, struct-mid quartile lines, warn-mid candle highlight
14. **Session boxes** (Asia / London / NY1 / NY2) in struct-soft fill, struct-mid border + midline
15. **P12 H/L lines** in info-ink, mid in info-mid
16. **Midnight line** in info-strong
17. **O/U lines** (4 sessions) in struct-strong
18. **MDR-10 H/L lines** in struct-strong
19. **Asia fib projections** — whole units in warn-strong, halves in warn-soft
20. **Session status table** in surface bg / ink text, semantic colors per cell
21. **Toggle gTheme**: Auto → Dark → Light. Mirror palette holds.

User reports back. Do NOT proceed to Phase 4 until user confirms.

---

## Phase 4 — Cross-indicator visual review

### Task 4.1: Stack all three on one chart

- [ ] **Step 1: User loads all three indicators on the same chart**

User opens TradingView with NQ 1m or 5m, adds:
1. `Analysis/pine/quarter_theory.pine`
2. `Fractal Sweep/pine/fractal_sweep.pine`
3. `Fractal Sweep/pine/ttfm+fadi.pine`

- [ ] **Step 2: User confirms the "one developer" feel**

Visual checklist:
- All amber markers (apex hour, sweep level, 9:30 candle, fib projections, VI) render in the same shade of amber
- All sky markers (CISD, P12, midnight, in-stat) render in the same shade of sky
- All slate structure (boxes, dividers, O/U, MDR, session boxes, FVG) reads as a coherent neutral layer
- Pills across all three indicators look consistent (same surface bg, same ink text)
- Toggle `gTheme` to Light. All three indicators flip together — none lag, none stay in dark mode.
- No two markers fight visually — semantic hue tells you what kind of signal regardless of source

- [ ] **Step 3: If issues found, file follow-up**

Any cross-indicator inconsistency should be tracked as a separate issue. The most likely sources:
- A color call missed in one indicator (residue grep would have caught most, not all)
- An opacity tier picked wrong for a role (should be obvious by eye — too loud or too quiet)
- A semantic role assignment that reads wrong in practice (only flagged after seeing it on real charts)

---

## Self-review (already done)

- **Spec coverage:** Every "Removed inputs" list and every "Role assignments" table from the spec is referenced by a task. ✓
- **Placeholder scan:** No TBD / TODO / "fill in details". Each step has either explicit code or explicit grep+replace instructions. ✓
- **Type consistency:** All accessor names match the canonical block (`pal_<role>_<tier>()`). ✓
- **Manual verification:** Phases end at user-driven checkpoints because Pine has no headless harness. ✓

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Palette block drift across files | Comment header in each file points at the reference file; `docs/superpowers/specs/2026-05-06-unified-pine-palette-block.pine` is the source of truth. Future edits update reference first, then copy. |
| Compile failure mid-phase | Each task ends with a residue grep + commit. Roll back the commit if the compile fails. |
| Visual regression user dislikes | Each phase ends at a user checkpoint. Phase 1's small surface area lets us catch tier mis-assignments early. |
| ttfm+fadi sage/coral → emerald/red rejection | Phase 2 Task 2.1 Step 4 calls out the change explicitly. Step 6 verification is the gate. |
