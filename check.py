import duckdb
print(duckdb.execute("DESCRIBE SELECT * FROM 'Nested FVG/data/v7_stage1_trades.parquet' LIMIT 1").df())
