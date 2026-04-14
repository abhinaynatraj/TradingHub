"""Tests for fade engine: block_range_pts helper + compute_fade_metrics."""
import numpy as np
import pytest
import model_stats_fixed_constant as mfc

NS_PER_MIN = np.int64(60_000_000_000)
BASE_TS = np.int64(1_700_000_000_000_000_000)


def _make_m1(n_bars, highs, lows, closes=None, opens=None, start_ts=BASE_TS):
    """Build a minimal m1_arrs dict from explicit OHLC arrays."""
    ts_ns = np.array([start_ts + i * NS_PER_MIN for i in range(n_bars)], dtype='int64')
    highs = np.asarray(highs, dtype='float64')
    lows = np.asarray(lows, dtype='float64')
    if closes is None:
        closes = (highs + lows) / 2
    if opens is None:
        opens = closes.copy()
    return dict(
        ts_ns=ts_ns,
        open=np.asarray(opens, dtype='float64'),
        high=highs,
        low=lows,
        close=np.asarray(closes, dtype='float64'),
    )


class TestBlockRangePts:
    def test_simple_range(self):
        """Block with high=100.5 and low=99.0 → range = 1.5."""
        m1 = _make_m1(
            n_bars=10,
            highs=[100.0, 100.5, 100.2, 100.1, 99.8, 99.5, 99.3, 99.2, 99.1, 99.0],
            lows= [ 99.5,  99.8,  99.7,  99.6, 99.2, 99.0, 99.1, 99.1, 99.0, 99.0],
        )
        result = mfc.compute_block_range_pts(m1, 0, 10)
        assert result == pytest.approx(1.5)

    def test_empty_slice_returns_zero(self):
        """Empty m1 slice → 0.0."""
        m1 = _make_m1(n_bars=5, highs=[100.0]*5, lows=[99.0]*5)
        result = mfc.compute_block_range_pts(m1, 2, 2)
        assert result == 0.0


