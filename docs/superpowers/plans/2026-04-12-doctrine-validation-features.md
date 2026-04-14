# Doctrine Validation Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close four Wolf Tank doctrine gaps in the Fractal Sweep fixed constant model: fade simulation engine, custom IS/OOS date-range filter, variance display across rolling lookbacks, and volatility regime cheat sheet + rolling 70-day lookback view.

**Architecture:** Three-layer change over three commits. (1) Engine gains `block_range_pts` per rep + a second-pass `compute_fade_metrics()` function that walks 1m bars after MAE99 breach and records three confirmation booleans. (2) Dashboard gains a global IS/OOS filter in the header + a client-side recompute pipeline (`filterReps` / `computeDistributions` / `classifyRegimes`) that re-scopes every existing tab on filter change. (3) Dashboard gains a new Validation tab with four panels (rolling live parameters, variance chart, fade engine view, regime cheat sheet), all consuming the same recompute pipeline.

**Tech Stack:** Python 3.9+ · pandas · numpy · DuckDB · pytest · vanilla JS + SVG (zero dependencies)

**Spec:** `docs/superpowers/specs/2026-04-12-doctrine-validation-features-design.md`

**Worktree note:** This plan was not created inside a git worktree. The three commits are structured to land cleanly on a feature branch; create one with `git checkout -b doctrine-validation` before starting if isolation is desired.

---

## File structure

**Engine (Commit 1):**
- Modify: `Fractal Sweep/model_stats_fixed_constant.py`
  - `scan_fixed_constant_model()` — emit `block_range_pts` and internal ns fields (`_m1_start`, `_m1_end`, `_lock_ts_end_ns`) per rep
  - New function `compute_block_range_pts(m1_arrs, m1_start_block, m1_end_block)` — helper
  - New function `compute_fade_metrics(reps, m1_arrs, mae99_up_pct, mae99_down_pct, p50_up_pct, p50_down_pct)` — mutates reps in-place
  - New function `build_fade_summary(reps)` — produces the `fade_summary` dict
  - `build_model_stats()` — call `build_fade_summary`, strip underscore-prefixed fields before returning `recent_reps`
  - `main()` — after scan, compute thresholds from aggregated dist, call `compute_fade_metrics`, then `build_model_stats`
- Create: `Fractal Sweep/tests/test_fade_engine.py` — six synthetic fixtures + helpers
- Create: `Fractal Sweep/tests/validate_fade_output.py` — Layer B sanity script

**Dashboard recompute pipeline (Commit 2):**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html`
  - Header HTML: date inputs, regime pill, rolling window dropdown
  - JS globals: `_filterStart`, `_filterEnd`, `_filterRegime`, `_rollingWindowDays`
  - New functions: `filterReps()`, `buildDist()`, `groupAndAggregate()`, `computeDistributions()`, `classifyRegimes()`
  - Modify `render()` and all existing render helpers to read from `computeDistributions(filterReps(D.recent_reps))` instead of pre-computed `D.up_dist` / `D.down_dist` / `D.by_*`

**Dashboard Validation tab (Commit 3):**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html`
  - New tab button in `.page-nav`
  - New tab container with four panels
  - New functions: `renderValidationTab()`, `renderRollingCard()`, `renderVarianceChart()`, `renderFadeView()`, `renderRegimeCheatsheet()`
  - Wire rolling window dropdown to trigger Panel 1 re-render
  - Back-compat guards for missing `fade_summary` / `block_range_pts`

---

# COMMIT 1 — ENGINE

## Task 1: Extract `compute_block_range_pts()` helper with failing test

**Files:**
- Modify: `Fractal Sweep/model_stats_fixed_constant.py`
- Create: `Fractal Sweep/tests/test_fade_engine.py`

- [ ] **Step 1: Create test file with imports and first failing test**

Create `Fractal Sweep/tests/test_fade_engine.py`:

```python
"""Tests for fade engine: block_range_pts helper + compute_fade_metrics."""
import numpy as np
import pytest
import model_stats_fixed_constant as mfc

NS_PER_MIN = np.int64(60_000_000_000)
BASE_TS = np.int64(1_700_000_000_000_000_000)


def _make_m1(n_bars, highs, lows, closes=None, opens=None, start_ts=BASE_TS):
    """Build a minimal m1_arrs dict from explicit OHLC arrays."""
    ts_ns = np.array([start_ts + i * NS_PER_MIN for i in range(n_bars)], dtype='int64')
    highs = np.asarray(highs, dtype='float64')
    lows = np.asarray(lows, dtype='float64')
    if closes is None:
        closes = (highs + lows) / 2
    if opens is None:
        opens = closes.copy()
    return dict(
        ts_ns=ts_ns,
        open=np.asarray(opens, dtype='float64'),
        high=highs,
        low=lows,
        close=np.asarray(closes, dtype='float64'),
    )


class TestBlockRangePts:
    def test_simple_range(self):
        """Block with high=100.5 and low=99.0 → range = 1.5."""
        m1 = _make_m1(
            n_bars=10,
            highs=[100.0, 100.5, 100.2, 100.1, 99.8, 99.5, 99.3, 99.2, 99.1, 99.0],
            lows= [ 99.5,  99.8,  99.7,  99.6, 99.2, 99.0, 99.1, 99.1, 99.0, 99.0],
        )
        result = mfc.compute_block_range_pts(m1, 0, 10)
        assert result == pytest.approx(1.5)

    def test_empty_slice_returns_zero(self):
        """Empty m1 slice → 0.0."""
        m1 = _make_m1(n_bars=5, highs=[100.0]*5, lows=[99.0]*5)
        result = mfc.compute_block_range_pts(m1, 2, 2)
        assert result == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py::TestBlockRangePts -v
```

Expected: FAIL with `AttributeError: module 'model_stats_fixed_constant' has no attribute 'compute_block_range_pts'`.

- [ ] **Step 3: Implement `compute_block_range_pts` in the engine**

Add to `Fractal Sweep/model_stats_fixed_constant.py` immediately after the `get_session` function (around line 134, before `scan_fixed_constant_model`):

```python
# ── BLOCK RANGE HELPER ───────────────────────────────────────────────────────
def compute_block_range_pts(m1_arrs, m1_start_block, m1_end_block):
    """
    Return the high-low range (in points) of all 1m bars in [m1_start_block, m1_end_block).
    Returns 0.0 if the slice is empty.
    """
    if m1_end_block <= m1_start_block:
        return 0.0
    highs = m1_arrs['high'][m1_start_block:m1_end_block]
    lows = m1_arrs['low'][m1_start_block:m1_end_block]
    return float(highs.max() - lows.min())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py::TestBlockRangePts -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_stats_fixed_constant.py" "Fractal Sweep/tests/test_fade_engine.py"
git commit -m "feat(fixed-constant): add compute_block_range_pts helper"
```

---

## Task 2: Emit `block_range_pts` and internal ns fields from scan

**Files:**
- Modify: `Fractal Sweep/model_stats_fixed_constant.py:224-243` (the `rep = {...}` dict in `scan_fixed_constant_model`)
- Modify: `Fractal Sweep/tests/test_fade_engine.py`

- [ ] **Step 1: Add failing test asserting new fields on a rep**

Append to `Fractal Sweep/tests/test_fade_engine.py`:

```python
def _make_htf_arrs(n_bars, start_ts=BASE_TS, period_min=60):
    """Minimal HTF arrays for scan_fixed_constant_model."""
    ts_ns = np.array([start_ts + i * period_min * NS_PER_MIN for i in range(n_bars)], dtype='int64')
    trade_date = np.array(['2023-11-14'] * n_bars)
    return dict(
        ts_ns=ts_ns,
        open=np.full(n_bars, 100.0, dtype='float64'),
        high=np.full(n_bars, 101.0, dtype='float64'),
        low=np.full(n_bars, 99.0, dtype='float64'),
        close=np.full(n_bars, 100.0, dtype='float64'),
        trade_date=trade_date,
        yr=np.full(n_bars, 2023, dtype='int32'),
        dow=np.full(n_bars, 1, dtype='int32'),
        hr=np.full(n_bars, 9, dtype='int32'),
        mn=np.full(n_bars, 0, dtype='int32'),
    )


def _make_chart_arrs(htf_ts_ns, chart_tf_min=5, bars_per_htf=12):
    """Chart-TF arrays aligned with HTF starts."""
    n = len(htf_ts_ns) * bars_per_htf
    ts_ns = np.zeros(n, dtype='int64')
    for i, h_ts in enumerate(htf_ts_ns):
        for b in range(bars_per_htf):
            ts_ns[i * bars_per_htf + b] = h_ts + b * chart_tf_min * NS_PER_MIN
    return dict(
        ts_ns=ts_ns,
        open=np.full(n, 100.0, dtype='float64'),
        high=np.full(n, 100.5, dtype='float64'),
        low=np.full(n, 99.5, dtype='float64'),
        close=np.full(n, 100.0, dtype='float64'),
        trade_date=np.array(['2023-11-14'] * n),
        yr=np.full(n, 2023, dtype='int32'),
        dow=np.full(n, 1, dtype='int32'),
        hr=np.full(n, 9, dtype='int32'),
        mn=np.array([b * chart_tf_min % 60 for b in range(n)], dtype='int32'),
    )


class TestScanEmitsNewFields:
    def test_rep_has_block_range_pts_and_internal_ns(self):
        """Every emitted rep carries block_range_pts + internal ns fields."""
        htf = _make_htf_arrs(n_bars=3, period_min=60)
        chart = _make_chart_arrs(htf['ts_ns'], chart_tf_min=5, bars_per_htf=12)
        # m1: 60 bars per HTF block, simple oscillation
        n_m1 = 60 * 3
        highs = np.full(n_m1, 100.3, dtype='float64')
        lows = np.full(n_m1, 99.7, dtype='float64')
        highs[30] = 101.0  # peak in block 1
        lows[45] = 99.0    # trough in block 1
        m1 = _make_m1(n_bars=n_m1, highs=highs, lows=lows, start_ts=BASE_TS)
        cfg = dict(htf_min=60, chart_tf_min=5)
        reps = mfc.scan_fixed_constant_model(htf, chart, m1, '1H_5M', cfg)
        assert len(reps) >= 1
        r = reps[0]
        assert 'block_range_pts' in r
        assert r['block_range_pts'] > 0
        assert '_m1_start' in r
        assert '_m1_end' in r
        assert '_lock_ts_end_ns' in r
        assert '_lock_close' in r
        assert isinstance(r['_m1_start'], int)
        assert isinstance(r['_m1_end'], int)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py::TestScanEmitsNewFields -v
```

Expected: FAIL — the rep dict is missing `block_range_pts` and internal ns fields.

- [ ] **Step 3: Modify the rep dict in `scan_fixed_constant_model`**

In `Fractal Sweep/model_stats_fixed_constant.py`, locate the rep dict construction inside `scan_fixed_constant_model()` (lines ~224-243). Immediately before the `rep = {` line, compute the block range:

```python
        # Block range: full HTF block window (for regime classification)
        m1_start_block = int(np.searchsorted(m1_arrs['ts_ns'], htf_start_ns, side='left'))
        m1_end_block = int(np.searchsorted(m1_arrs['ts_ns'], htf_end_ns, side='left'))
        block_range_pts = compute_block_range_pts(m1_arrs, m1_start_block, m1_end_block)
```

Then add these fields to the existing `rep = {...}` dict (append them after `'session': session,`):

```python
            'block_range_pts': round(block_range_pts, 2),
            # Internal fields consumed by compute_fade_metrics; stripped before JSON serialization
            '_m1_start': m1_start,
            '_m1_end': m1_end,
            '_lock_ts_end_ns': lock_ts_end_ns,
            '_lock_close': htf_close,
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py -v
```

Expected: all tests PASS (TestBlockRangePts + TestScanEmitsNewFields).

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_stats_fixed_constant.py" "Fractal Sweep/tests/test_fade_engine.py"
git commit -m "feat(fixed-constant): emit block_range_pts and internal ns fields per rep"
```

---

## Task 3: `compute_fade_metrics` — fixture 1 (no trigger)

**Files:**
- Modify: `Fractal Sweep/model_stats_fixed_constant.py`
- Modify: `Fractal Sweep/tests/test_fade_engine.py`

- [ ] **Step 1: Add failing fixture 1 test**

Append to `Fractal Sweep/tests/test_fade_engine.py`:

```python
def _synthetic_rep(m1_start, m1_end, lock_ts_end_ns, lock_close,
                   excursion_up_pct, excursion_down_pct):
    """Build a minimal rep dict with the fields compute_fade_metrics reads."""
    return {
        'excursion_up_pct': excursion_up_pct,
        'excursion_down_pct': excursion_down_pct,
        '_m1_start': m1_start,
        '_m1_end': m1_end,
        '_lock_ts_end_ns': lock_ts_end_ns,
        '_lock_close': lock_close,
    }


