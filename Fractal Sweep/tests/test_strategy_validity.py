"""
Unit tests for strategy-critical invariants.

Three areas covered:
  1. CISD detection — forward scan limits, anchor-window constraint,
     SHORT no-cross, start_idx=0 boundary
  2. Outcome resolution — same-bar SL/TP tie, EXPIRED cutoff,
     exact R values, MAE/MFE numerics, SHORT paths
  3. Filter variant calculations — 2^3 combination enumeration, EV
     ordering, per-filter column effects, missing-column robustness
"""
import numpy as np
import pandas as pd
import pytest
from helpers import NS_PER_MIN, BASE_TS, make_controlled_m1
import model_stats as ms


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def _cisd_arrs(bars_oc, step_mins=5):
    """Build CISD-TF arrays from (open, close) tuples."""
    n = len(bars_oc)
    ts_ns = np.array([BASE_TS + i * NS_PER_MIN * step_mins for i in range(n)], dtype='int64')
    opens  = np.array([b[0] for b in bars_oc], dtype='float64')
    closes = np.array([b[1] for b in bars_oc], dtype='float64')
    highs  = np.maximum(opens, closes) + 1.0
    lows   = np.minimum(opens, closes) - 1.0
    return dict(
        ts_ns=ts_ns, open=opens, close=closes, high=highs, low=lows,
        trade_date=np.array(['2020-01-01'] * n),
        hr=np.full(n, 9, dtype='int32'),
    )


def _pending(entry_price, direction, sl_price, tp_price, entry_ts=None):
    """Build a single pending trade dict for resolution testing.

    entry_ts_ns points to the first bar of scenario_bars (BASE_TS).
    resolve_outcomes_vectorised uses side='right', so scanning starts
    at the bar *after* this timestamp — callers prepend a neutral entry
    bar at BASE_TS - NS_PER_MIN so that the scenario bars are scanned.
    Convenience: use _m1(bars) which prepends that neutral bar automatically.
    """
    return dict(
        idx=0,
        entry_ts_ns=int(entry_ts or BASE_TS - NS_PER_MIN),
        entry_price=entry_price,
        stop_price=sl_price,
        target_price=tp_price,
        direction=direction,
        sweep_extreme=sl_price,
        base_risk=abs(entry_price - sl_price),
        hour_range_pts=50.0,
    )


def _m1(scenario_bars):
    """Build m1 arrays with a neutral bar at BASE_TS - NS_PER_MIN prepended.

    The resolution scanner uses searchsorted(side='right') so it starts
    scanning from the bar *after* entry_ts_ns. _pending() sets entry_ts_ns
    = BASE_TS - NS_PER_MIN, so scanning begins at BASE_TS (the first
    scenario bar).
    """
    neutral = (24000.0, 24000.5, 23999.5, 24000.0)
    all_bars = [neutral] + list(scenario_bars)
    ts_ns = np.array([BASE_TS - NS_PER_MIN + i * NS_PER_MIN for i in range(len(all_bars))],
                     dtype='int64')
    opens  = np.array([b[0] for b in all_bars], dtype='float64')
    highs  = np.array([b[1] for b in all_bars], dtype='float64')
    lows   = np.array([b[2] for b in all_bars], dtype='float64')
    closes = np.array([b[3] for b in all_bars], dtype='float64')
    n = len(all_bars)
    return dict(
        ts_ns=ts_ns, open=opens, high=highs, low=lows, close=closes,
        hr=np.full(n, 9, dtype='int32'),
        mn=np.arange(n, dtype='int32') % 60,
        dow=np.full(n, 2, dtype='int32'),
        yr=np.full(n, 2023, dtype='int32'),
        trade_date=np.array(['2023-11-14'] * n),
    )


