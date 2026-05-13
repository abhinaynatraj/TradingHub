"""Aggregation primitives — same patterns as Fractal Sweep's `agg()`.

WR for series_multi = % of trades that reached at least the 1.0× projection
(level index 1) BEFORE SL. Differs from simple_1r where WR = % winners.
"""
from collections import defaultdict


# Level index that defines a "win" for series_multi
WIN_LEVEL_IDX = 1   # 1.0× projection
LEVEL_LABELS = ['0.5x', '1.0x', '1.5x', '2.0x']


def agg(rows):
    n = len(rows)
    if n == 0:
        return dict(n=0, wins=0, wr=0.0, ev=0.0, pf=0.0,
                    avg_mae=0.0, avg_mfe=0.0)

    wins = sum(1 for r in rows if r['hits'][WIN_LEVEL_IDX])
    rs = [r['composite_r'] for r in rows]
    ev = sum(rs) / n
    pos = sum(r for r in rs if r > 0)
    neg = sum(r for r in rs if r < 0)
    pf = pos / abs(neg) if neg < 0 else 0.0
    wr = 100.0 * wins / n
    avg_mae = sum(r['mae_pts'] for r in rows) / n
    avg_mfe = sum(r['mfe_pts'] for r in rows) / n
    return dict(n=n, wins=wins, wr=wr, ev=ev, pf=pf,
                avg_mae=avg_mae, avg_mfe=avg_mfe)


def reach_rates(rows):
    n = len(rows)
    if n == 0:
        return {label: 0.0 for label in LEVEL_LABELS}
    out = {}
    n_levels = len(LEVEL_LABELS)
    for k in range(n_levels):
        cnt = sum(1 for r in rows if r['hits'][k])
        out[LEVEL_LABELS[k]] = 100.0 * cnt / n
    return out


def by_hour(rows):
    buckets = defaultdict(list)
    for r in rows:
        buckets[r['hour']].append(r)
    return {h: agg(rs) for h, rs in sorted(buckets.items())}


def by_dow(rows):
    buckets = defaultdict(list)
    for r in rows:
        buckets[r['dow']].append(r)
    return {d: agg(rs) for d, rs in sorted(buckets.items())}


def by_session(rows):
    """ASIA = 18..23 + 0..1; LONDON = 2..7; NY = 8..15; OTHER = 16..17."""
    def classify(h):
        if h >= 18 or h < 2: return 'ASIA'
        if h < 8:            return 'LONDON'
        if h < 16:           return 'NY'
        return 'OTHER'
    buckets = defaultdict(list)
    for r in rows:
        buckets[classify(r['hour'])].append(r)
    return {s: agg(rs) for s, rs in sorted(buckets.items())}


def by_direction(rows):
    buckets = defaultdict(list)
    for r in rows:
        buckets[r['direction']].append(r)
    return {d: agg(rs) for d, rs in sorted(buckets.items())}


def filter_combinations(rows, filter_keys):
    """Enumerate 2^k filter on/off combos; return dict combo_str → agg(filtered_rows)."""
    from itertools import product
    out = {}
    for state in product([False, True], repeat=len(filter_keys)):
        label = '+'.join(k for k, on in zip(filter_keys, state) if on) or 'NONE'
        filtered = [r for r in rows
                    if all((r.get(k, False) == on) or not on
                           for k, on in zip(filter_keys, state))]
        out[label] = agg(filtered)
    return out
