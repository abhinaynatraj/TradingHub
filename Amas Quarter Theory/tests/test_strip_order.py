"""Tests for strip-order ranking (MI of each field with outcome).

The strip order determines fallback when full state-key has too few samples.
The least-informative field (lowest MI) is stripped first.
"""
from __future__ import annotations

import pandas as pd

from engine.strip_order import compute_strip_order


def test_strip_order_returns_all_fields_in_ranked_order():
    # Fabricate samples where field "a" perfectly predicts outcome and "b"
    # is random. Strip order should place "a" LAST (highest MI = most informative).
    rows = []
    for i in range(100):
        rows.append({"a": "X", "b": i % 2, "outcome": "lup"})
        rows.append({"a": "Y", "b": i % 2, "outcome": "ldn"})
    df = pd.DataFrame(rows)
    order = compute_strip_order(df, fields=["a", "b"])
    assert order == ["b", "a"]  # "b" stripped first (less informative)


def test_strip_order_handles_constant_field():
    # Field with only one value carries 0 MI; strip first.
    rows = [
        {"a": "X", "b": "1", "outcome": "lup"},
        {"a": "X", "b": "2", "outcome": "ldn"},
        {"a": "Y", "b": "1", "outcome": "lup"},
        {"a": "Y", "b": "2", "outcome": "ldn"},
    ]
    df = pd.DataFrame(rows)
    order = compute_strip_order(df, fields=["a", "b"])
    assert order[0] == "a"  # "a" has MI=0 with outcome