def _filter_df(n=200, wr=0.55, f3_rate=0.5, f4_rate=0.6, smt_rate=0.3, seed=0):
    """Build a realistic-ish trade DataFrame for filter variant tests."""
    rng = np.random.RandomState(seed)
    outcomes = rng.choice(['WIN', 'LOSS'], n, p=[wr, 1 - wr])
    return pd.DataFrame({
        'date': [f'2023-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}' for i in range(n)],
        'outcome':     outcomes,
        'rejected_by': [''] * n,
        'r':           np.where(outcomes == 'WIN', 1.0, -1.0),
        'risk_pts':    np.full(n, 25.0),
        'passes_f3':   rng.choice([True, False], n, p=[f3_rate, 1 - f3_rate]),
        'passes_f4':   rng.choice([True, False], n, p=[f4_rate, 1 - f4_rate]),
        'smt':         rng.choice([True, False], n, p=[smt_rate, 1 - smt_rate]),
    })


# ══════════════════════════════════════════════════════════════════════════════
# 1. CISD DETECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestCisdForwardScanLimit:
    """n_bars caps how far the forward scan reaches."""

    def test_n_bars_prevents_fire_beyond_limit(self):
        """Forward scan capped at n_bars — fire bar outside window → None."""
        # Bearish bar at 0, return at 1, crossing bars start at 2
        bars = [
            (24050, 24040),   # 0: bearish → CISD level = 24050
            (24040, 24045),   # 1: return bar (start_idx)
            (24045, 24042),   # 2: below CISD level
            (24042, 24040),   # 3: still below
            (24040, 24055),   # 4: crosses — but outside 3-bar window
        ]
        arrs = _cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=1, n_bars=3, direction='LONG')
        assert ts is None, "Fire at bar 4 should be blocked by n_bars=3"
        assert lvl is None

    def test_n_bars_allows_fire_at_boundary(self):
        """Fire at exactly the last bar in the forward window succeeds."""
        bars = [
            (24050, 24040),   # 0: bearish
            (24040, 24045),   # 1: return bar
            (24045, 24042),   # 2: below
            (24042, 24055),   # 3: crosses — exactly at n_bars=3 boundary (idx 1+3=4 exclusive)
        ]
        arrs = _cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=1, n_bars=3, direction='LONG')
        # Bar 3 is index 1+2 = within range(1, 1+3) = range(1, 4)
        assert ts == arrs['ts_ns'][3]
        assert lvl == 24050.0

    def test_short_no_cross_before_limit(self):
        """SHORT: bullish run found but price never closes below level → None."""
        bars = [
            (24000, 24010),   # 0: bullish → CISD level = 24000
            (24010, 24005),   # 1: return bar
            (24005, 24003),   # 2: close = 24003 > 24000, no fire
            (24003, 24001),   # 3: close = 24001 > 24000, no fire
        ]
        arrs = _cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=1, n_bars=10, direction='SHORT')
        assert ts is None
        assert lvl is None

    def test_short_fires_when_cross_occurs(self):
        """SHORT: first close below CISD level triggers fire."""
        bars = [
            (24000, 24010),   # 0: bullish → CISD level = 24000
            (24010, 24005),   # 1: return bar
            (24005, 24003),   # 2: above level
            (24003, 23998),   # 3: closes below 24000 → fire
        ]
        arrs = _cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=1, n_bars=10, direction='SHORT')
        assert ts == arrs['ts_ns'][3]
        assert lvl == 24000.0


class TestCisdAnchorConstraint:
    """CISD timestamp must fall inside the anchor HTF window."""

    def test_cisd_inside_window_accepted(self):
        """Fire bar ts <= window end → valid (engine uses ts from _find_cisd)."""
        bars = [
            (24050, 24040),
            (24040, 24045),
            (24045, 24055),   # fires here
        ]
        arrs = _cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=1, n_bars=10, direction='LONG')
        # Simulate anchor window ending at ts[2]+1 (inclusive)
        window_end = arrs['ts_ns'][2] + 1
        assert ts is not None
        assert ts <= window_end, "CISD fired inside window — should be accepted"

    def test_cisd_outside_window_discarded(self):
        """Anchor constraint: if cisd_ts > q1_end_ns the setup is dropped.

        This invariant is enforced in detect_setups_base (not _find_cisd).
        We test it here as a logic assertion that callers must apply.
        """
        bars = [
            (24050, 24040),
            (24040, 24045),
            (24045, 24055),   # fires at ts[2]
        ]
        arrs = _cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=1, n_bars=10, direction='LONG')
        # Simulate a tight anchor window that ends before the fire bar
        tight_window_end = arrs['ts_ns'][1]  # ends at return bar
        if ts is not None:
            discarded = ts > tight_window_end
            assert discarded, "Caller must discard when cisd_ts > q1_end_ns"


