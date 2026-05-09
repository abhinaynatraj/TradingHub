"""Aggregations over simulated trades.

Splits trades into the *taken* (non-rejected) set and produces:
  - aggregate metrics (n, wr, ev_r, ev_usd, pf, max_dd, sharpe-ish, etc.)
  - per-year, per-hour, per-DOW breakdowns
  - equity curve points
  - rejection statistics

All metrics use Wilson lower-bound CIs where relevant; raw counts are
always exposed alongside rates so the dashboard can dim low-N cells.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from math import sqrt


def _wilson_lo(p: float, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def _profit_factor(gains: float, losses: float) -> float:
    return float('inf') if losses == 0 else round(gains / losses, 3)


def aggregate(taken: pd.DataFrame) -> dict:
    """Headline metrics across the taken trades."""
    # Resolved trades only — exclude any with missing realized_r (shouldn't
    # happen but defensive).
    df = taken.dropna(subset=['realized_r'])
    n = len(df)
    if n == 0:
        return {'n': 0}
    wins = (df['realized_r'] > 0).sum()
    losses_n = (df['realized_r'] < 0).sum()
    wr = wins / n
    avg_r = df['realized_r'].mean()
    avg_win_r = df.loc[df['realized_r'] > 0, 'realized_r'].mean() if wins > 0 else 0.0
    avg_loss_r = df.loc[df['realized_r'] < 0, 'realized_r'].mean() if losses_n > 0 else 0.0
    gains = df.loc[df['realized_r'] > 0, 'pnl_usd'].sum()
    losses = -df.loc[df['realized_r'] < 0, 'pnl_usd'].sum()
    pf = _profit_factor(gains, losses)

    # Equity curve, drawdown, sharpe-ish (per-trade)
    equity = df['pnl_usd'].cumsum()
    peak = equity.cummax()
    dd = peak - equity
    max_dd_usd = float(dd.max())
    total_pnl = float(df['pnl_usd'].sum())
    std_r = float(df['realized_r'].std(ddof=0))
    sharpe_per_trade = (avg_r / std_r) if std_r > 0 else 0.0

    return {
        'n': int(n),
        'wins': int(wins),
        'losses': int(losses_n),
        'wr': round(float(wr), 4),
        'wr_lo95': round(_wilson_lo(wr, n), 4),
        'avg_r': round(float(avg_r), 4),
        'avg_win_r': round(float(avg_win_r), 4),
        'avg_loss_r': round(float(avg_loss_r), 4),
        'pf': pf,
        'gross_profit_usd': round(float(gains), 2),
        'gross_loss_usd': round(float(losses), 2),
        'total_pnl_usd': round(total_pnl, 2),
        'max_dd_usd': round(max_dd_usd, 2),
        'sharpe_per_trade': round(sharpe_per_trade, 3),
        'avg_hold_min': round(float(df['hold_minutes'].mean()), 1),
    }


def by_slice(taken: pd.DataFrame, slice_col: str) -> pd.DataFrame:
    """Per-slice aggregate (year, hour_of_day_et, or dow)."""
    df = taken.dropna(subset=['realized_r'])
    if df.empty:
        return pd.DataFrame()
    out = []
    for key, g in df.groupby(slice_col):
        agg = aggregate(g)
        agg[slice_col] = key
        out.append(agg)
    cols = [slice_col, 'n', 'wins', 'wr', 'wr_lo95', 'avg_r',
            'pf', 'total_pnl_usd', 'max_dd_usd', 'avg_hold_min']
    return pd.DataFrame(out)[cols].sort_values(slice_col).reset_index(drop=True)


def equity_curve(taken: pd.DataFrame) -> pd.DataFrame:
    """One row per resolved trade in chronological order with running equity."""
    df = taken.dropna(subset=['realized_r']).sort_values('entry_ts').reset_index(drop=True)
    if df.empty:
        return pd.DataFrame()
    df = df[['entry_ts', 'realized_r', 'pnl_usd', 'exit_reason', 'direction', 'risk_pts']].copy()
    df['equity_usd'] = df['pnl_usd'].cumsum()
    df['peak_usd'] = df['equity_usd'].cummax()
    df['dd_usd'] = df['peak_usd'] - df['equity_usd']
    return df


def rejection_stats(all_trades: pd.DataFrame) -> dict:
    """How many events made it past the risk gate vs not?"""
    n_total = len(all_trades)
    n_taken = (all_trades['exit_reason'] != 'rejected').sum()
    n_rejected = (all_trades['exit_reason'] == 'rejected').sum()
    rejected = all_trades[all_trades['exit_reason'] == 'rejected']
    return {
        'n_total_events': int(n_total),
        'n_taken': int(n_taken),
        'n_rejected': int(n_rejected),
        'taken_rate': round(n_taken / n_total, 4) if n_total else 0,
        'avg_rejected_risk_pts': round(float(rejected['risk_pts'].mean()), 2) if len(rejected) else 0,
        'median_taken_risk_pts': round(float(all_trades.loc[all_trades['exit_reason'] != 'rejected', 'risk_pts'].median()), 2) if n_taken else 0,
    }


def exit_reason_breakdown(taken: pd.DataFrame) -> dict:
    """Distribution of exit reasons (tp, sl, time, expired)."""
    df = taken.dropna(subset=['realized_r'])
    if df.empty:
        return {}
    counts = df['exit_reason'].value_counts()
    total = int(counts.sum())
    return {
        'total': total,
        'by_reason': {k: int(v) for k, v in counts.items()},
        'by_reason_pct': {k: round(int(v) / total, 4) for k, v in counts.items()},
    }


def build_all_summaries(all_trades: pd.DataFrame) -> dict:
    """One-stop call. Returns dict of dataframes/dicts keyed by output filename."""
    taken = all_trades[all_trades['exit_reason'] != 'rejected'].copy()
    return {
        'aggregate': aggregate(taken),
        'rejection': rejection_stats(all_trades),
        'exits': exit_reason_breakdown(taken),
        'by_year': by_slice(taken, 'year'),
        'by_hour': by_slice(taken, 'hour_of_day_et'),
        'by_dow':  by_slice(taken, 'dow'),
        'by_direction': by_slice(taken, 'direction'),
        'equity':  equity_curve(taken),
    }
