"""Tests for midline source resolution.

Rule: if the current candle's range is STRICTLY inside the prior candle's range
(low > prior_low AND high < prior_high), use prior_mid. Else use current_mid.
Equality on either side counts as broken-out (uses current).
"""
from __future__ import annotations

from engine.midline import resolve_midline_source


def test_strictly_inside_uses_prior_mid():
    # current 100..101 inside prior 99..102 → use prior_mid
    mid, source = resolve_midline_source(
        current_high=101.0, current_low=100.0,
        prior_high=102.0,  prior_low=99.0,
    )
    assert source == "prior"
    assert mid == (102.0 + 99.0) / 2.0


def test_high_equality_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=102.0, current_low=100.0,
        prior_high=102.0,  prior_low=99.0,
    )
    # current_high == prior_high → broken-out
    assert source == "current"
    assert mid == (102.0 + 100.0) / 2.0


def test_low_equality_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=101.5, current_low=99.0,
        prior_high=102.0,  prior_low=99.0,
    )
    assert source == "current"


def test_breakout_above_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=103.0, current_low=100.0,
        prior_high=102.0,  prior_low=99.0,
    )
    assert source == "current"


def test_breakout_below_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=101.0, current_low=98.5,
        prior_high=102.0,  prior_low=99.0,
    )
    assert source == "current"


def test_no_prior_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=101.0, current_low=100.0,
        prior_high=None, prior_low=None,
    )
    assert source == "current"
    assert mid == 100.5


from engine.midline import detect_midline_reaction, MidlineReaction


def test_support_reaction_wick_below_close_above():
    # Mid at 100. Bar dips below mid then closes above → support
    r = detect_midline_reaction(mid=100.0, bar_open=100.5, bar_high=100.8, bar_low=99.7, bar_close=100.3)
    assert r == MidlineReaction.SUPPORT


def test_reject_reaction_wick_above_close_below():
    r = detect_midline_reaction(mid=100.0, bar_open=99.7, bar_high=100.4, bar_low=99.5, bar_close=99.9)
    assert r == MidlineReaction.REJECT


def test_no_reaction_when_bar_doesnt_cross_mid():
    r = detect_midline_reaction(mid=100.0, bar_open=100.2, bar_high=100.5, bar_low=100.1, bar_close=100.3)
    assert r is None


def test_no_reaction_when_close_on_wrong_side():
    # Wicks below mid AND closes below → no reaction (bar accepted the break)
    r = detect_midline_reaction(mid=100.0, bar_open=100.1, bar_high=100.0, bar_low=99.5, bar_close=99.7)
    assert r is None
