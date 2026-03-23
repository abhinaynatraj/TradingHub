import databento as db
import pandas as pd

client = db.Historical("REDACTED_API_KEY")

# Download (this may take a few minutes)
data = client.timeseries.get_range(
    dataset="GLBX.MDP3",
    symbols=["NQ.c.0"],
    schema="ohlcv-1m",
    stype_in="continuous",
    start="2010-06-06",
    end="2026-03-03",
)

# Save native format first (so you never have to re-download)
data.to_file("NQ_1m.dbn")

# Convert to DataFrame
df = data.to_df()
df = df[["open", "high", "low", "close", "volume"]]
df.index = pd.to_datetime(df.index)

# Save as Parquet (fast & compressed)
df.to_parquet("NQ_1m.parquet")

print(f"Done! Total rows: {len(df):,}")
print(df.head())