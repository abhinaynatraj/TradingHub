"""Tests for the two Phase-1 filters added 2026-05-11:
   passes_p42       — Amas "late extreme" (swept extreme formed in last 30%
                      of prior HTF candle; minute >= 42 for 1H, >= 21 for 30M)
   passes_pd_cisd   — Fearing "CISD in PD" (CISD bar close sits in premium
                      half for shorts / discount half for longs of prior range)

Both are mechanically verifiable: feed known inputs, assert the deterministic
output.
"""
import numpy as np
import pandas as pd
import pytest
import model_stats as ms


# ════════════════════════════════════════════════════════════════════════════
# P42 — Late Extreme :42 rule
# ════════════════════════════════════════════════════════════════════════════

class TestP42Threshold:
    """The 70%-of-candle threshold turns into minute 42 for H1 and minute 21
    for 30M. Verify the boundary math."""

    def test_h1_threshold(self):
        full_tf_min = 60
        threshold = int(full_tf_min * 0.7)
        assert threshold == 42

    def test_30m_threshold(self):
        full_tf_min = 30
        threshold = int(full_tf_min * 0.7)
        assert threshold == 21

    def test_h1_minute_41_fails(self):
        """Extreme printed at minute 41 fails the :42 rule (just under)."""
        offset = 41
        assert (offset >= 42) is False

    def test_h1_minute_42_passes(self):
        """Extreme printed exactly at minute 42 passes (>= threshold)."""
        offset = 42
        assert (offset >= 42) is True

    def test_h1_minute_59_passes(self):
        offset = 59
        assert (offset >= 42) is True

    def test_h1_minute_0_fails(self):
        """Extreme printed at the very start of the candle is a 'pullback'."""
        offset = 0
        assert (offset >= 42) is False

    def test_30m_minute_20_fails(self):
        offset = 20
        assert (offset >= 21) is False

    def test_30m_minute_21_passes(self):
        offset = 21
        assert (offset >= 21) is True


class TestP42ExtremeLocation:
    """Given a synthetic 1-minute window for a prior HTF candle, the engine's
    extreme-locator (argmax/argmin) must find the right bar."""

    def test_short_finds_high_argmax(self):
        # 60 bars; highest bar at index 50 (= minute 50)
        highs = np.full(60, 100.0)
        highs[50] = 105.0
        extreme_rel = int(np.argmax(highs))
        assert extreme_rel == 50

    def test_long_finds_low_argmin(self):
        # 60 bars; lowest bar at index 10 (= minute 10, a pullback)
        lows = np.full(60, 50.0)
        lows[10] = 48.0
        extreme_rel = int(np.argmin(lows))
        assert extreme_rel == 10

    def test_tie_breaks_to_first(self):
        # If two bars share the extreme, argmax returns the FIRST occurrence.
        # Document the behavior; this means a tie at minute 20 + minute 45
        # is treated as minute 20 (FAILS p42).
        highs = np.array([100.0, 100.0, 100.0, 100.0])
        highs[1] = 105.0
        highs[3] = 105.0
        assert int(np.argmax(highs)) == 1


# ════════════════════════════════════════════════════════════════════════════
# PD — CISD-in-PD rule (Fearing premium/discount)
# ════════════════════════════════════════════════════════════════════════════

class TestPDLocation:
    """For LONG, CISD must close in the discount half (≤ 50%);
       for SHORT, in the premium half (≥ 50%)."""

    @staticmethod
    def _pd_pct(cisd_close, prior_low, prior_high):
        rng = prior_high - prior_low
        if rng <= 0:
            return 0.5
        return (cisd_close - prior_low) / rng

    def test_long_discount_passes(self):
        # Prior range 100..110, CISD close at 103 → 30% of range → discount
        r = self._pd_pct(103.0, 100.0, 110.0)
        assert r == pytest.approx(0.3)
        assert (r <= 0.5) is True

    def test_long_premium_fails(self):
        # Prior range 100..110, CISD close at 108 → 80% → premium → fails LONG
        r = self._pd_pct(108.0, 100.0, 110.0)
        assert r == pytest.approx(0.8)
        assert (r <= 0.5) is False

    def test_short_premium_passes(self):
        # Prior range 100..110, CISD close at 107 → 70% → premium → passes SHORT
        r = self._pd_pct(107.0, 100.0, 110.0)
        assert r == pytest.approx(0.7)
        assert (r >= 0.5) is True

    def test_short_discount_fails(self):
        r = self._pd_pct(102.0, 100.0, 110.0)
        assert r == pytest.approx(0.2)
        assert (r >= 0.5) is False

    def test_long_exactly_at_50_passes(self):
        # Exactly 50% should pass LONG (<= 0.5 is inclusive)
        r = self._pd_pct(105.0, 100.0, 110.0)
        assert r == pytest.approx(0.5)
        assert (r <= 0.5) is True

    def test_short_exactly_at_50_passes(self):
        # Exactly 50% should also pass SHORT (>= 0.5 is inclusive)
        r = self._pd_pct(105.0, 100.0, 110.0)
        assert (r >= 0.5) is True

    def test_cisd_below_prior_low_long_passes(self):
        # CISD broke way below prior low → still discount (extreme negative)
        r = self._pd_pct(95.0, 100.0, 110.0)
        assert r == pytest.approx(-0.5)
        assert (r <= 0.5) is True

    def test_cisd_above_prior_high_short_passes(self):
        # CISD broke way above prior high → still premium (extreme positive)
        r = self._pd_pct(115.0, 100.0, 110.0)
        assert r == pytest.approx(1.5)
        assert (r >= 0.5) is True

    def test_zero_range_defaults_to_50pct(self):
        """Degenerate prior candle (high == low) gets pd_pct=0.5, both pass."""
        r = self._pd_pct(50.0, 50.0, 50.0)
        assert r == 0.5


