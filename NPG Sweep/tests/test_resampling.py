"""Tests for resampling 1m bars to higher timeframes."""
import numpy as np
import pytest
from helpers import NS_PER_MIN, BASE_TS
import resampling as r

# BASE_TS = 1_700_000_000_000_000_000 is NOT 60-minute bucket-aligned.
# bucket_ns for 60m = 3_600_000_000_000; BASE_TS % bucket_ns == 800_000_000_000.
# That means 60 contiguous 1m bars starting at BASE_TS cross a bucket boundary
# and produce 2 HTF candles instead of 1.
#
# Fix: align the test start_ts to the nearest prior 60m bucket edge:
#   START_TS = (BASE_TS // bucket_ns) * bucket_ns = 1_699_999_200_000_000_000
# This is bucket-aligned so 60 bars fit inside one 60m bucket, and 120 bars
# produce exactly 2 buckets — matching the test assertions.
_BUCKET_NS = NS_PER_MIN * np.int64(60)
START_TS = (BASE_TS // _BUCKET_NS) * _BUCKET_NS   # 1_699_999_200_000_000_000


class TestResample1mTo60m:
    def test_60_one_minute_bars_become_one_hour_candle(self):
        # 60 bars of 1-minute data, all from 09:00–09:59
        # Open of first, close of last, max high, min low
        n = 60
        ts_ns = np.array([START_TS + i * NS_PER_MIN for i in range(n)], dtype='int64')
        # Make a clear pattern: open=100, close walks up to 160, high=close+1, low=open-1
        opens = np.arange(100, 100 + n, dtype='float64')
        closes = opens + 1
        highs = closes + 1
        lows = opens - 1
        m1 = dict(ts_ns=ts_ns, open=opens, high=highs, low=lows, close=closes)

        htf = r.resample(m1, tf_min=60)
        assert len(htf['open']) == 1
        assert htf['open'][0] == 100.0
        assert htf['close'][0] == closes[-1]   # 160
        assert htf['high'][0] == highs.max()
        assert htf['low'][0] == lows.min()

    def test_120_one_minute_bars_become_two_hour_candles(self):
        n = 120
        ts_ns = np.array([START_TS + i * NS_PER_MIN for i in range(n)], dtype='int64')
        opens = np.full(n, 100.0)
        closes = np.full(n, 100.0)
        highs = np.full(n, 101.0)
        lows = np.full(n, 99.0)
        m1 = dict(ts_ns=ts_ns, open=opens, high=highs, low=lows, close=closes)

        htf = r.resample(m1, tf_min=60)
        assert len(htf['open']) == 2
