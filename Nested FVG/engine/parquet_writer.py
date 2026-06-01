"""Parquet writer for Nested FVG trade tables. One row per simulated trade.

Canonical column names (no aliasing) so the DuckDB-WASM dashboard reads them directly.
"""
import pyarrow as pa
import pyarrow.parquet as pq


SCHEMA = pa.schema([
    ('instrument', pa.string()),
    ('direction', pa.string()),
    ('entry_ts_ns', pa.int64()),
    ('date', pa.string()),
    ('yr', pa.int32()),
    ('dow', pa.int32()),          # DuckDB convention 0=Sun
    ('hour', pa.int32()),         # 0-23 ET
    ('minute', pa.int32()),
    ('session', pa.string()),     # ASIA/LONDON/NY/OTHER
    ('entry_price', pa.float64()),
    ('stop_price', pa.float64()),
    ('partial_price', pa.float64()),
    ('target_price', pa.float64()),
    ('htf_top', pa.float64()),
    ('htf_bot', pa.float64()),
    ('ltf_top', pa.float64()),
    ('ltf_bot', pa.float64()),
    ('gap_ltf_pts', pa.float64()),
    ('gap_htf_pts', pa.float64()),
    ('outcome', pa.string()),     # win/loss/scratch/expired
    ('partial_hit', pa.bool_()),
    ('reached_ext', pa.bool_()),
    ('pnl_pts', pa.float64()),
    ('r', pa.float64()),
    ('pnl_usd', pa.float64()),
    ('mae_pts', pa.float64()),
    ('mfe_pts', pa.float64()),
    ('bars_held', pa.int32()),
    ('smt', pa.bool_()),
    ('minute_of_hour', pa.int32()),  # alias kept = minute; reserved for :42 studies
])

_STR = {'instrument', 'direction', 'date', 'session', 'outcome'}
_BOOL = {'partial_hit', 'reached_ext', 'smt'}
_INT = {'entry_ts_ns', 'yr', 'dow', 'hour', 'minute', 'bars_held', 'minute_of_hour'}


def write_trades_parquet(trades, path):
    """Write a list of trade dicts to parquet matching SCHEMA."""
    cols = {col.name: [] for col in SCHEMA}
    for t in trades:
        for col in SCHEMA:
            name = col.name
            if name == 'minute_of_hour':
                cols[name].append(int(t['minute']))
                continue
            v = t[name]
            if name in _STR:
                cols[name].append(str(v))
            elif name in _BOOL:
                cols[name].append(bool(v))
            elif name in _INT:
                cols[name].append(int(v))
            else:
                cols[name].append(float(v))
    table = pa.table(cols, schema=SCHEMA)
    pq.write_table(table, path, compression='snappy')