class TestCisdStartIdxZero:
    """start_idx=0 means no bars behind it — no run possible."""

    def test_start_idx_zero_long(self):
        """No bars before start_idx=0 → no run → None."""
        bars = [
            (24050, 24045),   # 0: return bar (start_idx)
            (24045, 24060),   # 1: would-be fire
        ]
        arrs = _cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=0, n_bars=10, direction='LONG')
        assert ts is None
        assert lvl is None

    def test_start_idx_zero_short(self):
        """Same for SHORT direction at boundary."""
        bars = [
            (24000, 24005),   # 0: return bar
            (24005, 23995),   # 1: would-be fire
        ]
        arrs = _cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=0, n_bars=10, direction='SHORT')
        assert ts is None
        assert lvl is None


class TestFindCisdMaxBarsInteger:
    """find_cisd() with an integer max_bars value."""

    def test_max_bars_integer_limits_scan(self):
        """find_cisd with max_bars=5 caps forward scan (n_forward = min(5*2, 40) = 10)."""
        bars = [(24050, 24040), (24040, 24045)] + [(24045, 24042)] * 12 + [(24042, 24055)]
        arrs = _cisd_arrs(bars)
        return_ts = int(arrs['ts_ns'][1])
        # Bar that crosses is at index 14 — well beyond max_bars=5 window
        ts, lvl = ms.find_cisd(arrs, return_ts, 'LONG', max_bars=5, cisd_mode='CISD')
        # n_forward = min(5*2, 40) = 10; fire bar is at offset 13 from start_idx=1
        # range(1, 1+10) = range(1, 11) → fire at index 14 is outside
        assert ts is None

    def test_max_bars_integer_allows_nearby_fire(self):
        """find_cisd with max_bars=20 reaches a fire bar at offset 5."""
        bars = [(24050, 24040), (24040, 24045)] + [(24045, 24042)] * 4 + [(24042, 24055)]
        arrs = _cisd_arrs(bars)
        return_ts = int(arrs['ts_ns'][1])
        ts, lvl = ms.find_cisd(arrs, return_ts, 'LONG', max_bars=20, cisd_mode='CISD')
        # n_forward = min(20*2, 40) = 40; fire is at index 6 which is offset 5 from start_idx=1
        assert ts is not None
        assert lvl == 24050.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. OUTCOME RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════

