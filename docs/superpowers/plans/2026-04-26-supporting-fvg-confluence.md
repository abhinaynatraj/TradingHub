# Supporting FVG Confluence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four boolean flags per trade row (CISD-TF and 1M, each strict and loose) marking the presence of a supporting unfilled same-side FVG behind entry, plus a new `fvg_summary` aggregate in `model_stats.json`. Engine-only — no dashboard or Pine changes in this plan.

**Architecture:** A pure-function helper `find_supporting_fvg` scans a single OHLC array for unfilled, correctly-polarised 3-bar FVGs in a given window and returns `(strict, loose)` booleans for a trade with a known sweep extreme and entry price. `detect_setups_base` calls it twice per setup — once on the CISD-TF arrays (`c_arrs`) and once on the 1M arrays (`m1_arrs`). `build_model_stats` consumes the four resulting flag columns to emit an `fvg_summary` block alongside `smt_summary`.

**Tech Stack:** Python 3.14 · numpy · pandas · pytest. All changes confined to `Fractal Sweep/engine/model_stats.py` and `Fractal Sweep/tests/`.

**Spec:** [docs/superpowers/specs/2026-04-26-supporting-fvg-confluence-design.md](../specs/2026-04-26-supporting-fvg-confluence-design.md)

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `Fractal Sweep/engine/model_stats.py` | Modify | Add `find_supporting_fvg` helper after `find_cisd` (~line 322). Call twice in `detect_setups_base` per setup. Write four new flag fields onto each trade row. Add `fvg_summary` block to `build_model_stats` output. |
| `Fractal Sweep/tests/test_supporting_fvg.py` | Create | Unit tests for `find_supporting_fvg` covering both polarities, both geometries, fill detection, edge cases, and the strict ⇒ loose invariant. |
| `Fractal Sweep/tests/test_supporting_fvg_integration.py` | Create | End-to-end test asserting flags appear on trade rows and `fvg_summary` block exists in the model_stats output. |

No other files modified in this plan. Dashboard, Pine indicator, and CLAUDE.md / PIPELINE.md updates are deferred until decision criterion is evaluated against fresh engine output.

---

## Glossary (used throughout this plan)

For a **LONG** trade (bullish FVG required):

- **3-bar bullish FVG at index `i`** in array `arr`: `arr['low'][i] > arr['high'][i-2]`. The "gap" is the price band `(arr['high'][i-2], arr['low'][i])`.
- **Top of the gap (for a long):** `arr['low'][i]` (the upper edge of the unfilled space).
- **Bottom of the gap (for a long):** `arr['high'][i-2]` (the lower edge).
- **Unfilled at entry**: for every bar `j` in `(i, entry_idx)`, `arr['low'][j] > arr['high'][i-2]`. (No subsequent bar dipped into the lower edge of the gap.) Note: forming bar `i` has `low[i] > high[i-2]` by definition, so it does not count as a fill of itself.
- **Strict geometry**: `sweep_extreme ≤ arr['high'][i-2]` AND `arr['low'][i] ≤ entry_price`. Body fully between SL and entry.
- **Loose geometry**: `arr['low'][i] ≤ entry_price`. Top of gap below entry.

SHORT mirror (bearish FVG required):

- **3-bar bearish FVG at index `i`**: `arr['high'][i] < arr['low'][i-2]`. Gap band: `(arr['high'][i], arr['low'][i-2])`.
- **Top (for a short, i.e. upper edge of where the gap "supports" from above):** `arr['low'][i-2]`.
- **Bottom (for a short):** `arr['high'][i]`.
- **Unfilled at entry**: for every `j` in `(i, entry_idx)`, `arr['high'][j] < arr['low'][i-2]`.
- **Strict**: `arr['high'][i] ≤ entry_price ≤ arr['low'][i-2]` AND `arr['low'][i-2] ≤ sweep_extreme`. Equivalently: gap band fully inside `[entry_price, sweep_extreme]`.
- **Loose**: `arr['low'][i-2] ≥ entry_price`. Bottom of gap above entry.

The window scanned is `[window_start_idx, entry_idx)` — formation bar `i` must satisfy `i ≥ window_start_idx + 2` (FVG needs three bars) and `i < entry_idx` (formation strictly before entry).

---

## Task 1: `find_supporting_fvg` helper — bullish strict, single FVG

**Files:**
- Create: `Fractal Sweep/tests/test_supporting_fvg.py`
- Modify: `Fractal Sweep/engine/model_stats.py` (add helper after `find_cisd`, around line 322)

- [ ] **Step 1: Write the failing test**

Create `Fractal Sweep/tests/test_supporting_fvg.py`:

```python
"""Tests for find_supporting_fvg — supporting FVG confluence detection."""
import numpy as np
import pytest

import model_stats as ms


def _arrs(bars):
    """Build a minimal arrs dict with just the OHLC fields find_supporting_fvg uses."""
    n = len(bars)
    return dict(
        open  = np.array([b[0] for b in bars], dtype='float64'),
        high  = np.array([b[1] for b in bars], dtype='float64'),
        low   = np.array([b[2] for b in bars], dtype='float64'),
        close = np.array([b[3] for b in bars], dtype='float64'),
    )


def test_bullish_strict_fvg_between_sl_and_entry():
    # 5 bars total. FVG forms at index 2 (3-bar pattern using bars 0,1,2).
    # bar 0 high = 100, bar 2 low = 105 → bullish FVG band (100, 105].
    # No subsequent bar dips below 100 → unfilled.
    bars = [
        # (open, high, low, close)
        (95, 100, 92, 99),   # 0 — defines lower edge (high=100)
        (99, 103, 98, 102),  # 1 — middle bar (irrelevant to gap)
        (102, 108, 105, 107),# 2 — defines upper edge (low=105) → FVG forms here
        (107, 110, 106, 109),# 3 — stays above 100, doesn't fill
        (109, 112, 108, 111),# 4 — entry bar (will not be inspected past entry_idx)
    ]
    arrs = _arrs(bars)
    # Long trade: sweep_extreme=98 (below the gap), entry_price=109 (above the gap).
    # Body of gap (100, 105] is fully between 98 and 109 → strict True, loose True.
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=109.0, direction='LONG',
    )
    assert strict is True
    assert loose is True
```