class TestFadeMetricsFixtures:
    def test_fixture_1_no_trigger(self):
        """
        Neither excursion side breaches MAE99. fade_triggered = false,
        all fade fields None, no walk forward.
        """
        # lock_close = 100.0; MAE99 up = 0.5%; MAE99 down = 0.5%
        # Max up = 100.2 (0.20% < 0.5%); Max down = 99.8 (0.20% < 0.5%)
        highs = np.full(10, 100.2, dtype='float64')
        lows  = np.full(10, 99.8, dtype='float64')
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.20, excursion_down_pct=0.20,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is False
        assert rep['fade_breach_side'] is None
        assert rep['fade_reached_anchor'] is None
        assert rep['fade_reached_mfe50_opp'] is None
        assert rep['fade_reached_mae99_opp'] is None
        assert rep['fade_mfe_opp_pct'] is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py::TestFadeMetricsFixtures::test_fixture_1_no_trigger -v
```

Expected: FAIL with `AttributeError: module 'model_stats_fixed_constant' has no attribute 'compute_fade_metrics'`.

- [ ] **Step 3: Implement `compute_fade_metrics` (minimal — handles no-trigger path only)**

Add to `Fractal Sweep/model_stats_fixed_constant.py` immediately after `compute_block_range_pts`:

```python
# ── FADE ENGINE ──────────────────────────────────────────────────────────────
def compute_fade_metrics(reps, m1_arrs,
                         mae99_up_pct, mae99_down_pct,
                         p50_up_pct, p50_down_pct):
    """
    Second pass: for each rep, determine if MAE99 was breached and walk forward
    from the breach bar to block end to measure fade outcome. Mutates reps in place.

    For each rep, sets:
      fade_triggered        bool
      fade_breach_side      'up' | 'down' | None
      fade_reached_anchor   bool | None
      fade_reached_mfe50_opp bool | None
      fade_reached_mae99_opp bool | None
      fade_mfe_opp_pct      float | None  (always >= 0, % of lock_close)

    None (not 0) on non-triggered reps.
    """
    for rep in reps:
        up = rep['excursion_up_pct']
        dn = rep['excursion_down_pct']
        up_breached = up >= mae99_up_pct
        dn_breached = dn >= mae99_down_pct

        if not up_breached and not dn_breached:
            rep['fade_triggered'] = False
            rep['fade_breach_side'] = None
            rep['fade_reached_anchor'] = None
            rep['fade_reached_mfe50_opp'] = None
            rep['fade_reached_mae99_opp'] = None
            rep['fade_mfe_opp_pct'] = None
            continue

        # Determine breach side (first-to-breach wins ties — implemented in later task)
        # For now, handle single-side breach only.
        rep['fade_triggered'] = True
        rep['fade_breach_side'] = 'up' if up_breached else 'down'
        # Placeholder — full walk-forward logic added in Task 4
        rep['fade_reached_anchor'] = False
        rep['fade_reached_mfe50_opp'] = False
        rep['fade_reached_mae99_opp'] = False
        rep['fade_mfe_opp_pct'] = 0.0
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py::TestFadeMetricsFixtures::test_fixture_1_no_trigger -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_stats_fixed_constant.py" "Fractal Sweep/tests/test_fade_engine.py"
git commit -m "feat(fixed-constant): scaffold compute_fade_metrics with no-trigger path"
```

---

## Task 4: `compute_fade_metrics` — fixtures 2, 3, 4 (up breach, walk-forward logic)

**Files:**
- Modify: `Fractal Sweep/model_stats_fixed_constant.py`
- Modify: `Fractal Sweep/tests/test_fade_engine.py`

- [ ] **Step 1: Add failing tests for fixtures 2, 3, 4**

Append to `TestFadeMetricsFixtures` class in `Fractal Sweep/tests/test_fade_engine.py`:

```python
    def test_fixture_2_up_breach_no_fade(self):
        """
        Up excursion breaches MAE99 (0.5%), then price stays above lock_close.
        Expected: fade_triggered=True, fade_breach_side='up',
        fade_reached_anchor=False, fade_mfe_opp_pct ≈ 0.
        """
        # lock_close = 100.0; 10 m1 bars
        # Bars 0-4: rising up to 100.8 (0.8% breach at bar 4)
        # Bars 5-9: hold 100.5..100.7 — price never returns to anchor
        highs = np.array([100.1, 100.3, 100.5, 100.7, 100.8, 100.7, 100.6, 100.7, 100.5, 100.6])
        lows  = np.array([100.0, 100.1, 100.2, 100.4, 100.5, 100.4, 100.4, 100.5, 100.4, 100.5])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.80, excursion_down_pct=0.00,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        assert rep['fade_breach_side'] == 'up'
        assert rep['fade_reached_anchor'] is False
        assert rep['fade_reached_mfe50_opp'] is False
        assert rep['fade_reached_mae99_opp'] is False
        assert rep['fade_mfe_opp_pct'] == pytest.approx(0.0, abs=1e-6)

    def test_fixture_3_up_breach_anchor_reached_no_mfe50(self):
        """
        Up excursion breaches MAE99, then price dips to 99.95 after breach
        (0.05% below anchor — reaches anchor but not MFE50 of 0.15%).
        """
        # Bar 3 breaches up to 100.8; bar 7 dips to 99.95
        highs = np.array([100.2, 100.4, 100.6, 100.8, 100.5, 100.3, 100.1, 99.98, 99.99, 100.0])
        lows  = np.array([100.0, 100.2, 100.4, 100.5, 100.2, 100.0, 99.98, 99.95, 99.96, 99.97])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.80, excursion_down_pct=0.05,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        assert rep['fade_breach_side'] == 'up'
        assert rep['fade_reached_anchor'] is True
        assert rep['fade_reached_mfe50_opp'] is False
        assert rep['fade_reached_mae99_opp'] is False
        # fade_mfe_opp_pct = max opposite (down) excursion from anchor after breach ≈ 0.05%
        assert rep['fade_mfe_opp_pct'] == pytest.approx(0.05, abs=0.01)

    def test_fixture_4_up_breach_full_mae99_opposite(self):
        """
        Up excursion breaches MAE99 at bar 3, then fully reverses to 99.4
        (0.6% below anchor — beyond MAE99 down of 0.5%).
        Expected: all three confirmation booleans true.
        """
        highs = np.array([100.2, 100.4, 100.6, 100.8, 100.3, 99.9, 99.6, 99.5, 99.4, 99.5])
        lows  = np.array([100.0, 100.2, 100.4, 100.5, 100.0, 99.7, 99.5, 99.4, 99.4, 99.4])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.80, excursion_down_pct=0.60,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        assert rep['fade_breach_side'] == 'up'
        assert rep['fade_reached_anchor'] is True
        assert rep['fade_reached_mfe50_opp'] is True
        assert rep['fade_reached_mae99_opp'] is True
        assert rep['fade_mfe_opp_pct'] >= 0.50
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py::TestFadeMetricsFixtures -v
```

Expected: fixture 1 PASS; fixtures 2, 3, 4 FAIL (placeholder logic doesn't walk forward).

- [ ] **Step 3: Implement full walk-forward logic**

Replace the body of `compute_fade_metrics` in `Fractal Sweep/model_stats_fixed_constant.py` with:

```python
def compute_fade_metrics(reps, m1_arrs,
                         mae99_up_pct, mae99_down_pct,
                         p50_up_pct, p50_down_pct):
    """
    Second pass: for each rep, determine if MAE99 was breached and walk forward
    from the breach bar to block end to measure fade outcome. Mutates reps in place.

    Thresholds (mae99/p50) are in percent. Breach bar is the first m1 bar in
    [m1_start, m1_end) whose high (up breach) or low (down breach) crosses the
    threshold price. Walk-forward starts at breach_bar + 1.

    Sets per rep:
      fade_triggered         bool
      fade_breach_side       'up' | 'down' | None
      fade_reached_anchor    bool | None
      fade_reached_mfe50_opp bool | None
      fade_reached_mae99_opp bool | None
      fade_mfe_opp_pct       float | None  (always >= 0, % of lock_close)

    None (not 0) on non-triggered reps.
    """
    highs = m1_arrs['high']
    lows = m1_arrs['low']

    for rep in reps:
        up = rep['excursion_up_pct']
        dn = rep['excursion_down_pct']
        up_breached = up >= mae99_up_pct
        dn_breached = dn >= mae99_down_pct

        if not up_breached and not dn_breached:
            rep['fade_triggered'] = False
            rep['fade_breach_side'] = None
            rep['fade_reached_anchor'] = None
            rep['fade_reached_mfe50_opp'] = None
            rep['fade_reached_mae99_opp'] = None
            rep['fade_mfe_opp_pct'] = None
            continue

        m1_start = rep['_m1_start']
        m1_end = rep['_m1_end']
        lock_close = rep['_lock_close']

        up_trigger_price = lock_close * (1.0 + mae99_up_pct / 100.0)
        dn_trigger_price = lock_close * (1.0 - mae99_down_pct / 100.0)

        # Find breach bar for each side (first m1 bar whose extreme crosses)
        up_breach_idx = -1
        dn_breach_idx = -1
        if up_breached:
            for k in range(m1_start, m1_end):
                if highs[k] >= up_trigger_price:
                    up_breach_idx = k
                    break
        if dn_breached:
            for k in range(m1_start, m1_end):
                if lows[k] <= dn_trigger_price:
                    dn_breach_idx = k
                    break

        # Tiebreaker: whichever side's breach bar is earliest
        if up_breach_idx >= 0 and (dn_breach_idx < 0 or up_breach_idx <= dn_breach_idx):
            breach_side = 'up'
            breach_idx = up_breach_idx
        else:
            breach_side = 'down'
            breach_idx = dn_breach_idx

        rep['fade_triggered'] = True
        rep['fade_breach_side'] = breach_side

        # Walk forward from breach_bar + 1 to m1_end
        # For up-breach: measure max down excursion (low) from anchor
        # For down-breach: measure max up excursion (high) from anchor
        max_opp_pct = 0.0
        if breach_side == 'up':
            for k in range(breach_idx + 1, m1_end):
                low_k = lows[k]
                opp_pct = (lock_close - low_k) / lock_close * 100.0
                if opp_pct > max_opp_pct:
                    max_opp_pct = opp_pct
        else:  # 'down'
            for k in range(breach_idx + 1, m1_end):
                high_k = highs[k]
                opp_pct = (high_k - lock_close) / lock_close * 100.0
                if opp_pct > max_opp_pct:
                    max_opp_pct = opp_pct

        # Confirmation thresholds (opposite-side percentiles from anchor)
        opp_p50 = p50_down_pct if breach_side == 'up' else p50_up_pct
        opp_mae99 = mae99_down_pct if breach_side == 'up' else mae99_up_pct

        rep['fade_reached_anchor'] = max_opp_pct > 0.0
        rep['fade_reached_mfe50_opp'] = max_opp_pct >= opp_p50
        rep['fade_reached_mae99_opp'] = max_opp_pct >= opp_mae99
        rep['fade_mfe_opp_pct'] = round(max_opp_pct, 4)
```

- [ ] **Step 4: Run tests to verify all four fixtures pass**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py -v
```

