"""Tests for engine.constants — single source of truth for risk/sizing/resolver values."""
from engine import constants


def test_min_risk_pts_is_none():
    """No lower floor on risk; arbitrarily tight stops pass."""
    assert constants.MIN_RISK_PTS is None


def test_max_risk_pts_is_twenty():
    """20-point cap on NQ at $20/pt = $400 risk."""
    assert constants.MAX_RISK_PTS == 20.0


def test_outcome_max_bars_matches_fractal_sweep():
    assert constants.OUTCOME_MAX_BARS == 1440


def test_point_values_per_instrument():
    assert constants.POINT_VALUES["nq_1m"] == 20.0
    assert constants.POINT_VALUES["es_1m"] == 50.0


def test_risk_per_trade_usd():
    assert constants.RISK_PER_TRADE_USD == 400.0


def test_max_risk_dollars_consistent():
    """MAX_RISK_PTS × NQ point value = RISK_PER_TRADE_USD; 20 × $20 = $400."""
    assert constants.MAX_RISK_PTS * constants.POINT_VALUES["nq_1m"] == constants.RISK_PER_TRADE_USD
