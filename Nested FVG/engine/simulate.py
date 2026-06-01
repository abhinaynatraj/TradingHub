"""Trade simulation: fixed-point exit with 50% scale-out at the partial.

Pure function over a 1m bar path. Walks bars forward from the entry, checking
stop before target on each bar (conservative tie-break), banking a 50% partial
on first touch, and force-closing the runner at session end (expiry).
"""


def simulate_trade(m1, entry_idx, entry_price, direction, session_end_idx,
                   stop_pts, partial_pts, target_pts, ext_pts):
    """Simulate one trade and return an outcome dict.

    Args:
        m1: dict with high/low/ts_ns numpy arrays (1m timeline).
        entry_idx: index of the entry bar (entry already filled at entry_price).
        entry_price: fill price (next-bar open, set by caller).
        direction: 1 long, -1 short.
        session_end_idx: last bar index still in-session; expiry forces close here.
        stop_pts/partial_pts/target_pts/ext_pts: fixed point distances.

    Returns:
        dict(outcome, pnl_pts, r, partial_hit, reached_ext, mae_pts, mfe_pts,
             bars_held, exit_idx).
        r = pnl_pts / stop_pts (initial risk).
    """
    high = m1['high']
    low = m1['low']
    n = len(high)

    if direction == 1:
        stop = entry_price - stop_pts
        partial = entry_price + partial_pts
        target = entry_price + target_pts
        ext = entry_price + ext_pts
    else:
        stop = entry_price + stop_pts
        partial = entry_price - partial_pts
        target = entry_price - target_pts
        ext = entry_price - ext_pts

    partial_hit = False
    reached_ext = False
    mae = 0.0  # max adverse excursion (pts, positive number)
    mfe = 0.0  # max favorable excursion (pts, positive number)

    last = min(session_end_idx, n - 1)
    for i in range(entry_idx, last + 1):
        hi = high[i]
        lo = low[i]

        # update excursions
        if direction == 1:
            mfe = max(mfe, hi - entry_price)
            mae = max(mae, entry_price - lo)
            if hi >= ext:
                reached_ext = True
            hit_stop = lo <= stop
            hit_target = hi >= target
            hit_partial = hi >= partial
        else:
            mfe = max(mfe, entry_price - lo)
            mae = max(mae, hi - entry_price)
            if lo <= ext:
                reached_ext = True
            hit_stop = hi >= stop
            hit_target = lo <= target
            hit_partial = lo <= partial

        # Conservative tie: stop checked before target on the same bar.
        if hit_stop:
            if partial_hit:
                # 0.5 banked at +partial, 0.5 stopped at -stop
                pnl = 0.5 * partial_pts + 0.5 * (-stop_pts)
                outcome = 'scratch' if abs(pnl) < 1e-9 else ('win' if pnl > 0 else 'loss')
            else:
                pnl = -stop_pts
                outcome = 'loss'
            return _result(outcome, pnl, stop_pts, partial_hit, reached_ext, mae, mfe, entry_idx, i)

        if hit_target:
            # runner reaches full target; if partial wasn't separately flagged,
            # it must have passed +partial on the way (target > partial), so bank both legs.
            partial_hit = True
            pnl = 0.5 * partial_pts + 0.5 * target_pts
            return _result('win', pnl, stop_pts, partial_hit, reached_ext, mae, mfe, entry_idx, i)

        if hit_partial and not partial_hit:
            partial_hit = True  # bank 50%, runner continues

    # Expiry: force-close runner flat at session end.
    if partial_hit:
        pnl = 0.5 * partial_pts + 0.5 * 0.0  # runner closed at ~entry (flat leg)
    else:
        pnl = 0.0
    return _result('expired', pnl, stop_pts, partial_hit, reached_ext, mae, mfe, entry_idx, last)


def _result(outcome, pnl_pts, stop_pts, partial_hit, reached_ext, mae, mfe, entry_idx, exit_idx):
    return dict(
        outcome=outcome,
        pnl_pts=float(pnl_pts),
        r=float(pnl_pts / stop_pts) if stop_pts else 0.0,
        partial_hit=bool(partial_hit),
        reached_ext=bool(reached_ext),
        mae_pts=float(mae),
        mfe_pts=float(mfe),
        bars_held=int(exit_idx - entry_idx),
        exit_idx=int(exit_idx),
    )
