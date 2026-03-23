import databento as db

client = db.Historical("REDACTED_API_KEY")

cost = client.metadata.get_cost(
    dataset="GLBX.MDP3",
    symbols=["NQ.c.0"],        # ← changed from "NQ1!"
    schema="ohlcv-1m",
    stype_in="continuous",
    start="2010-06-06",
    end="2026-03-03",
)
print(f"Estimated cost: ${cost:.2f}")