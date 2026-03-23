import databento as db

# Load the saved .dbn file (no re-download needed)
data = db.DBNStore.from_file("NQ_1m.dbn")

# Export to CSV
data.to_csv("NQ_1m_with_timestamps.csv")

print("Done!")