- [ ] **Step 2: Run test to verify it fails**

Run from the `Fractal Sweep/` directory:

```bash
python3 -m pytest tests/test_supporting_fvg.py::test_bullish_strict_fvg_between_sl_and_entry -v
```

Expected: FAIL with `AttributeError: module 'model_stats' has no attribute 'find_supporting_fvg'`.

- [ ] **Step 3: Write minimal implementation**

Open `Fractal Sweep/engine/model_stats.py`. After the `find_cisd` function (it ends at line 321 with `return _find_cisd(...)`), add:

```python
# ── SUPPORTING FVG DETECTION ──────────────────────────────────────────────────
def find_supporting_fvg(arrs, window_start_idx, entry_idx,
                        sweep_extreme, entry_price, direction):
    """
    Scan a single OHLC array for an unfilled same-side 3-bar FVG that supports
    the trade. Returns (strict, loose) booleans.

    Bullish FVG at index i: low[i] > high[i-2]. Gap band (high[i-2], low[i]).
    Bearish FVG at index i: high[i] < low[i-2]. Gap band (high[i], low[i-2]).

    Strict: gap body fully between sweep_extreme and entry_price.
    Loose:  top-of-gap (relative to direction) below/above entry_price.
    Unfilled at entry: no bar in (i, entry_idx) wicks into the gap.

    Window: scans formation indices i in [window_start_idx + 2, entry_idx).
    Returns early as soon as a strict FVG is found (strict ⇒ loose).
    """
    highs = arrs['high']
    lows  = arrs['low']
    n     = len(highs)

    first_i = max(window_start_idx + 2, 2)
    last_i  = min(entry_idx, n)

    found_loose = False

    if direction == 'LONG':
        for i in range(first_i, last_i):
            top    = float(lows[i])
            bottom = float(highs[i - 2])
            if top <= bottom:
                continue  # no bullish gap
            # Unfilled at entry: no bar in (i, entry_idx) has low <= bottom
            unfilled = True
            for j in range(i + 1, last_i):
                if float(lows[j]) <= bottom:
                    unfilled = False
                    break
            if not unfilled:
                continue
            # Loose: top of gap at or below entry_price
            if top <= entry_price:
                found_loose = True
                # Strict: bottom at or above sweep_extreme AND top at or below entry
                if bottom >= sweep_extreme:
                    return True, True
        return False, found_loose
    else:  # SHORT
        for i in range(first_i, last_i):
            top    = float(lows[i - 2])  # upper edge of bearish gap
            bottom = float(highs[i])     # lower edge of bearish gap
            if top <= bottom:
                continue  # no bearish gap
            unfilled = True
            for j in range(i + 1, last_i):
                if float(highs[j]) >= top:
                    unfilled = False
                    break
            if not unfilled:
                continue
            # Loose (short): bottom of gap at or above entry
            if bottom >= entry_price:
                found_loose = True
                # Strict (short): top at or below sweep_extreme
                if top <= sweep_extreme:
                    return True, True
        return False, found_loose
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_supporting_fvg.py::test_bullish_strict_fvg_between_sl_and_entry -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add "Fractal Sweep/engine/model_stats.py" "Fractal Sweep/tests/test_supporting_fvg.py"
git commit -m "feat(fractal-sweep): find_supporting_fvg helper — bullish strict case"
```

---

## Task 2: Bullish loose-only case (FVG below entry, extends below SL)

**Files:**
- Modify: `Fractal Sweep/tests/test_supporting_fvg.py`

- [ ] **Step 1: Write the failing test**

Append to `test_supporting_fvg.py`:

```python
def test_bullish_loose_only_fvg_extends_below_sl():
    # FVG body extends BELOW the sweep extreme — top is below entry but
    # bottom is below SL. Loose True, strict False.
    bars = [
        (95, 96, 92, 95),    # 0 — high=96 is BELOW sweep_extreme=98 → strict will fail
        (95, 99, 94, 98),    # 1
        (98, 105, 101, 104), # 2 — low=101 → bullish FVG band (96, 101]
        (104, 108, 102, 107),# 3 — stays above 96, unfilled
        (107, 110, 106, 109),# 4 — entry
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=109.0, direction='LONG',
    )
    assert strict is False  # bottom (96) < sweep_extreme (98)
    assert loose is True    # top (101) <= entry (109)
```

- [ ] **Step 2: Run test to verify it fails or passes**

```bash
python3 -m pytest tests/test_supporting_fvg.py::test_bullish_loose_only_fvg_extends_below_sl -v
```

Expected: PASS (the helper from Task 1 already handles this case — strict requires `bottom >= sweep_extreme`, which is False here, so it falls through to `found_loose = True`).

