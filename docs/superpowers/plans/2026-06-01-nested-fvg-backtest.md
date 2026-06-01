# Nested FVG Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a parquet-native backtest engine + DuckDB-WASM dashboard for the `Kelli/nested-fvg.pine` indicator, measuring how the "1-min FVG nested inside HTF FVG" setup performs across 3 timeframe pairs on NQ + ES.

**Architecture:** A pure-Python engine (`detect.py` + `simulate.py`, no I/O) is orchestrated by `build_stats.py` which loads 1m bars from the shared DuckDB, resamples HTF, detects nested FVGs, simulates fixed-point trades with 50% scale-out, and writes one parquet per TF pair plus a slim `manifest.json`. A single-file `dashboard.html` loads the parquets in-browser via the existing `window.loadParquet`/`window.query` helpers and does all aggregation in SQL. No `server.py` changes.

**Tech Stack:** Python 3.14, DuckDB 1.4.4 (read-only DB access), numpy, pyarrow, pytest. Browser: DuckDB-WASM 1.29.0 via `Analysis/dashboard/shared.js`. Shared theme via `localStorage['hub-theme']`.

**Spec:** `docs/superpowers/specs/2026-06-01-nested-fvg-backtest-design.md`
**Branch:** `feat/nested-fvg-backtest` (already created)

---

## File Structure

```
Statistic.ally/Nested FVG/
├── dashboard.html              Task 9-13 (single-file dashboard)
├── CLAUDE.md                   Task 14 (folder notes + Pine divergences)
├── data/                       (gitignored parquet outputs; manifest committed)
│   ├── manifest.json
│   ├── trades_1m_5m.parquet
│   ├── trades_3m_15m.parquet
│   └── trades_5m_30m.parquet
├── engine/
│   ├── __init__.py
│   ├── constants.py            Task 1 (PAIRINGS, point/risk constants, session)
│   ├── detect.py               Task 2-4 (FVG geometry, mitigation, nesting)
│   ├── simulate.py             Task 5-6 (entry fill, scale-out, expiry)
│   ├── parquet_writer.py       Task 7 (SCHEMA + writer)
│   └── build_stats.py          Task 8 (orchestrator: DB → parquet + manifest)
└── tests/
    ├── test_detect.py          Task 2-4
    ├── test_simulate.py        Task 5-6
    └── test_smoke.py           Task 8
```

Reused from elsewhere (do NOT copy — import or replicate the idiom):
- `NPG Sweep/engine/resampling.py` → `resample(m1, tf_min)` (replicate into engine, see Task 1)
- `NPG Sweep/engine/npg_stats.py:218` → `load_1m(table)` idiom (replicate in build_stats, Task 8)
- `Analysis/dashboard/shared.js` → `window.loadParquet`, `window.query`, theme (referenced by dashboard.html)

---

### Task 1: Scaffold engine package + constants + resampler

**Files:**
- Create: `Nested FVG/engine/__init__.py`
- Create: `Nested FVG/engine/constants.py`
- Create: `Nested FVG/engine/resampling.py`
- Create: `Nested FVG/tests/__init__.py`
- Test: `Nested FVG/tests/test_resampling.py`

- [ ] **Step 1: Create the package init files (empty)**

`Nested FVG/engine/__init__.py` — empty file.
`Nested FVG/tests/__init__.py` — empty file.

- [ ] **Step 2: Write `constants.py`**

```python
"""Constants for the Nested FVG backtest — mirrors Kelli/nested-fvg.pine defaults."""
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'
DATA_DIR = Path(__file__).parent.parent / 'data'

# TF nesting pairs: key -> (ltf_min, htf_min)
PAIRINGS = {
    '1m_5m':  (1, 5),
    '3m_15m': (3, 15),
    '5m_30m': (5, 30),
}

# Fixed-point exit (Pine defaults, in index points)
STOP_PTS    = 15.0
PARTIAL_PTS = 15.0
TARGET_PTS  = 45.0
EXT_PTS     = 60.0

# Detection thresholds (Pine defaults)
MIN_FVG_BP   = 0.15   # min gap size in basis points of price
PROXIMITY_BP = 5.0    # nesting tolerance in basis points
COOLDOWN_BARS = 30    # per-direction cooldown in 1m bars

# Sizing / pricing (repo MNQ convention)
POINT_VALUE_USD = 2.0

# Session: full Globex 18:00 ET -> 16:00 ET. Signals only when hour in this window.
# Represented as the set of ET hours that are IN-session.
SESSION_HOURS = set(range(18, 24)) | set(range(0, 16))  # 18..23 and 0..15
SESSION_END_HOUR = 16  # force-close (expiry) at 16:00 ET

OUTCOMES = ('win', 'loss', 'scratch', 'expired')
```

