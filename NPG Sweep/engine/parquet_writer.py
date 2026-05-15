"""Parquet writer for NPG trade tables.

Expands the legacy `hits` list (4 booleans) into 4 named boolean columns —
SQL-friendlier and matches the dashboard's per-projection-level chip pattern.
"""
import pyarrow as pa
import pyarrow.parquet as pq


SCHEMA = pa.schema([
    ('direction', pa.string()),
    ('composite_r', pa.float64()),
    ('hits_05x', pa.bool_()),
    ('hits_10x', pa.bool_()),
    ('hits_15x', pa.bool_()),
    ('hits_20x', pa.bool_()),
    ('silver', pa.bool_()),
    ('smt', pa.bool_()),
    ('hour', pa.int32()),
    ('dow', pa.int32()),
    ('mae_pts', pa.float64()),
    ('mfe_pts', pa.float64()),
    ('entry_price', pa.float64()),
    ('sl_price', pa.float64()),
    ('series_range', pa.float64()),
    ('sweep_extreme', pa.float64()),
    ('sl_hit', pa.bool_()),
    ('entry_ts_ns', pa.int64()),
])


def write_trades_parquet(trades, path):
    """Write a list of trade dicts to a parquet file matching SCHEMA.

    Args:
        trades: list of dicts. Each dict must contain a `hits` list of 4 bools
                (corresponding to 0.5x/1.0x/1.5x/2.0x projection reach) plus
                all other SCHEMA columns.
        path: filesystem path to write to.
    """
    cols = {col.name: [] for col in SCHEMA}
    for t in trades:
        cols['direction'].append(t['direction'])
        cols['composite_r'].append(float(t['composite_r']))
        hits = t['hits']
        cols['hits_05x'].append(bool(hits[0]))
        cols['hits_10x'].append(bool(hits[1]))
        cols['hits_15x'].append(bool(hits[2]))
        cols['hits_20x'].append(bool(hits[3]))
        cols['silver'].append(bool(t['silver']))
        cols['smt'].append(bool(t['smt']))
        cols['hour'].append(int(t['hour']))
        cols['dow'].append(int(t['dow']))
        cols['mae_pts'].append(float(t['mae_pts']))
        cols['mfe_pts'].append(float(t['mfe_pts']))
        cols['entry_price'].append(float(t['entry_price']))
        cols['sl_price'].append(float(t['sl_price']))
        cols['series_range'].append(float(t['series_range']))
        cols['sweep_extreme'].append(float(t['sweep_extreme']))
        cols['sl_hit'].append(bool(t['sl_hit']))
        cols['entry_ts_ns'].append(int(t['entry_ts_ns']))

    table = pa.table(cols, schema=SCHEMA)
    pq.write_table(table, path, compression='snappy')
