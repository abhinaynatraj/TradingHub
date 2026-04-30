"""Tests for state-vector key construction.

The state-key string is the contract between Python and Pine. Byte-identical
output is mandatory; pinned by parity tests in Phase 9.

Schema fields (triad key):
  v1|sym|tf|block|c1cls|c2q|c2vh|c2vl|c2sw_c1h|c2sw_c1l|c2_inside|midhr|mid3h|box_react

Schema fields (hour key):
  v1|sym|tf|block|hour_idx|q|q1cls|q2cls|q3cls|q4cls|sweep_set|midhr|box_react
"""
from __future__ import annotations

from engine.state_vector import (
    TriadStateInputs, HourStateInputs,
    build_triad_key, build_hour_key,
    canonical_hash,
)


def test_triad_key_canonical_form():
    inputs = TriadStateInputs(
        sym="NQ", block="09-12", c1cls="line-up", c2q="Q3",
        c2vh="above", c2vl="above",
        c2sw_c1h=True, c2sw_c1l=False, c2_inside=False,
        midhr="support", mid3h="untouched", box_react="10up_rejected",
    )
    key = build_triad_key(inputs)
    expected = (
        "v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up|c2q=Q3|"
        "c2vh=above|c2vl=above|c2sw_c1h=Y|c2sw_c1l=N|c2_inside=N|"
        "midhr=support|mid3h=untouched|box_react=10up_rejected"
    )
    assert key == expected


def test_hour_key_canonical_form():
    inputs = HourStateInputs(
        sym="NQ", block="09-12", hour_idx=2, q="Q3",
        q1cls="in-stat-high", q2cls="swept-q1-low",
        q3cls="inside", q4cls="inside",
        sweep_set=("Q2_swept_Q1_low",),
        midhr="support", box_react="05dn_rejected",
    )
    key = build_hour_key(inputs)
    expected = (
        "v1|sym=NQ|tf=hour|block=09-12|hour_idx=2|q=Q3|"
        "q1cls=in-stat-high|q2cls=swept-q1-low|q3cls=inside|q4cls=inside|"
        "sweep_set=Q2_swept_Q1_low|midhr=support|box_react=05dn_rejected"
    )
    assert key == expected


def test_hour_key_empty_sweep_set_renders_as_none():
    inputs = HourStateInputs(
        sym="NQ", block="09-12", hour_idx=1, q="Q1",
        q1cls="inside", q2cls="inside", q3cls="inside", q4cls="inside",
        sweep_set=(),
        midhr="untouched", box_react="none",
    )
    key = build_hour_key(inputs)
    assert "sweep_set=none" in key


def test_hour_key_multiple_sweeps_sorted_and_comma_joined():
    inputs = HourStateInputs(
        sym="NQ", block="09-12", hour_idx=2, q="Q4",
        q1cls="in-stat-high", q2cls="inside", q3cls="inside", q4cls="inside",
        sweep_set=("Q3_swept_Q1_low", "Q2_swept_Q1_high"),  # unsorted input
        midhr="support", box_react="none",
    )
    key = build_hour_key(inputs)
    # Sorted alphabetically, comma-joined
    assert "sweep_set=Q2_swept_Q1_high,Q3_swept_Q1_low" in key


def test_canonical_hash_is_deterministic():
    h1 = canonical_hash("v1|sym=NQ|tf=triad|block=09-12")
    h2 = canonical_hash("v1|sym=NQ|tf=triad|block=09-12")
    assert h1 == h2


def test_canonical_hash_different_for_different_strings():
    h1 = canonical_hash("v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up")
    h2 = canonical_hash("v1|sym=NQ|tf=triad|block=09-12|c1cls=line-down")
    assert h1 != h2


def test_canonical_hash_is_short_base36():
    h = canonical_hash("v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up|c2q=Q3")
    # Base36 of 64-bit int → 13 chars max
    assert len(h) <= 13
    assert all(c in "0123456789abcdefghijklmnopqrstuvwxyz" for c in h)


def test_triad_key_es_symbol():
    inputs = TriadStateInputs(
        sym="ES", block="06-09", c1cls="doji", c2q="closed",
        c2vh="inside", c2vl="inside",
        c2sw_c1h=False, c2sw_c1l=False, c2_inside=True,
        midhr="untouched", mid3h="reject", box_react="none",
    )
    key = build_triad_key(inputs)
    assert key.startswith("v1|sym=ES|tf=triad|")


def test_invalid_block_rejected():
    import pytest
    with pytest.raises(ValueError, match="block"):
        TriadStateInputs(
            sym="NQ", block="15-18",  # excluded gap — not a real block
            c1cls="line-up", c2q="Q3",
            c2vh="above", c2vl="above",
            c2sw_c1h=True, c2sw_c1l=False, c2_inside=False,
            midhr="support", mid3h="untouched", box_react="none",
        )


def test_invalid_c2q_rejected():
    import pytest
    with pytest.raises(ValueError, match="c2q"):
        TriadStateInputs(
            sym="NQ", block="09-12", c1cls="line-up", c2q="Q5",  # invalid
            c2vh="above", c2vl="above",
            c2sw_c1h=True, c2sw_c1l=False, c2_inside=False,
            midhr="support", mid3h="untouched", box_react="none",
        )
