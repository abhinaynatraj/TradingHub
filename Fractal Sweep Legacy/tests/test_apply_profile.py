"""Integration tests for apply_profile_and_resolve()."""
import numpy as np
import pandas as pd
import pytest
from helpers import NS_PER_MIN, BASE_TS, make_controlled_m1
import model_stats as ms


def _make_base_rows_and_pending(entries):
    """Build base_rows and base_pending from a list of entry specs.

    entries: list of dicts with keys:
        entry_price, sweep_extreme, direction
    Returns: (base_rows, base_pending, m1_arrs)
    """
    # Build enough 1m bars for resolution (400 bars)
    bars = []
    for i in range(400):
        p = 24000 + i * 0.1
        bars.append((p, p + 5, p - 5, p + 0.5))
    m1 = make_controlled_m1(bars, start_ts=BASE_TS)
    m1['hr'][:] = 9

    base_rows = []
    base_pending = []

    for i, e in enumerate(entries):
        entry_price = e['entry_price']
        sweep_extreme = e['sweep_extreme']
        direction = e['direction']
        base_risk = abs(entry_price - sweep_extreme)

        row = dict(
            date='2023-11-14', yr=2023, dow=2,
            direction=direction,
            ref_range=50.0, sweep_ext=10.0, sweep_pct=0.2,
            sweep_extreme=sweep_extreme,
            sweep_mode='PREV', cisd_mode='CISD', ref_lookback=1,
            smt=False,
            hr=9, mn=i * 5, session='NY1',
            entry_price=entry_price, base_risk=round(base_risk, 2),
            cisd_level=entry_price - 5 if direction == 'LONG' else entry_price + 5,
            hour_range_pts=50.0,
            rejected_by='',
            stop_price=None, target_price=None, risk_pts=None,
            outcome='', r=0.0,
            mae_pct=None, mfe_pct=None,
            mae_pct_hr=None, mfe_pct_hr=None,
        )
        base_rows.append(row)

        bp = dict(
            idx=i,
            entry_ts_ns=int(BASE_TS + (i + 1) * NS_PER_MIN),
            entry_price=entry_price,
            sweep_extreme=sweep_extreme,
            base_risk=base_risk,
            direction=direction,
            hour_range_pts=50.0,
        )
        base_pending.append(bp)

    return base_rows, base_pending, m1


class TestApplyProfileMult:
    def test_structural_profile(self):
        """Structural profile: stop=1×base_risk, target=1×base_risk."""
        entries = [
            dict(entry_price=24020.0, sweep_extreme=24000.0, direction='LONG'),
        ]
        rows, pending, m1 = _make_base_rows_and_pending(entries)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=1.0,
                                           profile_type='structural')
        assert not df.empty
        assert df.iloc[0]['stop_price'] == 24000.0  # entry - 1*base_risk(20)
        assert df.iloc[0]['target_price'] == 24040.0  # entry + 1*base_risk(20)
        assert df.iloc[0]['risk_pts'] == 20.0

    def test_short_profile(self):
        """SHORT: stop above, target below."""
        entries = [
            dict(entry_price=24020.0, sweep_extreme=24050.0, direction='SHORT'),
        ]
        rows, pending, m1 = _make_base_rows_and_pending(entries)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=1.0,
                                           profile_type='structural')
        assert not df.empty
        assert df.iloc[0]['stop_price'] == 24050.0  # entry + 1*base_risk(30)
        assert df.iloc[0]['target_price'] == 23990.0  # entry - 1*base_risk(30)

    def test_outcome_populated(self):
        """Outcome (WIN/LOSS/EXPIRED) is populated after resolution."""
        entries = [
            dict(entry_price=24020.0, sweep_extreme=24000.0, direction='LONG'),
        ]
        rows, pending, m1 = _make_base_rows_and_pending(entries)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=1.0,
                                           profile_type='structural')
        assert df.iloc[0]['outcome'] in ('WIN', 'LOSS', 'EXPIRED', 'INVALID')


class TestApplyProfilePct:
    def test_pct_profile_stop_target(self):
        """PCT profile: stop/target as % of entry price."""
        entries = [
            dict(entry_price=24000.0, sweep_extreme=23950.0, direction='LONG'),
        ]
        rows, pending, m1 = _make_base_rows_and_pending(entries)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=0.26, target_val=0.18,
                                           profile_type='pct')
        assert not df.empty
        # stop = 24000 * (1 - 0.26/100) = 24000 - 62.4 = 23937.6
        assert abs(df.iloc[0]['stop_price'] - 23937.6) < 1.0
        # target = 24000 * (1 + 0.18/100) = 24000 + 43.2 = 24043.2
        assert abs(df.iloc[0]['target_price'] - 24043.2) < 1.0


class TestApplyProfileSplitTp:
    def test_split_tp_sl_capping(self):
        """Split TP: SL = min(structural, MAE p90 cap)."""
        entries = [
            dict(entry_price=24000.0, sweep_extreme=23900.0, direction='LONG'),
        ]
        rows, pending, m1 = _make_base_rows_and_pending(entries)
        # sl_mae_pct = 0.30 → mae_stop = 24000 * 0.30 / 100 = 72
        # structural_stop = 1.0 * 100 = 100
        # SL = min(100, 72) = 72
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=0.42,
                                           profile_type='split_tp',
                                           sl_mae_pct=0.30)
        assert not df.empty
        assert df.iloc[0]['risk_pts'] == 72.0  # min(100, 72)

    def test_split_tp_without_mae_cap(self):
        """Split TP without MAE cap: SL = structural."""
        entries = [
            dict(entry_price=24000.0, sweep_extreme=23950.0, direction='LONG'),
        ]
        rows, pending, m1 = _make_base_rows_and_pending(entries)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=0.42,
                                           profile_type='split_tp',
                                           sl_mae_pct=None)
        assert not df.empty
        assert df.iloc[0]['risk_pts'] == 50.0  # structural = 1 * base_risk(50)


class TestApplyProfileRiskValidation:
    def test_invalid_risk_too_small(self):
        """Risk < MIN_RISK_PTS → INVALID."""
        entries = [
            dict(entry_price=24000.0, sweep_extreme=23999.0, direction='LONG'),
        ]
        rows, pending, m1 = _make_base_rows_and_pending(entries)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=1.0,
                                           profile_type='mult')
        assert df.iloc[0]['outcome'] == 'INVALID'
        assert df.iloc[0]['rejected_by'] == 'INVALID_RISK'

    def test_invalid_risk_too_large(self):
        """Risk > MAX_RISK_PTS → INVALID."""
        entries = [
            dict(entry_price=24000.0, sweep_extreme=23800.0, direction='LONG'),
        ]
        rows, pending, m1 = _make_base_rows_and_pending(entries)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=1.0,
                                           profile_type='mult')
        assert df.iloc[0]['outcome'] == 'INVALID'
        assert df.iloc[0]['rejected_by'] == 'RISK_TOO_LARGE'

    def test_returns_dataframe(self):
        """Returns a pandas DataFrame."""
        entries = [
            dict(entry_price=24020.0, sweep_extreme=24000.0, direction='LONG'),
        ]
        rows, pending, m1 = _make_base_rows_and_pending(entries)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=1.0,
                                           profile_type='mult')
        assert isinstance(df, pd.DataFrame)

    def test_empty_pending(self):
        """Empty pending list → empty DataFrame."""
        df = ms.apply_profile_and_resolve([], [], make_controlled_m1([(24000, 24005, 23995, 24002)]),
                                           stop_val=1.0, target_val=1.0)
        assert df.empty