Expected: fixtures 1, 2, 3, 4 all PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_stats_fixed_constant.py" "Fractal Sweep/tests/test_fade_engine.py"
git commit -m "feat(fixed-constant): implement fade walk-forward with MAE99 confirmation"
```

---

## Task 5: `compute_fade_metrics` — fixtures 5, 6 (symmetric down, both-sides tiebreaker)

**Files:**
- Modify: `Fractal Sweep/tests/test_fade_engine.py`

- [ ] **Step 1: Add failing tests for fixtures 5 and 6**

Append to `TestFadeMetricsFixtures`:

```python
    def test_fixture_5_down_breach_symmetric(self):
        """
        Symmetric of fixture 4 on the down side: down excursion breaches MAE99,
        then rebounds past anchor + MAE99 up.
        """
        # Bar 3 breaches down to 99.2 (0.8%); bars 7-9 rebound to 100.6+
        highs = np.array([100.0, 99.8, 99.6, 99.5, 100.0, 100.3, 100.5, 100.6, 100.7, 100.6])
        lows  = np.array([99.8, 99.6, 99.4, 99.2, 99.7, 100.0, 100.2, 100.5, 100.5, 100.5])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.70, excursion_down_pct=0.80,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        assert rep['fade_breach_side'] == 'down'
        assert rep['fade_reached_anchor'] is True
        assert rep['fade_reached_mfe50_opp'] is True
        assert rep['fade_reached_mae99_opp'] is True
        assert rep['fade_mfe_opp_pct'] >= 0.50

    def test_fixture_6_both_sides_breach_earliest_wins(self):
        """
        Down breach occurs at bar 2, up breach occurs at bar 6. Tiebreaker:
        earliest bar wins. Expected fade_breach_side='down'.
        """
        # Bar 2: down to 99.4 (0.6% down breach)
        # Bar 6: up to 100.6 (0.6% up breach)
        highs = np.array([100.0, 99.9, 99.7, 99.9, 100.1, 100.3, 100.6, 100.5, 100.2, 99.9])
        lows  = np.array([99.9, 99.7, 99.4, 99.5, 99.8, 100.1, 100.3, 100.3, 100.0, 99.8])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.60, excursion_down_pct=0.60,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        # Bar 2 is the earliest breach → down wins the tiebreaker
        assert rep['fade_breach_side'] == 'down'
```

- [ ] **Step 2: Run tests to verify them**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py::TestFadeMetricsFixtures -v
```

Expected: all six fixtures PASS. The Task 4 implementation already handles the symmetric case and the tiebreaker logic (earliest breach index wins).

If fixture 5 or 6 FAILS, the tiebreaker condition in the Task 4 implementation is wrong — review `if up_breach_idx >= 0 and (dn_breach_idx < 0 or up_breach_idx <= dn_breach_idx)` and fix in place.

- [ ] **Step 3: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/tests/test_fade_engine.py"
git commit -m "test(fixed-constant): add fade symmetric and both-sides-breach fixtures"
```

---

## Task 6: `build_fade_summary` function with test

**Files:**
- Modify: `Fractal Sweep/model_stats_fixed_constant.py`
- Modify: `Fractal Sweep/tests/test_fade_engine.py`

- [ ] **Step 1: Add failing test for build_fade_summary**

Append to `Fractal Sweep/tests/test_fade_engine.py`:

```python
class TestFadeSummary:
    def test_builds_summary_from_reps(self):
        """Summary aggregates per-rep fade fields correctly."""
        reps = [
            # 1 non-triggered rep
            {'fade_triggered': False, 'fade_breach_side': None,
             'fade_reached_anchor': None, 'fade_reached_mfe50_opp': None,
             'fade_reached_mae99_opp': None, 'fade_mfe_opp_pct': None},
            # 1 up-breach rep that reached anchor only
            {'fade_triggered': True, 'fade_breach_side': 'up',
             'fade_reached_anchor': True, 'fade_reached_mfe50_opp': False,
             'fade_reached_mae99_opp': False, 'fade_mfe_opp_pct': 0.08},
            # 1 down-breach rep that reached anchor + MFE50 opp
            {'fade_triggered': True, 'fade_breach_side': 'down',
             'fade_reached_anchor': True, 'fade_reached_mfe50_opp': True,
             'fade_reached_mae99_opp': False, 'fade_mfe_opp_pct': 0.22},
            # 1 up-breach rep that reached all three
            {'fade_triggered': True, 'fade_breach_side': 'up',
             'fade_reached_anchor': True, 'fade_reached_mfe50_opp': True,
             'fade_reached_mae99_opp': True, 'fade_mfe_opp_pct': 0.55},
        ]
        summary = mfc.build_fade_summary(
            reps,
            mae99_up_pct=0.50, mae99_down_pct=0.48,
            p50_mfe_up_pct=0.14, p50_mfe_down_pct=0.13,
        )
        assert summary['n_total'] == 4
        assert summary['n_triggered'] == 3
        assert summary['trigger_rate'] == pytest.approx(0.75, abs=1e-6)
        assert summary['trigger_rate_up'] == pytest.approx(0.50, abs=1e-6)
        assert summary['trigger_rate_down'] == pytest.approx(0.25, abs=1e-6)
        assert summary['mae99_up_pct'] == 0.50
        assert summary['mae99_down_pct'] == 0.48
        assert summary['p50_mfe_up_pct'] == 0.14
        assert summary['p50_mfe_down_pct'] == 0.13
        # 3/3 reached anchor, 2/3 reached mfe50_opp, 1/3 reached mae99_opp
        assert summary['confirm_anchor_rate'] == pytest.approx(1.0, abs=1e-6)
        assert summary['confirm_mfe50_opp_rate'] == pytest.approx(2/3, abs=1e-6)
        assert summary['confirm_mae99_opp_rate'] == pytest.approx(1/3, abs=1e-6)
        assert 'fade_mfe_opp_dist' in summary
        assert summary['fade_mfe_opp_dist']['median'] == pytest.approx(0.22, abs=1e-6)

    def test_empty_triggered_set(self):
        """No triggered reps → rates and dist still present, zeros and None."""
        reps = [
            {'fade_triggered': False, 'fade_breach_side': None,
             'fade_reached_anchor': None, 'fade_reached_mfe50_opp': None,
             'fade_reached_mae99_opp': None, 'fade_mfe_opp_pct': None},
        ]
        summary = mfc.build_fade_summary(
            reps, mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_mfe_up_pct=0.15, p50_mfe_down_pct=0.15,
        )
        assert summary['n_triggered'] == 0
        assert summary['trigger_rate'] == 0.0
        assert summary['confirm_anchor_rate'] == 0.0
        assert summary['confirm_mfe50_opp_rate'] == 0.0
        assert summary['confirm_mae99_opp_rate'] == 0.0
        assert summary['fade_mfe_opp_dist'] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py::TestFadeSummary -v
