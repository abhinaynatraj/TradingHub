"""Tests for engine.time_primitives — derived from a tz-aware timestamp."""
from __future__ import annotations

import pandas as pd
import pytest

from engine import time_primitives as tp


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="America/New_York")


def test_quarter_of_hour():
    assert tp.quarter_of(_ts("2024-01-02 09:00")) == 1
    assert tp.quarter_of(_ts("2024-01-02 09:14")) == 1
    assert tp.quarter_of(_ts("2024-01-02 09:15")) == 2
    assert tp.quarter_of(_ts("2024-01-02 09:29")) == 2
    assert tp.quarter_of(_ts("2024-01-02 09:30")) == 3
    assert tp.quarter_of(_ts("2024-01-02 09:44")) == 3
    assert tp.quarter_of(_ts("2024-01-02 09:45")) == 4
    assert tp.quarter_of(_ts("2024-01-02 09:59")) == 4


def test_block_id_of():
    assert tp.block_id_of(_ts("2024-01-02 00:30")) == "00-03"
    assert tp.block_id_of(_ts("2024-01-02 09:00")) == "09-12"
    assert tp.block_id_of(_ts("2024-01-02 11:59")) == "09-12"
    assert tp.block_id_of(_ts("2024-01-02 14:30")) == "12-15"
    assert tp.block_id_of(_ts("2024-01-02 23:30")) == "21-00"


def test_block_id_of_excluded_gap_returns_none():
    assert tp.block_id_of(_ts("2024-01-02 15:30")) is None
    assert tp.block_id_of(_ts("2024-01-02 16:30")) is None
    assert tp.block_id_of(_ts("2024-01-02 17:30")) is None


def test_hour_index_in_triad():
    # 09-12 block: 09:xx → 1 (C1), 10:xx → 2 (C2), 11:xx → 3 (C3)
    assert tp.hour_index_in_triad(_ts("2024-01-02 09:30")) == 1
    assert tp.hour_index_in_triad(_ts("2024-01-02 10:00")) == 2
    assert tp.hour_index_in_triad(_ts("2024-01-02 11:45")) == 3


def test_hour_index_in_triad_excluded_gap_returns_none():
    assert tp.hour_index_in_triad(_ts("2024-01-02 16:00")) is None


def test_triad_anchor_ts_is_first_hour_open():
    # The "anchor" is the timestamp of the first 1m bar of C1 (HH:00:00 of block start).
    assert tp.triad_anchor_ts(_ts("2024-01-02 10:30")) == _ts("2024-01-02 09:00")
    assert tp.triad_anchor_ts(_ts("2024-01-02 14:59")) == _ts("2024-01-02 12:00")


def test_triad_anchor_ts_excluded_gap_raises():
    with pytest.raises(ValueError, match="excluded"):
        tp.triad_anchor_ts(_ts("2024-01-02 16:00"))


def test_hour_anchor_ts():
    # Anchor of the hour the bar belongs to (HH:00:00 of that hour).
    assert tp.hour_anchor_ts(_ts("2024-01-02 10:37")) == _ts("2024-01-02 10:00")


def test_quarter_anchor_ts():
    # Anchor of the quarter the bar belongs to (HH:MM:00 of quarter start).
    assert tp.quarter_anchor_ts(_ts("2024-01-02 10:37")) == _ts("2024-01-02 10:30")
    assert tp.quarter_anchor_ts(_ts("2024-01-02 10:14")) == _ts("2024-01-02 10:00")
    assert tp.quarter_anchor_ts(_ts("2024-01-02 10:15")) == _ts("2024-01-02 10:15")
