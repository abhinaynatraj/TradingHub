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
