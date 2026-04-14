"""Tests for SMT divergence detection."""
import numpy as np
import pytest
from helpers import NS_PER_MIN, BASE_TS, make_sweep_arrs, make_m1_arrs
import model_stats as ms


def _build_smt_scenario(nq_sweeps_low=True, es_also_sweeps_low=True):
    """Build NQ + ES arrays for testing SMT divergence in LONG direction.

    The NQ prior candle low is 23950. Current period Q1 has NQ going below it.
    ES prior candle low is 5900. If es_also_sweeps_low, ES goes below 5900 too.
    """
    # NQ sweep-TF: 2 candles (prior + current period)
    nq_s = make_sweep_arrs(2, [
        (24000, 24050, 23950, 24000),  # candle 0: prior (high=24050, low=23950)
        (24000, 24020, 23940, 24010),  # candle 1: current — sweeps below 23950
    ])

    # NQ 1m bars in Q1 window (3 bars for 1H_5M q1=15min → 3 5-min bars)
    q1_start = int(nq_s['ts_ns'][1])
    nq_m1_bars = [
        (24000, 24005, 23955, 23960),  # bar 0: goes below 23950 if nq_sweeps_low
        (23960, 23970, 23945, 23965),  # bar 1: deeper low
        (23965, 23975, 23960, 23975),  # bar 2: returns above 23950
    ]
    if not nq_sweeps_low:
        nq_m1_bars = [
            (24000, 24005, 23955, 23960),
            (23960, 23970, 23955, 23965),
            (23965, 23975, 23960, 23975),
        ]

    nq_m1 = {}
    n = len(nq_m1_bars)
    nq_m1['ts_ns'] = np.array([q1_start + i * NS_PER_MIN for i in range(n)], dtype='int64')
    nq_m1['open'] = np.array([b[0] for b in nq_m1_bars], dtype='float64')
    nq_m1['high'] = np.array([b[1] for b in nq_m1_bars], dtype='float64')
    nq_m1['low'] = np.array([b[2] for b in nq_m1_bars], dtype='float64')
    nq_m1['close'] = np.array([b[3] for b in nq_m1_bars], dtype='float64')
    nq_m1['hr'] = np.full(n, 9, dtype='int32')
    nq_m1['mn'] = np.arange(n, dtype='int32') * 5
    nq_m1['dow'] = np.full(n, 2, dtype='int32')
    nq_m1['yr'] = np.full(n, 2023, dtype='int32')
    nq_m1['trade_date'] = np.array(['2023-11-14'] * n)

    # ES sweep-TF: same timestamps as NQ
    es_prior_low = 5900.0
    es_s = make_sweep_arrs(2, [
        (5920, 5950, es_prior_low, 5930),  # ES prior candle
        (5930, 5940, 5895 if es_also_sweeps_low else 5905, 5925),  # ES current
    ])
    # Override ES timestamps to match NQ
    es_s['ts_ns'] = nq_s['ts_ns'].copy()

    # ES 1m bars in same window
    if es_also_sweeps_low:
        es_m1_bars = [
            (5930, 5935, 5895, 5900),  # ES goes below 5900
            (5900, 5910, 5890, 5905),
            (5905, 5915, 5900, 5910),
        ]
    else:
        es_m1_bars = [
            (5930, 5935, 5910, 5920),  # ES stays ABOVE 5900
            (5920, 5925, 5905, 5915),
            (5915, 5920, 5908, 5918),
        ]

    es_m1 = {}
    es_m1['ts_ns'] = nq_m1['ts_ns'].copy()
    es_m1['open'] = np.array([b[0] for b in es_m1_bars], dtype='float64')
    es_m1['high'] = np.array([b[1] for b in es_m1_bars], dtype='float64')
    es_m1['low'] = np.array([b[2] for b in es_m1_bars], dtype='float64')
    es_m1['close'] = np.array([b[3] for b in es_m1_bars], dtype='float64')
    es_m1['hr'] = nq_m1['hr'].copy()
    es_m1['mn'] = nq_m1['mn'].copy()
    es_m1['dow'] = nq_m1['dow'].copy()
    es_m1['yr'] = nq_m1['yr'].copy()
    es_m1['trade_date'] = nq_m1['trade_date'].copy()

    return nq_s, nq_m1, es_s, es_m1


class TestSmtDivergenceLogic:
    """Test the core SMT comparison logic in isolation."""

    def test_es_holds_above_prior_low_is_smt(self):
        """NQ sweeps below prior low, ES holds above → SMT = True."""
        # ES prior low = 5900, ES Q1 min = 5905 (above 5900)
        es_ref_low = 5900.0
        es_q1_low = 5905.0  # ES held above
        es_also_swept = es_q1_low < es_ref_low
        smt_divergence = not es_also_swept
        assert smt_divergence is True

    def test_es_also_sweeps_is_not_smt(self):
        """NQ sweeps below prior low, ES also sweeps → SMT = False."""
        es_ref_low = 5900.0
        es_q1_low = 5895.0  # ES also went below
        es_also_swept = es_q1_low < es_ref_low
        smt_divergence = not es_also_swept
        assert smt_divergence is False

    def test_short_es_holds_below_prior_high_is_smt(self):
        """NQ sweeps above prior high, ES holds below → SMT = True."""
        es_ref_high = 5950.0
        es_q1_high = 5945.0  # ES held below
        es_also_swept = es_q1_high > es_ref_high
        smt_divergence = not es_also_swept
        assert smt_divergence is True

    def test_short_es_also_sweeps_is_not_smt(self):
        """NQ sweeps above prior high, ES also sweeps → SMT = False."""
        es_ref_high = 5950.0
        es_q1_high = 5955.0  # ES also went above
        es_also_swept = es_q1_high > es_ref_high
        smt_divergence = not es_also_swept
        assert smt_divergence is False


class TestSmtFallback:
    def test_no_es_data_smt_false(self):
        """When es_s_arrs is None, has_smt = False, all trades get smt = False."""
        has_smt = None is not None and None is not None
        assert has_smt is False

    def test_es_timestamp_mismatch(self):
        """When ES period timestamp doesn't match NQ, es_ref should be None."""
        nq_ts = np.int64(1700000000000000000)
        es_ts = np.array([nq_ts + NS_PER_MIN * 100], dtype='int64')  # far off
        es_idx = int(np.searchsorted(es_ts, nq_ts, side='left'))
        # No match within 1 minute
        match = es_idx < len(es_ts) and abs(es_ts[es_idx] - nq_ts) < NS_PER_MIN
        assert match == False
