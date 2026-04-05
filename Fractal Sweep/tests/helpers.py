"""Shared test helpers and constants."""
import sys, os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

NS_PER_MIN = np.int64(60_000_000_000)
BASE_TS = np.int64(1_700_000_000_000_000_000)


def make_m1_arrs(n_bars, start_price=24000.0, trend=0.0, volatility=5.0,
                 start_hr=9, start_ts=None):
    rng = np.random.RandomState(42)
    ts = start_ts or BASE_TS
    ts_ns = np.array([ts + i * NS_PER_MIN for i in range(n_bars)], dtype='int64')
    opens = np.zeros(n_bars, dtype='float64')
    highs = np.zeros(n_bars, dtype='float64')
    lows = np.zeros(n_bars, dtype='float64')
    closes = np.zeros(n_bars, dtype='float64')
    hrs = np.zeros(n_bars, dtype='int32')
    mns = np.zeros(n_bars, dtype='int32')
    dows = np.zeros(n_bars, dtype='int32')
    yrs = np.full(n_bars, 2023, dtype='int32')
    price = start_price
    for i in range(n_bars):
        o = price
        noise = rng.uniform(-volatility, volatility)
        c = o + trend + noise
        h = max(o, c) + abs(rng.uniform(0, volatility * 0.3))
        l = min(o, c) - abs(rng.uniform(0, volatility * 0.3))
        opens[i] = round(o, 2)
        highs[i] = round(h, 2)
        lows[i] = round(l, 2)
        closes[i] = round(c, 2)
        hr = start_hr + (i // 60)
        hrs[i] = min(hr, 16)
        mns[i] = i % 60
        dows[i] = 2
        price = c
    trade_dates = np.array(['2023-11-14'] * n_bars)
    return dict(ts_ns=ts_ns, open=opens, high=highs, low=lows, close=closes,
                hr=hrs, mn=mns, dow=dows, yr=yrs, trade_date=trade_dates)


def make_controlled_m1(bars_data, start_ts=None):
    ts = start_ts or BASE_TS
    n = len(bars_data)
    ts_ns = np.array([ts + i * NS_PER_MIN for i in range(n)], dtype='int64')
    opens = np.array([b[0] for b in bars_data], dtype='float64')
    highs = np.array([b[1] for b in bars_data], dtype='float64')
    lows = np.array([b[2] for b in bars_data], dtype='float64')
    closes = np.array([b[3] for b in bars_data], dtype='float64')
    hrs = np.full(n, 9, dtype='int32')
    mns = np.arange(n, dtype='int32') % 60
    dows = np.full(n, 2, dtype='int32')
    yrs = np.full(n, 2023, dtype='int32')
    trade_dates = np.array(['2023-11-14'] * n)
    return dict(ts_ns=ts_ns, open=opens, high=highs, low=lows, close=closes,
                hr=hrs, mn=mns, dow=dows, yr=yrs, trade_date=trade_dates)


def make_sweep_arrs(n_candles, candle_data):
    ts_step = NS_PER_MIN * 60
    ts_ns = np.array([BASE_TS + i * ts_step for i in range(n_candles)], dtype='int64')
    opens = np.array([c[0] for c in candle_data], dtype='float64')
    highs = np.array([c[1] for c in candle_data], dtype='float64')
    lows = np.array([c[2] for c in candle_data], dtype='float64')
    closes = np.array([c[3] for c in candle_data], dtype='float64')
    hrs = np.arange(n_candles, dtype='int32') + 9
    dows = np.full(n_candles, 2, dtype='int32')
    yrs = np.full(n_candles, 2023, dtype='int32')
    trade_dates = np.array(['2023-11-14'] * n_candles)
    return dict(ts_ns=ts_ns, open=opens, high=highs, low=lows, close=closes,
                hr=hrs, dow=dows, yr=yrs, trade_date=trade_dates)