If it fails: re-read the helper's branching logic and fix. The semantic is "loose ⇒ top below entry; strict ⇒ loose AND bottom above SL."

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/tests/test_supporting_fvg.py"
git commit -m "test(fractal-sweep): supporting FVG loose-only case below SL"
```

---

## Task 3: FVG above entry → both False

**Files:**
- Modify: `Fractal Sweep/tests/test_supporting_fvg.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_bullish_fvg_above_entry_both_false():
    # Gap forms ABOVE entry — not supporting. Both False.
    bars = [
        (95, 100, 92, 99),
        (99, 103, 98, 102),
        (102, 108, 105, 107),  # FVG (100, 105]
        (107, 110, 106, 109),
        (109, 112, 108, 111),  # entry
    ]
    arrs = _arrs(bars)
    # Entry below the gap → top (105) > entry (104) → loose False.
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=104.0, direction='LONG',
    )
    assert strict is False
    assert loose is False
```

- [ ] **Step 2: Run**

```bash
python3 -m pytest tests/test_supporting_fvg.py::test_bullish_fvg_above_entry_both_false -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/tests/test_supporting_fvg.py"
git commit -m "test(fractal-sweep): supporting FVG above entry → both false"
```

---

## Task 4: Filled gap → both False

**Files:**
- Modify: `Fractal Sweep/tests/test_supporting_fvg.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_bullish_fvg_filled_before_entry_both_false():
    # FVG forms at bar 2, but bar 3 wicks into bottom of gap (low <= 100).
    # Should be treated as filled → both False.
    bars = [
        (95, 100, 92, 99),
        (99, 103, 98, 102),
        (102, 108, 105, 107),  # FVG (100, 105]
        (107, 110, 99, 109),   # low=99 <= 100 → fills the gap
        (109, 112, 108, 111),  # entry
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=111.0, direction='LONG',
    )
    assert strict is False
    assert loose is False
```

- [ ] **Step 2: Run**

```bash
python3 -m pytest tests/test_supporting_fvg.py::test_bullish_fvg_filled_before_entry_both_false -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/tests/test_supporting_fvg.py"
git commit -m "test(fractal-sweep): filled FVG → both false"
```

---

## Task 5: Wrong-side FVG (bearish FVG on long trade)

**Files:**
- Modify: `Fractal Sweep/tests/test_supporting_fvg.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_bearish_fvg_does_not_count_for_long():
    # All bars contain a bearish 3-bar gap but no bullish gap. Long trade.
    bars = [
        (110, 112, 108, 109),  # 0 — low=108
        (109, 110, 106, 107),  # 1
        (107, 105, 102, 104),  # 2 — high=105 < low[0]=108 → bearish FVG (105, 108)
        (104, 105, 100, 102),
        (102, 104,  98, 100),  # entry below — but trade is LONG so wrong-side
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=95.0, entry_price=102.0, direction='LONG',
    )
    assert strict is False
    assert loose is False
```

- [ ] **Step 2: Run**

```bash
python3 -m pytest tests/test_supporting_fvg.py::test_bearish_fvg_does_not_count_for_long -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/tests/test_supporting_fvg.py"
git commit -m "test(fractal-sweep): wrong-polarity FVG ignored"
```

---

## Task 6: SHORT mirror — strict bearish FVG between entry and SL

**Files:**
- Modify: `Fractal Sweep/tests/test_supporting_fvg.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_bearish_strict_fvg_between_entry_and_sl_short():
    # SHORT trade: sweep_extreme is ABOVE entry (sweep of prior high).
    # Bearish FVG should sit with body fully inside [entry, sweep_extreme].
    bars = [
        (110, 112, 108, 109),  # 0 — low=108 → upper edge of bearish gap
        (109, 110, 106, 107),  # 1
        (107, 105, 102, 104),  # 2 — high=105 → lower edge. Bearish gap (105, 108)
        (104, 107, 102, 103),  # 3 — high=107 < 108 → does not fill
        (103, 105, 100, 102),  # 4 — entry
    ]
    arrs = _arrs(bars)
    # Short: sweep_extreme=110 (above), entry=102 (below). Gap (105, 108) is
    # fully inside [102, 110] → strict True, loose True.
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=110.0, entry_price=102.0, direction='SHORT',
    )
    assert strict is True
    assert loose is True
```

- [ ] **Step 2: Run**

```bash
python3 -m pytest tests/test_supporting_fvg.py::test_bearish_strict_fvg_between_entry_and_sl_short -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/tests/test_supporting_fvg.py"
git commit -m "test(fractal-sweep): supporting FVG SHORT strict mirror"
```

---

## Task 7: SHORT loose-only and SHORT filled cases

**Files:**
- Modify: `Fractal Sweep/tests/test_supporting_fvg.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_bearish_loose_only_short_extends_above_sl():
    # SHORT: bearish gap with top above sweep_extreme → strict False, loose True.
    bars = [
        (114, 116, 112, 113),  # 0 — low=112
        (113, 114, 110, 111),  # 1
        (111, 109, 106, 108),  # 2 — high=109 → bearish gap (109, 112)
        (108, 110, 106, 107),  # 3 — does not fill (max high in (i,entry)=110 < 112)
        (107, 109, 100, 102),  # 4 — entry
    ]
    arrs = _arrs(bars)
    # sweep_extreme=111 (below the top of gap=112) → strict False
    # gap bottom=109 >= entry=102 → loose True
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=111.0, entry_price=102.0, direction='SHORT',
    )
    assert strict is False
    assert loose is True


