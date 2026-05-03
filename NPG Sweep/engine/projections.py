"""series_multi profile: 4 partial-exit projections + single SL.

Each projection level represents 25% of position size.
Same-bar TP/SL ties: SL wins.
Composite R = sum over levels of (0.25 × R_at_level if hit) − (remaining × 1R if SL hit).
"""
import numpy as np


def compute_targets(direction, break_price, series_range, multipliers):
    """Compute target prices = break_price ± (series_range × m) for each m."""
    if direction == 'SHORT':
        return [break_price - series_range * m for m in multipliers]
    else:
        return [break_price + series_range * m for m in multipliers]


def resolve_series_multi(o, h, l, c, ts, entry_idx, entry_price, sl_price,
                         direction, targets, max_bars=1440):
    """Walk forward from entry_idx and resolve each target + SL.

    Returns dict(hits, hit_ts_ns, sl_hit, sl_ts_ns, exit_idx, composite_r,
                 mae_pts, mfe_pts).

    Same-bar tie rule: if both an unhit target's price and the SL fall within
    the bar's [low, high] in the same bar, SL is considered hit FIRST and any
    remaining size is closed at SL. Already-hit-on-prior-bars targets remain hit.
    """
    n = len(o)
    n_levels = len(targets)
    hits = [False] * n_levels
    hit_ts = [0] * n_levels
    sl_hit = False
    sl_ts = 0
    exit_idx = entry_idx
    mae_pts = 0.0
    mfe_pts = 0.0

    for i in range(entry_idx, min(n, entry_idx + max_bars)):
        bar_h, bar_l = h[i], l[i]

        # MAE/MFE updates (running max adverse / favorable excursion)
        if direction == 'SHORT':
            adverse = bar_h - entry_price
            favorable = entry_price - bar_l
        else:
            adverse = entry_price - bar_l
            favorable = bar_h - entry_price
        mae_pts = max(mae_pts, adverse)
        mfe_pts = max(mfe_pts, favorable)

        # Determine if SL would be hit this bar
        if direction == 'SHORT':
            sl_in_bar = bar_h >= sl_price
        else:
            sl_in_bar = bar_l <= sl_price

        # Determine which targets are hit this bar (in addition to prior hits)
        new_hits = []
        for k, tgt in enumerate(targets):
            if hits[k]:
                continue
            if direction == 'SHORT' and bar_l <= tgt:
                new_hits.append(k)
            elif direction == 'LONG' and bar_h >= tgt:
                new_hits.append(k)

        if sl_in_bar:
            # Same-bar tie rule: SL wins. New hits this bar do NOT count.
            sl_hit = True
            sl_ts = int(ts[i])
            exit_idx = i
            break

        for k in new_hits:
            hits[k] = True
            hit_ts[k] = int(ts[i])

        if all(hits):
            exit_idx = i
            break
    else:
        exit_idx = min(n - 1, entry_idx + max_bars - 1)

    # Composite R: fraction-per-leg = 1/n_levels
    leg_size = 1.0 / n_levels
    risk_pts = abs(entry_price - sl_price)
    if risk_pts == 0:
        composite_r = 0.0
    else:
        r = 0.0
        n_hit = sum(1 for x in hits if x)
        for k, hit in enumerate(hits):
            if hit:
                r_at_level = abs(targets[k] - entry_price) / risk_pts
                r += leg_size * r_at_level
        if sl_hit:
            remaining_legs = n_levels - n_hit
            r -= leg_size * remaining_legs * 1.0
        composite_r = r

    return dict(
        hits=hits,
        hit_ts_ns=hit_ts,
        sl_hit=sl_hit,
        sl_ts_ns=sl_ts,
        exit_idx=exit_idx,
        composite_r=composite_r,
        mae_pts=mae_pts,
        mfe_pts=mfe_pts,
    )


def resolve_raw_measure(o, h, l, c, ts, entry_idx, entry_price, direction,
                        targets, max_bars=1440):
    """No SL, no TP. Walk full session, record MAE/MFE + which targets reached.

    Returns dict(hits, hit_ts_ns, mae_pts, mfe_pts, exit_idx).
    Composite R is not meaningful here; outcome is 'MEASURED'.
    """
    n = len(o)
    n_levels = len(targets)
    hits = [False] * n_levels
    hit_ts = [0] * n_levels
    mae_pts = 0.0
    mfe_pts = 0.0
    exit_idx = entry_idx

    for i in range(entry_idx, min(n, entry_idx + max_bars)):
        bar_h, bar_l = h[i], l[i]

        if direction == 'SHORT':
            adverse = bar_h - entry_price
            favorable = entry_price - bar_l
        else:
            adverse = entry_price - bar_l
            favorable = bar_h - entry_price
        mae_pts = max(mae_pts, adverse)
        mfe_pts = max(mfe_pts, favorable)

        for k, tgt in enumerate(targets):
            if hits[k]:
                continue
            if direction == 'SHORT' and bar_l <= tgt:
                hits[k] = True
                hit_ts[k] = int(ts[i])
            elif direction == 'LONG' and bar_h >= tgt:
                hits[k] = True
                hit_ts[k] = int(ts[i])

        exit_idx = i

    return dict(hits=hits, hit_ts_ns=hit_ts, mae_pts=mae_pts, mfe_pts=mfe_pts,
                exit_idx=exit_idx, composite_r=0.0, sl_hit=False)
