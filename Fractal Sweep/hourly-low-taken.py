import duckdb
import pandas as pd

con = duckdb.connect("NQ_futures.duckdb")

df = con.execute("""
    WITH hourly AS (
        SELECT 
            DATE_TRUNC('hour', timestamp) AS hour_ts,
            CAST(timestamp AS DATE) AS date,
            HOUR(timestamp) AS hour_of_day,
            MIN(low) AS low
        FROM nq_1m
        GROUP BY DATE_TRUNC('hour', timestamp), CAST(timestamp AS DATE), HOUR(timestamp)
    ),
    daily_stats AS (
        SELECT
            date,
            -- Low of the day up to 12pm
            MIN(CASE WHEN hour_of_day < 12 THEN low END) AS low_before_noon,
            -- Lowest low after 12pm
            MIN(CASE WHEN hour_of_day >= 12 THEN low END) AS low_after_noon
        FROM hourly
        GROUP BY date
    )
    SELECT
        COUNT(*) AS total_days,
        SUM(CASE WHEN low_after_noon < low_before_noon THEN 1 ELSE 0 END) AS days_low_taken_after_noon,
        ROUND(
            SUM(CASE WHEN low_after_noon < low_before_noon THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2
        ) AS pct_days
    FROM daily_stats
    WHERE low_before_noon IS NOT NULL AND low_after_noon IS NOT NULL
""").df()

con.close()
print(df)