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

from engine.simulate import pnl_to_usd

def test_pnl_to_usd_uses_point_value():
    assert pnl_to_usd(30.0, point_value_usd=2.0) == 60.0
    assert pnl_to_usd(-15.0, point_value_usd=2.0) == -30.0
    assert pnl_to_usd(0.0, point_value_usd=2.0) == 0.0


def test_long_partial_on_earlier_bar_then_target_win():
    # partial (+15 => 115) hit on bar 1, target (+45 => 145) on bar 2 (separate bars)
    m1 = _path([(101, 99), (116, 100), (146, 120)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=1,
                       session_end_idx=99,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'win'
    assert r['pnl_pts'] == 30.0
    assert r['partial_hit'] is True
    assert r['bars_held'] == 2

def test_long_partial_then_expiry_is_seven_point_five():
    # partial hit on bar 1, never targets/stops, session ends at idx 2 -> expired, +7.5
    m1 = _path([(101, 99), (116, 101), (114, 102)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=1,
                       session_end_idx=2,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'expired'
    assert r['pnl_pts'] == 7.5
    assert r['partial_hit'] is True

def test_short_partial_then_stop_is_scratch():
    # SHORT entry 100: partial=85 hit on bar1, stop=115 hit on bar2 -> scratch, 0 pts
    m1 = _path([(101, 99), (100, 84), (116, 110)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=-1,
                       session_end_idx=99,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'scratch'
    assert r['pnl_pts'] == 0.0
    assert r['partial_hit'] is True

def test_short_pure_stop_loss():
    # SHORT entry 100, stop=115 hit before partial=85 -> loss, -15
    m1 = _path([(101, 99), (120, 100)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=-1,
                       session_end_idx=99,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'loss'
    assert r['pnl_pts'] == -15.0

def test_reached_ext_flag_on_win():
    # long win whose runner pushes past ext (+60 => 160) before/at target
    m1 = _path([(101, 99), (116, 100), (165, 140)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=1,
                       session_end_idx=99,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['outcome'] == 'win'
    assert r['reached_ext'] is True

def test_mae_mfe_recorded():
    # long that dips to 96 (mae=4) and peaks at 120 (mfe=20) then expires at idx 2
    m1 = _path([(101, 96), (120, 99), (118, 100)])
    r = simulate_trade(m1, entry_idx=0, entry_price=100.0, direction=1,
                       session_end_idx=2,
                       stop_pts=15, partial_pts=15, target_pts=45, ext_pts=60)
    assert r['mae_pts'] == 4.0
    assert r['mfe_pts'] == 20.0
