"""Regression: the sweep-line nesting search must match the brute-force reference.

The orchestrator replaced an O(LTF * HTF) brute-force nesting search with an
O(LTF * live-set) sweep. This test locks in that they produce identical host
assignments on randomized inputs, so future edits can't silently diverge.
"""
import random

from engine.detect import is_nested
from engine.build_stats import _find_nested_hosts, _compute_mit_ts


def _brute_force_hosts(ltf_fvgs, htf_fvgs, proximity_bp):
    """Original O(N*M): first live, same-direction, containing HTF gap that
    CONFIRMED strictly before the signal (ts_ns are bar-close/confirmation times)."""
    out = []
    for lf in ltf_fvgs:
        sig = lf['ts_ns']
        host = None
        for hg in htf_fvgs:
            if hg['dir'] != lf['dir']:
                continue
            if hg['ts_ns'] >= sig:   # must confirm strictly before the signal
                continue
            if hg['mit_ts'] is not None and hg['mit_ts'] <= sig:
                continue
            if is_nested(lf, hg, proximity_bp):
                host = hg
                break
        out.append(host)
    return out


def _rand_gaps(n, seed, ts_start):
    """Build n random time-sorted gaps with assorted directions, edges, mit_ts."""
    rng = random.Random(seed)
    gaps = []
    ts = ts_start
    for k in range(n):
        ts += rng.randint(1, 5)  # strictly increasing formation times
        d = rng.choice([1, -1])
        bot = rng.uniform(90, 110)
        top = bot + rng.uniform(0.5, 8.0)
        # some gaps mitigate later, some never
        mit = ts + rng.randint(1, 50) if rng.random() < 0.5 else None
        gaps.append(dict(idx=k, ts_ns=ts, dir=d, top=top, bot=bot,
                         gap_pts=top - bot, mit_ts=mit))
    return gaps


def test_sweep_matches_brute_force_random():
    for seed in range(25):
        htf = _rand_gaps(60, seed, ts_start=1000)
        # LTF gaps interleaved in time across the same window
        ltf = _rand_gaps(200, seed + 999, ts_start=1000)
        prox = 50.0
        ref = _brute_force_hosts(ltf, htf, prox)
        got = _find_nested_hosts(ltf, htf, proximity_bp=prox)
        # compare by identity of the chosen host object (or None)
        assert [id(h) if h else None for h in got] == \
               [id(h) if h else None for h in ref], f"mismatch at seed {seed}"


def test_compute_mit_ts_sets_first_close_through():
    import numpy as np
    # one bull gap [100,105] formed at idx 0; closes: stays, then dips below 100 at idx 3
    htf_close = np.array([103.0, 104.0, 101.0, 99.5, 98.0], dtype='float64')
    htf_ts = np.array([10, 20, 30, 40, 50], dtype='int64')
    gaps = [dict(idx=0, dir=1, top=105.0, bot=100.0)]
    _compute_mit_ts(gaps, htf_close, htf_ts)
    assert gaps[0]['mit_ts'] == 40   # first close < 100 is at idx 3 (ts 40)

    # bear gap [95,100] never closes above 100 -> mit_ts None
    htf_close2 = np.array([99.0, 98.0, 97.0], dtype='float64')
    htf_ts2 = np.array([10, 20, 30], dtype='int64')
    gaps2 = [dict(idx=0, dir=-1, top=100.0, bot=95.0)]
    _compute_mit_ts(gaps2, htf_close2, htf_ts2)
    assert gaps2[0]['mit_ts'] is None
