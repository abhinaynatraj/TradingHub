"""Shared test helpers for synthetic OHLC arrays."""
import numpy as np

NS_PER_MIN = np.int64(60_000_000_000)
BASE_TS = np.int64(1_700_000_000_000_000_000)


def make_htf_arrs(candle_data, tf_min=60, start_ts=None):
    """Build HTF (sweep-TF) arrays from list of (open, high, low, close) tuples.

    All candles are spaced `tf_min` minutes apart starting from `start_ts` or BASE_TS.
    Hours/days populate as if starting at 09:00 ET on a single trading day.
    """
    n = len(candle_data)
    ts = start_ts or BASE_TS
    step = NS_PER_MIN * tf_min
    ts_ns = np.array([ts + i * step for i in range(n)], dtype='int64')
    opens = np.array([c[0] for c in candle_data], dtype='float64')
    highs = np.array([c[1] for c in candle_data], dtype='float64')
    lows = np.array([c[2] for c in candle_data], dtype='float64')
    closes = np.array([c[3] for c in candle_data], dtype='float64')
    hrs = np.array([(9 + (i * tf_min // 60)) % 24 for i in range(n)], dtype='int32')
    dows = np.full(n, 2, dtype='int32')  # Tuesday
    yrs = np.full(n, 2023, dtype='int32')
    trade_dates = np.array(['2023-11-14'] * n)
    return dict(ts_ns=ts_ns, open=opens, high=highs, low=lows, close=closes,
                hr=hrs, dow=dows, yr=yrs, trade_date=trade_dates)


def make_ltf_arrs(bars_data, tf_min=5, start_ts=None):
    """Build LTF (CISD-TF) arrays from (open, high, low, close) tuples."""
    n = len(bars_data)
    ts = start_ts or BASE_TS
    step = NS_PER_MIN * tf_min
    ts_ns = np.array([ts + i * step for i in range(n)], dtype='int64')
    opens = np.array([b[0] for b in bars_data], dtype='float64')
    highs = np.array([b[1] for b in bars_data], dtype='float64')
    lows = np.array([b[2] for b in bars_data], dtype='float64')
    closes = np.array([b[3] for b in bars_data], dtype='float64')
    return dict(ts_ns=ts_ns, open=opens, high=highs, low=lows, close=closes)


def make_oc_arrs(bars_data, tf_min=5):
    """Minimal (open, close) arrays for CISD unit tests. Highs/lows derived."""
    n = len(bars_data)
    ts_ns = np.array([BASE_TS + i * NS_PER_MIN * tf_min for i in range(n)], dtype='int64')
    opens = np.array([b[0] for b in bars_data], dtype='float64')
    closes = np.array([b[1] for b in bars_data], dtype='float64')
    highs = np.maximum(opens, closes) + 1.0
    lows = np.minimum(opens, closes) - 1.0
    return dict(ts_ns=ts_ns, open=opens, high=highs, low=lows, close=closes)
