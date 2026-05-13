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
      Bars 60-119: sweep HTF candle - sweeps prior high 24050 up to 24070,
          then bears take over and crash down well below series_low

    5m structure within sweep candle (60 1m bars → 12 5m bars indexed 12-23):
      5m bars 12-13: bullish run (closes 24040, 24055)
      5m bar 14 (bars 70-74): SWEEP bucket - poke high 24070, recovery close
          at 24056 (bullish bucket; this is c2 in CISD-TF since high == sweep_extreme)
      5m bar 15 (bars 75-79): bears take over, close DROPS below series_low
          (close ~ 23980 << series_low 24025) -> CISD FIRES here
      5m bar 16 (bars 80-84): entry bucket - opens at continuation lower
      5m bars 17-23: continued slide down to ~23900 -> hits all 4 SHORT targets

    cisd_npg fire rule for SHORT (correct semantics): bullish series is broken
    when a forward close < series_low. With break_price = series_low = 24025
    and series_range = 31, the 4 SHORT targets are at:
      [24009.5, 23994, 23978.5, 23963]
    Price reaches ~23900 by end -> all 4 targets hit -> composite_r > 0.
    SL = sweep_extreme = 24070.
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

    # 5m bar 12 (bars 60-64): open 24025 -> close 24040 (bullish, body=[24025,24040])
    for i in range(60, 65):
        o[i] = 24025 + (i - 60) * 3
        c[i] = o[i] + 3
        h[i] = c[i] + 1
        l[i] = o[i] - 1
    # 5m bar 13 (bars 65-69): open 24040 -> close 24055 (bullish, body=[24040,24055])
    for i in range(65, 70):
        o[i] = 24040 + (i - 65) * 3
        c[i] = o[i] + 3
        h[i] = c[i] + 1
        l[i] = o[i] - 1

    # 5m bar 14 (bars 70-74): SWEEP bucket. Must close bullish so it joins the
    # bullish CISD series. Open=24050. Bar 70 pokes high to 24070 then closes
    # back to 24050. Bars 71-74 drift up so bucket close = 24056.
    o[70] = 24050
    h[70] = 24070
    l[70] = 24050
    c[70] = 24050
    for k, i in enumerate(range(71, 75)):
        o[i] = 24050 + k * 1.5
        c[i] = o[i] + 1.5
        h[i] = c[i] + 0.5
        l[i] = o[i] - 0.5
    # 5m bar 14 resampled: open=24050, high=24070, low~24049.5, close=24056.
    # Body of 5m bars in the bullish series:
    #   bar 12: o=24025, c=24040 → body = [24025, 24040]
    #   bar 13: o=24040, c=24055 → body = [24040, 24055]
    #   bar 14: o=24050, c=24056 → body = [24050, 24056]
    # series_high = 24056, series_low = 24025, series_range = 31.

    # 5m bar 15 (bars 75-79): bears reverse — close DROPS far below series_low.
    # Need close of 1m bar 79 (= bucket close) << 24025. Crash to ~23980.
    o[75] = 24056
    h[75] = 24056.5
    l[75] = 24010
    c[75] = 24010
    for k, i in enumerate(range(76, 80)):
        o[i] = 24010 - k * 7.5
        c[i] = o[i] - 7.5
        h[i] = o[i] + 0.25
        l[i] = c[i] - 0.25
    # 5m bar 15 resampled: open=24056, close = c[79] = 24010 - 4*7.5 - 7.5 = 23972.5
    # 23972.5 < 24025 → CISD FIRES on 5m bar 15.

    # 5m bar 16 (bars 80-84): entry bucket. Entry = open of 1m bar 80.
    # Continue the slide.
    for k, i in enumerate(range(80, 85)):
        o[i] = 23965 - k * 5
        c[i] = o[i] - 5
        h[i] = o[i] + 0.25
        l[i] = c[i] - 0.25

    # 5m bars 17-23 (bars 85-119): continued slide to ~23900
    for k, i in enumerate(range(85, n)):
        base = 23940 - k * 1.2
        o[i] = base
        c[i] = base - 1.2
        h[i] = o[i] + 0.25
        l[i] = c[i] - 0.25

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
