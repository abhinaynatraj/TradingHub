import duckdb
print(duckdb.query("SELECT DISTINCT stop_pct FROM 'Nested FVG/data/v7_stage1_sweep.parquet' ORDER BY stop_pct DESC").df())
