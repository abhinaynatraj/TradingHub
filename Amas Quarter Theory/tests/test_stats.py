"""Tests for stats helpers — Wilson CI and outcome aggregation."""
from engine.stats import wilson_ci


def test_wilson_ci_zero_n_returns_zero_zero():
    lo, hi = wilson_ci(wins=0, n=0)
    assert lo == 0.0 and hi == 0.0


def test_wilson_ci_perfect_score_smaller_than_one():
    # 10/10 wins. Wilson upper bound < 1.0 (CI accounts for sample size).
    lo, hi = wilson_ci(wins=10, n=10)
    assert hi < 1.0
    assert 0.6 < lo < 1.0


def test_wilson_ci_centered_around_observed_rate():
    lo, hi = wilson_ci(wins=50, n=100)
    assert 0.40 < lo < 0.50
    assert 0.50 < hi < 0.60


def test_wilson_ci_widens_with_smaller_n():
    lo_big, hi_big = wilson_ci(wins=500, n=1000)
    lo_small, hi_small = wilson_ci(wins=5, n=10)
    assert (hi_small - lo_small) > (hi_big - lo_big)
