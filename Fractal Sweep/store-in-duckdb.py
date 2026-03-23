import duckdb
import pandas as pd

# Load parquet
df = pd.read_parquet("NQ_1m.parquet")
df = df.reset_index()  # moves timestamp from index to column
df.columns = ["timestamp", "open", "high", "low", "close", "volume"]

# Create DB and store
con = duckdb.connect("NQ_futures.duckdb")
con.execute("""
    CREATE TABLE IF NOT EXISTS nq_1m AS 
    SELECT * FROM df
""")
con.execute("CREATE INDEX IF NOT EXISTS idx_ts ON nq_1m (timestamp)")

print(con.execute("SELECT COUNT(*) FROM nq_1m").fetchone())
print(con.execute("SELECT MIN(timestamp), MAX(timestamp) FROM nq_1m").fetchone())
con.close()