def test_bearish_fvg_filled_before_entry_short():
    # SHORT bearish gap that gets filled (a later bar's high reaches the top).
    bars = [
        (114, 116, 112, 113),
        (113, 114, 110, 111),
        (111, 109, 106, 108),  # bearish gap (109, 112)
        (108, 113, 106, 110),  # high=113 >= 112 → fills the gap
        (110, 112, 100, 102),  # entry
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=120.0, entry_price=102.0, direction='SHORT',
    )
    assert strict is False
    assert loose is False
```

- [ ] **Step 2: Run**

```bash
python3 -m pytest tests/test_supporting_fvg.py -k "loose_only_short or filled_before_entry_short" -v
```

Expected: PASS for both.

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/tests/test_supporting_fvg.py"
git commit -m "test(fractal-sweep): supporting FVG SHORT loose and filled cases"
```

---

## Task 8: No-gap and tiny-window edge cases

**Files:**
- Modify: `Fractal Sweep/tests/test_supporting_fvg.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_no_gap_in_window_both_false():
    # All consecutive bars overlap — no 3-bar gap exists.
    bars = [
        (100, 102,  99, 101),
        (101, 103, 100, 102),
        (102, 104, 101, 103),
        (103, 105, 102, 104),
        (104, 106, 103, 105),
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=99.0, entry_price=105.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_window_too_small_returns_false():
    # entry_idx=2 means scan range [2, 2) — empty. Both False.
    bars = [
        (95, 100, 92, 99),
        (99, 103, 98, 102),
        (102, 108, 105, 107),
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=2,
        sweep_extreme=98.0, entry_price=109.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_strict_implies_loose_invariant_random():
    # Property test: for any inputs the helper accepts, strict ⇒ loose.
    rng = np.random.RandomState(7)
    for _ in range(50):
        n = 8
        opens  = rng.uniform(95, 110, n)
        closes = opens + rng.uniform(-2, 2, n)
        highs  = np.maximum(opens, closes) + rng.uniform(0, 2, n)
        lows   = np.minimum(opens, closes) - rng.uniform(0, 2, n)
        arrs = dict(open=opens, high=highs, low=lows, close=closes)
        sweep = float(lows.min()) - 1.0
        entry = float(highs.max()) + 1.0
        s, l = ms.find_supporting_fvg(
            arrs, 0, n, sweep, entry, 'LONG',
        )
        if s:
            assert l, "strict ⇒ loose violated for LONG"
        s, l = ms.find_supporting_fvg(
            arrs, 0, n, entry + 5.0, sweep - 5.0, 'SHORT',
        )
        if s:
            assert l, "strict ⇒ loose violated for SHORT"
```

- [ ] **Step 2: Run**

```bash
python3 -m pytest tests/test_supporting_fvg.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/tests/test_supporting_fvg.py"
git commit -m "test(fractal-sweep): supporting FVG edge cases + invariant"
```

---

## Task 9: Wire flags into `detect_setups_base`

**Files:**
- Modify: `Fractal Sweep/engine/model_stats.py`, `detect_setups_base` (around line 1217 — the `base_row = dict(...)` block — and line 1275 — the `base_row.update(...)` after entry resolution)

- [ ] **Step 1: Write the failing test**

Append to `Fractal Sweep/tests/test_supporting_fvg.py`:

```python
def test_detect_setups_base_writes_four_fvg_flags():
    """Smoke test that detect_setups_base writes the four flag fields onto
    every trade row (whether True or False). Uses an existing helper-built
    scenario to avoid reproducing all of detect_setups_base's plumbing."""
    from helpers import make_sweep_arrs, make_controlled_m1, NS_PER_MIN

    # Trivial scenario: build minimal arrs that produce at least one base_row.
    # We borrow shape from the SMT test fixtures.
    s_arrs = make_sweep_arrs(2, [
        (24000, 24050, 23950, 24000),
        (24000, 24020, 23940, 24010),  # sweeps below 23950
    ])
    # Build 1m bars with a bullish FVG between SL and entry.
    m1_arrs = make_controlled_m1([
        # Sweep low, then rally with a 3-bar bullish FVG, then return to range.
        (24000, 24005, 23945, 23950),   # 0 — sweeps 23950 (low=23945)
        (23950, 23960, 23945, 23955),   # 1
        (23955, 23990, 23980, 23985),   # 2 — bullish FVG: low=23980 > high[0]=24005? NO
        (23985, 23995, 23983, 23992),
        (23992, 24010, 23990, 24005),   # 4 — return into prior candle range (>= 23950)
        (24005, 24025, 24000, 24020),
        (24020, 24040, 24015, 24035),
        (24035, 24055, 24030, 24050),
    ], start_ts=int(s_arrs['ts_ns'][1]))
    # 5-min CISD-TF: re-aggregate the m1_arrs by groups of 5.
    c_arrs = dict(
        ts_ns = m1_arrs['ts_ns'][::5],
        open  = m1_arrs['open'][::5],
        high  = np.array([m1_arrs['high'][i:i+5].max() for i in range(0, len(m1_arrs['ts_ns']), 5)]),
        low   = np.array([m1_arrs['low'][i:i+5].min()  for i in range(0, len(m1_arrs['ts_ns']), 5)]),
        close = np.array([m1_arrs['close'][min(i+4, len(m1_arrs['close'])-1)] for i in range(0, len(m1_arrs['ts_ns']), 5)]),
        trade_date = m1_arrs['trade_date'][::5],
        yr = m1_arrs['yr'][::5],
        dow = m1_arrs['dow'][::5],
        hr = m1_arrs['hr'][::5],
    )

    base_rows, _ = ms.detect_setups_base(
        m1_arrs, s_arrs, c_arrs,
        model_key='1H_5M',
        model_cfg=dict(sweep_tf_min=60, session_hrs=None),
    )

    # We don't assert on the exact True/False values — just that all four
    # keys are present as booleans on every row.
    assert len(base_rows) > 0
    for row in base_rows:
        for key in ('passes_fvg_cisd_strict', 'passes_fvg_cisd_loose',
                    'passes_fvg_1m_strict',  'passes_fvg_1m_loose'):
            assert key in row, f"row missing {key}: {row.keys()}"
            assert isinstance(row[key], bool), f"{key} not bool: {type(row[key])}"
        # strict ⇒ loose invariant per TF
        assert (not row['passes_fvg_cisd_strict']) or row['passes_fvg_cisd_loose']
        assert (not row['passes_fvg_1m_strict'])   or row['passes_fvg_1m_loose']
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_supporting_fvg.py::test_detect_setups_base_writes_four_fvg_flags -v
```