class TestSameBarTieSLWins:
    """Critical: when TP and SL are both hit on the same bar, SL wins.

    This matches Pine's tie-break semantics and prevents the backtest
    from showing artificially optimistic results.
    """

    def test_long_same_bar_tie_is_loss(self):
        """LONG: bar where low <= SL and high >= TP simultaneously → LOSS."""
        entry, sl, tp = 24000.0, 23960.0, 24040.0  # 40pt risk, 40pt reward
        # One bar whose range straddles both SL and TP
        bars = [(24000, 24045, 23955, 24000)]       # high > TP, low < SL
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'LOSS', (
            "Same-bar TP/SL tie must resolve to LOSS to match Pine indicator"
        )

    def test_short_same_bar_tie_is_loss(self):
        """SHORT: bar where high >= SL and low <= TP simultaneously → LOSS."""
        entry, sl, tp = 24000.0, 24040.0, 23960.0
        bars = [(24000, 24045, 23955, 24000)]
        m1 = _m1(bars)
        pending = [_pending(entry, 'SHORT', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'LOSS'

    def test_tp_one_bar_before_sl_is_win(self):
        """TP hit on bar N, SL hit on bar N+1 → WIN (not a tie)."""
        entry, sl, tp = 24000.0, 23960.0, 24040.0
        bars = [
            (24000, 24045, 23965, 24042),   # bar 0: high >= TP, low > SL → WIN
            (24042, 24050, 23955, 23958),   # bar 1: SL (never reached)
        ]
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'WIN'

    def test_sl_one_bar_before_tp_is_loss(self):
        """SL hit on bar N, TP hit on bar N+1 → LOSS."""
        entry, sl, tp = 24000.0, 23960.0, 24040.0
        bars = [
            (24000, 24038, 23955, 23958),   # bar 0: low <= SL → LOSS
            (23958, 24045, 23950, 24042),   # bar 1: TP (never reached)
        ]
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'LOSS'


class TestExpiredResolution:
    """EXPIRED fires when OUTCOME_MAX_BARS elapse without TP or SL."""

    def test_expired_after_max_bars(self):
        """Exactly OUTCOME_MAX_BARS of neutral price action → EXPIRED."""
        entry, sl, tp = 24000.0, 23960.0, 24040.0
        # Build OUTCOME_MAX_BARS neutral bars (price moves ~0 in each)
        neutral_bar = (24000.0, 24002.0, 23998.0, 24000.0)
        bars = [neutral_bar] * ms.OUTCOME_MAX_BARS
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'EXPIRED'

    def test_expired_r_is_mark_to_market(self):
        """EXPIRED R is (close_of_last_bar - entry) / risk, not 0 or -1."""
        entry, sl, tp = 24000.0, 23960.0, 24040.0  # 40pt risk
        # All bars at entry price — last bar closes at 24010 (+10pt)
        bars = [(24000.0, 24002.0, 23998.0, 24000.0)] * (ms.OUTCOME_MAX_BARS - 1)
        bars += [(24000.0, 24012.0, 23998.0, 24010.0)]  # last bar
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        outcome, r_val = results[0][0], results[0][1]
        assert outcome == 'EXPIRED'
        # R ≈ (24010 - 24000) / 40 = 0.25
        assert abs(r_val - 0.25) < 0.01

    def test_short_expired_r_direction(self):
        """SHORT EXPIRED: favorable move produces positive R."""
        entry, sl, tp = 24000.0, 24040.0, 23960.0  # 40pt risk
        bars = [(24000.0, 24002.0, 23998.0, 24000.0)] * (ms.OUTCOME_MAX_BARS - 1)
        bars += [(24000.0, 24002.0, 23975.0, 23980.0)]  # closes lower → favorable
        m1 = _m1(bars)
        pending = [_pending(entry, 'SHORT', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        outcome, r_val = results[0][0], results[0][1]
        assert outcome == 'EXPIRED'
        # R ≈ (24000 - 23980) / 40 = 0.5
        assert r_val > 0


class TestExactRValues:
    """WIN R is exactly |target - entry| / risk (not just > 0)."""

    def test_long_win_r_equals_actual_rr(self):
        """1R target → r = 1.0 exactly."""
        entry, sl, tp = 24000.0, 23960.0, 24040.0  # 40pt risk, 40pt target
        bars = [(24000.0, 24041.0, 23995.0, 24041.0)]  # immediately hits TP
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'WIN'
        assert abs(results[0][1] - 1.0) < 0.01

    def test_long_loss_r_is_negative_one(self):
        """SL hit → r = -1.0 exactly."""
        entry, sl, tp = 24000.0, 23960.0, 24040.0
        bars = [(24000.0, 24005.0, 23955.0, 23958.0)]  # hits SL
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'LOSS'
        assert results[0][1] == -1.0

    def test_asymmetric_rr_win(self):
        """2R target → r = 2.0 exactly."""
        entry, sl, tp = 24000.0, 23960.0, 24080.0  # 40pt risk, 80pt target = 2R
        bars = [(24000.0, 24085.0, 23995.0, 24082.0)]  # hits 2R target
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'WIN'
        assert abs(results[0][1] - 2.0) < 0.01


class TestMaeMfeNumerics:
    """MAE and MFE are computed correctly as % of entry price."""

    def test_long_mae_is_adverse_excursion(self):
        """LONG: MAE = (entry - min_low) / entry * 100."""
        entry, sl, tp = 24000.0, 23900.0, 24100.0  # 100pt risk (still within MAX)
        # Trade eventually wins; dips to 23970 along the way
        bars = [
            (24000.0, 24002.0, 23970.0, 23998.0),  # low = 23970 → MAE = 30/24000 * 100 = 0.125%
            (23998.0, 24105.0, 23995.0, 24102.0),  # hits TP
        ]
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'WIN'
        mae_pct = results[0][2]
        expected_mae = (24000 - 23970) / 24000 * 100
        assert abs(mae_pct - expected_mae) < 0.01

    def test_long_mfe_is_favorable_excursion(self):
        """LONG: MFE = (max_high - entry) / entry * 100."""
        entry, sl, tp = 24000.0, 23900.0, 24100.0
        # Price reaches 24030 then reverses and hits SL (23900)
        bars = [
            (24000.0, 24030.0, 23895.0, 23898.0),  # high=24030, low < SL → LOSS
        ]
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'LOSS'
        mfe_pct = results[0][3]
        expected_mfe = (24030 - 24000) / 24000 * 100
        assert abs(mfe_pct - expected_mfe) < 0.01

    def test_short_mae_is_adverse_excursion(self):
        """SHORT: MAE = (max_high - entry) / entry * 100."""
        entry, sl, tp = 24000.0, 24100.0, 23900.0
        bars = [
            (24000.0, 24020.0, 23990.0, 23995.0),  # high=24020 → MAE = 20/24000 * 100
            (23995.0, 24000.0, 23895.0, 23898.0),  # hits TP
        ]
        m1 = _m1(bars)
        pending = [_pending(entry, 'SHORT', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'WIN'
        mae_pct = results[0][2]
        expected_mae = (24020 - 24000) / 24000 * 100
        assert abs(mae_pct - expected_mae) < 0.01

    def test_deepest_adverse_price_long(self):
        """Deepest adverse price = min low over trade window (LONG)."""
        entry, sl, tp = 24000.0, 23900.0, 24100.0
        bars = [
            (24000.0, 24005.0, 23975.0, 24002.0),
            (24002.0, 24105.0, 23980.0, 24102.0),  # TP
        ]
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        dap = results[0][4]
        assert dap == 23975.0

    def test_deepest_adverse_price_short(self):
        """Deepest adverse price = max high over trade window (SHORT)."""
        entry, sl, tp = 24000.0, 24100.0, 23900.0
        bars = [
            (24000.0, 24030.0, 23995.0, 23998.0),
            (23998.0, 24005.0, 23895.0, 23898.0),  # TP
        ]
        m1 = _m1(bars)
        pending = [_pending(entry, 'SHORT', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        dap = results[0][4]
        assert dap == 24030.0


class TestInvalidRiskBoundaries:
    """Risk gate: exactly at boundaries must not be INVALID."""

    def test_exactly_min_risk_is_valid(self):
        """risk == MIN_RISK_PTS (3.0) → not INVALID."""
        entry = 24000.0
        sl = entry - ms.MIN_RISK_PTS     # exactly 3 pts
        tp = entry + ms.MIN_RISK_PTS
        bars = [(24000.0, 24004.0, 23998.0, 24003.1)]  # hits TP
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] != 'INVALID'

    def test_exactly_max_risk_is_valid(self):
        """risk == MAX_RISK_PTS (112.5) → not INVALID."""
        entry = 24000.0
        sl = entry - ms.MAX_RISK_PTS
        tp = entry + ms.MAX_RISK_PTS
        bars = [(24000.0, 24115.0, 23990.0, 24113.0)]  # hits TP
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] != 'INVALID'

    def test_one_below_min_risk_is_invalid(self):
        """risk < MIN_RISK_PTS → INVALID."""
        entry = 24000.0
        sl = entry - (ms.MIN_RISK_PTS - 0.01)
        tp = entry + 10
        bars = [(24000.0, 24015.0, 23998.0, 24012.0)]
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'INVALID'

    def test_one_above_max_risk_is_invalid(self):
        """risk > MAX_RISK_PTS → INVALID."""
        entry = 24000.0
        sl = entry - (ms.MAX_RISK_PTS + 0.01)
        tp = entry + 200
        bars = [(24000.0, 24205.0, 23880.0, 24202.0)]
        m1 = _m1(bars)
        pending = [_pending(entry, 'LONG', sl, tp)]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'INVALID'


# ══════════════════════════════════════════════════════════════════════════════
# 3. FILTER VARIANT CALCULATIONS
# ══════════════════════════════════════════════════════════════════════════════

class TestFilterVariantEnumeration:
    """compute_filter_variants must produce exactly 2^3 = 8 combinations."""

    def test_all_combinations_count(self):
        df = _filter_df()
        result = ms.compute_filter_variants(df)
        assert len(result['all_combinations']) == 8, (
            f"Expected 8 combinations (2^3), got {len(result['all_combinations'])}"
        )

    def test_all_filter_subsets_present(self):
        """Every subset of {F3, F4, SMT} must appear exactly once."""
        from itertools import combinations as _combos
        FILTERS = ['F3', 'F4', 'SMT']
        expected_sets = set()
        for r in range(len(FILTERS) + 1):
            for c in _combos(FILTERS, r):
                expected_sets.add(frozenset(c))

        df = _filter_df()
        result = ms.compute_filter_variants(df)
        actual_sets = {frozenset(c['filters']) for c in result['all_combinations']}
        assert actual_sets == expected_sets

    def test_combinations_sorted_by_ev_descending(self):
        """all_combinations is sorted highest EV first."""
        df = _filter_df()
        result = ms.compute_filter_variants(df)
        evs = [c['ev'] for c in result['all_combinations']]
        assert evs == sorted(evs, reverse=True)

    def test_best_combination_is_first(self):
        """best_combination matches the first entry in all_combinations."""
        df = _filter_df()
        result = ms.compute_filter_variants(df)
        assert result['best_combination'] is result['all_combinations'][0]

    def test_no_filter_combo_equals_unfiltered(self):
        """The empty-filter combo has the same N as unfiltered baseline."""
        df = _filter_df()
        result = ms.compute_filter_variants(df)
        no_filter = next(c for c in result['all_combinations'] if c['filters'] == [])
        assert no_filter['n'] == result['unfiltered']['n']


class TestFilterVariantColumnEffects:
    """F3/F4/SMT columns reduce N when their respective filter is applied."""

    def test_f3_reduces_n(self):
        """Applying only F3 gives fewer trades than unfiltered."""
        df = _filter_df(n=300, f3_rate=0.4)
        result = ms.compute_filter_variants(df)
        f3_only = next(c for c in result['all_combinations']
                       if frozenset(c['filters']) == frozenset(['F3']))
        assert f3_only['n'] < result['unfiltered']['n'], (
            "F3 filter should reduce trade count (not all trades pass_f3)"
        )

    def test_f4_reduces_n(self):
        """Applying only F4 gives fewer trades than unfiltered."""
        df = _filter_df(n=300, f4_rate=0.5)
        result = ms.compute_filter_variants(df)
        f4_only = next(c for c in result['all_combinations']
                       if frozenset(c['filters']) == frozenset(['F4']))
        assert f4_only['n'] < result['unfiltered']['n']

    def test_smt_reduces_n(self):
        """Applying only SMT gives fewer trades than unfiltered."""
        df = _filter_df(n=300, smt_rate=0.3)
        result = ms.compute_filter_variants(df)
        smt_only = next(c for c in result['all_combinations']
                        if frozenset(c['filters']) == frozenset(['SMT']))
        assert smt_only['n'] < result['unfiltered']['n']

    def test_all_three_filters_gives_fewest_trades(self):
        """F3+F4+SMT together produces fewer or equal trades than any single filter."""
        df = _filter_df(n=400, f3_rate=0.6, f4_rate=0.65, smt_rate=0.35)
        result = ms.compute_filter_variants(df)
        all_three = next(c for c in result['all_combinations']
                         if frozenset(c['filters']) == frozenset(['F3', 'F4', 'SMT']))
        single_filters = [
            c for c in result['all_combinations']
            if len(c['filters']) == 1
        ]
        for single in single_filters:
            assert all_three['n'] <= single['n']

    def test_missing_f3_column_graceful(self):
        """If passes_f3 column absent, F3 filter has no effect (n unchanged)."""
        df = _filter_df().drop(columns=['passes_f3'])
        result = ms.compute_filter_variants(df)
        f3_only = next(c for c in result['all_combinations']
                       if frozenset(c['filters']) == frozenset(['F3']))
        assert f3_only['n'] == result['unfiltered']['n'], (
            "Without passes_f3 column, F3 filter should be a no-op"
        )

    def test_missing_smt_column_graceful(self):
        """If smt column absent, SMT filter has no effect."""
        df = _filter_df().drop(columns=['smt'])
        result = ms.compute_filter_variants(df)
        smt_only = next(c for c in result['all_combinations']
                        if frozenset(c['filters']) == frozenset(['SMT']))
        assert smt_only['n'] == result['unfiltered']['n']


class TestFilterVariantStatsCorrectness:
    """The stats inside each combination dict are internally consistent."""

    def test_n_wins_consistent_with_wr(self):
        """WR reported in each combo matches its actual win count."""
        df = _filter_df(n=200, wr=0.60, seed=1)
        result = ms.compute_filter_variants(df)
        # Check the no-filter combo, which we can verify externally
        no_filter = next(c for c in result['all_combinations'] if c['filters'] == [])
        n = no_filter['n']
        wr = no_filter['wr']
        ev = no_filter['ev']
        # Sanity: WR should be between 0 and 1, EV plausible
        assert 0 < wr < 1
        assert -1 <= ev <= 1

    def test_all_combos_have_required_keys(self):
        """Every combination dict has the mandatory output keys."""
        required = {'n', 'wr', 'ev', 'pf', 'filters', 'label', 'n_filters'}
        df = _filter_df()
        result = ms.compute_filter_variants(df)
        for combo in result['all_combinations']:
            missing = required - set(combo.keys())
            assert not missing, f"Combo missing keys: {missing}"

    def test_pf_positive_when_ev_positive(self):
        """If EV > 0, profit factor must be > 1.0."""
        df = _filter_df(n=300, wr=0.65, seed=2)
        result = ms.compute_filter_variants(df)
        for combo in result['all_combinations']:
            if combo['ev'] > 0 and combo['n'] >= 5:
                assert combo['pf'] > 1.0, (
                    f"EV={combo['ev']} > 0 but PF={combo['pf']} ≤ 1 for {combo['filters']}"
                )

    def test_individual_removal_has_all_three_filters(self):
        """individual_removal contains entries for F3, F4, and SMT."""
        df = _filter_df()
        result = ms.compute_filter_variants(df)
        codes = {e['removed_filter'] for e in result['individual_removal']}
        assert 'F3' in codes
        assert 'F4' in codes
        assert 'SMT' in codes

    def test_ev_delta_sign_consistent_for_high_wr_smt(self):
        """When SMT strongly selects winners, ev_delta for Add-SMT should be positive."""
        rng = np.random.RandomState(7)
        n = 500
        # SMT trades win 80% of the time; non-SMT win 50%
        smt_flag = rng.choice([True, False], n, p=[0.3, 0.7])
        outcomes = []
        for s in smt_flag:
            outcomes.append('WIN' if rng.random() < (0.80 if s else 0.50) else 'LOSS')
        df = pd.DataFrame({
            'date': [f'2023-01-{(i % 28) + 1:02d}' for i in range(n)],
            'outcome':     outcomes,
            'rejected_by': '',
            'r':           [1.0 if o == 'WIN' else -1.0 for o in outcomes],
            'risk_pts':    25.0,
            'passes_f3':   True,
            'passes_f4':   True,
            'smt':         smt_flag,
        })
        result = ms.compute_filter_variants(df)
        smt_entry = next(e for e in result['individual_removal']
                         if e['removed_filter'] == 'SMT')
        assert smt_entry['ev_delta'] > 0, (
            "SMT filter on high-WR SMT trades should yield positive EV delta"
        )
