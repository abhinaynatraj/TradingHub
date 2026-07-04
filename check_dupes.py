import duckdb
print(duckdb.query("SELECT stop_pct, target_pct, n, session, direction, smt FROM 'Nested FVG/data/v7_stage1_sweep.parquet' WHERE stop_pct=0.3 AND target_pct=0.45").df())