Expected: FAIL with `assert 'passes_fvg_cisd_strict' in row` (the key is missing — flags not yet wired).

- [ ] **Step 3: Compute the four flags inside `detect_setups_base`**

Open `Fractal Sweep/engine/model_stats.py`. Find this block in `detect_setups_base` (around line 1217, just before `base_row = dict(...)`):

```python
            if direction == 'LONG':
                passes_f4 = bool(ret_close >= float(s_low[i - 1]))
            else:
                passes_f4 = bool(ret_close <= float(s_high[i - 1]))
```

Right after that block (still inside the `for direction in (...)` loop, before `base_row = dict(...)`), insert:

```python
            # Default flags for the no-CISD / pre-entry path.
            # Real values are computed once we know entry_price and entry_idx.
            passes_fvg_cisd_strict = False
            passes_fvg_cisd_loose  = False
            passes_fvg_1m_strict   = False
            passes_fvg_1m_loose    = False
```

Then update the `base_row = dict(...)` literal (line 1217) to include the four new keys at the end of the dict (just before the closing `)`):

```python
            base_row = dict(
                date          = str(s_arrs['trade_date'][i]),
                yr            = int(s_arrs['yr'][i]),
                dow           = int(s_arrs['dow'][i]),
                direction     = direction,
                ref_range     = round(float(ref_range), 2),
                sweep_ext     = round(float(sweep_ext), 2),
                sweep_pct     = round(_sweep_pct_row, 3),
                sweep_extreme = round(float(sweep_extreme), 2),
                sweep_mode    = 'PREV',
                passes_f3     = passes_f3,
                passes_f4     = passes_f4,
                cisd_mode     = 'CISD',
                ref_lookback  = ref_lookback,
                smt           = smt_divergence,
                passes_fvg_cisd_strict = passes_fvg_cisd_strict,
                passes_fvg_cisd_loose  = passes_fvg_cisd_loose,
                passes_fvg_1m_strict   = passes_fvg_1m_strict,
                passes_fvg_1m_loose    = passes_fvg_1m_loose,
            )
```

Now find the entry-resolution block (around line 1252 onwards):

```python
            entry_ts_ns = int(c_arrs['ts_ns'][next_c_idx])
            entry_price = float(c_arrs['open'][next_c_idx])

            entry_start = int(np.searchsorted(m1_ts, entry_ts_ns, side='left'))
            if entry_start >= len(m1_ts):
                continue
```

Immediately after `entry_start = ...` and the bounds check, before the `base_risk = ...` line, insert:

```python
            # ── Supporting FVG flags (computed at entry, scoped to anchor window) ──
            # CISD-TF window: q1_start_ns to entry_ts_ns, indexed in c_arrs.
            cisd_window_start = int(np.searchsorted(c_arrs['ts_ns'], q1_start_ns, side='left'))
            cisd_entry_idx    = int(np.searchsorted(c_arrs['ts_ns'], entry_ts_ns, side='left'))
            passes_fvg_cisd_strict, passes_fvg_cisd_loose = find_supporting_fvg(
                c_arrs, cisd_window_start, cisd_entry_idx,
                sweep_extreme=float(sweep_extreme),
                entry_price=entry_price,
                direction=direction,
            )

            # 1M window: q1_start_ns to entry_ts_ns, indexed in m1_arrs.
            m1_window_start = q1_s            # already computed above
            m1_entry_idx    = entry_start
            passes_fvg_1m_strict, passes_fvg_1m_loose = find_supporting_fvg(
                m1_arrs, m1_window_start, m1_entry_idx,
                sweep_extreme=float(sweep_extreme),
                entry_price=entry_price,
                direction=direction,
            )
```

Finally, in the `base_row.update(...)` call near the end of the `for direction` loop (around line 1275), append the four flag fields:

```python
            base_row.update(
                date         = str(_entry_date),
                dow          = int(m1_dow[entry_start]),
                hr           = hr_val,
                mn           = mn_val,
                session      = get_session(hr_val + mn_val / 60.0),
                entry_price  = round(entry_price, 2),
                base_risk    = round(base_risk, 2),
                cisd_level   = round(cisd_level, 2) if cisd_level is not None else None,
                hour_range_pts = round(_hr_rng, 2),
                cisd_close      = round(_cisd_close, 2),
                rejected_by  = rejected_by,
                stop_price   = None,
                target_price = None,
                risk_pts     = None,
                outcome      = '',
                r            = 0.0,
                mae_pct      = None,
                mfe_pct      = None,
                mae_pct_hr   = None,
                mfe_pct_hr   = None,
                passes_fvg_cisd_strict = passes_fvg_cisd_strict,
                passes_fvg_cisd_loose  = passes_fvg_cisd_loose,
                passes_fvg_1m_strict   = passes_fvg_1m_strict,
                passes_fvg_1m_loose    = passes_fvg_1m_loose,
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_supporting_fvg.py::test_detect_setups_base_writes_four_fvg_flags -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
python3 -m pytest tests/ -q
```