```

Expected: FAIL with `AttributeError: module 'model_stats_fixed_constant' has no attribute 'build_fade_summary'`.

- [ ] **Step 3: Implement `build_fade_summary`**

Add to `Fractal Sweep/model_stats_fixed_constant.py` immediately after `compute_fade_metrics`:

```python
def build_fade_summary(reps, mae99_up_pct, mae99_down_pct,
                       p50_mfe_up_pct, p50_mfe_down_pct):
    """
    Aggregate fade metrics across reps. Returns dict suitable for the
    'fade_summary' key in the per-model output.
    """
    n_total = len(reps)
    triggered = [r for r in reps if r.get('fade_triggered')]
    n_triggered = len(triggered)

    up_triggered = sum(1 for r in triggered if r['fade_breach_side'] == 'up')
    dn_triggered = sum(1 for r in triggered if r['fade_breach_side'] == 'down')

    if n_total == 0:
        return {
            'n_total': 0, 'n_triggered': 0,
            'trigger_rate': 0.0, 'trigger_rate_up': 0.0, 'trigger_rate_down': 0.0,
            'mae99_up_pct': mae99_up_pct, 'mae99_down_pct': mae99_down_pct,
            'p50_mfe_up_pct': p50_mfe_up_pct, 'p50_mfe_down_pct': p50_mfe_down_pct,
            'confirm_anchor_rate': 0.0,
            'confirm_mfe50_opp_rate': 0.0,
            'confirm_mae99_opp_rate': 0.0,
            'fade_mfe_opp_dist': {},
        }

    if n_triggered == 0:
        confirm_anchor = 0.0
        confirm_mfe50 = 0.0
        confirm_mae99 = 0.0
        opp_dist = {}
    else:
        confirm_anchor = sum(1 for r in triggered if r['fade_reached_anchor']) / n_triggered
        confirm_mfe50 = sum(1 for r in triggered if r['fade_reached_mfe50_opp']) / n_triggered
        confirm_mae99 = sum(1 for r in triggered if r['fade_reached_mae99_opp']) / n_triggered
        opp_vals = pd.Series([r['fade_mfe_opp_pct'] for r in triggered if r['fade_mfe_opp_pct'] is not None])
        opp_dist = dist_stats(opp_vals) if len(opp_vals) >= 2 else {}

    return {
        'n_total': n_total,
        'n_triggered': n_triggered,
        'trigger_rate': round(n_triggered / n_total, 6),
        'trigger_rate_up': round(up_triggered / n_total, 6),
        'trigger_rate_down': round(dn_triggered / n_total, 6),
        'mae99_up_pct': mae99_up_pct,
        'mae99_down_pct': mae99_down_pct,
        'p50_mfe_up_pct': p50_mfe_up_pct,
        'p50_mfe_down_pct': p50_mfe_down_pct,
        'confirm_anchor_rate': round(confirm_anchor, 4),
        'confirm_mfe50_opp_rate': round(confirm_mfe50, 4),
        'confirm_mae99_opp_rate': round(confirm_mae99, 4),
        'fade_mfe_opp_dist': opp_dist,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py -v
```

Expected: all tests PASS including TestFadeSummary.

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_stats_fixed_constant.py" "Fractal Sweep/tests/test_fade_engine.py"
git commit -m "feat(fixed-constant): add build_fade_summary aggregation"
```

---

## Task 7: Wire fade pipeline into `main()` and strip internal fields

**Files:**
- Modify: `Fractal Sweep/model_stats_fixed_constant.py:297-374` (`build_model_stats`)
- Modify: `Fractal Sweep/model_stats_fixed_constant.py:378-439` (`main()`)

- [ ] **Step 1: Modify `build_model_stats` to accept `fade_summary` and strip internal fields**

In `Fractal Sweep/model_stats_fixed_constant.py`, change the signature of `build_model_stats` (line ~297) to accept an optional `fade_summary` argument:

```python
def build_model_stats(df, model_key, cfg, instrument, fade_summary=None):
```

At the end of the function, replace the current `return { ... 'recent_reps': df.to_dict('records') }` block with:

```python
    # Strip internal underscore-prefixed fields before serialization
    records = df.to_dict('records')
    for r in records:
        for k in ('_m1_start', '_m1_end', '_lock_ts_end_ns', '_lock_close'):
            r.pop(k, None)

    result = {
        'meta': meta,
        'by_hour': by_hour,
        'by_dow': by_dow,
        'by_session': by_session,
        'by_year': by_year,
        'up_dist': dist_stats(up_all),
        'down_dist': dist_stats(down_all),
        'recent_reps': records,
    }
    if fade_summary is not None:
        result['fade_summary'] = fade_summary
    return result
```

- [ ] **Step 2: Modify `main()` to compute thresholds and run fade pass**

In `Fractal Sweep/model_stats_fixed_constant.py`, locate the `main()` loop (line ~416 onwards) where `for model_key in args.models:` appears. Replace the inner body with:

```python
    for model_key in args.models:
        cfg = MODELS[model_key]
        htf_arrs = arrs[cfg['htf_min']]
        chart_arrs = arrs[cfg['chart_tf_min']]

        print(f'\n  Scanning {model_key} ...', flush=True)
        reps = scan_fixed_constant_model(htf_arrs, chart_arrs, m1_arrs, model_key, cfg)
        print(f'    {len(reps)} reps emitted', flush=True)

        if reps:
            # Compute aggregated thresholds from excursion fields
            up_series = pd.Series([r['excursion_up_pct'] for r in reps])
            dn_series = pd.Series([r['excursion_down_pct'] for r in reps])
            mae99_up = round(float(up_series.quantile(0.99)), 4)
            mae99_dn = round(float(dn_series.quantile(0.99)), 4)
            p50_up = round(float(up_series.quantile(0.50)), 4)
            p50_dn = round(float(dn_series.quantile(0.50)), 4)

            print(f'    [{model_key}] fade pass: mae99_up={mae99_up}% mae99_dn={mae99_dn}%', flush=True)
            compute_fade_metrics(reps, m1_arrs, mae99_up, mae99_dn, p50_up, p50_dn)
            fade_summary = build_fade_summary(reps, mae99_up, mae99_dn, p50_up, p50_dn)
            print(f'    [{model_key}] fade triggered: {fade_summary["n_triggered"]}/{fade_summary["n_total"]} ({fade_summary["trigger_rate"]*100:.2f}%)', flush=True)
        else:
            fade_summary = None

        df = pd.DataFrame(reps) if reps else pd.DataFrame()
        stats = build_model_stats(df, model_key, cfg, instrument, fade_summary=fade_summary)
        results[model_key] = stats
```

- [ ] **Step 3: Run full test suite**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py -v
```

Expected: all tests PASS (no regressions).

- [ ] **Step 4: Run engine on real NQ data**

```bash
cd "Fractal Sweep" && python3 model_stats_fixed_constant.py --models 1H_5M
```

Expected:
- Completes without error
- Prints `fade pass: mae99_up=... mae99_dn=...` for each model
- Prints `fade triggered: N/M (X.XX%)` — expect rate roughly 1-3%
- Writes `model_stats_fixed_constant.json`

- [ ] **Step 5: Verify JSON structure**

```bash
cd "Fractal Sweep" && python3 -c "
import json
d = json.load(open('model_stats_fixed_constant.json'))
m = d['1H_5M']
print('fade_summary present:', 'fade_summary' in m)
print('fade_summary:', m.get('fade_summary'))
r = m['recent_reps'][0]
print('rep fields:', sorted(r.keys()))
print('block_range_pts present:', 'block_range_pts' in r)
print('internal fields stripped:', not any(k.startswith('_') for k in r))
print('fade_triggered present:', 'fade_triggered' in r)
"
```

Expected:
- `fade_summary present: True`
- `block_range_pts present: True`
- `internal fields stripped: True`
- `fade_triggered present: True`

- [ ] **Step 6: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_stats_fixed_constant.py"
git commit -m "feat(fixed-constant): wire fade pipeline into main and strip internal fields"
```

---

## Task 8: `validate_fade_output.py` sanity script

**Files:**
- Create: `Fractal Sweep/tests/validate_fade_output.py`

- [ ] **Step 1: Create the validation script**

Create `Fractal Sweep/tests/validate_fade_output.py`:

```python
#!/usr/bin/env python3
"""
Layer B validation: sanity checks on the fade fields emitted by
model_stats_fixed_constant.py. Run after each engine execution.

Checks:
  1. fade_summary.trigger_rate is between 0.001 and 0.05 per model
  2. fade_summary.n_triggered matches count of reps with fade_triggered=True
  3. fade_breach_side matches which excursion exceeded its threshold
  4. Strict ordering: mae99_opp => mfe50_opp => anchor (if strongest reached,
     weaker ones must also be reached)

Exits 0 on success, non-zero on any violation.
"""
import json
import sys
from pathlib import Path

JSON_PATH = Path(__file__).parent.parent / 'model_stats_fixed_constant.json'


def validate_model(model_key, model):
    errors = []
    summary = model.get('fade_summary')
    if summary is None:
        errors.append(f'{model_key}: missing fade_summary')
        return errors

    reps = model.get('recent_reps', [])

    # Check 1: trigger rate in sane range (excluded for very small samples)
    if len(reps) >= 100:
        rate = summary['trigger_rate']
        if not (0.001 <= rate <= 0.05):
            errors.append(f'{model_key}: trigger_rate {rate:.4f} outside [0.001, 0.05]')

    # Check 2: n_triggered matches actual count
    actual_triggered = sum(1 for r in reps if r.get('fade_triggered'))
    if actual_triggered != summary['n_triggered']:
        errors.append(f'{model_key}: n_triggered mismatch (summary={summary["n_triggered"]}, actual={actual_triggered})')

    # Check 3 & 4: per-rep consistency
    mae99_up = summary['mae99_up_pct']
    mae99_dn = summary['mae99_down_pct']
    for i, r in enumerate(reps):
        if not r.get('fade_triggered'):
            continue
        side = r.get('fade_breach_side')
        up = r.get('excursion_up_pct', 0)
        dn = r.get('excursion_down_pct', 0)
        # Check 3: side matches a breach
        if side == 'up' and up < mae99_up:
            errors.append(f'{model_key} rep#{i}: side=up but excursion_up_pct={up} < mae99_up={mae99_up}')
        if side == 'down' and dn < mae99_dn:
            errors.append(f'{model_key} rep#{i}: side=down but excursion_down_pct={dn} < mae99_down={mae99_dn}')
        # Check 4: strict ordering
        a = r.get('fade_reached_anchor')
        m = r.get('fade_reached_mfe50_opp')
        m99 = r.get('fade_reached_mae99_opp')
        if m99 and not m:
            errors.append(f'{model_key} rep#{i}: mae99_opp=True but mfe50_opp=False')
        if m and not a:
            errors.append(f'{model_key} rep#{i}: mfe50_opp=True but anchor=False')

    return errors


def main():
    if not JSON_PATH.exists():
        print(f'ERROR: {JSON_PATH} not found', file=sys.stderr)
        sys.exit(2)

    data = json.load(open(JSON_PATH))
    all_errors = []
    for model_key, model in data.items():
        if not isinstance(model, dict) or 'meta' not in model:
            continue
        errors = validate_model(model_key, model)
        all_errors.extend(errors)

    if all_errors:
        print(f'FAIL: {len(all_errors)} violation(s)', file=sys.stderr)
        for e in all_errors[:50]:
            print(f'  {e}', file=sys.stderr)
        sys.exit(1)

    print(f'OK: all fade_summary checks passed for {len([k for k, v in data.items() if isinstance(v, dict)])} models')
    sys.exit(0)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run the validation script against the JSON from Task 7**

```bash
cd "/Users/abhi/Downloads/Statistic.ally" && python3 "Fractal Sweep/tests/validate_fade_output.py"
```

Expected: `OK: all fade_summary checks passed for N models`, exit 0.

- [ ] **Step 3: Run full engine + full test suite + validation one more time**

```bash
cd "Fractal Sweep" && python3 model_stats_fixed_constant.py && python3 -m pytest tests/test_fade_engine.py -v && python3 tests/validate_fade_output.py
```

Expected: engine completes, all tests PASS, validation OK.

- [ ] **Step 4: Verify existing dashboard still loads the new JSON (back-compat)**

```bash
cd "/Users/abhi/Downloads/Statistic.ally" && python3 -m http.server 8001 &
```

Open http://localhost:8001/Fractal%20Sweep/model_dashboard_fixed_constant.html in a browser. Verify:
- Dashboard loads without console errors
- Hero tiles render
- Percentile tables render
- Reps tab shows reps (the new `block_range_pts`, `fade_triggered`, etc. fields are present in the rep rows but existing render code ignores them)

Kill the server:

```bash
kill %1 2>/dev/null
```

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/tests/validate_fade_output.py"
git commit -m "test(fixed-constant): add fade output validation sanity script"
```

---

# COMMIT 2 — DASHBOARD FILTER + RECOMPUTE PIPELINE

## Task 9: Add header controls HTML

**Files:**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html` (around line 200, the existing header block)

- [ ] **Step 1: Locate the existing header**

Read lines 195-225 to locate the model-select dropdown and theme toggle. The header has a `<select id="model-select">` and buttons nearby.

- [ ] **Step 2: Add filter controls markup**

Immediately after the `<button class="load-btn">` element (or whichever existing element ends the right side of the header row), insert:

```html
<div class="filter-bar" style="display:flex;gap:12px;align-items:center;padding:8px 20px;border-bottom:1px solid var(--border);background:var(--bg-raised)">
  <label style="font-family:var(--font-data);font-size:11px;color:var(--text-dim);display:flex;align-items:center;gap:6px">
    From
    <input type="date" id="filter-start" style="background:var(--bg);border:1px solid var(--border-mid);color:var(--text-primary);border-radius:4px;padding:3px 6px;font-family:var(--font-data);font-size:11px">
  </label>
  <label style="font-family:var(--font-data);font-size:11px;color:var(--text-dim);display:flex;align-items:center;gap:6px">
    To
    <input type="date" id="filter-end" style="background:var(--bg);border:1px solid var(--border-mid);color:var(--text-primary);border-radius:4px;padding:3px 6px;font-family:var(--font-data);font-size:11px">
  </label>
  <button id="filter-apply" style="font-family:var(--font-data);font-size:11px;padding:4px 12px;border-radius:4px;border:1px solid var(--purple);background:var(--purple);color:#fff;cursor:pointer">Apply</button>
  <button id="filter-reset" style="font-family:var(--font-data);font-size:11px;padding:4px 12px;border-radius:4px;border:1px solid var(--border-mid);background:var(--bg-raised);color:var(--text-primary);cursor:pointer">Reset</button>

  <span style="width:1px;height:20px;background:var(--border)"></span>

  <span style="font-family:var(--font-data);font-size:11px;color:var(--text-dim)">Regime:</span>
  <div id="regime-pills" style="display:flex;gap:2px">
    <button class="regime-pill active" data-regime="all" style="font-family:var(--font-data);font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid var(--border-mid);background:var(--purple);color:#fff;cursor:pointer">All</button>
    <button class="regime-pill" data-regime="expanding" style="font-family:var(--font-data);font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid var(--border-mid);background:var(--bg-raised);color:var(--text-primary);cursor:pointer">Expanding</button>
    <button class="regime-pill" data-regime="neutral" style="font-family:var(--font-data);font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid var(--border-mid);background:var(--bg-raised);color:var(--text-primary);cursor:pointer">Neutral</button>
    <button class="regime-pill" data-regime="contracting" style="font-family:var(--font-data);font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid var(--border-mid);background:var(--bg-raised);color:var(--text-primary);cursor:pointer">Contracting</button>
  </div>

  <span style="width:1px;height:20px;background:var(--border)"></span>

  <label style="font-family:var(--font-data);font-size:11px;color:var(--text-dim);display:flex;align-items:center;gap:6px">
    Rolling
    <select id="rolling-window" style="background:var(--bg);border:1px solid var(--border-mid);color:var(--text-primary);border-radius:4px;padding:3px 6px;font-family:var(--font-data);font-size:11px">
      <option value="30">30d</option>
      <option value="70" selected>70d</option>
      <option value="180">180d</option>
      <option value="365">365d</option>
    </select>
  </label>

  <span id="filter-status" style="margin-left:auto;font-family:var(--font-data);font-size:11px;color:var(--text-dim)"></span>
</div>
```

- [ ] **Step 3: Reload the dashboard and verify the controls render**

```bash
cd "/Users/abhi/Downloads/Statistic.ally" && python3 -m http.server 8001 &
```

Open http://localhost:8001/Fractal%20Sweep/model_dashboard_fixed_constant.html. Verify:
- Header shows From/To date inputs, Apply/Reset buttons, Regime pills, Rolling dropdown
- No console errors
- Controls don't wire up yet — that's the next task

Kill server: `kill %1 2>/dev/null`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_dashboard_fixed_constant.html"
git commit -m "feat(fixed-constant-dash): add IS/OOS filter header controls"
```

---

## Task 10: Filter globals, `filterReps`, `buildDist`, `groupAndAggregate`, `computeDistributions`

**Files:**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html` (inside the existing `<script>` block, above `function render()`)

- [ ] **Step 1: Add filter state globals**

Locate the existing global declarations (near `let _repsPage` / `let _current`). Add:

```js
// ── IS/OOS filter state ──────────────────────────────────────────────────
let _filterStart = null;       // ISO date string 'YYYY-MM-DD' or null
let _filterEnd = null;         // ISO date string 'YYYY-MM-DD' or null
let _filterRegime = 'all';     // 'all' | 'expanding' | 'neutral' | 'contracting'
let _rollingWindowDays = 70;
```

- [ ] **Step 2: Add `filterReps()` primitive**

Below the globals, add:

```js
function filterReps(reps) {
  if (!reps) return [];
  return reps.filter(r => {
    const d = (r.date || '').slice(0, 10);  // 'YYYY-MM-DD'
    if (_filterStart && d < _filterStart) return false;
    if (_filterEnd   && d > _filterEnd)   return false;
    if (_filterRegime !== 'all' && r._regime !== _filterRegime) return false;
    return true;
  });
}
```

- [ ] **Step 3: Add `buildDist()` helper**

Add below `filterReps`:

```js
function _pct(sorted, p) {
  if (!sorted.length) return null;
  const idx = Math.max(0, Math.min(sorted.length - 1, Math.floor(sorted.length * p)));
  return sorted[idx];
}

function buildDist(values) {
  const arr = values.filter(v => v != null && !isNaN(v)).map(Number).sort((a, b) => a - b);
  if (arr.length < 2) return {};
  const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
  const sqDiff = arr.map(v => (v - mean) ** 2).reduce((a, b) => a + b, 0) / arr.length;
  return {
    n: arr.length,
    mean: +mean.toFixed(4),
    median: +_pct(arr, 0.50).toFixed(4),
    std: +Math.sqrt(sqDiff).toFixed(4),
    p10: +_pct(arr, 0.10).toFixed(4),
    p25: +_pct(arr, 0.25).toFixed(4),
    p50: +_pct(arr, 0.50).toFixed(4),
    p75: +_pct(arr, 0.75).toFixed(4),
    p90: +_pct(arr, 0.90).toFixed(4),
    p95: +_pct(arr, 0.95).toFixed(4),
    p99: +_pct(arr, 0.99).toFixed(4),
    min: +arr[0].toFixed(4),
    max: +arr[arr.length - 1].toFixed(4),
  };
}
```

- [ ] **Step 4: Add `groupAndAggregate()` helper**

```js
function groupAndAggregate(reps, keyFn, extraFn) {
  const groups = new Map();
  for (const r of reps) {
    const k = keyFn(r);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  }
  const out = [];
  for (const [k, g] of groups) {
    if (g.length < 3) continue;
    const up = g.map(r => r.excursion_up_pct).filter(v => v != null).sort((a, b) => a - b);
    const dn = g.map(r => r.excursion_down_pct).filter(v => v != null).sort((a, b) => a - b);
    const row = {
      n: g.length,
      up_mean: up.length ? +(up.reduce((a, b) => a + b, 0) / up.length).toFixed(4) : null,
      up_med: +(_pct(up, 0.50) ?? 0).toFixed(4),
      up_p25: +(_pct(up, 0.25) ?? 0).toFixed(4),
      up_p50: +(_pct(up, 0.50) ?? 0).toFixed(4),
      up_p75: +(_pct(up, 0.75) ?? 0).toFixed(4),
      up_p90: +(_pct(up, 0.90) ?? 0).toFixed(4),
      up_p95: +(_pct(up, 0.95) ?? 0).toFixed(4),
      up_p99: +(_pct(up, 0.99) ?? 0).toFixed(4),
      down_mean: dn.length ? +(dn.reduce((a, b) => a + b, 0) / dn.length).toFixed(4) : null,
      down_med: +(_pct(dn, 0.50) ?? 0).toFixed(4),
      down_p25: +(_pct(dn, 0.25) ?? 0).toFixed(4),
      down_p50: +(_pct(dn, 0.50) ?? 0).toFixed(4),
      down_p75: +(_pct(dn, 0.75) ?? 0).toFixed(4),
      down_p90: +(_pct(dn, 0.90) ?? 0).toFixed(4),
      down_p95: +(_pct(dn, 0.90) ?? 0).toFixed(4),
      down_p99: +(_pct(dn, 0.99) ?? 0).toFixed(4),
    };
    if (extraFn) Object.assign(row, extraFn(k, g));
    out.push(row);
  }
  return out;
}
```

- [ ] **Step 5: Add `computeDistributions()`**

```js
function computeDistributions(reps) {
  const up = reps.map(r => r.excursion_up_pct).filter(v => v != null);
  const dn = reps.map(r => r.excursion_down_pct).filter(v => v != null);
  return {
    up: buildDist(up),
    down: buildDist(dn),
    by_hour: groupAndAggregate(reps, r => r.hr, (k) => ({ hr: k, hr_label: `${String(k).padStart(2, '0')}:00` })).sort((a, b) => a.hr - b.hr),
    by_dow: groupAndAggregate(reps, r => r.dow, (k) => ({ dow: k, dow_name: ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][k] || '?' })).sort((a, b) => a.dow - b.dow),
    by_session: groupAndAggregate(reps, r => r.session, (k) => ({ session: k })),
    by_year: groupAndAggregate(reps, r => r.yr, (k) => ({ yr: k })).sort((a, b) => a.yr - b.yr),
  };
}
```

- [ ] **Step 6: Reload the dashboard and verify no errors**

```bash
cd "/Users/abhi/Downloads/Statistic.ally" && python3 -m http.server 8001 &
```

Open dashboard. Open browser console. Run:

```js
const reps = _current?.recent_reps || [];
const dist = computeDistributions(reps);
console.log('up P99:', dist.up.p99, 'vs json:', _current.up_dist.p99);
console.log('by_hour rows:', dist.by_hour.length);
```

Expected: `up P99` matches JSON value ±0.001 (floor-indexed percentile may differ slightly from pandas interpolation — that's acceptable for a dashboard). `by_hour rows` roughly matches the existing `_current.by_hour.length`.

Kill server: `kill %1 2>/dev/null`.

- [ ] **Step 7: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_dashboard_fixed_constant.html"
git commit -m "feat(fixed-constant-dash): add filter primitives and computeDistributions"
```