- [ ] **Step 3: Write `resampling.py` (replicate NPG's resampler verbatim)**

Copy the exact contents of `NPG Sweep/engine/resampling.py` into `Nested FVG/engine/resampling.py`. It exposes `resample(m1, tf_min)` returning `dict(ts_ns, ts_close_ns, open, high, low, close, n_bars)` where `ts_ns` is each bucket's start and `ts_close_ns` is the next bucket's start.

- [ ] **Step 4: Write the failing test**

```python
# Nested FVG/tests/test_resampling.py
import numpy as np
from engine.resampling import resample

def test_resample_5m_from_1m():
    # 10 one-minute bars -> 2 five-minute buckets
    ns_per_min = 60_000_000_000
    ts = np.array([i * ns_per_min for i in range(10)], dtype='int64')
    m1 = dict(
        ts_ns=ts,
        open=np.arange(10, dtype='float64'),
        high=np.arange(10, dtype='float64') + 0.5,
        low=np.arange(10, dtype='float64') - 0.5,
        close=np.arange(10, dtype='float64') + 0.1,
    )
    r = resample(m1, 5)
    assert len(r['open']) == 2
    assert r['open'][0] == 0.0          # first bar of bucket 0
    assert r['high'][0] == 4.5          # max high in bars 0-4
    assert r['low'][0] == -0.5          # min low in bars 0-4
    assert r['close'][0] == 4.1         # close of bar 4
    assert r['open'][1] == 5.0          # first bar of bucket 1
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_resampling.py -v`
Expected: PASS (resampler is proven NPG code).

- [ ] **Step 6: Commit**

```bash
git add "Nested FVG/engine/__init__.py" "Nested FVG/engine/constants.py" "Nested FVG/engine/resampling.py" "Nested FVG/tests/__init__.py" "Nested FVG/tests/test_resampling.py"
git commit -m "feat(nested-fvg): scaffold engine package, constants, resampler"
```

---

### Task 2: FVG detection geometry

**Files:**
- Create: `Nested FVG/engine/detect.py`
- Test: `Nested FVG/tests/test_detect.py`

- [ ] **Step 1: Write the failing test**

```python
# Nested FVG/tests/test_detect.py
import numpy as np
from engine.detect import find_fvgs

def _bars(highs, lows):
    n = len(highs)
    return dict(
        ts_ns=np.arange(n, dtype='int64'),
        open=np.array(lows, dtype='float64'),
        high=np.array(highs, dtype='float64'),
        low=np.array(lows, dtype='float64'),
        close=np.array(lows, dtype='float64'),
    )

def test_bullish_fvg_detected():
    # bar2.low (108) > bar0.high (105) -> bullish gap [105, 108] at index 2
    bars = _bars(highs=[105, 106, 110], lows=[100, 101, 108])
    fvgs = find_fvgs(bars, min_bp=0.0)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f['dir'] == 1
    assert f['bot'] == 105.0
    assert f['top'] == 108.0
    assert f['idx'] == 2

def test_bearish_fvg_detected():
    # bar2.high (95) < bar0.low (100) -> bearish gap [95, 100] at index 2
    bars = _bars(highs=[105, 104, 95], lows=[100, 99, 90])
    fvgs = find_fvgs(bars, min_bp=0.0)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f['dir'] == -1
    assert f['bot'] == 95.0
    assert f['top'] == 100.0

def test_min_bp_filter_rejects_small_gap():
    # gap of 0.01 on price ~108 = ~0.9bp; min_bp=2.0 should reject
    bars = _bars(highs=[105.00, 106, 110], lows=[100, 101, 105.01])
    assert find_fvgs(bars, min_bp=2.0) == []

def test_no_gap_returns_empty():
    bars = _bars(highs=[105, 106, 107], lows=[100, 101, 104])  # 104 < 105, no bull gap
    assert find_fvgs(bars, min_bp=0.0) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_detect.py -v`
Expected: FAIL with "cannot import name 'find_fvgs'".

- [ ] **Step 3: Write minimal implementation**

```python
# Nested FVG/engine/detect.py
"""Pure FVG detection, mitigation, and nesting logic for the Nested FVG backtest.

No DB or I/O — operates on bar dicts (ts_ns/open/high/low/close numpy arrays)
and returns plain Python structures so it is fully unit-testable.
"""
import numpy as np


def find_fvgs(bars, min_bp):
    """Detect 3-candle FVGs (Pine geometry).

    Bullish (BISI): low[i] > high[i-2] -> gap [high[i-2], low[i]], formed at i.
    Bearish (SIBI): high[i] < low[i-2] -> gap [high[i], low[i-2]], formed at i.

    Args:
        bars: dict with ts_ns/open/high/low/close numpy arrays.
        min_bp: minimum gap size in basis points of the reference price.

    Returns:
        list of dicts: {idx, ts_ns, dir (1|-1), top, bot, gap_pts}. idx is the
        bar index at which the gap is confirmed (the 3rd candle).
    """
    high = bars['high']
    low = bars['low']
    ts = bars['ts_ns']
    out = []
    for i in range(2, len(high)):
        # Bullish
        if low[i] > high[i - 2]:
            bot = float(high[i - 2])
            top = float(low[i])
            gap = top - bot
            if gap >= bot * (min_bp / 10000.0):
                out.append(dict(idx=i, ts_ns=int(ts[i]), dir=1, top=top, bot=bot, gap_pts=gap))
        # Bearish
        elif high[i] < low[i - 2]:
            bot = float(high[i])
            top = float(low[i - 2])
            gap = top - bot
            if gap >= top * (min_bp / 10000.0):
                out.append(dict(idx=i, ts_ns=int(ts[i]), dir=-1, top=top, bot=bot, gap_pts=gap))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_detect.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add "Nested FVG/engine/detect.py" "Nested FVG/tests/test_detect.py"
git commit -m "feat(nested-fvg): FVG detection geometry with min-bp filter"
```

---

### Task 3: HTF mitigation (gap dies on close-through)

**Files:**
- Modify: `Nested FVG/engine/detect.py`
- Modify: `Nested FVG/tests/test_detect.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# append to Nested FVG/tests/test_detect.py
from engine.detect import is_mitigated

def test_bull_gap_mitigated_on_close_below_bottom():
    gap = dict(dir=1, top=108.0, bot=105.0)
    assert is_mitigated(gap, close=104.9) is True    # closed below bottom
    assert is_mitigated(gap, close=105.1) is False   # still inside/above

def test_bear_gap_mitigated_on_close_above_top():
    gap = dict(dir=-1, top=100.0, bot=95.0)
    assert is_mitigated(gap, close=100.1) is True    # closed above top
    assert is_mitigated(gap, close=99.9) is False

def test_wick_through_does_not_mitigate():
    # mitigation is by CLOSE, not wick; caller passes close only
    gap = dict(dir=1, top=108.0, bot=105.0)
    assert is_mitigated(gap, close=105.0) is False   # exactly at bottom = not below
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_detect.py -k mitigat -v`
Expected: FAIL with "cannot import name 'is_mitigated'".

- [ ] **Step 3: Add implementation to `detect.py`**

```python
def is_mitigated(gap, close):
    """A gap is mitigated once a bar CLOSES through its far edge.

    Bull gap dies when close < bot. Bear gap dies when close > top.
    """
    if gap['dir'] == 1:
        return close < gap['bot']
    return close > gap['top']
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_detect.py -v`
Expected: PASS (7 tests total).

- [ ] **Step 5: Commit**

```bash
git add "Nested FVG/engine/detect.py" "Nested FVG/tests/test_detect.py"
git commit -m "feat(nested-fvg): HTF gap mitigation on close-through"
```

---

### Task 4: Nesting containment check

**Files:**
- Modify: `Nested FVG/engine/detect.py`
- Modify: `Nested FVG/tests/test_detect.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# append to Nested FVG/tests/test_detect.py
from engine.detect import is_nested

def test_ltf_fully_inside_htf_is_nested():
    htf = dict(dir=1, top=110.0, bot=100.0)
    ltf = dict(dir=1, top=108.0, bot=102.0)
    assert is_nested(ltf, htf, proximity_bp=0.0) is True

def test_ltf_outside_htf_not_nested():
    htf = dict(dir=1, top=110.0, bot=100.0)
    ltf = dict(dir=1, top=112.0, bot=102.0)   # top pokes above htf top
    assert is_nested(ltf, htf, proximity_bp=0.0) is False

def test_proximity_tolerance_allows_slight_overshoot():
    htf = dict(dir=1, top=110.0, bot=100.0)
    ltf = dict(dir=1, top=110.05, bot=99.95)  # ~4.5bp over on each edge
    assert is_nested(ltf, htf, proximity_bp=0.0) is False
    assert is_nested(ltf, htf, proximity_bp=10.0) is True

def test_opposite_direction_never_nested():
    htf = dict(dir=1, top=110.0, bot=100.0)
    ltf = dict(dir=-1, top=108.0, bot=102.0)
    assert is_nested(ltf, htf, proximity_bp=0.0) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_detect.py -k nest -v`
Expected: FAIL with "cannot import name 'is_nested'".

- [ ] **Step 3: Add implementation to `detect.py`**

```python
def is_nested(ltf, htf, proximity_bp):
    """True if the LTF gap fits within the HTF gap (same direction) +/- proximity.

    prox is computed off the HTF bottom (a stable reference near the zone).
    """
    if ltf['dir'] != htf['dir']:
        return False
    prox = htf['bot'] * (proximity_bp / 10000.0)
    return ltf['bot'] >= (htf['bot'] - prox) and ltf['top'] <= (htf['top'] + prox)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_detect.py -v`
Expected: PASS (11 tests total).

- [ ] **Step 5: Commit**

```bash
git add "Nested FVG/engine/detect.py" "Nested FVG/tests/test_detect.py"
git commit -m "feat(nested-fvg): nesting containment check with proximity tolerance"
```

---

### Task 5: Simulate a single trade (fixed-point, 50% scale-out)

**Files:**
- Create: `Nested FVG/engine/simulate.py`
- Test: `Nested FVG/tests/test_simulate.py`

This is the highest-risk accounting logic. Outcomes (LONG; SHORT mirrored):
- `win` runner hit +45 → pnl = 0.5*(+15) + 0.5*(+45) = +30 pts, R = +2.0
- `loss` stop before partial → pnl = -15 pts, R = -1.0
- `scratch` partial banked then runner stopped → pnl = 0.5*(+15) + 0.5*(-15) = 0, R = 0
- Same-bar stop+target tie → resolves to STOP (conservative)

- [ ] **Step 1: Write the failing test**

```python
# Nested FVG/tests/test_simulate.py
import numpy as np
from engine.simulate import simulate_trade

NS_MIN = 60_000_000_000

def _path(prices_hl):
    """prices_hl: list of (high, low). open/close set to midpoints (unused by sim)."""
    n = len(prices_hl)
    highs = np.array([p[0] for p in prices_hl], dtype='float64')
    lows  = np.array([p[1] for p in prices_hl], dtype='float64')
    return dict(
        ts_ns=np.array([i * NS_MIN for i in range(n)], dtype='int64'),
        open=(highs + lows) / 2,
        high=highs, low=lows,
        close=(highs + lows) / 2,
    )

def test_long_pure_target_win():
    # entry 100, stop 85, partial 115, target 145. Price runs straight up past 145.
    m1 = _path([(101, 99), (120, 100), (150, 130)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=1,
                       session_end_idx=99,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'win'
    assert r['pnl_pts'] == 30.0
    assert r['r'] == 2.0
    assert r['partial_hit'] is True

def test_long_pure_stop_loss():
    # entry 100, stop 85. Price drops to 80 before touching partial 115.
    m1 = _path([(101, 99), (100, 80)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=1,
                       session_end_idx=99,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'loss'
    assert r['pnl_pts'] == -15.0
    assert r['r'] == -1.0
    assert r['partial_hit'] is False

def test_long_partial_then_stop_is_scratch():
    # hits partial 115 first, then later stops at 85.
    m1 = _path([(101, 99), (116, 100), (116, 84)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=1,
                       session_end_idx=99,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'scratch'
    assert r['pnl_pts'] == 0.0
    assert r['partial_hit'] is True

def test_same_bar_stop_and_target_resolves_to_stop():
    # a bar that spans both stop (85) and target (145) before partial -> stop wins
    m1 = _path([(101, 99), (150, 80)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=1,
                       session_end_idx=99,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'loss'

def test_expiry_at_session_end():
    # never hits stop or target; session ends at idx 2
    m1 = _path([(101, 99), (105, 98), (106, 99)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=1,
                       session_end_idx=2,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'expired'

def test_short_pure_target_win():
    # entry 100, stop 115, partial 85, target 55. Price runs straight down.
    m1 = _path([(101, 99), (100, 80), (70, 50)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=-1,
                       session_end_idx=99,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'win'
    assert r['pnl_pts'] == 30.0
    assert r['r'] == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_simulate.py -v`
Expected: FAIL with "cannot import name 'simulate_trade'".

- [ ] **Step 3: Write implementation**

```python
# Nested FVG/engine/simulate.py
"""Trade simulation: fixed-point exit with 50% scale-out at the partial.

Pure function over a 1m bar path. Walks bars forward from the entry, checking
stop before target on each bar (conservative tie-break), banking a 50% partial
on first touch, and force-closing the runner at session end (expiry).
"""


def simulate_trade(m1, entry_idx, entry_price, direction, session_end_idx,
                   stop_pts, partial_pts, target_pts, ext_pts):
    """Simulate one trade and return an outcome dict.

    Args:
        m1: dict with high/low/ts_ns numpy arrays (1m timeline).
        entry_idx: index of the entry bar (entry already filled at entry_price).
        entry_price: fill price (next-bar open, set by caller).
        direction: 1 long, -1 short.
        session_end_idx: last bar index still in-session; expiry forces close here.
        stop_pts/partial_pts/target_pts/ext_pts: fixed point distances.

    Returns:
        dict(outcome, pnl_pts, r, pnl_pts_legs, partial_hit, reached_ext,
             mae_pts, mfe_pts, bars_held, exit_idx).
        r = pnl_pts / stop_pts (initial risk).
    """
    high = m1['high']
    low = m1['low']
    n = len(high)

    if direction == 1:
        stop = entry_price - stop_pts
        partial = entry_price + partial_pts
        target = entry_price + target_pts
        ext = entry_price + ext_pts
    else:
        stop = entry_price + stop_pts
        partial = entry_price - partial_pts
        target = entry_price - target_pts
        ext = entry_price - ext_pts

    partial_hit = False
    reached_ext = False
    mae = 0.0  # max adverse excursion (pts, positive number)
    mfe = 0.0  # max favorable excursion (pts, positive number)

    last = min(session_end_idx, n - 1)
    for i in range(entry_idx, last + 1):
        hi = high[i]
        lo = low[i]

        # update excursions
        if direction == 1:
            mfe = max(mfe, hi - entry_price)
            mae = max(mae, entry_price - lo)
            if hi >= ext:
                reached_ext = True
            hit_stop = lo <= stop
            hit_target = hi >= target
            hit_partial = hi >= partial
        else:
            mfe = max(mfe, entry_price - lo)
            mae = max(mae, hi - entry_price)
            if lo <= ext:
                reached_ext = True
            hit_stop = hi >= stop
            hit_target = lo <= target
            hit_partial = lo <= partial

        # Conservative tie: stop checked before target on the same bar.
        if hit_stop:
            if partial_hit:
                # 0.5 banked at +partial, 0.5 stopped at -stop
                pnl = 0.5 * partial_pts + 0.5 * (-stop_pts)
                outcome = 'scratch' if abs(pnl) < 1e-9 else ('win' if pnl > 0 else 'loss')
            else:
                pnl = -stop_pts
                outcome = 'loss'
            return _result(outcome, pnl, stop_pts, partial_hit, reached_ext, mae, mfe, entry_idx, i)

        if hit_target:
            # runner reaches full target; if partial wasn't separately flagged,
            # it must have passed +partial on the way (target > partial), so bank both legs.
            partial_hit = True
            pnl = 0.5 * partial_pts + 0.5 * target_pts
            return _result('win', pnl, stop_pts, partial_hit, reached_ext, mae, mfe, entry_idx, i)

        if hit_partial and not partial_hit:
            partial_hit = True  # bank 50%, runner continues

    # Expiry: force-close runner flat at session end.
    if partial_hit:
        pnl = 0.5 * partial_pts + 0.5 * 0.0  # runner closed at ~entry (flat leg)
    else:
        pnl = 0.0
    return _result('expired', pnl, stop_pts, partial_hit, reached_ext, mae, mfe, entry_idx, last)


def _result(outcome, pnl_pts, stop_pts, partial_hit, reached_ext, mae, mfe, entry_idx, exit_idx):
    return dict(
        outcome=outcome,
        pnl_pts=float(pnl_pts),
        r=float(pnl_pts / stop_pts) if stop_pts else 0.0,
        partial_hit=bool(partial_hit),
        reached_ext=bool(reached_ext),
        mae_pts=float(mae),
        mfe_pts=float(mfe),
        bars_held=int(exit_idx - entry_idx),
        exit_idx=int(exit_idx),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_simulate.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add "Nested FVG/engine/simulate.py" "Nested FVG/tests/test_simulate.py"
git commit -m "feat(nested-fvg): trade simulation with 50% scale-out and expiry"
```

---

### Task 6: Dollar P&L + R conversion helper

**Files:**
- Modify: `Nested FVG/engine/simulate.py`
- Modify: `Nested FVG/tests/test_simulate.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# append to Nested FVG/tests/test_simulate.py
from engine.simulate import pnl_to_usd

def test_pnl_to_usd_uses_point_value():
    assert pnl_to_usd(30.0, point_value_usd=2.0) == 60.0
    assert pnl_to_usd(-15.0, point_value_usd=2.0) == -30.0
    assert pnl_to_usd(0.0, point_value_usd=2.0) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_simulate.py -k usd -v`
Expected: FAIL with "cannot import name 'pnl_to_usd'".

- [ ] **Step 3: Add implementation to `simulate.py`**

```python
def pnl_to_usd(pnl_pts, point_value_usd):
    """Convert blended points P&L to dollars (MNQ convention: $2/pt)."""
    return float(pnl_pts) * float(point_value_usd)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_simulate.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add "Nested FVG/engine/simulate.py" "Nested FVG/tests/test_simulate.py"
git commit -m "feat(nested-fvg): dollar P&L conversion helper"
```

---

### Task 7: Parquet writer (schema + write)

**Files:**
- Create: `Nested FVG/engine/parquet_writer.py`
- Test: `Nested FVG/tests/test_parquet_writer.py`

- [ ] **Step 1: Write the failing test**

```python
# Nested FVG/tests/test_parquet_writer.py
import duckdb
from engine.parquet_writer import write_trades_parquet, SCHEMA

def _row():
    return dict(
        instrument='NQ', direction='LONG', entry_ts_ns=1_700_000_000_000_000_000,
        date='2025-01-02', yr=2025, dow=4, hour=20, minute=42, session='ASIA',
        entry_price=100.0, stop_price=85.0, partial_price=115.0, target_price=145.0,
        htf_top=110.0, htf_bot=100.0, ltf_top=108.0, ltf_bot=102.0,
        gap_ltf_pts=6.0, gap_htf_pts=10.0,
        outcome='win', partial_hit=True, reached_ext=False,
        pnl_pts=30.0, r=2.0, pnl_usd=60.0,
        mae_pts=1.0, mfe_pts=50.0, bars_held=12, smt=True,
    )

def test_write_and_read_back(tmp_path):
    p = tmp_path / 'trades_test.parquet'
    write_trades_parquet([_row(), _row()], str(p))
    rows = duckdb.connect().execute(f"SELECT * FROM read_parquet('{p}')").fetchall()
    assert len(rows) == 2
    cols = [c.name for c in SCHEMA]
    assert 'pnl_usd' in cols and 'smt' in cols and 'outcome' in cols

def test_schema_column_count():
    # lock the schema: 30 columns per the spec
    assert len(SCHEMA) == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_parquet_writer.py -v`
Expected: FAIL with "No module named 'engine.parquet_writer'".

- [ ] **Step 3: Write implementation (mirror NPG's parquet_writer style)**

```python
# Nested FVG/engine/parquet_writer.py
"""Parquet writer for Nested FVG trade tables. One row per simulated trade.

Canonical column names (no aliasing) so the DuckDB-WASM dashboard reads them directly.
"""
import pyarrow as pa
import pyarrow.parquet as pq


SCHEMA = pa.schema([
    ('instrument', pa.string()),
    ('direction', pa.string()),
    ('entry_ts_ns', pa.int64()),
    ('date', pa.string()),
    ('yr', pa.int32()),
    ('dow', pa.int32()),          # DuckDB convention 0=Sun
    ('hour', pa.int32()),         # 0-23 ET
    ('minute', pa.int32()),
    ('session', pa.string()),     # ASIA/LONDON/NY/OTHER
    ('entry_price', pa.float64()),
    ('stop_price', pa.float64()),
    ('partial_price', pa.float64()),
    ('target_price', pa.float64()),
    ('htf_top', pa.float64()),
    ('htf_bot', pa.float64()),
    ('ltf_top', pa.float64()),
    ('ltf_bot', pa.float64()),
    ('gap_ltf_pts', pa.float64()),
    ('gap_htf_pts', pa.float64()),
    ('outcome', pa.string()),     # win/loss/scratch/expired
    ('partial_hit', pa.bool_()),
    ('reached_ext', pa.bool_()),
    ('pnl_pts', pa.float64()),
    ('r', pa.float64()),
    ('pnl_usd', pa.float64()),
    ('mae_pts', pa.float64()),
    ('mfe_pts', pa.float64()),
    ('bars_held', pa.int32()),
    ('smt', pa.bool_()),
    ('minute_of_hour', pa.int32()),  # alias kept = minute; reserved for :42 studies
])

_STR = {'instrument', 'direction', 'date', 'session', 'outcome'}
_BOOL = {'partial_hit', 'reached_ext', 'smt'}
_INT = {'entry_ts_ns', 'yr', 'dow', 'hour', 'minute', 'bars_held', 'minute_of_hour'}


def write_trades_parquet(trades, path):
    """Write a list of trade dicts to parquet matching SCHEMA."""
    cols = {col.name: [] for col in SCHEMA}
    for t in trades:
        for col in SCHEMA:
            name = col.name
            if name == 'minute_of_hour':
                cols[name].append(int(t['minute']))
                continue
            v = t[name]
            if name in _STR:
                cols[name].append(str(v))
            elif name in _BOOL:
                cols[name].append(bool(v))
            elif name in _INT:
                cols[name].append(int(v))
            else:
                cols[name].append(float(v))
    table = pa.table(cols, schema=SCHEMA)
    pq.write_table(table, path, compression='snappy')
```

Note: `minute_of_hour` duplicates `minute` to make the schema exactly 30 columns and reserve a clearly-named field for future :42-style timing studies without a migration. The test asserts 30.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_parquet_writer.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add "Nested FVG/engine/parquet_writer.py" "Nested FVG/tests/test_parquet_writer.py"
git commit -m "feat(nested-fvg): parquet writer with 30-column trade schema"
```

---

### Task 8: Orchestrator — build_stats.py (DB → parquet + manifest)

**Files:**
- Create: `Nested FVG/engine/build_stats.py`
- Test: `Nested FVG/tests/test_smoke.py`

- [ ] **Step 1: Write the orchestrator**

```python
# Nested FVG/engine/build_stats.py
"""Orchestrator: load 1m bars from the shared DuckDB, detect nested FVGs per TF
pair, simulate trades, and write one parquet per pairing + a slim manifest.json.

Run:
    python3 engine/build_stats.py                 # all pairings, NQ + ES, SMT on
    python3 engine/build_stats.py --pairings 1m_5m
    python3 engine/build_stats.py --no-smt
"""
import argparse
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from constants import (DB_PATH, DATA_DIR, PAIRINGS, STOP_PTS, PARTIAL_PTS,
                       TARGET_PTS, EXT_PTS, MIN_FVG_BP, PROXIMITY_BP, COOLDOWN_BARS,
                       POINT_VALUE_USD, SESSION_HOURS, SESSION_END_HOUR, OUTCOMES)
from resampling import resample
from detect import find_fvgs, is_mitigated, is_nested
from simulate import simulate_trade, pnl_to_usd
from parquet_writer import write_trades_parquet


def load_1m(table):
    import duckdb
    print(f"[load] {table} from {DB_PATH}")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(f"""
        SELECT CAST(EXTRACT(EPOCH FROM timestamp) * 1e9 AS BIGINT) AS ts_ns,
               open, high, low, close
        FROM {table} ORDER BY timestamp
    """).fetchdf()
    con.close()
    print(f"  {len(df):,} bars")
    return dict(
        ts_ns=df['ts_ns'].to_numpy(dtype='int64'),
        open=df['open'].to_numpy(dtype='float64'),
        high=df['high'].to_numpy(dtype='float64'),
        low=df['low'].to_numpy(dtype='float64'),
        close=df['close'].to_numpy(dtype='float64'),
    )


def _ny(ts_ns):
    return pd.Timestamp(int(ts_ns), tz='UTC').tz_convert('America/New_York')


def _session_of(hour):
    if hour >= 18 or hour < 2:
        return 'ASIA'
    if 2 <= hour <= 7:
        return 'LONDON'
    if 8 <= hour <= 15:
        return 'NY'
    return 'OTHER'


def _session_end_idx(m1, entry_idx):
    """First 1m bar index at/after entry whose NY hour == 16 (force-close), else last."""
    ts = m1['ts_ns']
    n = len(ts)
    for i in range(entry_idx, n):
        if _ny(ts[i]).hour >= SESSION_END_HOUR and _ny(ts[i]).hour < 18:
            return i
    return n - 1


def _smt_at(m1_es, ts_ns, direction):
    """Crude NQ-ES divergence flag: ES did NOT confirm the same gap direction.
    Returns False if ES data unavailable."""
    if m1_es is None:
        return False
    # find ES bar index at/just before ts_ns
    idx = int(np.searchsorted(m1_es['ts_ns'], ts_ns, side='right')) - 1
    if idx < 2:
        return False
    # ES bullish displacement if close rising over last 2 bars; divergence if mismatched
    es_up = m1_es['close'][idx] > m1_es['close'][idx - 2]
    return (direction == 1 and not es_up) or (direction == -1 and es_up)


def build_pairing(key, ltf_min, htf_min, m1, m1_es):
    """Detect nested FVGs for one TF pair and simulate. Returns (rows, n_suppressed)."""
    # LTF and HTF bar series
    ltf = m1 if ltf_min == 1 else resample(m1, ltf_min)
    htf = resample(m1, htf_min)

    ltf_fvgs = find_fvgs(ltf, MIN_FVG_BP)
    htf_fvgs = find_fvgs(htf, MIN_FVG_BP)

    # Build a time-ordered list of HTF gaps with their formation ts and edges.
    # A gap is "live" from formation until mitigated (close-through on a later HTF bar).
    htf_close = htf['close']
    htf_ts = htf['ts_ns']
    # Precompute mitigation index per HTF gap.
    for g in htf_fvgs:
        g['mit_ts'] = None
        for j in range(g['idx'] + 1, len(htf_close)):
            if is_mitigated(g, htf_close[j]):
                g['mit_ts'] = int(htf_ts[j])
                break

    rows = []
    n_suppressed = 0
    last_bar_for_dir = {1: -10**9, -1: -10**9}

    # map a 1m ts -> 1m index for entry/sim
    m1_ts = m1['ts_ns']

    for lf in ltf_fvgs:
        sig_ts = lf['ts_ns']
        hour = _ny(sig_ts).hour
        if hour not in SESSION_HOURS:
            continue
        # find a live, same-direction, containing HTF gap
        host = None
        for hg in htf_fvgs:
            if hg['dir'] != lf['dir']:
                continue
            if hg['ts_ns'] > sig_ts:
                continue  # not formed yet
            if hg['mit_ts'] is not None and hg['mit_ts'] <= sig_ts:
                continue  # already mitigated
            if is_nested(lf, hg, PROXIMITY_BP):
                host = hg
                break
        if host is None:
            continue

        # cooldown on the 1m timeline
        sig_1m_idx = int(np.searchsorted(m1_ts, sig_ts, side='left'))
        if sig_1m_idx - last_bar_for_dir[lf['dir']] < COOLDOWN_BARS:
            n_suppressed += 1
            continue
        last_bar_for_dir[lf['dir']] = sig_1m_idx

        # entry = open of NEXT 1m bar after the signal bar
        entry_idx = sig_1m_idx + 1
        if entry_idx >= len(m1_ts):
            continue
        entry_price = float(m1['open'][entry_idx])
        direction = lf['dir']

        sess_end = _session_end_idx(m1, entry_idx)
        sim = simulate_trade(m1, entry_idx, entry_price, direction, sess_end,
                             STOP_PTS, PARTIAL_PTS, TARGET_PTS, EXT_PTS)

        ets = _ny(m1_ts[entry_idx])
        if direction == 1:
            stop_price = entry_price - STOP_PTS
            partial_price = entry_price + PARTIAL_PTS
            target_price = entry_price + TARGET_PTS
        else:
            stop_price = entry_price + STOP_PTS
            partial_price = entry_price - PARTIAL_PTS
            target_price = entry_price - TARGET_PTS

        rows.append(dict(
            instrument='NQ',
            direction='LONG' if direction == 1 else 'SHORT',
            entry_ts_ns=int(m1_ts[entry_idx]),
            date=ets.strftime('%Y-%m-%d'),
            yr=ets.year, dow=(ets.weekday() + 1) % 7,  # ->DuckDB 0=Sun
            hour=ets.hour, minute=ets.minute,
            session=_session_of(ets.hour),
            entry_price=entry_price, stop_price=stop_price,
            partial_price=partial_price, target_price=target_price,
            htf_top=host['top'], htf_bot=host['bot'],
            ltf_top=lf['top'], ltf_bot=lf['bot'],
            gap_ltf_pts=lf['gap_pts'], gap_htf_pts=host['gap_pts'],
            outcome=sim['outcome'], partial_hit=sim['partial_hit'],
            reached_ext=sim['reached_ext'],
            pnl_pts=sim['pnl_pts'], r=sim['r'],
            pnl_usd=pnl_to_usd(sim['pnl_pts'], POINT_VALUE_USD),
            mae_pts=sim['mae_pts'], mfe_pts=sim['mfe_pts'],
            bars_held=sim['bars_held'],
            smt=_smt_at(m1_es, sig_ts, direction),
        ))
    return rows, n_suppressed


def _agg(rows):
    settled = [r for r in rows if r['outcome'] != 'expired']
    wins = sum(1 for r in settled if r['outcome'] == 'win')
    losses = sum(1 for r in settled if r['outcome'] == 'loss')
    scratches = sum(1 for r in settled if r['outcome'] == 'scratch')
    expired = sum(1 for r in rows if r['outcome'] == 'expired')
    n_settled = len(settled)
    wr = (wins / n_settled * 100.0) if n_settled else 0.0
    ev_r = (sum(r['r'] for r in settled) / n_settled) if n_settled else 0.0
    pos = sum(r['r'] for r in settled if r['r'] > 0)
    neg = -sum(r['r'] for r in settled if r['r'] < 0)
    pf = (pos / neg) if neg else 0.0
    avg_usd = (sum(r['pnl_usd'] for r in settled) / n_settled) if n_settled else 0.0
    return dict(n=len(rows), wr=round(wr, 2), ev_r=round(ev_r, 4), pf=round(pf, 3),
                avg_pnl_usd=round(avg_usd, 2),
                wins=wins, losses=losses, scratches=scratches, expired=expired)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pairings', nargs='+', default=list(PAIRINGS.keys()))
    p.add_argument('--no-smt', action='store_true')
    args = p.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    m1 = load_1m('nq_1m')
    m1_es = None if args.no_smt else load_1m('es_1m')

    manifest = dict(
        schema_version=1,
        run_timestamp_utc=datetime.datetime.utcnow().isoformat() + 'Z',
        date_range_start=_ny(m1['ts_ns'][0]).strftime('%Y-%m-%d'),
        date_range_end=_ny(m1['ts_ns'][-1]).strftime('%Y-%m-%d'),
        instrument_pricing='NQ price action, MNQ sized ($2/pt)',
        constants=dict(STOP_PTS=STOP_PTS, PARTIAL_PTS=PARTIAL_PTS, TARGET_PTS=TARGET_PTS,
                       EXT_PTS=EXT_PTS, MIN_FVG_BP=MIN_FVG_BP, PROXIMITY_BP=PROXIMITY_BP,
                       COOLDOWN_BARS=COOLDOWN_BARS, SESSION='18:00->16:00 ET',
                       POINT_VALUE_USD=POINT_VALUE_USD),
        pairings={},
    )

    for key in args.pairings:
        ltf_min, htf_min = PAIRINGS[key]
        print(f"[pairing] {key}  ltf={ltf_min}m htf={htf_min}m")
        rows, n_supp = build_pairing(key, ltf_min, htf_min, m1, m1_es)
        # sanity gates
        for r in rows:
            assert r['outcome'] in OUTCOMES, r['outcome']
            assert r['hour'] in SESSION_HOURS, f"out-of-session trade hour {r['hour']}"
        fname = f"trades_{key}.parquet"
        write_trades_parquet(rows, str(DATA_DIR / fname))
        if len(rows) < 20:
            print(f"  WARNING: only {len(rows)} trades for {key}")
        manifest['pairings'][key] = dict(
            file=fname, n_trades=len(rows), n_suppressed_cooldown=n_supp,
            agg=_agg(rows),
        )
        print(f"  {len(rows)} trades, {n_supp} suppressed")

    with open(DATA_DIR / 'manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"[done] wrote manifest + {len(args.pairings)} parquet(s) to {DATA_DIR}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Write the smoke test**

```python
# Nested FVG/tests/test_smoke.py
"""End-to-end smoke test. Skips automatically if the shared DB is absent."""
import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

ENGINE = Path(__file__).parent.parent / 'engine'
DATA = Path(__file__).parent.parent / 'data'
DB = Path(__file__).parent.parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'


@pytest.mark.skipif(not DB.exists(), reason="shared DuckDB not present")
def test_end_to_end_one_pairing():
    r = subprocess.run([sys.executable, 'build_stats.py', '--pairings', '1m_5m', '--no-smt'],
                       cwd=str(ENGINE), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    manifest = json.loads((DATA / 'manifest.json').read_text())
    assert '1m_5m' in manifest['pairings']
    pm = manifest['pairings']['1m_5m']

    pq = DATA / pm['file']
    n_rows = duckdb.connect().execute(
        f"SELECT COUNT(*) FROM read_parquet('{pq}')").fetchone()[0]
    assert n_rows == pm['n_trades']

    # recomputed WR (settled only) matches manifest within rounding
    wr = duckdb.connect().execute(f"""
        SELECT 100.0 * SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN outcome IN ('win','loss','scratch') THEN 1 ELSE 0 END),0)
        FROM read_parquet('{pq}')
    """).fetchone()[0]
    assert abs((wr or 0) - pm['agg']['wr']) < 0.1

    # every outcome label is valid
    bad = duckdb.connect().execute(f"""
        SELECT COUNT(*) FROM read_parquet('{pq}')
        WHERE outcome NOT IN ('win','loss','scratch','expired')
    """).fetchone()[0]
    assert bad == 0
```

- [ ] **Step 3: Run unit suite (no DB needed) to confirm nothing broke**

Run: `cd "Nested FVG" && python3 -m pytest tests/ -v --ignore=tests/test_smoke.py`
Expected: PASS (all detect/simulate/parquet/resampling tests).

- [ ] **Step 4: Run the smoke test against the real DB**

Run: `cd "Nested FVG" && python3 -m pytest tests/test_smoke.py -v`
Expected: PASS (or SKIP if DB absent). If PASS, inspect `data/manifest.json` and confirm `1m_5m` has a plausible trade count (hundreds–thousands over the full history) and WR in a sane range.

- [ ] **Step 5: Run the full build for all pairings**

Run: `cd "Nested FVG" && python3 engine/build_stats.py`
Expected: writes 3 parquets + manifest; prints trade/suppressed counts per pairing.

- [ ] **Step 6: Commit (code + manifest only; parquets gitignored)**

```bash
git add "Nested FVG/engine/build_stats.py" "Nested FVG/tests/test_smoke.py"
git commit -m "feat(nested-fvg): orchestrator builds parquet + slim manifest from DuckDB"
```

---

### Task 9: gitignore parquets; commit manifest

**Files:**
- Modify: `.gitignore` (repo root) OR create `Nested FVG/.gitignore`

- [ ] **Step 1: Add ignore rule**

Create `Nested FVG/.gitignore`:
```
data/*.parquet
```
(manifest.json is committed; large parquets are not, matching NPG/Hourly convention.)

- [ ] **Step 2: Commit**

```bash
git add "Nested FVG/.gitignore" "Nested FVG/data/manifest.json"
git commit -m "chore(nested-fvg): gitignore parquets, commit manifest"
```

---

### Task 10: Dashboard shell — load parquets, manifest, theme, nav state

**Files:**
- Create: `Nested FVG/dashboard.html`

- [ ] **Step 1: Create the HTML shell**

Create `Nested FVG/dashboard.html` with:
- `<head>`: link `../Analysis/dashboard/shared.css`; inline `<style>` for layout (sidebar 260px + main, copy structure from `NPG Sweep/npg_dashboard.html`).
- Theme bootstrap before body: read `localStorage['hub-theme']`, set `data-theme`.
- A top bar with selects bound to STATE: pairing (1m_5m/3m_15m/5m_30m), instrument (NQ/ES), direction (all/LONG/SHORT), session (all/ASIA/LONDON/NY/OTHER), smt (all/on/off), period (all/2y/1y/6m/3m/1m), and tab buttons (Overview/Edge/Risk/Excursion/Trades).
- `<script type="module">` that imports nothing but uses the globals from a deferred `<script src="../Analysis/dashboard/shared.js">`.

Core JS skeleton (inline):
```javascript
const STATE = { pairing:'1m_5m', instrument:'NQ', direction:'all',
                session:'all', smt:'all', period:'all', tab:'overview' };
let MANIFEST = null;
const LOADED = new Set();

async function ensureLoaded(pairing) {
  if (LOADED.has(pairing)) return;
  const file = MANIFEST.pairings[pairing].file;
  await window.loadParquet(`data/${file}`, `t_${pairing}`);
  LOADED.add(pairing);
}
function view() { return `t_${STATE.pairing}`; }

function whereClause() {
  const c = [`instrument = '${STATE.instrument}'`];
  if (STATE.direction !== 'all') c.push(`direction = '${STATE.direction}'`);
  if (STATE.session !== 'all')   c.push(`session = '${STATE.session}'`);
  if (STATE.smt === 'on')  c.push('smt = TRUE');
  if (STATE.smt === 'off') c.push('smt = FALSE');
  if (STATE.period !== 'all') {
    const days = {'2y':730,'1y':365,'6m':182,'3m':91,'1m':30}[STATE.period];
    c.push(`date >= (SELECT strftime(MAX(date)::DATE - INTERVAL '${days} days','%Y-%m-%d') FROM ${view()})`);
  }
  return c.length ? 'WHERE ' + c.join(' AND ') : '';
}

async function boot() {
  MANIFEST = await (await fetch('data/manifest.json')).json();
  await ensureLoaded(STATE.pairing);
  wireControls();      // attach change handlers that call render()
  render();
}
async function render() {
  await ensureLoaded(STATE.pairing);
  if (STATE.tab === 'overview')  await renderOverview();
  else if (STATE.tab === 'edge') await renderEdge();
  else if (STATE.tab === 'risk') await renderRisk();
  else if (STATE.tab === 'excursion') await renderExcursion();
  else if (STATE.tab === 'trades') await renderTrades();
}
boot();
```

- [ ] **Step 2: Verify it loads in a browser**

Run a static server from the repo root and open the page:
`cd "/Users/abhi/Projects/Statistic.ally" && python3 -m http.server 8001` then visit `http://localhost:8001/Nested%20FVG/dashboard.html`.
Expected: page renders the shell, no console errors, parquet for `1m_5m` loads (check Network tab + `await window.query('SELECT COUNT(*) FROM t_1m_5m')` in console returns a number).

- [ ] **Step 3: Commit**

```bash
git add "Nested FVG/dashboard.html"
git commit -m "feat(nested-fvg): dashboard shell — loader, manifest, nav state"
```

---

### Task 11: Overview tab (hero tiles, outcome split, pairings compare, filter grid)

**Files:**
- Modify: `Nested FVG/dashboard.html`

- [ ] **Step 1: Implement renderOverview()**

Add an inline `renderOverview()` that runs these queries against `view()` + `whereClause()` and paints HTML/CSS tiles + bars (mirror NPG's overview):

```javascript
async function renderOverview() {
  const w = whereClause();
  const [agg] = await window.query(`
    SELECT COUNT(*) AS n,
      100.0*SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END)
        /NULLIF(SUM(CASE WHEN outcome IN('win','loss','scratch') THEN 1 ELSE 0 END),0) AS wr,
      AVG(CASE WHEN outcome!='expired' THEN r END) AS ev_r,
      SUM(CASE WHEN r>0 THEN r ELSE 0 END) AS pos,
      SUM(CASE WHEN r<0 THEN -r ELSE 0 END) AS neg,
      AVG(CASE WHEN outcome!='expired' THEN pnl_usd END) AS avg_usd
    FROM ${view()} ${w}`);
  const pf = agg.neg ? (agg.pos/agg.neg) : 0;
  // paint tiles: n, wr%, ev_r, pf, avg_usd

  const split = await window.query(`
    SELECT outcome, COUNT(*) AS n FROM ${view()} ${w} GROUP BY outcome`);
  // paint win/loss/scratch/expired bars

  // 3 pairings side-by-side (load each, query agg) — use MANIFEST agg for speed
  // SMT x direction grid:
  const grid = await window.query(`
    SELECT direction, smt, COUNT(*) AS n,
      AVG(CASE WHEN outcome!='expired' THEN r END) AS ev_r
    FROM ${view()} ${w} GROUP BY direction, smt ORDER BY direction, smt`);
  // paint 2x2 grid
}
```

- [ ] **Step 2: Verify in browser**

Reload the page. Expected: Overview tab shows non-zero tiles for `1m_5m` NQ; toggling direction/session/smt/period updates the numbers; outcome split bars sum to N.

- [ ] **Step 3: Commit**

```bash
git add "Nested FVG/dashboard.html"
git commit -m "feat(nested-fvg): overview tab with filter-impact grid"
```

---

### Task 12: Edge + Risk tabs

**Files:**
- Modify: `Nested FVG/dashboard.html`

- [ ] **Step 1: Implement renderEdge()**

```javascript
async function renderEdge() {
  const w = whereClause();
  const byHour = await window.query(`
    SELECT hour, COUNT(*) n, AVG(CASE WHEN outcome!='expired' THEN r END) ev
    FROM ${view()} ${w} GROUP BY hour ORDER BY hour`);
  const byDow = await window.query(`
    SELECT dow, COUNT(*) n, AVG(CASE WHEN outcome!='expired' THEN r END) ev
    FROM ${view()} ${w} GROUP BY dow ORDER BY dow`);   // dow 0=Sun
  const bySess = await window.query(`
    SELECT session, COUNT(*) n,
      100.0*SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END)
        /NULLIF(SUM(CASE WHEN outcome IN('win','loss','scratch') THEN 1 ELSE 0 END),0) wr,
      AVG(CASE WHEN outcome!='expired' THEN r END) ev
    FROM ${view()} ${w} GROUP BY session`);
  const heat = await window.query(`
    SELECT hour, dow, AVG(CASE WHEN outcome!='expired' THEN r END) ev, COUNT(*) n
    FROM ${view()} ${w} GROUP BY hour, dow`);
  // paint bar tables + CSS-grid heatmap (green/red by ev), dow label map Sun..Sat
}
```

- [ ] **Step 2: Implement renderRisk()**

```javascript
async function renderRisk() {
  const w = whereClause();
  const seq = await window.query(`
    SELECT r FROM ${view()} ${w} WHERE outcome!='expired' ORDER BY entry_ts_ns`);
  // cumulative-sum R -> SVG polyline equity curve
  // compute running max -> drawdown SVG (red area)
  // PF + longest win/loss streak from the same ordered array
}
```

- [ ] **Step 3: Verify in browser**

Reload, click Edge then Risk. Expected: hour/dow/session tables populate, heatmap colors by EV, equity curve draws an SVG polyline, drawdown panel renders.

- [ ] **Step 4: Commit**

```bash
git add "Nested FVG/dashboard.html"
git commit -m "feat(nested-fvg): edge and risk tabs"
```

---

### Task 13: Excursion + Trades tabs

**Files:**
- Modify: `Nested FVG/dashboard.html`

- [ ] **Step 1: Implement renderExcursion()**

```javascript
async function renderExcursion() {
  const w = whereClause();
  const reach = await window.query(`
    SELECT
      100.0*AVG(CASE WHEN mfe_pts>=15 THEN 1 ELSE 0 END) AS r15,
      100.0*AVG(CASE WHEN mfe_pts>=45 THEN 1 ELSE 0 END) AS r45,
      100.0*AVG(CASE WHEN reached_ext THEN 1 ELSE 0 END) AS r60
    FROM ${view()} ${w}`);
  const dist = await window.query(`
    SELECT
      AVG(mae_pts) AS avg_mae, MAX(mae_pts) AS max_mae,
      AVG(mfe_pts) AS avg_mfe, MAX(mfe_pts) AS max_mfe,
      AVG(CASE WHEN outcome='win' THEN mae_pts END) AS heat_before_win
    FROM ${view()} ${w}`);
  // paint reach-rate bars (15/45/60) + MAE/MFE summary table
}
```

- [ ] **Step 2: Implement renderTrades() with pagination**

```javascript
let tradesPage = 0;
async function renderTrades() {
  const w = whereClause();
  const pageSize = 25;
  const rows = await window.query(`
    SELECT date, hour, minute, instrument, direction,
           ROUND(entry_price,2) entry, ROUND(stop_price,2) stop,
           ROUND(target_price,2) target, outcome, ROUND(r,2) r, ROUND(pnl_usd,1) usd
    FROM ${view()} ${w}
    ORDER BY entry_ts_ns DESC
    LIMIT ${pageSize} OFFSET ${tradesPage*pageSize}`);
  // paint table; prev/next buttons adjust tradesPage and re-render
}
```

- [ ] **Step 3: Verify in browser**

Reload, click Excursion then Trades. Expected: reach-rate bars (15/45/60pt), MAE/MFE table; trades table shows recent-first rows with pagination; outcome cells colored.

- [ ] **Step 4: Commit**

```bash
git add "Nested FVG/dashboard.html"
git commit -m "feat(nested-fvg): excursion and trades tabs"
```

---

### Task 14: CLAUDE.md (folder notes + intentional Pine divergences)

**Files:**
- Create: `Nested FVG/CLAUDE.md`

- [ ] **Step 1: Write the folder doc**

```markdown
# Nested FVG

Backtest for the `Kelli/nested-fvg.pine` indicator: a 1-min FVG nested inside a
same-direction higher-timeframe FVG, during the Globex session, with fixed-point
risk. Reads the shared `../Fractal Sweep/candle_science.duckdb` (read-only).
Parquet-native / DuckDB-WASM (no server endpoints).

## Stack
Python 3.14 · DuckDB 1.4.4 · numpy · pyarrow · pytest. Browser: DuckDB-WASM 1.29.0
via `../Analysis/dashboard/shared.js`.

## Run
```bash
python3 engine/build_stats.py                 # all 3 pairings, NQ + ES, SMT on
python3 engine/build_stats.py --pairings 1m_5m --no-smt
python3 -m pytest tests/ -q
```
Dashboard: serve repo root (`python3 server.py` or `python3 -m http.server 8001`)
and open `Nested FVG/dashboard.html`.

## TF pairs
1m_5m, 3m_15m, 5m_30m (LTF gap nested in HTF gap).

## Intentional divergences from the Pine (backtest != raw indicator)
- Entry = OPEN of the next bar after the nested FVG forms (Pine assumes immediate
  fill at the gap edge).
- Partial is a REAL 50% scale-out at +15pt; runner to +45 or stop. (Pine flags a
  partial but keeps full size.) Blended P&L: pure target=+30pts, pure stop=-15,
  partial-then-stop=0 (scratch).
- Session recast to NY: full Globex 18:00->16:00 ET. Expiry force-closes at 16:00 ET.
- Outcomes: win/loss/scratch/expired. WR = win/(win+loss+scratch); expired excluded.
- HTF mitigation: gap dies on close-through far edge (matches Pine).

## Outputs
`data/trades_<pair>.parquet` (gitignored) + `data/manifest.json` (committed, slim
aggregates only). See `docs/superpowers/specs/2026-06-01-nested-fvg-backtest-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add "Nested FVG/CLAUDE.md"
git commit -m "docs(nested-fvg): folder CLAUDE.md with Pine divergences"
```

---

### Task 15: Hub registration (ASK FIRST — shared file)

**Files:**
- Modify: `index.html` (repo root)

> **GATE:** `index.html` is the shared hub. Before editing, confirm with the user. Do NOT touch `.claude/rules/*` (user maintains by hand).

- [ ] **Step 1: Add a PROJECTS entry**

In `index.html`, append to the `PROJECTS` array:
```javascript
{
  id:'nested-fvg', title:'Nested FVG',
  subtitle:'1-min FVG nested in HTF FVG · 3 pairings',
  desc:'Multi-timeframe nested fair-value-gap setups, fixed-point R/R, Globex session.',
  json:'Nested FVG/data/manifest.json',
  link:'Nested FVG/dashboard.html',
  color:'#06b6d4', icon:'◎', type:'nested-fvg', stats:null,
},
```

- [ ] **Step 2: Add a loadStats() block**

In `index.html`'s `loadStats()`, add a branch keyed on `project.type === 'nested-fvg'` that reads the best pairing's `agg` from the manifest and returns headline tiles:
```javascript
if (project.type === 'nested-fvg') {
  const ps = d.pairings || {};
  // pick pairing with highest n
  let best=null;
  for (const k in ps) if (!best || ps[k].n_trades > ps[best].n_trades) best=k;
  if (!best) return null;
  const a = ps[best].agg || {};
  return {
    label1:'Setups', val1:String(a.n||0), cls1:'neutral',
    label2:'Win rate', val2:(a.wr||0).toFixed(1)+'%', cls2:'pos',
    label3:'EV (R)', val3:(a.ev_r>=0?'+':'')+(a.ev_r||0).toFixed(3),
    cls3:(a.ev_r||0)>0?'pos':'neg',
    dateRange:(d.date_range_start||'—')+' → '+(d.date_range_end||'—'),
  };
}
```

- [ ] **Step 3: Verify in browser**

Reload `http://localhost:8001/index.html`. Expected: a "Nested FVG" card appears with the ◎ icon, cyan accent, and headline tiles populated from the manifest; clicking it opens the dashboard.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(nested-fvg): register dashboard on hub page"
```

---

### Task 16: Final verification + full suite

- [ ] **Step 1: Run the full test suite**

Run: `cd "Nested FVG" && python3 -m pytest tests/ -v`
Expected: all PASS (smoke may SKIP if DB absent).

- [ ] **Step 2: Rebuild from scratch and eyeball the manifest**

Run: `cd "Nested FVG" && python3 engine/build_stats.py && cat data/manifest.json`
Expected: 3 pairings, plausible trade counts, WR/EV/PF present, date range spans the DB history.

- [ ] **Step 3: Full dashboard walkthrough**

Serve repo root, open the dashboard, and exercise: each pairing, NQ↔ES, every filter, every period, all 5 tabs. Confirm no console errors and numbers move sensibly with filters.

- [ ] **Step 4: Final commit if any tweaks**

```bash
git add -A "Nested FVG"
git commit -m "chore(nested-fvg): final verification pass"
```

---

## Self-Review Notes

- **Spec coverage:** detection (T2-4), mitigation (T3), nesting+proximity (T4), next-bar entry (T8), 50% scale-out + outcomes + expiry (T5), $/R/pts (T5-6), SMT (T8), per-pair parquet + slim manifest (T7-8), 5 tabs incl. folded filter grid (T11-13), hub (T15), CLAUDE.md divergences (T14), tests + Pine-cross-check note (T16/T14). All spec sections map to tasks.
- **Schema:** the 30th column `minute_of_hour` duplicates `minute` to (a) reserve a clearly-named field for the later :42 timing study and (b) lock a round column count the test asserts. If undesired, drop both it and the `== 30` assertion.
- **Known approximation:** `_smt_at` is a deliberately simple NQ-ES divergence proxy (ES failed to confirm direction over 2 bars). Flagged in code + CLAUDE.md; can be sharpened later without schema change.
- **DOW convention:** engine writes DuckDB 0=Sun (`(weekday()+1)%7`); dashboard labels Sun..Sat accordingly.
```
