"""Tests for the NPG parquet writer.

Asserts schema (column names + types) and that hits arrays expand into
hits_05x/hits_10x/hits_15x/hits_20x boolean columns.
"""
import os
import tempfile
import pyarrow.parquet as pq
import pytest

import parquet_writer as pw


EXPECTED_COLUMNS = {
    'direction', 'composite_r',
    'hits_05x', 'hits_10x', 'hits_15x', 'hits_20x',
    'silver', 'smt', 'hour', 'dow',
    'mae_pts', 'mfe_pts',
    'entry_price', 'sl_price', 'series_range', 'sweep_extreme',
    'sl_hit', 'entry_ts_ns',
}


def _sample_trade(**overrides):
    base = dict(
        direction='SHORT',
        composite_r=1.25,
        hits=[True, True, False, False],
        silver=False,
        smt=False,
        hour=10,
        dow=2,
        mae_pts=5.0,
        mfe_pts=12.0,
        entry_price=100.0,
        sl_price=110.0,
        series_range=10.0,
        sweep_extreme=110.0,
        sl_hit=False,
        entry_ts_ns=1_700_000_000_000_000_000,
    )
    base.update(overrides)
    return base


def test_writer_emits_expected_columns():
    trades = [_sample_trade(), _sample_trade(direction='LONG', composite_r=-0.5, hits=[True, False, False, False])]
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        path = f.name
    try:
        pw.write_trades_parquet(trades, path)
        tbl = pq.read_table(path)
        actual = set(tbl.column_names)
        assert actual == EXPECTED_COLUMNS, f"expected {EXPECTED_COLUMNS}, got {actual}"
        assert tbl.num_rows == 2
    finally:
        os.unlink(path)


def test_hits_array_expands_to_four_boolean_columns():
    trades = [_sample_trade(hits=[True, False, True, False])]
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        path = f.name
    try:
        pw.write_trades_parquet(trades, path)
        tbl = pq.read_table(path)
        rows = tbl.to_pylist()
        assert rows[0]['hits_05x'] is True
        assert rows[0]['hits_10x'] is False
        assert rows[0]['hits_15x'] is True
        assert rows[0]['hits_20x'] is False
    finally:
        os.unlink(path)


def test_empty_trades_writes_empty_parquet_with_schema():
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        path = f.name
    try:
        pw.write_trades_parquet([], path)
        tbl = pq.read_table(path)
        assert tbl.num_rows == 0
        assert set(tbl.column_names) == EXPECTED_COLUMNS
    finally:
        os.unlink(path)
