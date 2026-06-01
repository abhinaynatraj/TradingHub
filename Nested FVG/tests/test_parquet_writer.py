import duckdb
from engine.parquet_writer import write_trades_parquet, SCHEMA

def _row():
    return dict(
        instrument='NQ', direction='LONG', entry_ts_ns=1_700_000_000_000_000_000,
        date='2025-01-02', yr=2025, dow=4, hour=20, minute=42, session='ASIA',
        entry_price=100.0, stop_price=85.0, partial_price=115.0, target_price=145.0,
        htf_top=110.0, htf_bot=100.0, ltf_top=108.0, ltf_bot=102.0,
        gap_ltf_pts=6.0, gap_htf_pts=10.0,
        outcome='win', partial_hit=True, reached_ext=False,
        pnl_pts=30.0, r=2.0, pnl_usd=60.0,
        mae_pts=1.0, mfe_pts=50.0, bars_held=12, smt=True,
    )

def test_write_and_read_back(tmp_path):
    p = tmp_path / 'trades_test.parquet'
    write_trades_parquet([_row(), _row()], str(p))
    rows = duckdb.connect().execute(f"SELECT * FROM read_parquet('{p}')").fetchall()
    assert len(rows) == 2
    cols = [c.name for c in SCHEMA]
    assert 'pnl_usd' in cols and 'smt' in cols and 'outcome' in cols

def test_schema_column_count():
    # lock the schema: 30 columns per the spec
    assert len(SCHEMA) == 30
