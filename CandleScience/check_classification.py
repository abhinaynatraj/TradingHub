"""
Run this on your machine to diagnose classification distributions.
Usage: python3 check_classification.py
"""
import duckdb
from pathlib import Path

DB_PATH = Path(__file__).parent / 'candle_science.duckdb'
con = duckdb.connect(str(DB_PATH), read_only=True)

con.execute("""
CREATE OR REPLACE TEMP TABLE intraday_feat AS
SELECT
    CAST(timezone('America/New_York', timestamp) AS DATE) AS date,
    FIRST(open ORDER BY timestamp) FILTER (
        WHERE EXTRACT(HOUR FROM timezone('America/New_York', timestamp)) = 9
          AND EXTRACT(MINUTE FROM timezone('America/New_York', timestamp)) = 30
    ) AS open_930,
    MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '09:30'
                       AND  timezone('America/New_York', timestamp)::TIME <  '10:00') AS hi_0930,
    MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '09:30'
                       AND  timezone('America/New_York', timestamp)::TIME <  '10:00') AS lo_0930,
    LAST(close ORDER BY timestamp) FILTER (
        WHERE timezone('America/New_York', timestamp)::TIME < '16:15'
    ) AS close_rth,
    MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '16:15') AS rth_high,
    MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '16:15') AS rth_low
FROM nq_1m
GROUP BY 1
""")

con.execute("""
CREATE OR REPLACE TEMP TABLE r1_touch AS
WITH hourly_afternoon AS (
    SELECT
        CAST(timezone('America/New_York', timestamp) AS DATE) AS date,
        EXTRACT(HOUR FROM timezone('America/New_York', timestamp))::INT AS hr,
        MAX(high) AS h_high,
        MIN(low)  AS h_low
    FROM nq_1m
    WHERE timezone('America/New_York', timestamp)::TIME >= '10:00'
      AND timezone('America/New_York', timestamp)::TIME <  '15:00'
    GROUP BY 1, 2
)
SELECT
    h.date,
    SUM(CASE WHEN h.h_low <= f.open_930 AND h.h_high >= f.open_930 THEN 1 ELSE 0 END) AS touch_count
FROM hourly_afternoon h
JOIN intraday_feat f ON f.date = h.date
GROUP BY h.date
""")

print("=" * 60)
print("touch_count distribution (how many hours 10-14 touch 9:30 candle)")
print("=" * 60)
rows = con.execute("""
    SELECT touch_count, COUNT(*) as n FROM r1_touch GROUP BY 1 ORDER BY 1
""").fetchall()
total = sum(r[1] for r in rows)
for tc, n in rows:
    bar = '█' * int(n/total*40)
    print(f"  {tc} hours: {n:4d} ({n/total*100:5.1f}%)  {bar}")
print()
for thresh in [1,2,3,4,5]:
    n = sum(r[1] for r in rows if r[0] >= thresh)
    print(f"  >= {thresh} touches: {n:4d} ({n/total*100:.1f}%)")

print()
print("=" * 60)
print("9:30 candle size as % of daily range (hi_0930-lo_0930 / rth_high-rth_low)")
print("=" * 60)
rows2 = con.execute("""
    SELECT
        ROUND((hi_0930 - lo_0930) / NULLIF(rth_high - rth_low, 0) * 100) AS pct_bucket,
        COUNT(*) as n
    FROM intraday_feat
    WHERE rth_high IS NOT NULL AND (rth_high - rth_low) > 0
    GROUP BY 1 ORDER BY 1
""").fetchall()
total2 = sum(r[1] for r in rows2)
cumulative = 0
for pct, n in rows2:
    cumulative += n
    if pct is not None and pct <= 80:
        print(f"  9:30 candle = {int(pct):3d}% of day range: {n:4d} days  (cumulative {cumulative/total2*100:.1f}%)")

con.close()
print("\nDone.")
