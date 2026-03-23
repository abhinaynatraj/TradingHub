import duckdb

con = duckdb.connect("NQ_futures.duckdb")

# Verify
print(con.execute("SELECT COUNT(*) FROM nq_1m").fetchone())
print(con.execute("SELECT MIN(timestamp), MAX(timestamp) FROM nq_1m").fetchone())
print(con.execute("SELECT * FROM nq_1m LIMIT 3").df())

con.close()