"""Tests asserting the shape of trade rows emitted by run_pairing post-Phase 2.

Phase 2 adds entry_ts_ns to every trade row (needed for parquet equity-curve
sort) and drops the now-unused fields targets/hit_ts_ns/sweep_ts_ns/risk_pts/
body_cisd/series_count.
"""
import numpy as np
import pytest
from helpers import NS_PER_MIN, BASE_TS
import npg_stats as ns


EXPECTED_TRADE_KEYS = {
    'direction', 'composite_r', 'hits', 'silver', 'smt',
    'hour', 'dow', 'mae_pts', 'mfe_pts',
    'entry_price', 'sl_price', 'series_range', 'sweep_extreme',
    'sl_hit', 'entry_ts_ns',
}

FORBIDDEN_TRADE_KEYS = {
    'targets', 'hit_ts_ns', 'sweep_ts_ns', 'risk_pts', 'body_cisd', 'series_count',
}


def _make_synthetic_1m_with_setup():
    """Same builder as test_integration; produces exactly one bearish setup."""
    n = 120
    HOUR_NS = np.int64(60 * 60 * 1_000_000_000)
    START_TS = (BASE_TS // HOUR_NS) * HOUR_NS
    ts_ns = np.array([START_TS + i * NS_PER_MIN for i in range(n)], dtype='int64')
    o = np.zeros(n); h = np.zeros(n); l = np.zeros(n); c = np.zeros(n)
    for i in range(60):
        o[i] = 24025; c[i] = 24025
        h[i] = 24050 if i == 30 else 24030
        l[i] = 24000 if i == 45 else 24020
    for i in range(60, 70):
        o[i] = 24025 + (i - 60) * 3
        c[i] = o[i] + 3
        h[i] = c[i] + 1
        l[i] = o[i] - 1
    o[70] = 24054; h[70] = 24070; l[70] = 24008; c[70] = 24056
    for i in range(71, 75):
        o[i] = 24056 + (i - 71) * 0.5
        c[i] = o[i] + 0.5
        h[i] = c[i] + 0.5
        l[i] = o[i] - 0.5
    for i in range(75, n):
        o[i] = 24050 - (i - 75) * 1.5
        c[i] = o[i] - 1.5
        h[i] = o[i] + 0.5
        l[i] = c[i] - 0.5
    return dict(ts_ns=ts_ns, open=o, high=h, low=l, close=c)


def test_trade_rows_contain_entry_ts_ns():
    m1 = _make_synthetic_1m_with_setup()
    result = ns.run_pairing(m1, sweep_tf_min=60, cisd_tf_min=5,
                            profile='series_multi', body_confirm=True,
                            multipliers=[0.5, 1.0, 1.5, 2.0])
    rows = result['trades']
    assert len(rows) >= 1
    for r in rows:
        assert 'entry_ts_ns' in r
        assert isinstance(r['entry_ts_ns'], int)


def test_trade_rows_have_exact_expected_keys():
    m1 = _make_synthetic_1m_with_setup()
    result = ns.run_pairing(m1, sweep_tf_min=60, cisd_tf_min=5,
                            profile='series_multi', body_confirm=True,
                            multipliers=[0.5, 1.0, 1.5, 2.0])
    rows = result['trades']
    assert len(rows) >= 1
    for r in rows:
        actual = set(r.keys())
        missing = EXPECTED_TRADE_KEYS - actual
        forbidden_present = FORBIDDEN_TRADE_KEYS & actual
        assert not missing, f"missing keys: {missing}"
        assert not forbidden_present, f"forbidden keys: {forbidden_present}"
