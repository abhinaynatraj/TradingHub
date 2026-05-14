"""Tests for engine.stats — aggregation, Wilson CI, EV/PF.

Per the design spec, Category G (Statistical hygiene): EV is mean R (not median),
PF from R values (not dollars), Wilson 95% CI on WR for every breakdown cell,
expired trades excluded from WR/EV but counted in N.
"""
from __future__ import annotations

import math

import pytest

from engine.stats import agg, wilson_ci


def test_agg_basic_wr_ev_pf():
    rows = [
        {"r": 1.0, "outcome": "TP"},
        {"r": 1.0, "outcome": "TP"},
        {"r": -1.0, "outcome": "SL"},
        {"r": 1.0, "outcome": "TP"},
    ]
    result = agg(rows)
    assert result["n"] == 4
    assert result["n_resolved"] == 4
    assert result["n_expired"] == 0
    assert result["wins"] == 3
    assert result["wr"] == pytest.approx(0.75)
    assert result["ev"] == pytest.approx(0.5)  # (1+1-1+1)/4
    # PF = sum(r>0) / abs(sum(r<0)) = 3 / 1 = 3.0
    assert result["pf"] == pytest.approx(3.0)


def test_agg_excludes_expired_from_wr_and_ev():
    """Per spec invariant D.2: expired excluded from WR/EV, counted in N."""
    rows = [
        {"r": 1.0, "outcome": "TP"},
        {"r": -1.0, "outcome": "SL"},
        {"r": None, "outcome": "EXPIRED"},
        {"r": None, "outcome": "EXPIRED"},
    ]
    result = agg(rows)
    assert result["n"] == 4
    assert result["n_resolved"] == 2
    assert result["n_expired"] == 2
    assert result["wins"] == 1
    assert result["wr"] == pytest.approx(0.5)
    assert result["ev"] == pytest.approx(0.0)


def test_agg_zero_resolved_trades_returns_none_metrics():
    rows = [
        {"r": None, "outcome": "EXPIRED"},
    ]
    result = agg(rows)
    assert result["n"] == 1
    assert result["n_resolved"] == 0
    assert result["wr"] is None
    assert result["ev"] is None
    assert result["pf"] is None


def test_agg_no_losers_returns_inf_pf():
    rows = [
        {"r": 1.0, "outcome": "TP"},
        {"r": 1.0, "outcome": "TP"},
    ]
    result = agg(rows)
    assert result["pf"] == math.inf or result["pf"] is None  # implementation choice; must not crash


def test_agg_wilson_ci_present_when_resolved():
    rows = [{"r": 1.0, "outcome": "TP"}, {"r": -1.0, "outcome": "SL"}]
    result = agg(rows)
    assert "wr_ci_low" in result
    assert "wr_ci_high" in result
    assert 0.0 <= result["wr_ci_low"] <= result["wr"] <= result["wr_ci_high"] <= 1.0


def test_wilson_ci_known_values():
    """Wilson 95% CI for 50% WR on N=100 is ~ (40.4%, 59.6%). Reasonable bounds check."""
    low, high = wilson_ci(wins=50, n=100)
    assert 0.39 <= low <= 0.42
    assert 0.58 <= high <= 0.61


def test_wilson_ci_zero_n_returns_zero_one():
    low, high = wilson_ci(wins=0, n=0)
    assert low == 0.0
    assert high == 1.0


def test_agg_empty_returns_zero_n():
    result = agg([])
    assert result["n"] == 0
    assert result["wr"] is None
    assert result["ev"] is None
