"""End-to-end integration test on synthetic 1m data.

Builds a small in-memory dataset with one designed Wick Lick + CISD setup,
runs the orchestrator, and asserts the trade row + aggregation appear in output.
"""
import numpy as np
import pytest
from helpers import NS_PER_MIN, BASE_TS
import npg_stats as ns


# Bucket-align BASE_TS to a 60-min boundary so 120 bars form exactly 2 HTF candles
HOUR_NS = np.int64(60 * 60_000_000_000)
START_TS = np.int64((int(BASE_TS) // int(HOUR_NS)) * int(HOUR_NS))


def _make_synthetic_1m_with_setup():
    """120 minutes of NQ 1m data containing exactly one bearish Wick Lick + CISD.

    Layout (using 60-min HTF, 5m CISD-TF):
      Bars 0-59: prior HTF candle, range [24000, 24050]
      Bars 60-119: sweep HTF candle - sweeps 24050 to 24070, closes well below 24050

    5m structure within sweep candle (24 bars 60-119 → 12 5m bars indexed 12-23):
      5m bars 12-13: bullish run (closes 24040, 24055)
      5m bar 14 (bars 70-74): sweep bucket, bullish close - poke high 24070,
          recovery close at 24056 (above body high of bar 13 -> CISD-relevant)
      5m bar 15 (bars 75-79): brief continuation up - closes 24062 (>series_high
          of 24060 from bar 14's body) -> CISD FIRES here
      5m bar 16 (bars 80-84): entry bucket - opens 24062
      5m bars 17-23: crash down to ~23985 -> hits all short targets

    cisd_npg fire rule for SHORT (per existing module): bullish series is broken
    when forward close > series_high. Entry on bar 16 open = 24062.
    SL = sweep_extreme = 24070. Risk = 8pts. Targets are series_range * mult below
    entry, so price falling far below 24062 hits all targets - composite_r > 0.
    """
    n = 120
    ts_ns = np.array([START_TS + i * NS_PER_MIN for i in range(n)], dtype='int64')
    o = np.zeros(n)
    h = np.zeros(n)
    l = np.zeros(n)
    c = np.zeros(n)

    # Prior HTF candle (bars 0-59): tight range, high=24050, low=24000
    for i in range(60):
        o[i] = 24025
        c[i] = 24025
        h[i] = 24050 if i == 30 else 24030  # high printed at bar 30
        l[i] = 24000 if i == 45 else 24020

    # 5m bars 12-13 (1m bars 60-69): bullish run building toward sweep
    # 5m bar 12 (bars 60-64): open 24025 -> close 24040 (bullish, body high 24040)
    for i in range(60, 65):
        o[i] = 24025 + (i - 60) * 3
        c[i] = o[i] + 3
        h[i] = c[i] + 1
        l[i] = o[i] - 1
    # 5m bar 13 (bars 65-69): open 24040 -> close 24055 (bullish, body high 24055)
    for i in range(65, 70):
        o[i] = 24040 + (i - 65) * 3
        c[i] = o[i] + 3
        h[i] = c[i] + 1
        l[i] = o[i] - 1

    # 5m bar 14 (bars 70-74): the sweep bucket, MUST close bullish so it joins the
    # CISD series. Open=24050 (from bar 70). Bar 70 pokes high to 24070 then closes
    # back to 24050. Bars 71-74 drift up to close at 24056 -> bucket close = 24056.
    o[70] = 24050
    h[70] = 24070
    l[70] = 24050
    c[70] = 24050
    # bars 71-74 drift up
    for k, i in enumerate(range(71, 75)):
        o[i] = 24050 + k * 1.5
        c[i] = o[i] + 1.5
        h[i] = c[i] + 0.5
        l[i] = o[i] - 0.5
    # 5m bar 14 effective: open=24050, high=24070, low=24049.5, close=24056
    # body high = 24056. So series_high (across body of bars 12,13,14) = 24056.

    # 5m bar 15 (bars 75-79): brief continuation up that BREAKS series_high
    # bucket needs close > 24056 to fire CISD
    for k, i in enumerate(range(75, 80)):
        o[i] = 24056 + k * 1.0
        c[i] = o[i] + 1.0
        h[i] = c[i] + 0.5
        l[i] = o[i] - 0.5
    # 5m bar 15: open=24056, close=24061 (last bar = bar 79: c=24061+1=close of bar 79)
    # Actually bar 79: o=24056+4=24060, c=24061. So bucket close = 24061 > 24056. FIRES.

    # 5m bar 16 (bars 80-84): entry bucket. Open of bar 80 = 24061 (continuation).
    # Then immediately reverse and crash. Entry will be at open of bar 80.
    o[80] = 24061
    h[80] = 24061.5
    l[80] = 24050
    c[80] = 24050
    for k, i in enumerate(range(81, 85)):
        o[i] = 24050 - k * 2.5
        c[i] = o[i] - 2.5
        h[i] = o[i] + 0.5
        l[i] = c[i] - 0.5

    # 5m bars 17-23 (bars 85-119): crash downward to ~23985
    for i in range(85, n):
        base = 24040 - (i - 85) * 1.5
        o[i] = base
        c[i] = base - 1.5
        h[i] = o[i] + 0.5
        l[i] = c[i] - 0.5

    return dict(ts_ns=ts_ns, open=o, high=h, low=l, close=c)


def test_orchestrator_finds_one_bearish_setup():
    m1 = _make_synthetic_1m_with_setup()

    # Minimal orchestrator entrypoint for testing: just detect + resolve
    result = ns.run_pairing(m1, sweep_tf_min=60, cisd_tf_min=5,
                            profile='series_multi', body_confirm=True,
                            multipliers=[0.5, 1.0, 1.5, 2.0])
    rows = result['trades']
    # Expect exactly one bearish setup
    assert len(rows) == 1
    r = rows[0]
    assert r['direction'] == 'SHORT'
    assert r['sweep_extreme'] == 24070.0
    # Composite R should be positive (price ran down through targets)
    assert r['composite_r'] > 0
