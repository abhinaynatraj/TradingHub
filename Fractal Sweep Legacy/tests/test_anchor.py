"""Tests for sweep line anchor bar logic."""
import numpy as np
import pytest
from helpers import NS_PER_MIN, BASE_TS


class TestAnchorBarScan:
    """Test the newest-to-oldest overwrite pattern for finding earliest bar at a price level."""

    def _scan_anchor(self, highs, target_level, htf_bars, tol=0.50):
        """Replicate the anchor scan logic from the Pine indicator.

        Scans k=1 to htf_bars, each match overwrites anc_bar.
        Result = earliest (oldest) matching bar.
        """
        anc_bar = 0  # default: most recent bar (bar_index - 1)
        for k in range(1, htf_bars + 1):
            if k >= len(highs):
                break
            if highs[k] >= target_level - tol:
                anc_bar = k
        return anc_bar

    def test_high_on_bar_5_of_12(self):
        """High made on bar 5 → anchor at bar 5 (earliest)."""
        highs = np.array([24140, 24145, 24148, 24150, 24155, 24160,  # bar 5 hits
                          24155, 24150, 24145, 24140, 24135, 24130, 24125])
        target = 24160.0
        result = self._scan_anchor(highs, target, htf_bars=12)
        assert result == 5

    def test_high_on_last_bar(self):
        """High made on bar 12 (last bar of period)."""
        highs = np.array([24130] * 12 + [24160])
        target = 24160.0
        result = self._scan_anchor(highs, target, htf_bars=12)
        assert result == 12

    def test_high_on_first_bar(self):
        """High made on bar 1 (first bar)."""
        highs = np.array([24130, 24160, 24130, 24130, 24130])
        target = 24160.0
        result = self._scan_anchor(highs, target, htf_bars=12)
        assert result == 1

    def test_multiple_bars_touch_level(self):
        """Multiple bars touch the high → anchor at earliest (largest k overwrite)."""
        highs = np.array([24130, 24160, 24155, 24160, 24130, 24130, 24130,
                          24160, 24130, 24130, 24130, 24130, 24130])
        target = 24160.0
        result = self._scan_anchor(highs, target, htf_bars=12)
        # Bars 1, 3, 7 all touch. k=7 is the last overwrite = earliest.
        assert result == 7

    def test_no_bar_matches(self):
        """No bar reaches the level → stays at default (0)."""
        highs = np.array([24130] * 13)
        target = 24160.0
        result = self._scan_anchor(highs, target, htf_bars=12)
        assert result == 0  # default

    def test_tolerance_match(self):
        """Bar within tolerance of target → should match."""
        highs = np.array([24130, 24159.75, 24130, 24130])
        target = 24160.0
        tol = 0.50  # mintick * 2
        result = self._scan_anchor(highs, target, htf_bars=12, tol=tol)
        assert result == 1  # 24159.75 >= 24160 - 0.50

    def test_outside_tolerance(self):
        """Bar outside tolerance → should NOT match."""
        highs = np.array([24130, 24158.0, 24130, 24130])
        target = 24160.0
        tol = 0.50
        result = self._scan_anchor(highs, target, htf_bars=12, tol=tol)
        assert result == 0  # 24158.0 < 24160 - 0.50


class TestAnchorScanRange:
    """Test that scan range limits to 1x HTF period."""

    def _scan_anchor(self, highs, target_level, htf_bars, tol=0.50):
        anc_bar = 0
        for k in range(1, htf_bars + 1):
            if k >= len(highs):
                break
            if highs[k] >= target_level - tol:
                anc_bar = k
        return anc_bar

    def test_5m_chart_1h_sweep_range_12(self):
        """5M chart / 1H sweep: htf_bars = 12."""
        htf_bars = 12
        # Bar at offset 13 should NOT be scanned
        highs = np.array([24130] * 13 + [24160] + [24130] * 5)
        target = 24160.0
        result = self._scan_anchor(highs, target, htf_bars=htf_bars)
        assert result == 0  # bar 13 is out of range

    def test_15m_chart_4h_sweep_range_16(self):
        """15M chart / 4H sweep: htf_bars = 16."""
        htf_bars = 16
        # Bar at offset 10 should be found
        highs = np.array([24130] * 10 + [24160] + [24130] * 10)
        target = 24160.0
        result = self._scan_anchor(highs, target, htf_bars=htf_bars)
        assert result == 10  # within range


