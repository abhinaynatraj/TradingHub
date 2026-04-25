"""Tests for all rejection filter codes."""
import numpy as np
import pytest
import model_stats as ms


class TestFilterConstants:
    def test_sweep_max_pct(self):
        assert ms.SWEEP_MAX_PCT == 0.50

    def test_min_risk_pts(self):
        assert ms.MIN_RISK_PTS == 3.0

    def test_max_risk_pts(self):
        assert ms.MAX_RISK_PTS == 112.5

    def test_outcome_max_bars(self):
        # Bumped from 360 (6h) to 1440 (24h) to match indicator's
        # no-hard-lifetime-cap behavior on resolved trades.
        assert ms.OUTCOME_MAX_BARS == 1440


class TestFilterLogic:
    """Test filter rejection logic in isolation."""

    def test_f3_sweep_too_large(self):
        """Sweep > 50% of range → F3_SWEEP_TOO_LARGE."""
        sweep_ext = 10.0
        ref_range = 15.0
        rejected = (sweep_ext / ref_range) > ms.SWEEP_MAX_PCT
        assert rejected is True

    def test_f3_at_boundary(self):
        """Sweep exactly 50% → passes (not > 50%)."""
        sweep_ext = 7.5
        ref_range = 15.0
        rejected = (sweep_ext / ref_range) > ms.SWEEP_MAX_PCT
        assert rejected is False

    def test_f4_no_close_back_long(self):
        """LONG: ret_close < ref_level → F4_NO_CLOSE_BACK."""
        direction = 'LONG'
        ret_close = 23948.0
        ref_level = 23950.0
        no_close_back = (direction == 'LONG' and ret_close < ref_level)
        assert no_close_back is True

    def test_f4_passes_long(self):
        direction = 'LONG'
        ret_close = 23955.0
        ref_level = 23950.0
        no_close_back = (direction == 'LONG' and ret_close < ref_level)
        assert no_close_back is False

    def test_f4_no_close_back_short(self):
        direction = 'SHORT'
        ret_close = 24055.0
        ref_level = 24050.0
        no_close_back = (direction == 'SHORT' and ret_close > ref_level)
        assert no_close_back is True

    def test_invalid_risk_too_small(self):
        """risk_pts < MIN_RISK_PTS → INVALID."""
        risk = 1.5
        assert risk < ms.MIN_RISK_PTS

    def test_invalid_risk_at_minimum(self):
        """risk_pts == MIN_RISK_PTS → valid."""
        risk = 3.0
        assert not (risk < ms.MIN_RISK_PTS)

    def test_risk_too_large(self):
        """risk_pts > MAX_RISK_PTS → RISK_TOO_LARGE."""
        risk = 150.0
        assert risk > ms.MAX_RISK_PTS

    def test_risk_at_maximum(self):
        """risk_pts == MAX_RISK_PTS → valid (not > max)."""
        risk = 112.5
        assert not (risk > ms.MAX_RISK_PTS)

    def test_valid_setup_passes_all(self):
        """Setup with valid parameters passes all filters."""
        ref_range = 20.0
        sweep_ext = 5.0
        risk_pts = 15.0

        assert not ((sweep_ext / ref_range) > ms.SWEEP_MAX_PCT)  # F3 passes
        assert not (risk_pts < ms.MIN_RISK_PTS)  # risk valid
        assert not (risk_pts > ms.MAX_RISK_PTS)  # risk valid
