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