class TestAnchorHiLoIndependent:
    """High and low anchors are computed independently."""

    def test_different_bars_for_hi_and_lo(self):
        """High at bar 3, low at bar 9 → different anchor bars."""
        highs = np.array([24130, 24130, 24130, 24160, 24130, 24130,
                          24130, 24130, 24130, 24130, 24130, 24130, 24130])
        lows = np.array([24000, 24000, 24000, 24000, 24000, 24000,
                         24000, 24000, 24000, 23900, 24000, 24000, 24000])

        # Scan for high
        hi_bar = 0
        for k in range(1, 13):
            if highs[k] >= 24160 - 0.5:
                hi_bar = k

        # Scan for low
        lo_bar = 0
        for k in range(1, 13):
            if lows[k] <= 23900 + 0.5:
                lo_bar = k

        assert hi_bar == 3
        assert lo_bar == 9
        assert hi_bar != lo_bar


class TestPreSeed:
    """Test pre-seed logic (prior candle sweeps prev-prev range)."""

    def test_long_preseed_conditions(self):
        """Prior candle swept below prev-prev low and closed back above."""
        prev2_high = 24100.0
        prev2_low = 24000.0
        prior_high = 24080.0
        prior_low = 23980.0   # swept below prev2_low
        prior_close = 24010.0  # closed back above prev2_low

        pp_range = prev2_high - prev2_low  # 100
        ext_l = prev2_low - prior_low  # 20

        should_preseed = (
            prior_low < prev2_low and
            prior_close >= prev2_low and
            pp_range >= 12 and  # min_range
            ext_l / pp_range <= 0.50  # sweep_max
        )
        assert should_preseed is True

    def test_no_preseed_if_not_swept(self):
        """Prior candle did NOT go below prev-prev low → no pre-seed."""
        prev2_low = 24000.0
        prior_low = 24005.0  # above prev2_low

        assert not (prior_low < prev2_low)

    def test_no_preseed_if_no_close_back(self):
        """Prior candle swept but didn't close back above → no pre-seed."""
        prev2_low = 24000.0
        prior_low = 23980.0
        prior_close = 23990.0  # below prev2_low

        assert prior_low < prev2_low  # swept
        assert not (prior_close >= prev2_low)  # didn't close back

    def test_no_preseed_sweep_too_large(self):
        """Sweep > 50% of range → no pre-seed."""
        prev2_high = 24020.0
        prev2_low = 24000.0
        prior_low = 23985.0

        pp_range = prev2_high - prev2_low  # 20
        ext_l = prev2_low - prior_low  # 15
        ratio = ext_l / pp_range  # 0.75 > 0.50

        assert ratio > 0.50

    def test_no_preseed_range_too_small(self):
        """Range < min_range → no pre-seed."""
        prev2_high = 24005.0
        prev2_low = 24000.0
        pp_range = prev2_high - prev2_low  # 5 < 12
        min_range = 12.0

        assert pp_range < min_range

    def test_short_preseed_conditions(self):
        """Prior candle swept above prev-prev high and closed back below."""
        prev2_high = 24100.0
        prev2_low = 24000.0
        prior_high = 24120.0   # swept above
        prior_close = 24090.0  # closed back below

        pp_range = prev2_high - prev2_low  # 100
        ext_s = prior_high - prev2_high  # 20

        should_preseed = (
            prior_high > prev2_high and
            prior_close <= prev2_high and
            pp_range >= 12 and
            ext_s / pp_range <= 0.50
        )
        assert should_preseed is True
