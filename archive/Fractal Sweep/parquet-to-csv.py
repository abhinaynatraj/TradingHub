import pandas as pd

# Read the Parquet file into a DataFrame
df = pd.read_parquet('NQ_1m.parquet', engine='pyarrow')

# Convert the DataFrame to a CSV file
df.to_csv('output_file_name.csv', index=False)
