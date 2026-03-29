import duckdb
import pandas as pd

con = duckdb.connect("NQ_futures.duckdb")

# ── 1. Basic overview ──────────────────────────────────────
print("=== DATABASE OVERVIEW ===")
print(con.execute("""
    SELECT
        COUNT(*)                            AS total_rows,
        MIN(timestamp)                      AS earliest,
        MAX(timestamp)                      AS latest,
        ROUND(MIN(low), 2)                  AS all_time_low,
        ROUND(MAX(high), 2)                 AS all_time_high,
        ROUND(AVG(volume), 0)               AS avg_volume_per_min
    FROM nq_1m
""").df().to_string(index=False))

# ── 2. Yearly summary ──────────────────────────────────────
print("\n=== YEARLY SUMMARY ===")
print(con.execute("""
    SELECT
        YEAR(timestamp)                     AS year,
        ROUND(MIN(low), 2)                  AS low,
        ROUND(MAX(high), 2)                 AS high,
        ROUND(MAX(high) - MIN(low), 2)      AS annual_range,
        ROUND(AVG(volume), 0)               AS avg_min_volume,
        COUNT(DISTINCT CAST(timestamp AS DATE)) AS trading_days
    FROM nq_1m
    GROUP BY YEAR(timestamp)
    ORDER BY year
""").df().to_string(index=False))

# ── 3. Best and worst days ever ────────────────────────────
print("\n=== TOP 5 BIGGEST UP DAYS ===")
print(con.execute("""
    SELECT
        CAST(timestamp AS DATE)             AS date,
        FIRST(open ORDER BY timestamp)      AS open,
        LAST(close ORDER BY timestamp)      AS close,
        ROUND(LAST(close ORDER BY timestamp) - FIRST(open ORDER BY timestamp), 2) AS points,
        ROUND((LAST(close ORDER BY timestamp) - FIRST(open ORDER BY timestamp))
            / FIRST(open ORDER BY timestamp) * 100, 2) AS pct
    FROM nq_1m
    GROUP BY CAST(timestamp AS DATE)
    ORDER BY points DESC
    LIMIT 5
""").df().to_string(index=False))

print("\n=== TOP 5 BIGGEST DOWN DAYS ===")
print(con.execute("""
    SELECT
        CAST(timestamp AS DATE)             AS date,
        FIRST(open ORDER BY timestamp)      AS open,
        LAST(close ORDER BY timestamp)      AS close,
        ROUND(LAST(close ORDER BY timestamp) - FIRST(open ORDER BY timestamp), 2) AS points,
        ROUND((LAST(close ORDER BY timestamp) - FIRST(open ORDER BY timestamp))
            / FIRST(open ORDER BY timestamp) * 100, 2) AS pct
    FROM nq_1m
    GROUP BY CAST(timestamp AS DATE)
    ORDER BY points ASC
    LIMIT 5
""").df().to_string(index=False))

# ── 4. Average range by hour of day ───────────────────────
print("\n=== AVG RANGE BY HOUR (which hours move most) ===")
print(con.execute("""
    SELECT
        HOUR(timestamp)                     AS hour,
        ROUND(AVG(high - low), 2)           AS avg_range,
        ROUND(AVG(volume), 0)               AS avg_volume
    FROM nq_1m
    GROUP BY HOUR(timestamp)
    ORDER BY hour
""").df().to_string(index=False))

# ── 5. Average range by day of week ───────────────────────
print("\n=== AVG DAILY RANGE BY DAY OF WEEK ===")
print(con.execute("""
    SELECT
        day,
        ROUND(AVG(daily_range), 2)          AS avg_range,
        ROUND(AVG(daily_volume), 0)         AS avg_volume
    FROM (
        SELECT
            CAST(timestamp AS DATE)         AS date,
            DAYNAME(CAST(timestamp AS DATE)) AS day,
            MAX(high) - MIN(low)            AS daily_range,
            SUM(volume)                     AS daily_volume
        FROM nq_1m
        GROUP BY CAST(timestamp AS DATE)
    )
    GROUP BY day
    ORDER BY AVG(daily_range) DESC
""").df().to_string(index=False))

con.close()