---

## Task 11: `classifyRegimes()` and load-time wiring

**Files:**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html`

- [ ] **Step 1: Add `classifyRegimes()` function**

Add below `computeDistributions`:

```js
function classifyRegimes(reps) {
  const WINDOW_DAYS = 70;
  const msPerDay = 86400000;
  // Assumes reps sorted ascending by date; if not, sort a copy first.
  const sorted = [...reps].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  for (let i = 0; i < sorted.length; i++) {
    const r = sorted[i];
    if (r.block_range_pts == null) { r._regime = 'unknown'; continue; }
    const rDate = new Date((r.date || '').slice(0, 10)).getTime();
    if (isNaN(rDate)) { r._regime = 'unknown'; continue; }
    const cutoff = rDate - WINDOW_DAYS * msPerDay;
    const window = [];
    for (let j = i - 1; j >= 0; j--) {
      const pDate = new Date((sorted[j].date || '').slice(0, 10)).getTime();
      if (isNaN(pDate) || pDate < cutoff) break;
      if (sorted[j].block_range_pts != null) window.push(sorted[j].block_range_pts);
    }
    if (window.length < 30) { r._regime = 'unknown'; continue; }
    window.sort((a, b) => a - b);
    const p33 = window[Math.floor(window.length * 0.333)];
    const p67 = window[Math.floor(window.length * 0.667)];
    if      (r.block_range_pts >= p67) r._regime = 'expanding';
    else if (r.block_range_pts <= p33) r._regime = 'contracting';
    else                                r._regime = 'neutral';
  }
}
```

- [ ] **Step 2: Wire `classifyRegimes` into JSON load path**

Locate where the JSON is loaded and `_current` (or equivalent) is set — typically inside the `fetch(...).then(...)` or `loadData()` function. Find the point just after the data is assigned.

Add immediately after the data assignment:

```js
// Classify regimes once per model at load time
for (const mk of Object.keys(data)) {
  const model = data[mk];
  if (model && model.recent_reps) {
    classifyRegimes(model.recent_reps);
  }
}
```

If the dashboard has a `switchModel(mk)` function that assigns `_current = data[mk]`, ensure `classifyRegimes` has already run on load before the first switch.

- [ ] **Step 3: Reload the dashboard and spot-check regime labels in console**

```bash
cd "/Users/abhi/Downloads/Statistic.ally" && python3 -m http.server 8001 &
```

Open dashboard. Console:

```js
const reps = _current?.recent_reps || [];
const counts = {};
for (const r of reps) counts[r._regime || 'undefined'] = (counts[r._regime || 'undefined'] || 0) + 1;
console.log('regime counts:', counts);
```

Expected:
- `expanding`, `neutral`, `contracting`, `unknown` keys present
- Roughly equal counts for expanding / neutral / contracting (within 10% of 1/3 of classified total)
- `unknown` count ≈ 70 days worth of reps (e.g. for 1H_5M with ~25 reps/day, ~1750 unknown reps)

Kill server: `kill %1 2>/dev/null`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_dashboard_fixed_constant.html"
git commit -m "feat(fixed-constant-dash): add classifyRegimes with 70d trailing tercile"
```

---

## Task 12: Thread filter through `render()` — audit all reads of pre-computed aggregates

**Files:**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html`

- [ ] **Step 1: Identify all reads of `D.up_dist`, `D.down_dist`, `D.by_hour`, `D.by_dow`, `D.by_session`, `D.by_year`**

```bash
cd "/Users/abhi/Downloads/Statistic.ally" && grep -n "up_dist\|down_dist\|\.by_hour\|\.by_dow\|\.by_session\|\.by_year\|recent_reps" "Fractal Sweep/model_dashboard_fixed_constant.html"
```

Write down every line number. Each is a site that needs to be threaded through the filter.

- [ ] **Step 2: Add `_filtered` global and `applyFilter()` orchestrator**

Near the existing globals, add:

```js
// Current filtered view — recomputed on every filter change
let _filtered = null;  // { reps: [...], dist: {...} }

function applyFilter() {
  if (!_current || !_current.recent_reps) return;
  const reps = filterReps(_current.recent_reps);
  if (reps.length < 30) {
    const bar = document.getElementById('filter-status');
    if (bar) bar.textContent = `Sample too small: ${reps.length} reps (need ≥30)`;
    return;  // keep prior render
  }
  const dist = computeDistributions(reps);
  _filtered = { reps, dist };
  const bar = document.getElementById('filter-status');
  if (bar) bar.textContent = `${reps.length.toLocaleString()} reps in view`;
  render();
}
```

- [ ] **Step 3: Modify `render()` to pull from `_filtered` when available**

Locate the existing `render()` function. At the top of the function, immediately after the early-return guard for missing `_current`, add:

```js
function render() {
  if (!_current) return;
  // Use filtered view if available, else fall back to original JSON aggregates
  const reps = _filtered ? _filtered.reps : (_current.recent_reps || []);
  const dist = _filtered ? _filtered.dist : null;
  const D = _filtered ? {
    ..._current,
    recent_reps: reps,
    up_dist: dist.up,
    down_dist: dist.down,
    by_hour: dist.by_hour,
    by_dow: dist.by_dow,
    by_session: dist.by_session,
    by_year: dist.by_year,
  } : _current;

  // ... rest of existing render() body — change all references from _current to D
```

Then: inside the existing `render()` body, replace every reference to `_current.up_dist` / `_current.down_dist` / `_current.by_*` / `_current.recent_reps` with `D.up_dist` / `D.by_*` / `D.recent_reps`. Do the same for any helper function that `render()` calls which currently takes `_current` as argument — either pass `D` instead, or have the helper read from the local `D`.

- [ ] **Step 4: Wire up the filter controls**

Near the bottom of the script (before the existing `render()` call on DOMContentLoaded or wherever init happens), add:

```js
function _initFilterControls() {
  const startEl = document.getElementById('filter-start');
  const endEl = document.getElementById('filter-end');
  const applyBtn = document.getElementById('filter-apply');
  const resetBtn = document.getElementById('filter-reset');
  const rollingSel = document.getElementById('rolling-window');

  applyBtn.addEventListener('click', () => {
    _filterStart = startEl.value || null;
    _filterEnd = endEl.value || null;
    applyFilter();
  });

  resetBtn.addEventListener('click', () => {
    _filterStart = null;
    _filterEnd = null;
    _filterRegime = 'all';
    startEl.value = '';
    endEl.value = '';
    document.querySelectorAll('.regime-pill').forEach(b => {
      b.classList.toggle('active', b.dataset.regime === 'all');
      b.style.background = b.dataset.regime === 'all' ? 'var(--purple)' : 'var(--bg-raised)';
      b.style.color = b.dataset.regime === 'all' ? '#fff' : 'var(--text-primary)';
    });
    _filtered = null;
    const bar = document.getElementById('filter-status');
    if (bar) bar.textContent = '';
    render();
  });

  document.querySelectorAll('.regime-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      _filterRegime = btn.dataset.regime;
      document.querySelectorAll('.regime-pill').forEach(b => {
        const active = b.dataset.regime === _filterRegime;
        b.classList.toggle('active', active);
        b.style.background = active ? 'var(--purple)' : 'var(--bg-raised)';
        b.style.color = active ? '#fff' : 'var(--text-primary)';
      });
      applyFilter();
    });
  });

  rollingSel.addEventListener('change', () => {
    _rollingWindowDays = parseInt(rollingSel.value, 10);
    render();  // Only Panel 1 (Validation tab) uses this, render() will pick it up
  });
}

