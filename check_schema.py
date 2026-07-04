import duckdb
res = duckdb.query("SELECT * FROM 'Nested FVG/data/v7_stage1_trades.parquet' LIMIT 1").df().to_dict(orient='records')[0]
print(res.keys())
