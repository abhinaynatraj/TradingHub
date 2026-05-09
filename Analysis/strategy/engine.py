"""Breakout trade simulator.

Reads breakouts.parquet + 1-min bars and resolves each event under three
stop-placement variants. All variants share the same baseline:

  - Instrument: NQ price action, sized for MNQ ($2/pt, $225/trade target risk)
  - Direction: long after bullish breakout, short after bearish
  - Entry: open of H+1 (the hour after the breakout-classified hour)
  - Same-bar TP/SL tie → SL (matches Fractal Sweep convention)
  - Bar walk: 1-min bars, up to OUTCOME_MAX_BARS

Stop variants:
  structural_1r   stop = prior-hour opposite extreme
                  rejected if stop > MAX_RISK_PTS_STRUCT (30 pts)
                  target = entry + 1R
  breakout_bar    stop = breakout bar's opposite extreme (the H that just closed)
                  rejected if stop > MAX_RISK_PTS_TIGHT (15 pts)
                  target = entry + 1R
  time_bounded    stop = same as structural_1r
                  exit = MIN(target=1R, time_stop after 15 min)
                  exit_reason in {tp, sl, time}

Output: per-trade rows with realised R, MAE/MFE in points, $ P&L sized for MNQ.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
import numpy as np


# ── Sizing constants (MNQ-calibrated) ────────────────────────────────────
POINT_VALUE_USD = 2.0          # MNQ: $2 per NQ point
RISK_PER_TRADE_USD = 225.0     # Same as Fractal Sweep MAX_RISK_PTS gate
MIN_RISK_PTS = 3.0             # Reject setups whose stop is too tight
                               # (slippage / spread eats the edge)
MAX_RISK_PTS_STRUCT = 30.0     # Variant A / C cap
MAX_RISK_PTS_TIGHT  = 15.0     # Variant B cap
OUTCOME_MAX_BARS = 240         # 4 hours of 1-min bars max hold (long enough
                               # to resolve > 99% of breakout 1R targets;
                               # caps stale "time" exits)
TIME_STOP_BARS = 15            # variant C: 15 min after entry


@dataclass
class Trade:
    event_id: int
    entry_ts: pd.Timestamp
    direction: str             # 'long' | 'short'
    entry: float
    stop: float
    target: float
    risk_pts: float
    exit_ts: pd.Timestamp | None
    exit: float | None
    exit_reason: str           # 'tp' | 'sl' | 'time' | 'expired' | 'rejected'
    realized_r: float | None
    mae_pts: float
    mfe_pts: float
    hold_minutes: int
    pnl_usd: float
    contracts: int
    year: int
    hour_of_day_et: int
    dow: int


def _round_to_tick(x: float, tick: float = 0.25) -> float:
    return round(x / tick) * tick


def _size_contracts(risk_pts: float) -> int:
    """How many MNQ contracts at $225 target risk per trade."""
    if risk_pts <= 0:
        return 0
    risk_per_contract = risk_pts * POINT_VALUE_USD
    return max(1, int(RISK_PER_TRADE_USD // risk_per_contract))


def _resolve_one_trade(
    bars_after: pd.DataFrame,
    direction: str,
    entry: float,
    stop: float,
    target: float | None,
    time_stop_bars: int | None = None,
) -> tuple[str, pd.Timestamp | None, float | None, float, float, int]:
    """Walk 1-min bars after entry. Return (reason, exit_ts, exit, mae, mfe, hold_min).

    Same-bar tie: if both stop and target are touched in one bar, stop wins.
    """
    mae = 0.0   # adverse excursion in points (always positive)
    mfe = 0.0   # favorable excursion in points (always positive)
    n = 0
    if direction == 'long':
        for n, row in enumerate(bars_after.itertuples(index=False), start=1):
            # Update MAE/MFE first (always reflects intra-bar reach)
            mae = max(mae, entry - row.low)
            mfe = max(mfe, row.high - entry)
            hit_sl = row.low  <= stop
            hit_tp = (target is not None) and (row.high >= target)
            if hit_sl and hit_tp:
                return 'sl', row.ny_ts, stop, mae, mfe, n
            if hit_sl:
                return 'sl', row.ny_ts, stop, mae, mfe, n
            if hit_tp:
                return 'tp', row.ny_ts, target, mae, mfe, n
            if time_stop_bars is not None and n >= time_stop_bars:
                return 'time', row.ny_ts, row.close, mae, mfe, n
            if n >= OUTCOME_MAX_BARS:
                return 'expired', row.ny_ts, row.close, mae, mfe, n
    else:  # short
        for n, row in enumerate(bars_after.itertuples(index=False), start=1):
            mae = max(mae, row.high - entry)
            mfe = max(mfe, entry - row.low)
            hit_sl = row.high >= stop
            hit_tp = (target is not None) and (row.low <= target)
            if hit_sl and hit_tp:
                return 'sl', row.ny_ts, stop, mae, mfe, n
            if hit_sl:
                return 'sl', row.ny_ts, stop, mae, mfe, n
            if hit_tp:
                return 'tp', row.ny_ts, target, mae, mfe, n
            if time_stop_bars is not None and n >= time_stop_bars:
                return 'time', row.ny_ts, row.close, mae, mfe, n
            if n >= OUTCOME_MAX_BARS:
                return 'expired', row.ny_ts, row.close, mae, mfe, n
    return 'expired', None, None, mae, mfe, n


def _simulate_event(
    event: pd.Series,
    bars_after: pd.DataFrame,
    variant: str,
) -> Trade | None:
    """Build a Trade record for one breakout event under one stop variant.

    Returns None if event isn't a breakout (no_prev / inside).
    Returns a Trade with exit_reason='rejected' if risk gate fails.
    """
    if event['breakout'] not in ('bullish', 'bearish'):
        return None
    if bars_after.empty:
        return None
    direction = 'long' if event['breakout'] == 'bullish' else 'short'
    # Entry = open of the first 1-min bar of H+1
    first_bar = bars_after.iloc[0]
    entry = float(first_bar['open'])

    # ── Stop placement per variant ──────────────────────────────────────
    if variant == 'structural_1r':
        # Stop at prior-hour's opposite extreme
        stop_raw = event['prev_hour_low'] if direction == 'long' else event['prev_hour_high']
        max_risk = MAX_RISK_PTS_STRUCT
        time_stop = None
    elif variant == 'breakout_bar':
        # Stop at the breakout bar's own opposite extreme
        stop_raw = event['low'] if direction == 'long' else event['high']
        max_risk = MAX_RISK_PTS_TIGHT
        time_stop = None
    elif variant == 'time_bounded':
        # Same stop as structural, but with a 15-min time stop layered on top
        stop_raw = event['prev_hour_low'] if direction == 'long' else event['prev_hour_high']
        max_risk = MAX_RISK_PTS_STRUCT
        time_stop = TIME_STOP_BARS
    else:
        raise ValueError(f"Unknown variant: {variant}")

    stop = _round_to_tick(float(stop_raw))
    risk_pts = abs(entry - stop)

    # ── Risk gates ──────────────────────────────────────────────────────
    if risk_pts < MIN_RISK_PTS or risk_pts > max_risk:
        return Trade(
            event_id=int(event.name),
            entry_ts=first_bar['ny_ts'],
            direction=direction,
            entry=entry, stop=stop, target=float('nan'),
            risk_pts=risk_pts,
            exit_ts=None, exit=None, exit_reason='rejected',
            realized_r=None, mae_pts=0.0, mfe_pts=0.0,
            hold_minutes=0, pnl_usd=0.0, contracts=0,
            year=int(event['year']), hour_of_day_et=int(event['hour_of_day_et']),
            dow=int(event['dow']),
        )

    # 1R target
    target = _round_to_tick(entry + risk_pts) if direction == 'long' else _round_to_tick(entry - risk_pts)

    # ── Walk bars ──────────────────────────────────────────────────────
    reason, exit_ts, exit_px, mae_pts, mfe_pts, n_bars = _resolve_one_trade(
        bars_after, direction, entry, stop, target, time_stop,
    )

    if exit_px is None:
        realized_r = None
        pnl_usd = 0.0
        contracts = _size_contracts(risk_pts)
    else:
        if direction == 'long':
            r = (exit_px - entry) / risk_pts
        else:
            r = (entry - exit_px) / risk_pts
        realized_r = round(r, 4)
        contracts = _size_contracts(risk_pts)
        pnl_usd = realized_r * RISK_PER_TRADE_USD if contracts > 0 else 0.0

    return Trade(
        event_id=int(event.name),
        entry_ts=first_bar['ny_ts'],
        direction=direction,
        entry=entry, stop=stop, target=target,
        risk_pts=risk_pts,
        exit_ts=exit_ts, exit=exit_px, exit_reason=reason,
        realized_r=realized_r, mae_pts=mae_pts, mfe_pts=mfe_pts,
        hold_minutes=n_bars, pnl_usd=round(pnl_usd, 2),
        contracts=contracts,
        year=int(event['year']), hour_of_day_et=int(event['hour_of_day_et']),
        dow=int(event['dow']),
    )


def simulate(
    events: pd.DataFrame,
    minutes: pd.DataFrame,
    variant: str,
    progress_every: int = 2000,
) -> pd.DataFrame:
    """Run one variant across all breakout events.

    `events`: breakouts.parquet rows
    `minutes`: enriched 1-min bars (must include ny_ts, open/high/low/close)
    """
    # Filter events to bull/bear only
    breakouts = events[events['breakout'].isin(['bullish', 'bearish'])].copy()
    breakouts = breakouts.reset_index(drop=False).rename(columns={'index': '_orig_idx'})

    # Index minutes by ny_ts for fast slicing
    m = minutes.sort_values('ny_ts').reset_index(drop=True)
    m_ts = m['ny_ts'].values

    trades: list[Trade] = []
    n_events = len(breakouts)
    print(f"[strategy] simulating variant={variant!r} on {n_events:,} events...")

    for i, event in breakouts.iterrows():
        # H+1 starts at hour_start_et + 1h. Resolve up to 4h of 1-min bars.
        h_start = pd.Timestamp(event['hour_start_et'])
        h1_start = h_start + pd.Timedelta(hours=1)
        h1_end_window = h1_start + pd.Timedelta(minutes=OUTCOME_MAX_BARS)
        # Slice
        lo = np.searchsorted(m_ts, np.datetime64(h1_start.to_datetime64()), side='left')
        hi = np.searchsorted(m_ts, np.datetime64(h1_end_window.to_datetime64()), side='left')
        bars_after = m.iloc[lo:hi]
        if bars_after.empty:
            continue
        # Use original index as event_id for traceability with breakouts.parquet
        event_for_sim = event.copy()
        event_for_sim.name = int(event['_orig_idx'])
        trade = _simulate_event(event_for_sim, bars_after, variant)
        if trade is not None:
            trades.append(trade)
        if (i + 1) % progress_every == 0:
            print(f"[strategy]   {variant}: {i+1:,}/{n_events:,}")

    # To dataframe
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([t.__dict__ for t in trades])
    df['variant'] = variant
    return df
