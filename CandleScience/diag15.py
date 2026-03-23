import duckdb
from pathlib import Path

DB_PATH = Path(__file__).parent / 'candle_science.duckdb'
con = duckdb.connect(str(DB_PATH))

for tbl in ["daily","intraday_feat","hourly","hourly2","r1_touch"]:
    con.execute(f"DROP TABLE IF EXISTS {tbl}")

con.execute("""CREATE OR REPLACE TEMP TABLE daily AS
SELECT date_trunc('day', timezone('America/New_York', timestamp))::DATE AS date
FROM nq_1m WHERE EXTRACT(dow FROM timezone('America/New_York', timestamp)) BETWEEN 1 AND 5
GROUP BY 1 HAVING MIN(timezone('America/New_York', timestamp)::TIME) <= '09:35'""")

con.execute("""CREATE OR REPLACE TEMP TABLE intraday_feat AS
SELECT
    date_trunc('day', timezone('America/New_York', timestamp))::DATE AS date,
    FIRST(open ORDER BY timestamp) FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '09:31') AS open_930,
    MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '09:59') AS hi_0930,
    MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '09:59') AS lo_0930,
    LAST(close ORDER BY timestamp) FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '15:59' AND '16:00') AS close_rth,
    MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '16:00') AS rth_high,
    MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '16:00') AS rth_low
FROM nq_1m GROUP BY 1""")

con.execute("""CREATE OR REPLACE TEMP TABLE hourly AS
SELECT
    date_trunc('day', timezone('America/New_York', timestamp))::DATE AS date,
    date_trunc('hour', timezone('America/New_York', timestamp))::TIME AS hr,
    MAX(high) AS h_high, MIN(low) AS h_low
FROM nq_1m
WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '10:00' AND '14:59'
GROUP BY 1, 2""")

con.execute("""CREATE OR REPLACE TEMP TABLE hourly2 AS
SELECT date, hr, h_high, h_low,
    LAG(h_low,  1) OVER (PARTITION BY date ORDER BY hr) AS prev_h_low,
    LAG(h_high, 1) OVER (PARTITION BY date ORDER BY hr) AS prev_h_high
FROM hourly""")

con.execute("""CREATE OR REPLACE TEMP TABLE r1_touch AS
SELECT f.date,
    SUM(CASE WHEN h.h_high >= f.lo_0930 AND h.h_low <= f.hi_0930 THEN 1 ELSE 0 END) AS touch_count
FROM hourly h JOIN intraday_feat f ON f.date = h.date GROUP BY f.date""")

con.execute("""CREATE OR REPLACE TEMP TABLE breach AS
SELECT date,
    MAX(CASE WHEN prev_h_low  IS NOT NULL AND h_low  < prev_h_low  THEN 1 ELSE 0 END) AS low_taken,
    MAX(CASE WHEN prev_h_high IS NOT NULL AND h_high > prev_h_high THEN 1 ELSE 0 END) AS high_taken
FROM hourly2 GROUP BY date""")

total = con.execute("""SELECT COUNT(*) FROM intraday_feat f JOIN daily d ON d.date=f.date
WHERE f.open_930 IS NOT NULL AND f.close_rth IS NOT NULL AND (f.rth_high-f.rth_low)>0""").fetchone()[0]

# How many of the thigh-gap+reversion days also have touch_count >= 5?
print("=== Overlap: Range2 candidates that are also touch>=5 (would be stolen by Range1) ===")
r = con.execute("""
SELECT
    SUM(CASE WHEN (f.hi_0930-f.lo_0930) > (f.rth_high-f.rth_low)*0.25
              AND ABS(f.close_rth-f.open_930) <= (f.rth_high-f.rth_low)*0.20 THEN 1 ELSE 0 END) AS r2_raw,
    SUM(CASE WHEN (f.hi_0930-f.lo_0930) > (f.rth_high-f.rth_low)*0.25
              AND ABS(f.close_rth-f.open_930) <= (f.rth_high-f.rth_low)*0.20
              AND t.touch_count >= 5 THEN 1 ELSE 0 END) AS r2_also_touch5,
    SUM(CASE WHEN (f.hi_0930-f.lo_0930) > (f.rth_high-f.rth_low)*0.25
              AND ABS(f.close_rth-f.open_930) <= (f.rth_high-f.rth_low)*0.20
              AND t.touch_count < 5 THEN 1 ELSE 0 END) AS r2_not_touch5
FROM intraday_feat f JOIN daily d ON d.date=f.date JOIN r1_touch t ON t.date=f.date
WHERE f.open_930 IS NOT NULL AND f.close_rth IS NOT NULL AND (f.rth_high-f.rth_low)>0
""").fetchone()
print(f"  Range2 candidates (gap>25% + revert<=20%): {r[0]} ({100*r[0]/total:.1f}%)")
print(f"    ...also touch>=5 (stolen by R1):  {r[1]} ({100*r[1]/total:.1f}%)")
print(f"    ...touch<5 (survive to R2):       {r[2]} ({100*r[2]/total:.1f}%)")
print()

# The fix: Range2 should take priority OVER Range1 when thigh gap is present
# Because the thigh gap is a more specific signature — it means the morning was NOT complex
# Test: Range2 first (thigh gap + reversion), THEN Range1 (touch>=5 for remaining days)
print("=== Priority: Range2 → Range1 → DNP → DWP ===")
print("(Range2 claimed first, then Range1 from remaining days)")
print()
for gap in [0.20, 0.25, 0.30]:
    for rev in [0.15, 0.20, 0.25]:
        rows = con.execute(f"""
        WITH classified AS (
            SELECT CASE
                -- Range2 FIRST: thigh gap morning + close reverts near 9:30
                WHEN (f.hi_0930-f.lo_0930) > (f.rth_high-f.rth_low)*{gap}
                 AND ABS(f.close_rth-f.open_930) <= (f.rth_high-f.rth_low)*{rev}
                THEN 'Range2'
                -- Range1: orbits 9:30 all day
                WHEN t.touch_count >= 5 THEN 'Range1'
                -- DNP: no low taken + strongly displaced close
                WHEN (f.close_rth > f.open_930 AND b.low_taken  = 0
                      AND ABS(f.close_rth-f.open_930) >= (f.rth_high-f.rth_low)*0.50)
                  OR (f.close_rth < f.open_930 AND b.high_taken = 0
                      AND ABS(f.close_rth-f.open_930) >= (f.rth_high-f.rth_low)*0.50)
                THEN 'DNP'
                ELSE 'DWP'
            END AS cls
            FROM intraday_feat f
            JOIN daily ON daily.date=f.date
            JOIN r1_touch t ON t.date=f.date
            JOIN breach b ON b.date=f.date
            WHERE f.open_930 IS NOT NULL AND f.close_rth IS NOT NULL
              AND f.rth_high IS NOT NULL AND (f.rth_high-f.rth_low)>0
        )
        SELECT cls, COUNT(*) n, ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(),1) pct
        FROM classified GROUP BY cls ORDER BY pct DESC
        """).fetchall()
        dist = {c:(n,p) for c,n,p in rows}
        r1=dist.get('Range1',(0,0)); r2=dist.get('Range2',(0,0))
        dnp=dist.get('DNP',(0,0));   dwp=dist.get('DWP',(0,0))
        print(f"gap>{gap:.0%} rev<={rev:.0%}:  R1={r1[1]}%({r1[0]})  DWP={dwp[1]}%({dwp[0]})  DNP={dnp[1]}%({dnp[0]})  R2={r2[1]}%({r2[0]})")
    print()

print("Targets: Range1=38%  DWP=32%  DNP=15%  Range2=12%")
