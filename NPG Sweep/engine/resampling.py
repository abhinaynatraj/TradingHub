"""Resample 1-minute OHLC to higher timeframes using bucket alignment.

Buckets are anchored to UTC midnight (matching pandas resample default).
For non-divisor timeframes (e.g. 4H from 1m), bars are grouped by floor(ts / tf_ns).
"""
import numpy as np

NS_PER_MIN = np.int64(60_000_000_000)


def resample(m1, tf_min):
    """Group 1m bars into tf_min buckets and emit OHLC per bucket.

    Args:
        m1: dict with ts_ns/open/high/low/close arrays
        tf_min: target timeframe in minutes

    Returns:
        dict(ts_ns, open, high, low, close, n_bars_per_bucket) — one entry per bucket.
        ts_ns of bucket = the start (first bar's ts) of that bucket.
    """
    ts = m1['ts_ns'].astype('int64')
    o, h, l, c = m1['open'], m1['high'], m1['low'], m1['close']
    bucket_ns = NS_PER_MIN * np.int64(tf_min)
    bucket_id = ts // bucket_ns

    # Find bucket boundaries
    change_idx = np.concatenate(([0], np.where(np.diff(bucket_id) != 0)[0] + 1, [len(ts)]))
    n_buckets = len(change_idx) - 1

    bucket_ts = np.zeros(n_buckets, dtype='int64')
    bucket_o = np.zeros(n_buckets, dtype='float64')
    bucket_h = np.zeros(n_buckets, dtype='float64')
    bucket_l = np.zeros(n_buckets, dtype='float64')
    bucket_c = np.zeros(n_buckets, dtype='float64')
    bucket_n = np.zeros(n_buckets, dtype='int32')

    for i in range(n_buckets):
        s, e = change_idx[i], change_idx[i+1]
        bucket_ts[i] = ts[s]
        bucket_o[i] = o[s]
        bucket_h[i] = h[s:e].max()
        bucket_l[i] = l[s:e].min()
        bucket_c[i] = c[e-1]
        bucket_n[i] = e - s

    # Bucket close ts = next bucket's open, or estimated end of bucket for the last one
    bucket_close_ts = np.concatenate([bucket_ts[1:], [bucket_ts[-1] + bucket_ns]]).astype('int64')

    return dict(
        ts_ns=bucket_ts,
        ts_close_ns=bucket_close_ts,
        open=bucket_o,
        high=bucket_h,
        low=bucket_l,
        close=bucket_c,
        n_bars=bucket_n,
    )