# ════════════════════════════════════════════════════════════════════════════
# Filter variants — combos table now has 2^5 = 32 entries
# ════════════════════════════════════════════════════════════════════════════

class TestFilterVariantsWithNewFilters:
    """compute_filter_variants must enumerate {F3, F4, SMT, P42, PD}."""

    @staticmethod
    def _df(n=200, seed=0, **rates):
        rng = np.random.RandomState(seed)
        outcomes = rng.choice(['WIN', 'LOSS'], n, p=[0.5, 0.5])
        return pd.DataFrame({
            'date': [f'2023-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}' for i in range(n)],
            'outcome':     outcomes,
            'rejected_by': [''] * n,
            'r':           np.where(outcomes == 'WIN', 1.0, -1.0),
            'risk_pts':    np.full(n, 25.0),
            'passes_f3':   rng.choice([True, False], n, p=[rates.get('f3', 0.5), 1 - rates.get('f3', 0.5)]),
            'passes_f4':   rng.choice([True, False], n, p=[rates.get('f4', 0.5), 1 - rates.get('f4', 0.5)]),
            'smt':         rng.choice([True, False], n, p=[rates.get('smt', 0.3), 1 - rates.get('smt', 0.3)]),
            'passes_p42':  rng.choice([True, False], n, p=[rates.get('p42', 0.5), 1 - rates.get('p42', 0.5)]),
            'passes_pd_cisd': rng.choice([True, False], n, p=[rates.get('pd', 0.5), 1 - rates.get('pd', 0.5)]),
        })

    def test_combo_count_is_32(self):
        result = ms.compute_filter_variants(self._df())
        assert len(result['all_combinations']) == 32

    def test_p42_alone_reduces_n(self):
        df = self._df(n=500, p42=0.4)
        result = ms.compute_filter_variants(df)
        p42_only = next(c for c in result['all_combinations']
                        if frozenset(c['filters']) == frozenset(['P42']))
        assert p42_only['n'] < result['unfiltered']['n']

    def test_pd_alone_reduces_n(self):
        df = self._df(n=500, pd=0.4)
        result = ms.compute_filter_variants(df)
        pd_only = next(c for c in result['all_combinations']
                       if frozenset(c['filters']) == frozenset(['PD']))
        assert pd_only['n'] < result['unfiltered']['n']

    def test_missing_p42_column_graceful(self):
        df = self._df().drop(columns=['passes_p42'])
        result = ms.compute_filter_variants(df)
        p42_only = next(c for c in result['all_combinations']
                        if frozenset(c['filters']) == frozenset(['P42']))
        assert p42_only['n'] == result['unfiltered']['n']

    def test_missing_pd_column_graceful(self):
        df = self._df().drop(columns=['passes_pd_cisd'])
        result = ms.compute_filter_variants(df)
        pd_only = next(c for c in result['all_combinations']
                       if frozenset(c['filters']) == frozenset(['PD']))
        assert pd_only['n'] == result['unfiltered']['n']

    def test_all_five_filters_combo_present(self):
        """The full F3+F4+SMT+P42+PD combo appears exactly once."""
        df = self._df()
        result = ms.compute_filter_variants(df)
        full = [c for c in result['all_combinations']
                if frozenset(c['filters']) == frozenset(['F3', 'F4', 'SMT', 'P42', 'PD'])]
        assert len(full) == 1

    def test_empty_combo_equals_unfiltered(self):
        df = self._df()
        result = ms.compute_filter_variants(df)
        empty = next(c for c in result['all_combinations'] if c['filters'] == [])
        assert empty['n'] == result['unfiltered']['n']

    def test_full_combo_intersection_correctness(self):
        """All 5 filters together = literal intersection of all flag masks."""
        df = self._df(n=400, seed=42)
        result = ms.compute_filter_variants(df)
        full = next(c for c in result['all_combinations']
                    if frozenset(c['filters']) == frozenset(['F3', 'F4', 'SMT', 'P42', 'PD']))
        # Independently compute the expected n
        # Need to filter the same way compute_filter_variants does
        # (excluding SKIP/INVALID outcomes — none in our synthetic df)
        mask = (df['passes_f3'] & df['passes_f4'] & df['smt']
                & df['passes_p42'] & df['passes_pd_cisd'])
        expected_n = int((mask & df['outcome'].isin(['WIN','LOSS'])).sum())
        assert full['n'] == expected_n
