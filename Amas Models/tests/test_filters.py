"""Tests for engine.filters — filter primitives + combo enumeration."""
from __future__ import annotations

import pytest

from engine.filters import enumerate_combos, apply_combo


def test_enumerate_combos_2_filters():
    keys = ["F1", "F2"]
    combos = enumerate_combos(keys)
    # 2^2 = 4: (), (F1), (F2), (F1,F2)
    assert len(combos) == 4
    assert frozenset() in combos
    assert frozenset(["F1"]) in combos
    assert frozenset(["F2"]) in combos
    assert frozenset(["F1", "F2"]) in combos


def test_enumerate_combos_3_filters():
    combos = enumerate_combos(["F1", "F2", "F3"])
    assert len(combos) == 8


def test_apply_combo_and_semantics():
    """Per spec invariant G.7: filter combos use AND, not OR."""
    rows = [
        {"id": 1, "passes_F1": True, "passes_F2": True},
        {"id": 2, "passes_F1": True, "passes_F2": False},
        {"id": 3, "passes_F1": False, "passes_F2": True},
        {"id": 4, "passes_F1": False, "passes_F2": False},
    ]
    result = apply_combo(rows, frozenset(["F1", "F2"]))
    assert [r["id"] for r in result] == [1]


def test_apply_combo_empty_returns_all():
    rows = [{"id": 1, "passes_F1": False}, {"id": 2, "passes_F1": True}]
    result = apply_combo(rows, frozenset())
    assert len(result) == 2


def test_apply_combo_missing_flag_treated_as_false():
    """A trade row missing a passes_<key> flag for an applied filter should be excluded."""
    rows = [
        {"id": 1, "passes_F1": True},  # no passes_F2 field
        {"id": 2, "passes_F1": True, "passes_F2": True},
    ]
    result = apply_combo(rows, frozenset(["F1", "F2"]))
    assert [r["id"] for r in result] == [2]