// Call from existing init
_initFilterControls();
```

Add the `_initFilterControls()` call wherever the dashboard's existing init runs (typically after `loadData()` completes, or at the bottom of the script).

- [ ] **Step 5: Reload the dashboard and manually verify Layer C steps 1-2**

```bash
cd "/Users/abhi/Downloads/Statistic.ally" && python3 -m http.server 8001 &
```

Open dashboard. Verify:

1. **No filter applied**: Hero tiles and percentile tables match pre-Commit-2 values. No regressions.
2. **Set From = 2023-01-01, To = 2023-12-31, click Apply**: Hero tiles update. `by_hour` / `by_dow` tables update. Reps tab shows only 2023 reps. Filter status bar shows rep count.
3. **Click Reset**: Everything reverts to full-sample view.
4. **Click "Expanding" regime pill with full-sample filter**: Rep count drops to roughly 1/3 of total. Hero tiles shift (MAE99 should be larger in expanding regime).
5. **Click "All"**: Rep count returns to full.

Also check: no console errors throughout.

Kill server: `kill %1 2>/dev/null`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_dashboard_fixed_constant.html"
git commit -m "feat(fixed-constant-dash): thread IS/OOS filter through render pipeline"
```

---

# COMMIT 3 — VALIDATION TAB

## Task 13: Add Validation tab button and empty container with back-compat guards

**Files:**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html`

- [ ] **Step 1: Add the tab button**

Locate the `.page-nav` block (around line 225):

```html
<div class="page-nav">
  <button class="page-tab active" onclick="switchPageTab('overview')">Overview</button>
  <button class="page-tab" onclick="switchPageTab('reps')">Reps</button>
</div>
```

Insert the Validation tab between Overview and Reps:

```html
<div class="page-nav">
  <button class="page-tab active" onclick="switchPageTab('overview')">Overview</button>
  <button class="page-tab" onclick="switchPageTab('validation')">Validation</button>
  <button class="page-tab" onclick="switchPageTab('reps')">Reps</button>
</div>
```

- [ ] **Step 2: Add the Validation tab container**

Find where the existing `overview` and `reps` panel containers are (search for `switchPageTab` or `page-tab`). Add a sibling container for the validation tab:

```html
<div id="page-validation" class="page-content" style="display:none">
  <div class="panel">
    <div class="ph-title">Rolling Live Parameters</div>
    <div id="validation-panel-1" style="padding:16px"></div>
  </div>
  <div class="panel">
    <div class="ph-title">Variance Across Lookbacks</div>
    <div id="validation-panel-2" style="padding:16px"></div>
  </div>
  <div class="panel">
    <div class="ph-title">Fade Engine</div>
    <div id="validation-panel-3" style="padding:16px"></div>
  </div>
  <div class="panel">
    <div class="ph-title">Regime Cheat Sheet</div>
    <div id="validation-panel-4" style="padding:16px"></div>
  </div>
</div>
```

Match the exact class names (`panel`, `ph-title`) to the existing overview tab's panels — if they're different, use whatever the overview tab uses.

- [ ] **Step 3: Update `switchPageTab` to handle the new tab**

Find `switchPageTab` (or whatever function handles page-tab switching). Extend it:

```js
function switchPageTab(tab) {
  document.querySelectorAll('.page-tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.page-content').forEach(el => el.style.display = 'none');
  document.querySelector(`[onclick="switchPageTab('${tab}')"]`).classList.add('active');
  const target = document.getElementById(`page-${tab}`);
  if (target) target.style.display = '';
  if (tab === 'validation') renderValidationTab();
}
```

- [ ] **Step 4: Add `renderValidationTab` stub with back-compat guards**

Add a new function:

```js
function renderValidationTab() {
  if (!_current) return;
  const reps = _filtered ? _filtered.reps : (_current.recent_reps || []);
  const dist = _filtered ? _filtered.dist : computeDistributions(reps);

  renderRollingCard(reps, dist);
  renderVarianceChart(reps);
  renderFadeView(reps, _current.fade_summary);
  renderRegimeCheatsheet(reps);
}

// Stubs — filled in by later tasks
function renderRollingCard(reps, dist) {
  document.getElementById('validation-panel-1').innerHTML =
    '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim)">Panel 1 placeholder</div>';
}
function renderVarianceChart(reps) {
  document.getElementById('validation-panel-2').innerHTML =
    '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim)">Panel 2 placeholder</div>';
}
function renderFadeView(reps, fadeSummary) {
  const el = document.getElementById('validation-panel-3');
  if (!fadeSummary) {
    el.innerHTML = '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim);padding:24px;text-align:center">Run <code>python3 model_stats_fixed_constant.py</code> to compute fade data, then reload.</div>';
    return;
  }
  el.innerHTML = '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim)">Panel 3 placeholder (fade_summary present)</div>';
}
function renderRegimeCheatsheet(reps) {
  const classified = reps.filter(r => r._regime && r._regime !== 'unknown');
  if (classified.length === 0) {
    document.getElementById('validation-panel-4').innerHTML =
      '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim);padding:24px;text-align:center">No regime-classified reps. Engine may need <code>block_range_pts</code> — run <code>python3 model_stats_fixed_constant.py</code> and reload.</div>';
    return;
  }
  document.getElementById('validation-panel-4').innerHTML =
    '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim)">Panel 4 placeholder</div>';
}
```

- [ ] **Step 5: Reload and verify tab switching**

Start server, open dashboard. Click Validation tab. Verify:
- Tab switches
- Four panels visible with placeholder text or stubs
- No console errors
- Clicking Overview returns to the overview content
- Clicking Reps returns to the reps table

- [ ] **Step 6: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_dashboard_fixed_constant.html"
git commit -m "feat(fixed-constant-dash): add Validation tab scaffolding with back-compat guards"
```

---

## Task 14: Panel 4 — Regime cheat sheet (simplest panel first)

**Files:**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html`

- [ ] **Step 1: Replace the Panel 4 stub with the real implementation**

Replace `renderRegimeCheatsheet` with:

```js
function renderRegimeCheatsheet(reps) {
  const classified = reps.filter(r => r._regime && r._regime !== 'unknown');
  const el = document.getElementById('validation-panel-4');
  if (classified.length === 0) {
    el.innerHTML = '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim);padding:24px;text-align:center">No regime-classified reps in current view.</div>';
    return;
  }

  const buckets = ['expanding', 'neutral', 'contracting'];
  const cols = buckets.map(b => {
    const rs = classified.filter(r => r._regime === b);
    if (rs.length < 30) {
      return { regime: b, n: rs.length, insufficient: true };
    }
    const up = rs.map(r => r.excursion_up_pct);
    const dn = rs.map(r => r.excursion_down_pct);
    const dUp = buildDist(up);
    const dDn = buildDist(dn);
    return {
      regime: b,
      n: rs.length,
      mae99_up: dUp.p99,
      mae99_dn: dDn.p99,
      p50_up: dUp.p50,
      p50_dn: dDn.p50,
      ratio: dUp.p99 ? (dUp.p50 / dUp.p99).toFixed(3) : '—',
    };
  });

  const unknownCount = reps.filter(r => r._regime === 'unknown').length;
  const labels = { expanding: 'EXPANDING', neutral: 'NEUTRAL', contracting: 'CONTRACTING' };
  const subs = { expanding: 'top tercile block range', neutral: 'mid tercile block range', contracting: 'bottom tercile block range' };

  const colHtml = cols.map(c => {
    const highlight = (_filterRegime === c.regime) ? 'border:2px solid var(--purple)' : 'border:1px solid var(--border)';
    if (c.insufficient) {
      return `
        <div style="flex:1;padding:16px;${highlight};border-radius:8px;background:var(--bg-raised)">
          <div style="font-family:var(--font-display);font-size:13px;color:var(--text-primary);font-weight:700">${labels[c.regime]}</div>
          <div style="font-family:var(--font-data);font-size:10px;color:var(--text-dim);margin-bottom:12px">${subs[c.regime]}</div>
          <div style="font-family:var(--font-data);font-size:11px;color:var(--text-dim)">n = ${c.n} (< 30, insufficient)</div>
        </div>`;
    }
    return `
      <div style="flex:1;padding:16px;${highlight};border-radius:8px;background:var(--bg-raised)">
        <div style="font-family:var(--font-display);font-size:13px;color:var(--text-primary);font-weight:700">${labels[c.regime]}</div>
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-dim);margin-bottom:12px">${subs[c.regime]}</div>
        <table style="width:100%;font-family:var(--font-data);font-size:11px;border-collapse:collapse">
          <tr><td style="color:var(--text-dim);padding:2px 0">n</td><td style="text-align:right;color:var(--text-primary)">${c.n.toLocaleString()}</td></tr>
          <tr><td style="color:var(--text-dim);padding:2px 0">MAE99 up</td><td style="text-align:right;color:var(--text-primary)">${c.mae99_up}%</td></tr>
          <tr><td style="color:var(--text-dim);padding:2px 0">MAE99 dn</td><td style="text-align:right;color:var(--text-primary)">${c.mae99_dn}%</td></tr>
          <tr><td style="color:var(--text-dim);padding:2px 0">MFE50 up</td><td style="text-align:right;color:var(--text-primary)">${c.p50_up}%</td></tr>
          <tr><td style="color:var(--text-dim);padding:2px 0">MFE50 dn</td><td style="text-align:right;color:var(--text-primary)">${c.p50_dn}%</td></tr>
          <tr><td style="color:var(--text-dim);padding:2px 0;border-top:1px solid var(--border)">Ratio</td><td style="text-align:right;color:var(--text-primary);border-top:1px solid var(--border);font-weight:700">${c.ratio}</td></tr>
        </table>
      </div>`;
  }).join('');

  el.innerHTML = `
    <div style="display:flex;gap:12px">${colHtml}</div>
    <div style="margin-top:12px;font-family:var(--font-data);font-size:10px;color:var(--text-dim)">
      Classified: ${classified.length.toLocaleString()} reps · Unknown (first 70d + early samples): ${unknownCount.toLocaleString()} reps
    </div>
  `;
}
```

- [ ] **Step 2: Reload and verify Panel 4**

Start server, open dashboard, click Validation. Verify:
- Three columns render with regime labels
- Each shows n, MAE99 up/dn, MFE50 up/dn, Ratio
- Expanding's MAE99 should be larger than Contracting's
- Set regime pill to Expanding → Expanding column gets purple border highlight
- Set filter to 2023 → column numbers change, reflecting 2023 subset

Kill server.

- [ ] **Step 3: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_dashboard_fixed_constant.html"
git commit -m "feat(fixed-constant-dash): implement Panel 4 regime cheat sheet"
```

---

## Task 15: Panel 1 — Rolling live parameters card + window dropdown wiring