Expected: same 195 pass · 20 skip count as baseline (per CLAUDE.md), plus the 10 new tests added in tasks 1–9 → **205 pass · 20 skip**.

If anything fails: read the failure, fix in this task before committing. Common failures and fixes:
- Existing test that asserts row dict equality → either widen the assertion or include the new keys.
- Existing test on `len(base_row)` → bump expected count by 4.

- [ ] **Step 6: Commit**

```bash
git add "Fractal Sweep/engine/model_stats.py" "Fractal Sweep/tests/test_supporting_fvg.py"
git commit -m "feat(fractal-sweep): wire supporting FVG flags into detect_setups_base"
```

---

## Task 10: `fvg_summary` aggregate in `build_model_stats`

**Files:**
- Modify: `Fractal Sweep/engine/model_stats.py`, `build_model_stats` (around line 1588 — right after the `smt_summary` block)
- Create: `Fractal Sweep/tests/test_supporting_fvg_integration.py`

- [ ] **Step 1: Write the failing test**

Create `Fractal Sweep/tests/test_supporting_fvg_integration.py`:

```python
"""End-to-end check that fvg_summary appears in build_model_stats output."""
import pandas as pd
import pytest

import model_stats as ms


def _wl_fixture():
    """Hand-built minimal trade DataFrame mimicking what detect+resolve produces."""
    rows = []
    # 6 trades — 3 wins, 3 losses, varied flag combinations
    for i, (outcome, r, smt, fvg_cisd_strict, fvg_cisd_loose, fvg_1m_strict, fvg_1m_loose) in enumerate([
        ('WIN',   1.0, True,  True,  True,  True,  True),
        ('LOSS', -1.0, True,  False, True,  False, True),
        ('WIN',   1.0, False, True,  True,  False, False),
        ('LOSS', -1.0, False, False, False, True,  True),
        ('WIN',   1.0, True,  False, False, False, True),
        ('LOSS', -1.0, False, False, True,  False, False),
    ]):
        rows.append(dict(
            date='2023-11-14', yr=2023, dow=2, hr=10, mn=0,
            session='NY1', direction='LONG',
            ref_range=10.0, sweep_ext=4.0, sweep_pct=0.4,
            sweep_extreme=23945.0, sweep_mode='PREV',
            passes_f3=True, passes_f4=True,
            cisd_mode='CISD', ref_lookback=1,
            smt=smt,
            passes_fvg_cisd_strict=fvg_cisd_strict,
            passes_fvg_cisd_loose=fvg_cisd_loose,
            passes_fvg_1m_strict=fvg_1m_strict,
            passes_fvg_1m_loose=fvg_1m_loose,
            entry_price=23950.0, base_risk=5.0, cisd_level=23948.0,
            hour_range_pts=20.0, cisd_close=23949.0,
            stop_price=23945.0, target_price=23955.0, risk_pts=5.0,
            outcome=outcome, rejected_by='', r=r,
            mae_pct=0.001, mfe_pct=0.002,
            mae_pct_hr=5.0, mfe_pct_hr=10.0,
        ))
    return pd.DataFrame(rows)


def test_fvg_summary_block_exists_with_expected_keys():
    df = _wl_fixture()
    stats = ms.build_model_stats(
        df, trading_days=1, model_key='1H_5M',
        model_cfg=dict(sweep_tf_min=60, session_hrs=None),
        stop_mult=1.0, target_mult=1.0, profile_key='simple_1r',
        profile_type='mult',
    )
    assert 'fvg_summary' in stats
    fs = stats['fvg_summary']
    for key in ('cisd_strict', 'cisd_loose', 'no_cisd_fvg',
                'm1_strict',   'm1_loose',   'no_m1_fvg',
                'any_strict',  'any_loose',
                'cisd_strict_smt', 'm1_strict_smt', 'any_strict_smt'):
        assert key in fs, f"fvg_summary missing key: {key}"
        # Each leaf must have agg() shape
        leaf = fs[key]
        for leaf_key in ('n', 'wins', 'wr', 'ev', 'pf'):
            assert leaf_key in leaf, f"fvg_summary[{key!r}] missing {leaf_key}"


def test_fvg_summary_counts_match_fixture():
    df = _wl_fixture()
    stats = ms.build_model_stats(
        df, trading_days=1, model_key='1H_5M',
        model_cfg=dict(sweep_tf_min=60, session_hrs=None),
        stop_mult=1.0, target_mult=1.0, profile_key='simple_1r',
        profile_type='mult',
    )
    fs = stats['fvg_summary']
    # From the fixture: cisd_strict True on rows 0,2 → n=2, wins=2 (both WIN)
    assert fs['cisd_strict']['n']    == 2
    assert fs['cisd_strict']['wins'] == 2
    # cisd_loose True on rows 0,1,2,5 → n=4, wins=2 (rows 0 and 2)
    assert fs['cisd_loose']['n']    == 4
    assert fs['cisd_loose']['wins'] == 2
    # no_cisd_fvg = NOT cisd_loose: rows 3,4 → n=2, wins=1 (row 4)
    assert fs['no_cisd_fvg']['n']    == 2
    assert fs['no_cisd_fvg']['wins'] == 1
    # any_strict = cisd_strict OR m1_strict: rows 0,2,3 → n=3, wins=2 (rows 0,2)
    assert fs['any_strict']['n']    == 3
    assert fs['any_strict']['wins'] == 2
    # any_strict_smt = any_strict AND smt: row 0 only → n=1, wins=1
    assert fs['any_strict_smt']['n']    == 1
    assert fs['any_strict_smt']['wins'] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_supporting_fvg_integration.py -v
```

