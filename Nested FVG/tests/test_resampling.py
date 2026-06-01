import numpy as np
from engine.resampling import resample

def test_resample_5m_from_1m():
    # 10 one-minute bars -> 2 five-minute buckets
    ns_per_min = 60_000_000_000
    ts = np.array([i * ns_per_min for i in range(10)], dtype='int64')
    m1 = dict(
        ts_ns=ts,
        open=np.arange(10, dtype='float64'),
        high=np.arange(10, dtype='float64') + 0.5,
        low=np.arange(10, dtype='float64') - 0.5,
        close=np.arange(10, dtype='float64') + 0.1,
    )
    r = resample(m1, 5)
    assert len(r['open']) == 2
    assert r['open'][0] == 0.0          # first bar of bucket 0
    assert r['high'][0] == 4.5          # max high in bars 0-4
    assert r['low'][0] == -0.5          # min low in bars 0-4
    assert r['close'][0] == 4.1         # close of bar 4
    assert r['open'][1] == 5.0          # first bar of bucket 1