**Files:**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html`

- [ ] **Step 1: Implement `renderRollingCard`**

Replace the stub with:

```js
function renderRollingCard(reps, dist) {
  const el = document.getElementById('validation-panel-1');
  if (reps.length === 0) {
    el.innerHTML = '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim)">No reps in view.</div>';
    return;
  }

  // Rolling window anchored to most recent rep in filtered set
  const sorted = [...reps].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  const latestDate = new Date((sorted[sorted.length - 1].date || '').slice(0, 10)).getTime();
  const msPerDay = 86400000;
  const cutoff = latestDate - _rollingWindowDays * msPerDay;

  const window = sorted.filter(r => {
    const d = new Date((r.date || '').slice(0, 10)).getTime();
    return !isNaN(d) && d >= cutoff;
  });

  if (window.length < 30) {
    el.innerHTML = `<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim);padding:24px;text-align:center">Rolling window too short: ${window.length} reps in last ${_rollingWindowDays}d (need ≥30)</div>`;
    return;
  }

  const upDist = buildDist(window.map(r => r.excursion_up_pct));
  const dnDist = buildDist(window.map(r => r.excursion_down_pct));
  const ratioUp = upDist.p99 ? (upDist.p50 / upDist.p99).toFixed(3) : '—';
  const ratioDn = dnDist.p99 ? (dnDist.p50 / dnDist.p99).toFixed(3) : '—';

  // Threshold drift: compare to engine's full-sample MAE99
  const engUp = _current.fade_summary?.mae99_up_pct;
  const engDn = _current.fade_summary?.mae99_down_pct;
  let driftLine = '';
  if (engUp != null && engDn != null && upDist.p99 && dnDist.p99) {
    const dUp = ((upDist.p99 - engUp) / engUp * 100).toFixed(0);
    const dDn = ((dnDist.p99 - engDn) / engDn * 100).toFixed(0);
    driftLine = `
      <div style="margin-top:12px;padding:10px;background:var(--bg);border-radius:6px;font-family:var(--font-data);font-size:11px;color:var(--text-dim);line-height:1.6">
        Engine MAE99 (full sample): up ${engUp}%, dn ${engDn}%<br>
        Rolling ${_rollingWindowDays}d (current): up ${upDist.p99}%, dn ${dnDist.p99}%<br>
        Drift: ${dUp >= 0 ? '+' : ''}${dUp}% up, ${dDn >= 0 ? '+' : ''}${dDn}% dn
      </div>`;
  }

  el.innerHTML = `
    <div style="display:flex;gap:12px">
      <div style="flex:1;padding:16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-raised)">
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-dim);letter-spacing:.1em;text-transform:uppercase">UP SIDE (rolling ${_rollingWindowDays}d)</div>
        <table style="width:100%;font-family:var(--font-data);font-size:11px;margin-top:8px;border-collapse:collapse">
          <tr><td style="color:var(--text-dim);padding:3px 0">MAE99</td><td style="text-align:right;color:var(--text-primary);font-weight:700">${upDist.p99}%</td></tr>
          <tr><td style="color:var(--text-dim);padding:3px 0">P90</td><td style="text-align:right;color:var(--text-primary)">${upDist.p90}%</td></tr>
          <tr><td style="color:var(--text-dim);padding:3px 0">P50</td><td style="text-align:right;color:var(--text-primary)">${upDist.p50}%</td></tr>
        </table>
      </div>
      <div style="flex:1;padding:16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-raised)">
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-dim);letter-spacing:.1em;text-transform:uppercase">DOWN SIDE (rolling ${_rollingWindowDays}d)</div>
        <table style="width:100%;font-family:var(--font-data);font-size:11px;margin-top:8px;border-collapse:collapse">
          <tr><td style="color:var(--text-dim);padding:3px 0">MAE99</td><td style="text-align:right;color:var(--text-primary);font-weight:700">${dnDist.p99}%</td></tr>
          <tr><td style="color:var(--text-dim);padding:3px 0">P90</td><td style="text-align:right;color:var(--text-primary)">${dnDist.p90}%</td></tr>
          <tr><td style="color:var(--text-dim);padding:3px 0">P50</td><td style="text-align:right;color:var(--text-primary)">${dnDist.p50}%</td></tr>
        </table>
      </div>
      <div style="flex:1;padding:16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-raised)">
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-dim);letter-spacing:.1em;text-transform:uppercase">MFE/MAE Ratio</div>
        <table style="width:100%;font-family:var(--font-data);font-size:11px;margin-top:8px;border-collapse:collapse">
          <tr><td style="color:var(--text-dim);padding:3px 0">Up: P50/MAE99</td><td style="text-align:right;color:var(--text-primary);font-weight:700">${ratioUp}</td></tr>
          <tr><td style="color:var(--text-dim);padding:3px 0">Dn: P50/MAE99</td><td style="text-align:right;color:var(--text-primary);font-weight:700">${ratioDn}</td></tr>
        </table>
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-dim);margin-top:8px">n = ${window.length.toLocaleString()} reps</div>
      </div>
    </div>
    ${driftLine}
  `;
}
```

- [ ] **Step 2: Ensure `renderValidationTab` is called when rolling window dropdown changes**

Verify that the `rollingSel.addEventListener('change', ...)` added in Task 12 Step 4 calls `render()`, and that `render()` in turn calls `renderValidationTab()` if the active tab is Validation.

If `render()` does not call `renderValidationTab()` automatically, update it:

```js
// Inside existing render() body, after all other render calls:
if (document.getElementById('page-validation')?.style.display !== 'none') {
  renderValidationTab();
}
```

- [ ] **Step 3: Reload and verify Panel 1**

Start server, open dashboard, click Validation. Verify:
- Three columns render with MAE99 / P90 / P50 values
- Drift callout shows "Engine vs Rolling" comparison
- Change rolling dropdown 70d → 30d → numbers update, "(rolling 30d)" label updates
- Set IS/OOS filter to 2023 → rolling window now anchored to last date in 2023
- Set filter back to full → rolling anchored to most recent rep overall

Kill server.

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_dashboard_fixed_constant.html"
git commit -m "feat(fixed-constant-dash): implement Panel 1 rolling live parameters card"
```

---

## Task 16: Panel 2 — Variance chart across five lookbacks

**Files:**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html`

- [ ] **Step 1: Implement `renderVarianceChart`**

Replace the stub with:

```js
function renderVarianceChart(reps) {
  const el = document.getElementById('validation-panel-2');
  if (reps.length < 30) {
    el.innerHTML = '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim);padding:24px;text-align:center">Not enough reps for variance analysis.</div>';
    return;
  }

  // Anchor end date to most recent rep in filtered set
  const sorted = [...reps].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  const latestDate = new Date((sorted[sorted.length - 1].date || '').slice(0, 10)).getTime();
  const msPerDay = 86400000;

  const windows = [
    { label: '30d',  days: 30 },
    { label: '70d',  days: 70 },
    { label: '180d', days: 180 },
    { label: '365d', days: 365 },
    { label: 'full', days: null },
  ];

  const rows = windows.map(w => {
    const subset = w.days == null
      ? sorted
      : sorted.filter(r => {
          const d = new Date((r.date || '').slice(0, 10)).getTime();
          return !isNaN(d) && d >= latestDate - w.days * msPerDay;
        });
    if (subset.length < 30) return { label: w.label, n: subset.length, insufficient: true };
    const up = buildDist(subset.map(r => r.excursion_up_pct));
    const ratio = up.p99 ? up.p50 / up.p99 : 0;
    return {
      label: w.label,
      n: subset.length,
      mae99: up.p99,
      p50: up.p50,
      ratio: +ratio.toFixed(4),
    };
  });

  // Scale for bars: max MAE99 across all rows sets 100% width
  const maxMae = Math.max(...rows.filter(r => !r.insufficient).map(r => r.mae99), 0.001);
  const maxP50 = Math.max(...rows.filter(r => !r.insufficient).map(r => r.p50), 0.001);
  const maxRatio = Math.max(...rows.filter(r => !r.insufficient).map(r => r.ratio), 0.001);

  const barRow = (row) => {
    if (row.insufficient) {
      return `<tr><td style="color:var(--text-dim);font-family:var(--font-data);font-size:11px;padding:4px 8px">${row.label}</td><td colspan="3" style="color:var(--text-dim);font-family:var(--font-data);font-size:10px;padding:4px 8px">n=${row.n} (insufficient)</td></tr>`;
    }
    const bar = (val, max, color) => {
      const pct = Math.min(100, (val / max) * 100);
      return `<div style="display:flex;align-items:center;gap:8px"><div style="height:8px;width:${pct}%;min-width:2px;background:${color};border-radius:2px"></div><span style="font-family:var(--font-data);font-size:10px;color:var(--text-primary)">${val.toFixed(4)}</span></div>`;
    };
    return `
      <tr>
        <td style="color:var(--text-primary);font-family:var(--font-data);font-size:11px;padding:6px 8px;font-weight:700">${row.label}</td>
        <td style="padding:6px 8px;min-width:180px">${bar(row.mae99, maxMae, '#ff6b6b')}</td>
        <td style="padding:6px 8px;min-width:180px">${bar(row.p50, maxP50, '#51cf66')}</td>
        <td style="padding:6px 8px;min-width:180px">${bar(row.ratio, maxRatio, '#a855f7')}</td>
        <td style="color:var(--text-dim);font-family:var(--font-data);font-size:10px;padding:6px 8px">n=${row.n.toLocaleString()}</td>
      </tr>`;
  };

  // Compute variance (std) across the five rows for each metric
  const valid = rows.filter(r => !r.insufficient);
  const std = (arr) => {
    if (arr.length < 2) return 0;
    const m = arr.reduce((a, b) => a + b, 0) / arr.length;
    return Math.sqrt(arr.map(v => (v - m) ** 2).reduce((a, b) => a + b, 0) / arr.length);
  };
  const varMae = std(valid.map(r => r.mae99)).toFixed(4);
  const varP50 = std(valid.map(r => r.p50)).toFixed(4);
  const varRatio = std(valid.map(r => r.ratio)).toFixed(4);

  el.innerHTML = `
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr>
          <th style="text-align:left;color:var(--text-dim);font-family:var(--font-data);font-size:10px;padding:4px 8px;font-weight:400;text-transform:uppercase;letter-spacing:.1em">Window</th>
          <th style="text-align:left;color:#ff6b6b;font-family:var(--font-data);font-size:10px;padding:4px 8px;font-weight:400;text-transform:uppercase;letter-spacing:.1em">MAE99 up</th>
          <th style="text-align:left;color:#51cf66;font-family:var(--font-data);font-size:10px;padding:4px 8px;font-weight:400;text-transform:uppercase;letter-spacing:.1em">P50 up</th>
          <th style="text-align:left;color:#a855f7;font-family:var(--font-data);font-size:10px;padding:4px 8px;font-weight:400;text-transform:uppercase;letter-spacing:.1em">P50/MAE99</th>
          <th style="text-align:left;color:var(--text-dim);font-family:var(--font-data);font-size:10px;padding:4px 8px;font-weight:400"></th>
        </tr>
      </thead>
      <tbody>${rows.map(barRow).join('')}</tbody>
    </table>
    <div style="margin-top:12px;padding:10px;background:var(--bg);border-radius:6px;font-family:var(--font-data);font-size:11px;color:var(--text-dim);line-height:1.8">
      σ(MAE99 up across windows)   = <span style="color:var(--text-primary)">${varMae}</span><br>
      σ(P50 up across windows)     = <span style="color:var(--text-primary)">${varP50}</span><br>
      σ(P50/MAE99 across windows)  = <span style="color:var(--text-primary)">${varRatio}</span>
    </div>
  `;
}
```

- [ ] **Step 2: Reload and verify Panel 2**

Start server, open dashboard, click Validation. Verify:
- Five rows render (30d, 70d, 180d, 365d, full)
- Three bars per row with values
- Variance stats below the chart
- Earlier windows (30d, 70d) may show "insufficient" if filter is set narrow
- Set filter to 2023 → chart re-renders with 2023-anchored windows

Kill server.

- [ ] **Step 3: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_dashboard_fixed_constant.html"
git commit -m "feat(fixed-constant-dash): implement Panel 2 variance chart"
```

---

## Task 17: Panel 3 — Fade engine view (tiles + histogram + drift callout)

**Files:**
- Modify: `Fractal Sweep/model_dashboard_fixed_constant.html`

- [ ] **Step 1: Implement `renderFadeView` in full**

Replace the stub with:

```js
function renderFadeView(reps, fadeSummary) {
  const el = document.getElementById('validation-panel-3');
  if (!fadeSummary) {
    el.innerHTML = '<div style="font-family:var(--font-data);font-size:12px;color:var(--text-dim);padding:24px;text-align:center">Run <code>python3 model_stats_fixed_constant.py</code> to compute fade data, then reload.</div>';
    return;
  }

  // Recompute filtered fade rates from per-rep fields
  const triggered = reps.filter(r => r.fade_triggered === true);
  const nTotal = reps.length;
  const nTriggered = triggered.length;
  const triggerRate = nTotal ? (nTriggered / nTotal) : 0;

  const anchorRate = nTriggered ? triggered.filter(r => r.fade_reached_anchor).length / nTriggered : 0;
  const mfe50Rate  = nTriggered ? triggered.filter(r => r.fade_reached_mfe50_opp).length / nTriggered : 0;
  const mae99Rate  = nTriggered ? triggered.filter(r => r.fade_reached_mae99_opp).length / nTriggered : 0;

  // Tiles
  const tile = (label, value, sub, color) => `
    <div style="flex:1;padding:16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-raised);text-align:center">
      <div style="font-family:var(--font-data);font-size:10px;color:var(--text-dim);letter-spacing:.1em;text-transform:uppercase">${label}</div>
      <div style="font-family:var(--font-display);font-size:28px;color:${color};margin-top:6px;font-weight:700">${value}</div>
      <div style="font-family:var(--font-data);font-size:10px;color:var(--text-dim);margin-top:4px">${sub}</div>
    </div>`;

  const tilesHtml = `
    <div style="display:flex;gap:12px;margin-bottom:16px">
      ${tile('Trigger rate',   (triggerRate * 100).toFixed(2) + '%', 'of ' + nTotal.toLocaleString() + ' blocks', '#a855f7')}
      ${tile('Reached anchor', (anchorRate * 100).toFixed(0) + '%',  'of ' + nTriggered + ' triggered',            '#51cf66')}
      ${tile('Reached MFE50',  (mfe50Rate * 100).toFixed(0) + '%',   'of ' + nTriggered + ' triggered',            '#4dabf7')}
      ${tile('Reached MAE99',  (mae99Rate * 100).toFixed(0) + '%',   'of ' + nTriggered + ' triggered',            '#ff6b6b')}
    </div>`;

  // Histogram of fade_mfe_opp_pct over triggered reps
  const opp = triggered.map(r => r.fade_mfe_opp_pct).filter(v => v != null).sort((a, b) => a - b);
  let histHtml = '<div style="font-family:var(--font-data);font-size:11px;color:var(--text-dim);padding:12px">No triggered reps in current filter.</div>';
  if (opp.length >= 5) {
    const minV = opp[0];
    const maxV = opp[opp.length - 1];
    const nBuckets = 20;
    const bucketSize = (maxV - minV) / nBuckets || 1;
    const counts = new Array(nBuckets).fill(0);
    for (const v of opp) {
      const idx = Math.min(nBuckets - 1, Math.floor((v - minV) / bucketSize));
      counts[idx]++;
    }
    const maxCount = Math.max(...counts, 1);
    const bars = counts.map((c, i) => {
      const h = (c / maxCount) * 80;
      const x0 = minV + i * bucketSize;
      return `<div title="${x0.toFixed(3)}% - ${(x0 + bucketSize).toFixed(3)}%: n=${c}" style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;min-width:4px">
        <div style="width:90%;height:${h}px;background:#a855f7;border-radius:2px 2px 0 0"></div>
      </div>`;
    }).join('');
    histHtml = `
      <div style="font-family:var(--font-data);font-size:10px;color:var(--text-dim);margin-bottom:6px">fade_mfe_opp_pct distribution (${opp.length} triggered reps)</div>
      <div style="display:flex;align-items:flex-end;height:90px;gap:1px;background:var(--bg);padding:4px;border-radius:4px">${bars}</div>
      <div style="display:flex;justify-content:space-between;font-family:var(--font-data);font-size:9px;color:var(--text-dim);margin-top:4px">
        <span>${minV.toFixed(3)}%</span><span>${maxV.toFixed(3)}%</span>
      </div>
    `;
  }

  // Threshold drift callout (recompute rolling from current filter)
  const sorted = [...reps].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  let driftHtml = '';
  if (sorted.length >= 30) {
    const msPerDay = 86400000;
    const latestDate = new Date((sorted[sorted.length - 1].date || '').slice(0, 10)).getTime();
    const cutoff = latestDate - _rollingWindowDays * msPerDay;
    const window = sorted.filter(r => {
      const d = new Date((r.date || '').slice(0, 10)).getTime();
      return !isNaN(d) && d >= cutoff;
    });
    if (window.length >= 30) {
      const rollUp = buildDist(window.map(r => r.excursion_up_pct));
      const rollDn = buildDist(window.map(r => r.excursion_down_pct));
      const engUp = fadeSummary.mae99_up_pct;
      const engDn = fadeSummary.mae99_down_pct;
      const dUp = ((rollUp.p99 - engUp) / engUp * 100).toFixed(0);
      const dDn = ((rollDn.p99 - engDn) / engDn * 100).toFixed(0);
      driftHtml = `
        <div style="margin-top:16px;padding:12px;background:var(--bg);border-left:3px solid #ffd43b;border-radius:4px;font-family:var(--font-data);font-size:11px;color:var(--text-dim);line-height:1.7">
          <div style="color:#ffd43b;font-weight:700;margin-bottom:4px">THRESHOLD DRIFT</div>
          Engine trigger threshold: MAE99 up ${engUp}%, dn ${engDn}% (full sample, static)<br>
          Rolling ${_rollingWindowDays}d threshold: MAE99 up ${rollUp.p99}%, dn ${rollDn.p99}% (live)<br>
          Drift: ${dUp >= 0 ? '+' : ''}${dUp}% up, ${dDn >= 0 ? '+' : ''}${dDn}% dn
          <div style="margin-top:6px;font-style:italic;color:var(--text-dim)">Fade booleans in this view are re-scoped by the date filter, but the MAE99 breach threshold was fixed at engine-run time.</div>
        </div>`;
    }
  }

  el.innerHTML = tilesHtml + histHtml + driftHtml;
}
```

- [ ] **Step 2: Reload and verify Panel 3**

Start server, open dashboard, click Validation. Verify:
- Four tiles render with trigger rate + three confirmation rates
- Trigger rate ~1-3% on full sample
- Histogram renders if triggered reps present
- Threshold drift callout shows engine vs rolling comparison
- Change filter to a narrower window → tiles recompute; histogram shrinks
- Change filter to a regime with few triggered reps → histogram shows "No triggered reps" fallback

Kill server.

- [ ] **Step 3: Commit**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git add "Fractal Sweep/model_dashboard_fixed_constant.html"
git commit -m "feat(fixed-constant-dash): implement Panel 3 fade engine view"
```

---

## Task 18: Final verification — full Layer C + spot-check triggered reps

**Files:** none modified; pure verification pass.

- [ ] **Step 1: Run the full test suite**

```bash
cd "Fractal Sweep" && python3 -m pytest tests/test_fade_engine.py -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run the engine one more time and Layer B validation**

```bash
cd "Fractal Sweep" && python3 model_stats_fixed_constant.py && python3 tests/validate_fade_output.py
```

Expected: engine completes, fade stats summary prints per model, validation outputs `OK: all fade_summary checks passed`.

- [ ] **Step 3: Full Layer C dashboard walkthrough**

```bash
cd "/Users/abhi/Downloads/Statistic.ally" && python3 -m http.server 8001 &
```

Open http://localhost:8001/Fractal%20Sweep/model_dashboard_fixed_constant.html. Execute all Layer C steps from the spec:

1. **No filter** → Overview hero tiles match pre-filter values.
2. **Set filter to 2023** → hero tiles, percentile tables, by_hour/by_dow/by_session/by_year all re-scope. Rep count matches.
3. **Set regime pill to expanding** → rep count drops ~1/3; Panel 4 expanding column highlights with purple border.
4. **Rolling dropdown 70d → 30d** → Panel 1 numbers update; Panel 1 banner updates; Panel 3 drift callout updates.
5. **Variance chart** → five rows render; 30d row has smaller n than full row.
6. **Fade panel → spot check**: scroll through the Reps table to find a row with `fade_triggered=true`. Note its `lock_time`, `block_end`, `lock_close`, `excursion_up_pct`, `excursion_down_pct`. Open TradingView for NQ, navigate to that date+time, visually confirm:
   - The 1m bar at `lock_time + chart_tf_min` matches the lock close
   - Price did exceed `lock_close * (1 + mae99_up_pct/100)` during the block (for an up breach)
   - The fade fields are consistent with what you see on the chart

Repeat spot-check for 2-3 more triggered reps across different sessions.

Kill server: `kill %1 2>/dev/null`.

- [ ] **Step 4: Back-compat check — old engine JSON**

```bash
cd "/Users/abhi/Downloads/Statistic.ally" && git stash
cd "Fractal Sweep" && git stash pop -- model_stats_fixed_constant.json 2>/dev/null || true
```

Actually simpler: temporarily rename the current JSON, regenerate without fade changes, reload dashboard.

Alternative: skip this check if it's fragile — the placeholder guards in Task 13 are straightforward and can be verified by deleting `fade_summary` from a copy of the JSON:

```bash
cd "Fractal Sweep" && python3 -c "
import json
d = json.load(open('model_stats_fixed_constant.json'))
for k in d:
    if isinstance(d[k], dict):
        d[k].pop('fade_summary', None)
        for r in d[k].get('recent_reps', []):
            for f in ('block_range_pts','fade_triggered','fade_breach_side','fade_reached_anchor','fade_reached_mfe50_opp','fade_reached_mae99_opp','fade_mfe_opp_pct'):
                r.pop(f, None)
json.dump(d, open('/tmp/old_shape.json', 'w'), default=str)
print('wrote /tmp/old_shape.json')
"
```

Load `/tmp/old_shape.json` via the dashboard's `Load model_stats_fixed_constant.json` button. Verify:
- Overview tab renders normally
- Validation tab Panel 1 shows "rolling window too short" (no block_range_pts → all `unknown` regime → but rolling computation still works off excursion fields — so it should actually render OK)
- Validation tab Panel 2 (variance) renders from excursion fields
- Validation tab Panel 3 (fade) shows the "run model_stats_fixed_constant.py" placeholder
- Validation tab Panel 4 (regime) shows "no regime-classified reps" placeholder
- No console errors

Reload the real JSON before committing.

- [ ] **Step 5: Final commit — merge-ready marker**

```bash
cd "/Users/abhi/Downloads/Statistic.ally"
git log --oneline -20
```

Review the commit history. If satisfied with the three-commit structure (Engine / Filter+Recompute / Validation Tab), no additional commit is needed. Otherwise squash or reword via interactive rebase (only if this is on a feature branch and not on main).

---

## Self-review

**Spec coverage check:**

| Spec section | Plan task(s) | Status |
|---|---|---|
| § 1 Fade engine mechanics — trigger logic | Task 4 | ✓ |
| § 1 Tiebreaker (both sides breach) | Task 5 | ✓ |
| § 1 Walk forward from breach bar | Task 4 | ✓ |
| § 1 Three confirmation booleans + fade_mfe_opp_pct | Tasks 3–5 | ✓ |
| § 1 Full-sample threshold (not rolling) | Task 7 main() | ✓ |
| § 2 Per-rep block_range_pts + fade fields | Tasks 2–7 | ✓ |
| § 2 fade_summary aggregate | Task 6 | ✓ |
| § 2 Null (not 0) for non-triggered | Task 3 | ✓ |
| § 2 Echoed thresholds in fade_summary | Task 6 | ✓ |
| § 2 Back-compat (new JSON ↔ old dashboard) | Task 8 step 4 | ✓ |
| § 2 Back-compat (old JSON ↔ new dashboard) | Task 18 step 4 | ✓ |
| § 3 Header controls | Task 9 | ✓ |
| § 3 filterReps primitive | Task 10 | ✓ |
| § 3 computeDistributions recompute pipeline | Task 10 | ✓ |
| § 3 Thread through existing render | Task 12 | ✓ |
| § 3 Empty state < 30 reps | Task 12 applyFilter | ✓ |
| § 4 Panel 1 rolling card | Task 15 | ✓ |
| § 4 Panel 2 variance chart | Task 16 | ✓ |
| § 4 Panel 3 fade view | Task 17 | ✓ |
| § 4 Panel 4 regime cheat sheet | Task 14 | ✓ |
| § 4 Rolling window dropdown → Panel 1 | Task 15 step 2 | ✓ |
| § 5 classifyRegimes 70d trailing tercile | Task 11 | ✓ |
| § 5 Unknown for first 70 days / < 30 window | Task 11 | ✓ |
| § 5 Runs once on JSON load | Task 11 step 2 | ✓ |
| § 6 Layer A pytest fixtures | Tasks 3, 4, 5, 6 | ✓ |
| § 6 Layer B validate_fade_output.py | Task 8 | ✓ |
| § 6 Layer C manual verification | Tasks 12, 14–18 | ✓ |
| § 6 Layer D back-compat check | Task 18 step 4 | ✓ |
| § 7 Commit 1 scope + verification | Tasks 1–8 | ✓ |
| § 7 Commit 2 scope + verification | Tasks 9–12 | ✓ |
| § 7 Commit 3 scope + verification | Tasks 13–18 | ✓ |

No gaps.

**Placeholder scan:** No "TBD", "TODO", or vague instructions. Every step has exact code or exact commands.

**Type consistency:** `compute_fade_metrics` signature is consistent between Tasks 3, 4, 5, 7 (`(reps, m1_arrs, mae99_up_pct, mae99_down_pct, p50_up_pct, p50_down_pct)`). `build_fade_summary` signature is consistent between Tasks 6 and 7. Rep field names (`_m1_start`, `_m1_end`, `_lock_ts_end_ns`, `_lock_close`) are consistent across Tasks 2, 3, 4, 7. Dashboard globals (`_filterStart`, `_filterEnd`, `_filterRegime`, `_rollingWindowDays`, `_filtered`) are consistent. Function names (`filterReps`, `buildDist`, `groupAndAggregate`, `computeDistributions`, `classifyRegimes`, `applyFilter`, `renderValidationTab`, `renderRollingCard`, `renderVarianceChart`, `renderFadeView`, `renderRegimeCheatsheet`) are consistent.