Expected: FAIL with `assert 'fvg_summary' in stats` — the block doesn't exist yet.

- [ ] **Step 3: Add `fvg_summary` block to `build_model_stats`**

Open `Fractal Sweep/engine/model_stats.py`. Find the SMT block in `build_model_stats` (around line 1587):

```python
    # SMT divergence breakdown
    smt_summary = []
    if 'smt' in wl.columns:
        for smt_val, g in wl.groupby('smt'):
            s = agg(g); s.update(smt=bool(smt_val))
            smt_summary.append(s)
```

Immediately after that block, insert:

```python
    # ── Supporting FVG breakdown ─────────────────────────────────────────────
    # Each leaf is the result of agg() on a boolean-mask slice of wl.
    # Cells: per-TF (cisd / m1 / any) × geometry (strict / loose / none) +
    # confluence with SMT for the strict cells (since SMT is the strongest
    # known filter).
    fvg_summary = {}
    if {'passes_fvg_cisd_strict', 'passes_fvg_cisd_loose',
        'passes_fvg_1m_strict',   'passes_fvg_1m_loose'} <= set(wl.columns):
        cs = wl['passes_fvg_cisd_strict'].astype(bool)
        cl = wl['passes_fvg_cisd_loose'].astype(bool)
        ms_ = wl['passes_fvg_1m_strict'].astype(bool)
        ml = wl['passes_fvg_1m_loose'].astype(bool)
        smt_mask = wl['smt'].astype(bool) if 'smt' in wl.columns else pd.Series(False, index=wl.index)

        any_strict = cs | ms_
        any_loose  = cl | ml

        cells = {
            'cisd_strict':     cs,
            'cisd_loose':      cl,
            'no_cisd_fvg':     ~cl,
            'm1_strict':       ms_,
            'm1_loose':        ml,
            'no_m1_fvg':       ~ml,
            'any_strict':      any_strict,
            'any_loose':       any_loose,
            'cisd_strict_smt': cs & smt_mask,
            'm1_strict_smt':   ms_ & smt_mask,
            'any_strict_smt':  any_strict & smt_mask,
        }
        for key, mask in cells.items():
            fvg_summary[key] = agg(wl[mask])
```

Now find the `return dict(...)` at the end of `build_model_stats` (search for `smt_summary=smt_summary`) and add the new field next to it. Search for the line `smt_summary=smt_summary,` (one occurrence) and replace with:

```python
        smt_summary=smt_summary,
        fvg_summary=fvg_summary,
```

