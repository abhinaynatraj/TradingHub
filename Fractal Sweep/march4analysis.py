import duckdb
import pandas as pd

con = duckdb.connect("NQ_futures.duckdb")

# ── Recent price action (last 5 days) ─────────────────────
recent = con.execute("""
    SELECT 
        DATE_TRUNC('day', timestamp) as date,
        FIRST(open ORDER BY timestamp) as open,
        MAX(high) as high,
        MIN(low) as low,
        LAST(close ORDER BY timestamp) as close,
        SUM(volume) as volume
    FROM nq_1m
    WHERE timestamp >= NOW() - INTERVAL '10 days'
    GROUP BY DATE_TRUNC('day', timestamp)
    ORDER BY date
""").df()

# ── Key levels (swing highs/lows last 20 days) ─────────────
levels = con.execute("""
    SELECT
        MAX(high) as swing_high_20d,
        MIN(low)  as swing_low_20d,
        AVG(close) as avg_close_20d
    FROM (
        SELECT DATE_TRUNC('day', timestamp) as date,
               MAX(high) as high,
               MIN(low) as low,
               LAST(close ORDER BY timestamp) as close
        FROM nq_1m
        WHERE timestamp >= NOW() - INTERVAL '20 days'
        GROUP BY DATE_TRUNC('day', timestamp)
    )
""").df()

# ── Today's (March 3) intraday structure ───────────────────
today = con.execute("""
    SELECT 
        HOUR(timestamp) as hour,
        MAX(high) as high,
        MIN(low) as low,
        LAST(close ORDER BY timestamp) as close,
        SUM(volume) as volume
    FROM nq_1m
    WHERE CAST(timestamp AS DATE) = '2026-03-03'
    GROUP BY HOUR(timestamp)
    ORDER BY hour
""").df()

# ── Volume profile last 5 days ─────────────────────────────
vp = con.execute("""
    SELECT
        ROUND(close / 25) * 25 as price_level,
        SUM(volume) as total_volume
    FROM nq_1m
    WHERE timestamp >= NOW() - INTERVAL '5 days'
    GROUP BY ROUND(close / 25) * 25
    ORDER BY total_volume DESC
    LIMIT 10
""").df()

con.close()

print("=== LAST 10 DAYS DAILY BARS ===")
print(recent.to_string(index=False))
print("\n=== KEY LEVELS (20 DAY) ===")
print(levels.to_string(index=False))
print("\n=== TODAY MARCH 3 HOURLY ===")
print(today.to_string(index=False))
print("\n=== TOP VOLUME NODES (last 5 days) ===")
print(vp.to_string(index=False))