class TestHourOpen:
    def _make_hour_aligned_m1(self, n_bars, start_hour_offset_min=0, gap_at=None, opens=None):
        """Build an m1_arrs dict where ts_ns[0] is aligned to a clock hour boundary."""
        # Use a BASE_TS that's already aligned to a clock hour (hour boundary).
        HOUR_NS = np.int64(60 * 60 * 10**9)
        aligned_ts = (BASE_TS // HOUR_NS) * HOUR_NS
        start_ts = aligned_ts + np.int64(start_hour_offset_min) * NS_PER_MIN
        ts_list = []
        for i in range(n_bars):
            if gap_at is not None and i in gap_at:
                continue
            ts_list.append(start_ts + i * NS_PER_MIN)
        ts_ns = np.array(ts_list, dtype='int64')
        if opens is None:
            opens = np.arange(100.0, 100.0 + len(ts_ns), dtype='float64')
        else:
            opens = np.asarray(opens, dtype='float64')
        return dict(
            ts_ns=ts_ns,
            open=opens,
            high=opens + 0.5,
            low=opens - 0.5,
            close=opens.copy(),
        )

    def test_entry_on_hour_boundary(self):
        """Entry at 10:00:00 → hour_open is the 10:00 bar's open."""
        m1 = self._make_hour_aligned_m1(n_bars=60)
        # Entry ts at bar 0 (hour start)
        result = mfc.compute_hour_open(m1, int(m1['ts_ns'][0]))
        assert result == pytest.approx(100.0)

    def test_entry_mid_hour(self):
        """Entry at 10:14:00 → still returns the 10:00 bar's open."""
        m1 = self._make_hour_aligned_m1(n_bars=60)
        # Entry ts at bar 14 (14 minutes into the hour)
        result = mfc.compute_hour_open(m1, int(m1['ts_ns'][14]))
        assert result == pytest.approx(100.0)

    def test_entry_later_hour(self):
        """Entry at 11:05:00 in a 120-bar dataset → returns the 11:00 bar's open."""
        m1 = self._make_hour_aligned_m1(n_bars=120)
        # Entry ts at bar 65 (1 hour + 5 minutes in) → hour start is bar 60
        result = mfc.compute_hour_open(m1, int(m1['ts_ns'][65]))
        # bar 60's open is 100.0 + 60 = 160.0
        assert result == pytest.approx(160.0)

    def test_entry_hour_missing_first_minute(self):
        """Entry hour missing the :00 minute but has a :01 bar → returns :01 open."""
        # Skip the :00 minute bar; the hour's first present bar is at :01.
        m1 = self._make_hour_aligned_m1(n_bars=60, gap_at={0})
        # Query for an entry ts at the start of the hour (00:00) — no bar exists
        # exactly there, but the first bar inside [00:00, 01:00) is :01 which
        # is still inside the hour, so the helper returns its open.
        HOUR_NS = np.int64(60 * 60 * 10**9)
        aligned_ts = int((BASE_TS // HOUR_NS) * HOUR_NS)
        result = mfc.compute_hour_open(m1, aligned_ts)
        # The first remaining bar's open is 100.0 (helper assigns opens
        # sequentially to retained bars, starting at 100.0)
        assert result == pytest.approx(100.0)

    def test_entry_hour_completely_empty(self):
        """Next bar is in a later hour → returns None."""
        # Only one bar, placed 2 hours after BASE_TS aligned
        HOUR_NS = np.int64(60 * 60 * 10**9)
        aligned_ts = (BASE_TS // HOUR_NS) * HOUR_NS
        ts_ns = np.array([aligned_ts + 2 * HOUR_NS + 10 * NS_PER_MIN], dtype='int64')
        m1 = dict(ts_ns=ts_ns, open=np.array([200.0]), high=np.array([200.5]),
                  low=np.array([199.5]), close=np.array([200.0]))
        # Query for a hypothetical entry in hour 0 (before the only bar)
        result = mfc.compute_hour_open(m1, int(aligned_ts + 30 * NS_PER_MIN))
        assert result is None


def _make_htf_arrs(n_bars, start_ts=BASE_TS, period_min=60):
    """Minimal HTF arrays for scan_fixed_constant_model."""
    ts_ns = np.array([start_ts + i * period_min * NS_PER_MIN for i in range(n_bars)], dtype='int64')
    trade_date = np.array(['2023-11-14'] * n_bars)
    return dict(
        ts_ns=ts_ns,
        open=np.full(n_bars, 100.0, dtype='float64'),
        high=np.full(n_bars, 101.0, dtype='float64'),
        low=np.full(n_bars, 99.0, dtype='float64'),
        close=np.full(n_bars, 100.0, dtype='float64'),
        trade_date=trade_date,
        yr=np.full(n_bars, 2023, dtype='int32'),
        dow=np.full(n_bars, 1, dtype='int32'),
        hr=np.full(n_bars, 9, dtype='int32'),
        mn=np.full(n_bars, 0, dtype='int32'),
    )


def _make_chart_arrs(htf_ts_ns, chart_tf_min=5, bars_per_htf=12):
    """Chart-TF arrays aligned with HTF starts."""
    n = len(htf_ts_ns) * bars_per_htf
    ts_ns = np.zeros(n, dtype='int64')
    for i, h_ts in enumerate(htf_ts_ns):
        for b in range(bars_per_htf):
            ts_ns[i * bars_per_htf + b] = h_ts + b * chart_tf_min * NS_PER_MIN
    return dict(
        ts_ns=ts_ns,
        open=np.full(n, 100.0, dtype='float64'),
        high=np.full(n, 100.5, dtype='float64'),
        low=np.full(n, 99.5, dtype='float64'),
        close=np.full(n, 100.0, dtype='float64'),
        trade_date=np.array(['2023-11-14'] * n),
        yr=np.full(n, 2023, dtype='int32'),
        dow=np.full(n, 1, dtype='int32'),
        hr=np.full(n, 9, dtype='int32'),
        mn=np.array([b * chart_tf_min % 60 for b in range(n)], dtype='int32'),
    )


def _synthetic_rep(m1_start, m1_end, lock_ts_end_ns, lock_close,
                   excursion_up_pct, excursion_down_pct):
    """Build a minimal rep dict with the fields compute_fade_metrics reads."""
    return {
        'excursion_up_pct': excursion_up_pct,
        'excursion_down_pct': excursion_down_pct,
        '_m1_start': m1_start,
        '_m1_end': m1_end,
        '_lock_ts_end_ns': lock_ts_end_ns,
        '_lock_close': lock_close,
    }


class TestScanEmitsNewFields:
    def test_rep_has_block_range_pts_and_internal_ns(self):
        """Every emitted rep carries block_range_pts + internal ns fields."""
        htf = _make_htf_arrs(n_bars=3, period_min=60)
        chart = _make_chart_arrs(htf['ts_ns'], chart_tf_min=5, bars_per_htf=12)
        # m1: 60 bars per HTF block, simple oscillation
        n_m1 = 60 * 3
        highs = np.full(n_m1, 100.3, dtype='float64')
        lows = np.full(n_m1, 99.7, dtype='float64')
        highs[30] = 101.0  # peak in block 1
        lows[45] = 99.0    # trough in block 1
        m1 = _make_m1(n_bars=n_m1, highs=highs, lows=lows, start_ts=BASE_TS)
        cfg = dict(htf_min=60, chart_tf_min=5)
        reps = mfc.scan_fixed_constant_model(htf, chart, m1, '1H_5M', cfg)
        assert len(reps) >= 1
        r = reps[0]
        assert 'block_range_pts' in r
        assert r['block_range_pts'] > 0
        assert '_m1_start' in r
        assert '_m1_end' in r
        assert '_lock_ts_end_ns' in r
        assert '_lock_close' in r
        assert isinstance(r['_m1_start'], int)
        assert isinstance(r['_m1_end'], int)


class TestFadeMetricsFixtures:
    def test_fixture_1_no_trigger(self):
        """
        Neither excursion side breaches MAE99. fade_triggered = false,
        all fade fields None, no walk forward.
        """
        # lock_close = 100.0; MAE99 up = 0.5%; MAE99 down = 0.5%
        # Max up = 100.2 (0.20% < 0.5%); Max down = 99.8 (0.20% < 0.5%)
        highs = np.full(10, 100.2, dtype='float64')
        lows  = np.full(10, 99.8, dtype='float64')
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.20, excursion_down_pct=0.20,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is False
        assert rep['fade_breach_side'] is None
        assert rep['fade_reached_anchor'] is None
        assert rep['fade_reached_mfe50_opp'] is None
        assert rep['fade_reached_mae99_opp'] is None
        assert rep['fade_mfe_opp_pct'] is None

    def test_fixture_2_up_breach_no_fade(self):
        """
        Up excursion breaches MAE99 (0.5%), then price stays above lock_close.
        Expected: fade_triggered=True, fade_breach_side='up',
        fade_reached_anchor=False, fade_mfe_opp_pct ≈ 0.
        """
        # lock_close = 100.0; 10 m1 bars
        # Bars 0-4: rising up to 100.8 (0.8% breach at bar 4)
        # Bars 5-9: hold 100.5..100.7 — price never returns to anchor
        highs = np.array([100.1, 100.3, 100.5, 100.7, 100.8, 100.7, 100.6, 100.7, 100.5, 100.6])
        lows  = np.array([100.0, 100.1, 100.2, 100.4, 100.5, 100.4, 100.4, 100.5, 100.4, 100.5])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.80, excursion_down_pct=0.00,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        assert rep['fade_breach_side'] == 'up'
        assert rep['fade_reached_anchor'] is False
        assert rep['fade_reached_mfe50_opp'] is False
        assert rep['fade_reached_mae99_opp'] is False
        assert rep['fade_mfe_opp_pct'] == pytest.approx(0.0, abs=1e-6)

    def test_fixture_3_up_breach_anchor_reached_no_mfe50(self):
        """
        Up excursion breaches MAE99, then price dips to 99.95 after breach
        (0.05% below anchor — reaches anchor but not MFE50 of 0.15%).
        """
        # Bar 3 breaches up to 100.8; bar 7 dips to 99.95
        highs = np.array([100.2, 100.4, 100.6, 100.8, 100.5, 100.3, 100.1, 99.98, 99.99, 100.0])
        lows  = np.array([100.0, 100.2, 100.4, 100.5, 100.2, 100.0, 99.98, 99.95, 99.96, 99.97])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.80, excursion_down_pct=0.05,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        assert rep['fade_breach_side'] == 'up'
        assert rep['fade_reached_anchor'] is True
        assert rep['fade_reached_mfe50_opp'] is False
        assert rep['fade_reached_mae99_opp'] is False
        # fade_mfe_opp_pct = max opposite (down) excursion from anchor after breach ≈ 0.05%
        assert rep['fade_mfe_opp_pct'] == pytest.approx(0.05, abs=0.01)

    def test_fixture_4_up_breach_full_mae99_opposite(self):
        """
        Up excursion breaches MAE99 at bar 3, then fully reverses to 99.4
        (0.6% below anchor — beyond MAE99 down of 0.5%).
        Expected: all three confirmation booleans true.
        """
        highs = np.array([100.2, 100.4, 100.6, 100.8, 100.3, 99.9, 99.6, 99.5, 99.4, 99.5])
        lows  = np.array([100.0, 100.2, 100.4, 100.5, 100.0, 99.7, 99.5, 99.4, 99.4, 99.4])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.80, excursion_down_pct=0.60,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        assert rep['fade_breach_side'] == 'up'
        assert rep['fade_reached_anchor'] is True
        assert rep['fade_reached_mfe50_opp'] is True
        assert rep['fade_reached_mae99_opp'] is True
        assert rep['fade_mfe_opp_pct'] >= 0.50

    def test_fixture_5_down_breach_symmetric(self):
        """
        Symmetric of fixture 4 on the down side: down excursion breaches MAE99,
        then rebounds past anchor + MAE99 up.
        """
        # Bar 3 breaches down to 99.2 (0.8%); bars 7-9 rebound to 100.6+
        highs = np.array([100.0, 99.8, 99.6, 99.5, 100.0, 100.3, 100.5, 100.6, 100.7, 100.6])
        lows  = np.array([99.8, 99.6, 99.4, 99.2, 99.7, 100.0, 100.2, 100.5, 100.5, 100.5])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.70, excursion_down_pct=0.80,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        assert rep['fade_breach_side'] == 'down'
        assert rep['fade_reached_anchor'] is True
        assert rep['fade_reached_mfe50_opp'] is True
        assert rep['fade_reached_mae99_opp'] is True
        assert rep['fade_mfe_opp_pct'] >= 0.50

    def test_fixture_6_both_sides_breach_earliest_wins(self):
        """
        Down breach occurs at bar 2, up breach occurs at bar 6. Tiebreaker:
        earliest bar wins. Expected fade_breach_side='down'.
        """
        # Bar 2: down to 99.4 (0.6% down breach)
        # Bar 6: up to 100.6 (0.6% up breach)
        highs = np.array([100.0, 99.9, 99.7, 99.9, 100.1, 100.3, 100.6, 100.5, 100.2, 99.9])
        lows  = np.array([99.9, 99.7, 99.4, 99.5, 99.8, 100.1, 100.3, 100.3, 100.0, 99.8])
        m1 = _make_m1(n_bars=10, highs=highs, lows=lows)
        rep = _synthetic_rep(
            m1_start=0, m1_end=10,
            lock_ts_end_ns=int(m1['ts_ns'][0]), lock_close=100.0,
            excursion_up_pct=0.60, excursion_down_pct=0.60,
        )
        mfc.compute_fade_metrics(
            [rep], m1,
            mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_up_pct=0.15, p50_down_pct=0.15,
        )
        assert rep['fade_triggered'] is True
        # Bar 2 is the earliest breach → down wins the tiebreaker
        assert rep['fade_breach_side'] == 'down'


class TestFadeSummary:
    def test_builds_summary_from_reps(self):
        """Summary aggregates per-rep fade fields correctly."""
        reps = [
            # 1 non-triggered rep
            {'fade_triggered': False, 'fade_breach_side': None,
             'fade_reached_anchor': None, 'fade_reached_mfe50_opp': None,
             'fade_reached_mae99_opp': None, 'fade_mfe_opp_pct': None},
            # 1 up-breach rep that reached anchor only
            {'fade_triggered': True, 'fade_breach_side': 'up',
             'fade_reached_anchor': True, 'fade_reached_mfe50_opp': False,
             'fade_reached_mae99_opp': False, 'fade_mfe_opp_pct': 0.08},
            # 1 down-breach rep that reached anchor + MFE50 opp
            {'fade_triggered': True, 'fade_breach_side': 'down',
             'fade_reached_anchor': True, 'fade_reached_mfe50_opp': True,
             'fade_reached_mae99_opp': False, 'fade_mfe_opp_pct': 0.22},
            # 1 up-breach rep that reached all three
            {'fade_triggered': True, 'fade_breach_side': 'up',
             'fade_reached_anchor': True, 'fade_reached_mfe50_opp': True,
             'fade_reached_mae99_opp': True, 'fade_mfe_opp_pct': 0.55},
        ]
        summary = mfc.build_fade_summary(
            reps,
            mae99_up_pct=0.50, mae99_down_pct=0.48,
            p50_mfe_up_pct=0.14, p50_mfe_down_pct=0.13,
        )
        assert summary['n_total'] == 4
        assert summary['n_triggered'] == 3
        assert summary['trigger_rate'] == pytest.approx(0.75, abs=1e-6)
        assert summary['trigger_rate_up'] == pytest.approx(0.50, abs=1e-6)
        assert summary['trigger_rate_down'] == pytest.approx(0.25, abs=1e-6)
        assert summary['mae99_up_pct'] == 0.50
        assert summary['mae99_down_pct'] == 0.48
        assert summary['p50_mfe_up_pct'] == 0.14
        assert summary['p50_mfe_down_pct'] == 0.13
        # 3/3 reached anchor, 2/3 reached mfe50_opp, 1/3 reached mae99_opp
        assert summary['confirm_anchor_rate'] == pytest.approx(1.0, abs=1e-6)
        assert summary['confirm_mfe50_opp_rate'] == pytest.approx(2/3, abs=1e-6)
        assert summary['confirm_mae99_opp_rate'] == pytest.approx(1/3, abs=1e-6)
        assert 'fade_mfe_opp_dist' in summary
        assert summary['fade_mfe_opp_dist']['median'] == pytest.approx(0.22, abs=1e-6)

    def test_empty_triggered_set(self):
        """No triggered reps → rates and dist still present, zeros and None."""
        reps = [
            {'fade_triggered': False, 'fade_breach_side': None,
             'fade_reached_anchor': None, 'fade_reached_mfe50_opp': None,
             'fade_reached_mae99_opp': None, 'fade_mfe_opp_pct': None},
        ]
        summary = mfc.build_fade_summary(
            reps, mae99_up_pct=0.5, mae99_down_pct=0.5,
            p50_mfe_up_pct=0.15, p50_mfe_down_pct=0.15,
        )
        assert summary['n_triggered'] == 0
        assert summary['trigger_rate'] == 0.0
        assert summary['confirm_anchor_rate'] == 0.0
        assert summary['confirm_mfe50_opp_rate'] == 0.0
        assert summary['confirm_mae99_opp_rate'] == 0.0
        assert summary['fade_mfe_opp_dist'] == {}