(If `smt_summary=smt_summary` appears in a different shape — e.g. dict keys with quotes — match the surrounding style.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_supporting_fvg_integration.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 207 pass · 20 skip (205 from before + 2 from this task).

- [ ] **Step 6: Commit**

```bash
git add "Fractal Sweep/engine/model_stats.py" "Fractal Sweep/tests/test_supporting_fvg_integration.py"
git commit -m "feat(fractal-sweep): fvg_summary aggregate block in build_model_stats"
```

---

## Task 11: Run engine end-to-end and capture FVG numbers

**Files:**
- No code changes. This is the data-generation + decision step.

- [ ] **Step 1: Run the full engine on NQ for both models**

From the `Fractal Sweep/` directory:

```bash
python3 engine/model_stats.py
```

Expected: completes without error, writes `model_stats.json` (~140 MB) to the same folder.

- [ ] **Step 2: Inspect the new `fvg_summary` blocks**

```bash
python3 -c "
import json
with open('model_stats.json') as f:
    data = json.load(f)
for model_key in ('1H_5M', '30M_3M'):
    m = data['models'][model_key]['profiles']['simple_1r']
    fs = m['fvg_summary']
    print(f'\n=== {model_key} ===')
    for k in ('cisd_strict','cisd_loose','no_cisd_fvg',
              'm1_strict','m1_loose','no_m1_fvg',
              'any_strict','any_loose',
              'cisd_strict_smt','m1_strict_smt','any_strict_smt'):
        cell = fs[k]
        print(f'  {k:20s}  n={cell[\"n\"]:>5d}  wr={cell[\"wr\"]:.3f}  ev={cell[\"ev\"]:+.3f}  pf={cell[\"pf\"]:.2f}')
"
```

If the JSON path differs from `data['models'][model_key]['profiles']['simple_1r']`, inspect with:

```bash
python3 -c "import json; d = json.load(open('model_stats.json')); print(list(d.keys()))"
```

…and adjust accordingly.

- [ ] **Step 3: Apply decision criterion and write a one-paragraph note**

Decision rules (from the spec):

1. Standalone edge ≥ +3% WR over baseline (~50%) AND N ≥ 500 → promote.
2. Stacks with SMT ≥ +1% WR over `smt`-alone with N ≥ 200 → promote.

Compute the deltas:

```bash
python3 -c "
import json
data = json.load(open('model_stats.json'))
for model_key in ('1H_5M', '30M_3M'):
    m = data['models'][model_key]['profiles']['simple_1r']
    baseline_wr = m['overall']['wr']
    smt_only_wr = next(s['wr'] for s in m['smt_summary'] if s.get('smt') is True)
    fs = m['fvg_summary']
    print(f'\n{model_key}: baseline_wr={baseline_wr:.3f}  smt_only_wr={smt_only_wr:.3f}')
    for k, cell in fs.items():
        if cell['n'] == 0:
            continue
        delta = cell['wr'] - baseline_wr
        smt_delta = cell['wr'] - smt_only_wr if 'smt' in k else None
        smt_str = f'  vs_smt={smt_delta:+.3f}' if smt_delta is not None else ''
        print(f'  {k:20s}  n={cell[\"n\"]:>5d}  wr={cell[\"wr\"]:.3f}  Δbase={delta:+.3f}{smt_str}')
"
```

Write the verdict (promote / drop / mixed) to a short note appended to the spec file at `docs/superpowers/specs/2026-04-26-supporting-fvg-confluence-design.md` under a new `## Results` section. Include the per-cell numbers from above and the promote/drop call for each cell.

- [ ] **Step 4: Commit the results note**

```bash
git add "docs/superpowers/specs/2026-04-26-supporting-fvg-confluence-design.md"
git commit -m "results(fractal-sweep): supporting FVG confluence — engine numbers"
```

---

## Task 12: Update CLAUDE.md / PIPELINE.md (only if any cell promotes)

**Skip this task entirely** if no cell met the decision criterion in Task 11. The flags stay in trade rows for future reference but no documentation surface-area is added.

If at least one cell promotes:

**Files:**
- Modify: `Fractal Sweep/CLAUDE.md` — add the four flag names to the trade-row field list and document the `fvg_summary` block alongside `smt_summary`.
- Modify: `Fractal Sweep/PIPELINE.md` — same: extend the "Trade Row Fields" table with the four flags and add an `fvg_summary` row to the aggregation list.
- Modify: `Statistic.ally/.claude/rules/fractal-sweep.md` — add the four flag names under "Runtime Filter Fields on Each Trade Row".

- [ ] **Step 1: Add to CLAUDE.md trade-row fields table**

Open `Fractal Sweep/CLAUDE.md` and find the existing trade-row docs (search for `passes_f3`). Add four rows beneath:

```markdown
| `passes_fvg_cisd_strict` | bool | CISD-TF unfilled same-side FVG between SL and entry |
| `passes_fvg_cisd_loose`  | bool | CISD-TF unfilled same-side FVG with top below entry  |
| `passes_fvg_1m_strict`   | bool | 1M unfilled same-side FVG between SL and entry       |
| `passes_fvg_1m_loose`    | bool | 1M unfilled same-side FVG with top below entry       |
```

- [ ] **Step 2: Add to PIPELINE.md**

Make the same trade-row addition to the table in `Fractal Sweep/PIPELINE.md`. Then add to the aggregation list (near `smt_summary`):

```markdown
Applied to: `by_hour`, `by_session`, `by_dow`, `by_year`, `dir_summary`, `tspot_breakdown`, `smt_summary`, `fvg_summary`
```

- [ ] **Step 3: Add to .claude/rules/fractal-sweep.md**

Open `Statistic.ally/.claude/rules/fractal-sweep.md` and find the section "Runtime Filter Fields on Each Trade Row". Add:

```markdown
- `passes_fvg_cisd_strict`, `passes_fvg_cisd_loose` — CISD-TF supporting FVG flags
- `passes_fvg_1m_strict`,   `passes_fvg_1m_loose`   — 1M supporting FVG flags
```

- [ ] **Step 4: Commit**

```bash
git add "Fractal Sweep/CLAUDE.md" "Fractal Sweep/PIPELINE.md" ".claude/rules/fractal-sweep.md"
git commit -m "docs(fractal-sweep): document supporting FVG flags + fvg_summary"
```

---

## Self-Review

**Spec coverage:**
- Detection helper with strict/loose per TF → Tasks 1–8 (helper + unit tests).
- Two TFs scanned (CISD-TF + 1M) → Task 9 wires both calls in `detect_setups_base`.
- Anchor-window scope → Task 9 uses `q1_start_ns` and `entry_ts_ns`/`entry_start` as window boundaries (matches existing engine invariant).
- Four boolean fields per trade row → Task 9 adds them to both `base_row = dict(...)` (no-CISD path defaults) and `base_row.update(...)` (post-entry real values).
- `fvg_summary` block with all listed keys → Task 10 builds it and includes confluence-with-SMT cells.
- Decision criterion application → Task 11 computes deltas and writes the verdict.
- Doc updates deferred until criterion met → Task 12 is conditional.
- Strict ⇒ loose invariant → covered in helper (strict early-returns `(True, True)`), in `test_strict_implies_loose_invariant_random` (Task 8), and in the integration test (Task 9).

**Placeholder scan:**
- No "TBD", "TODO", or "implement later" anywhere.
- Every code step contains the actual code.
- All commands have explicit expected output.

**Type consistency:**
- Helper signature `find_supporting_fvg(arrs, window_start_idx, entry_idx, sweep_extreme, entry_price, direction)` is identical in Tasks 1, 9, and the integration test.
- Flag field names `passes_fvg_cisd_strict`, `passes_fvg_cisd_loose`, `passes_fvg_1m_strict`, `passes_fvg_1m_loose` are spelled identically across Tasks 9, 10, 11, and 12.
- `fvg_summary` cell keys match between Task 10's implementation, the integration test, and the JSON inspection in Task 11.

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-26-supporting-fvg-confluence.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
