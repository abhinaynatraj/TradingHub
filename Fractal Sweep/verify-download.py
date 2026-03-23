import pandas as pd

df = pd.read_parquet("NQ_1m.parquet")

print(f"Total rows: {len(df):,}")
print(f"Date range: {df.index.min()} → {df.index.max()}")
print(f"Columns: {df.columns.tolist()}")
print(f"Any nulls: {df.isnull().sum().sum()}")
print(df.head())