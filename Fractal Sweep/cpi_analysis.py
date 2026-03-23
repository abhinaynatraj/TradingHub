#!/usr/bin/env python3
"""
Candle Science — Pre-CPI Day Statistical Analysis
===================================================
Compares pre-CPI trading days against all other days across:
  1. Day type distribution (Range1 / DWP / DNP / Range2)
  2. Session ranges vs quarterly baseline (overspend/underspend)
  3. HOD/LOD timing distribution
  4. Session variable false rates (Asia, London, NY1)
  5. OU line hit rates
  6. RTH range size vs 10-day median

Usage:
    python3 cpi_analysis.py
    python3 cpi_analysis.py --symbol ES
    python3 cpi_analysis.py --symbol NQ --output cpi_report.json

Output:
    Prints a formatted report to stdout.
    Optionally writes full JSON to --output file.
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).parent / "candle_science.duckdb"

INSTRUMENTS = {
    "NQ": {"table": "nq_1m", "ref_price": 21000},
    "ES": {"table": "es_1m", "ref_price": 5800},
}

# ─────────────────────────────────────────────────────────────────────────────
# CPI RELEASE DATES (BLS, 8:30 ET)
# Source: U.S. Bureau of Labor Statistics historical release calendar
# These are the actual CPI release dates — we analyse the DAY BEFORE each.
# ─────────────────────────────────────────────────────────────────────────────
CPI_RELEASE_DATES = [
    # 2014
    "2014-01-17", "2014-02-20", "2014-03-18", "2014-04-15", "2014-05-15",
    "2014-06-17", "2014-07-22", "2014-08-19", "2014-09-17", "2014-10-22",
    "2014-11-20", "2014-12-17",
    # 2015
    "2015-01-16", "2015-02-26", "2015-03-24", "2015-04-17", "2015-05-22",
    "2015-06-18", "2015-07-17", "2015-08-19", "2015-09-16", "2015-10-15",
    "2015-11-17", "2015-12-15",
    # 2016
    "2016-01-20", "2016-02-19", "2016-03-16", "2016-04-14", "2016-05-17",
    "2016-06-16", "2016-07-15", "2016-08-16", "2016-09-16", "2016-10-18",
    "2016-11-17", "2016-12-15",
    # 2017
    "2017-01-18", "2017-02-15", "2017-03-15", "2017-04-14", "2017-05-12",
    "2017-06-14", "2017-07-14", "2017-08-11", "2017-09-14", "2017-10-13",
    "2017-11-15", "2017-12-13",
    # 2018
    "2018-01-12", "2018-02-14", "2018-03-13", "2018-04-11", "2018-05-10",
    "2018-06-12", "2018-07-12", "2018-08-10", "2018-09-13", "2018-10-11",
    "2018-11-14", "2018-12-12",
    # 2019
    "2019-01-11", "2019-02-13", "2019-03-12", "2019-04-10", "2019-05-10",
    "2019-06-12", "2019-07-11", "2019-08-13", "2019-09-12", "2019-10-10",
    "2019-11-13", "2019-12-11",
    # 2020
    "2020-01-14", "2020-02-13", "2020-03-11", "2020-04-10", "2020-05-12",
    "2020-06-10", "2020-07-14", "2020-08-12", "2020-09-11", "2020-10-13",
    "2020-11-12", "2020-12-10",
    # 2021
    "2021-01-13", "2021-02-10", "2021-03-10", "2021-04-13", "2021-05-12",
    "2021-06-10", "2021-07-13", "2021-08-11", "2021-09-14", "2021-10-13",
    "2021-11-10", "2021-12-10",
    # 2022
    "2022-01-12", "2022-02-10", "2022-03-10", "2022-04-12", "2022-05-11",
    "2022-06-10", "2022-07-13", "2022-08-10", "2022-09-13", "2022-10-13",
    "2022-11-10", "2022-12-13",
    # 2023
    "2023-01-12", "2023-02-14", "2023-03-14", "2023-04-12", "2023-05-10",
    "2023-06-13", "2023-07-12", "2023-08-10", "2023-09-13", "2023-10-12",
    "2023-11-14", "2023-12-12",
    # 2024
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15",
    "2024-06-12", "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10",
    "2024-11-13", "2024-12-11",
    # 2025
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13",
    "2025-06-11", "2025-07-15", "2025-08-12", "2025-09-10", "2025-10-15",
    "2025-11-13", "2025-12-10",
]

TIME_BUCKETS = [
    ("18:00–02:29", "18:00", "02:29"),
    ("02:30–07:29", "02:30", "07:29"),
    ("07:30–09:29", "07:30", "09:29"),
    ("09:30–10:29", "09:30", "10:29"),
    ("10:30–12:29", "10:30", "12:29"),
    ("12:30–14:59", "12:30", "14:59"),
    ("15:00–16:29", "15:00", "16:29"),
]


def get_pre_cpi_dates():
    """Return trading days immediately before each CPI release date."""
    pre_cpi = []
    for ds in CPI_RELEASE_DATES:
        d = date.fromisoformat(ds)
        # Step back to the previous weekday
        prev = d - timedelta(days=1)
        while prev.weekday() >= 5:  # skip Saturday (5) and Sunday (6)
            prev -= timedelta(days=1)
        pre_cpi.append(str(prev))
    return sorted(set(pre_cpi))


def pct(n, total):
    return round(n / total * 100, 1) if total > 0 else 0.0


def bar(val, total, width=30):
    filled = int(round(val / total * width)) if total > 0 else 0
    return "█" * filled + "░" * (width - filled)


def analyse(symbol: str, con) -> dict:
    cfg   = INSTRUMENTS[symbol]
    table = cfg["table"]
    ref   = cfg["ref_price"]

    pre_cpi_dates = get_pre_cpi_dates()
    dates_sql = ", ".join(f"'{d}'" for d in pre_cpi_dates)

    print(f"\n[{symbol}] Building base tables…")

    # ── daily OHLC features ────────────────────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE daily AS
        SELECT
            CAST(timezone('America/New_York', timestamp) AS DATE) AS date,
            FIRST(open ORDER BY timestamp)
                FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '09:30'
                           AND timezone('America/New_York', timestamp)::TIME <  '09:31') AS open_930,
            MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '16:15') AS rth_high,
            MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '16:15') AS rth_low,
            LAST(close ORDER BY timestamp)
                FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '16:15') AS close_rth,
            MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '09:31') AS hi_0930,
            MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '09:31') AS lo_0930
        FROM {table}
        GROUP BY 1
    """)

    # ── touch count (Range1 detection) ────────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE r1_touch AS
        SELECT
            CAST(timezone('America/New_York', timestamp) AS DATE) AS date,
            COUNT(DISTINCT DATE_TRUNC('hour', timezone('America/New_York', timestamp)))
                FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '10:00' AND '14:59') AS touch_count
        FROM {table} t
        JOIN daily d ON CAST(timezone('America/New_York', t.timestamp) AS DATE) = d.date
        WHERE timezone('America/New_York', t.timestamp)::TIME BETWEEN '10:00' AND '14:59'
          AND t.low  <= d.open_930
          AND t.high >= d.open_930
        GROUP BY 1
    """)

    # ── hourly breach (for DNP check) ────────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE hourly_struct AS
        WITH hourly AS (
            SELECT
                CAST(timezone('America/New_York', timestamp) AS DATE) AS date,
                DATE_TRUNC('hour', timezone('America/New_York', timestamp)) AS hr,
                MAX(high) AS h_high,
                MIN(low)  AS h_low
            FROM {table}
            WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '10:00' AND '14:59'
            GROUP BY 1, 2
        )
        SELECT
            d.date,
            MAX(CASE WHEN h.h_high > d.open_930 THEN 1 ELSE 0 END) AS bull_breach,
            MAX(CASE WHEN h.h_low  < d.open_930 THEN 1 ELSE 0 END) AS bear_breach,
            COALESCE(MAX(t.touch_count), 0) AS touch_count
        FROM daily d
        LEFT JOIN hourly h ON h.date = d.date
        LEFT JOIN r1_touch t ON t.date = d.date
        WHERE d.open_930 IS NOT NULL
        GROUP BY d.date
    """)

    # ── day classification ────────────────────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE day_class AS
        SELECT
            f.date,
            CASE
                WHEN s.touch_count >= 5 THEN 'Range1'
                WHEN (f.close_rth > f.open_930
                      AND s.bull_breach = 0
                      AND ABS(f.close_rth - f.open_930) >= (f.rth_high - f.rth_low) * 0.50)
                  OR (f.close_rth < f.open_930
                      AND s.bear_breach = 0
                      AND ABS(f.close_rth - f.open_930) >= (f.rth_high - f.rth_low) * 0.50)
                THEN 'DNP'
                WHEN (f.rth_high - f.rth_low) > 0
                 AND (f.hi_0930 - f.lo_0930) > (f.rth_high - f.rth_low) * 0.20
                 AND ABS(f.close_rth - f.open_930) <= (f.rth_high - f.rth_low) * 0.20
                THEN 'Range2'
                ELSE 'DWP'
            END AS classification
        FROM daily f
        JOIN hourly_struct s ON s.date = f.date
        WHERE f.open_930 IS NOT NULL AND f.rth_high IS NOT NULL AND f.rth_low IS NOT NULL
          AND (f.rth_high - f.rth_low) > 0
    """)

    # ── session ranges ────────────────────────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE session_ranges AS
        SELECT
            CAST(timezone('America/New_York', timestamp) AS DATE) AS date,
            MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '16:15')
          - MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME BETWEEN '09:30' AND '16:15')
            AS rth_range,
            MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '18:00'
                               OR  timezone('America/New_York', timestamp)::TIME <  '02:30')
          - MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '18:00'
                               OR  timezone('America/New_York', timestamp)::TIME <  '02:30')
            AS asia_range,
            MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '02:30'
                               AND  timezone('America/New_York', timestamp)::TIME <  '07:30')
          - MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '02:30'
                               AND  timezone('America/New_York', timestamp)::TIME <  '07:30')
            AS london_range,
            MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '07:30'
                               AND  timezone('America/New_York', timestamp)::TIME <  '11:30')
          - MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '07:30'
                               AND  timezone('America/New_York', timestamp)::TIME <  '11:30')
            AS ny1_range,
            MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '11:30'
                               AND  timezone('America/New_York', timestamp)::TIME <  '16:15')
          - MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '11:30'
                               AND  timezone('America/New_York', timestamp)::TIME <  '16:15')
            AS ny2_range
        FROM {table}
        GROUP BY 1
    """)

    # ── 15-min bars for HOD/LOD ───────────────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE bars_15m AS
        SELECT
            CAST(timezone('America/New_York', timestamp) AS DATE) AS date,
            CAST(
                DATE_TRUNC('hour', timezone('America/New_York', timestamp))
                + INTERVAL '15 minutes'
                  * FLOOR(EXTRACT(MINUTE FROM timezone('America/New_York', timestamp)) / 15)::INT
            AS TIME) AS t15,
            MAX(high) AS bar_high,
            MIN(low)  AS bar_low
        FROM {table}
        GROUP BY 1, 2
    """)

    con.execute("""
        CREATE OR REPLACE TEMP TABLE hod_lod AS
        WITH day_ext AS (
            SELECT date, MAX(bar_high) AS day_high, MIN(bar_low) AS day_low
            FROM bars_15m GROUP BY date
        ),
        hod_bar AS (
            SELECT b.date, MIN(b.t15) AS hod_t
            FROM bars_15m b JOIN day_ext e ON e.date=b.date AND b.bar_high=e.day_high
            GROUP BY b.date
        ),
        lod_bar AS (
            SELECT b.date, MIN(b.t15) AS lod_t
            FROM bars_15m b JOIN day_ext e ON e.date=b.date AND b.bar_low=e.day_low
            GROUP BY b.date
        )
        SELECT h.date, h.hod_t, l.lod_t
        FROM hod_bar h JOIN lod_bar l ON l.date=h.date
    """)

    # ── session variables ────────────────────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE session_vars AS
        WITH
        asia_raw AS (
            SELECT
                CASE
                    WHEN timezone('America/New_York', timestamp)::TIME >= '18:00'
                    THEN CAST(timezone('America/New_York', timestamp) AS DATE) + INTERVAL '1 day'
                    ELSE CAST(timezone('America/New_York', timestamp) AS DATE)
                END AS trading_date,
                timezone('America/New_York', timestamp)::TIME AS t,
                high, low
            FROM {table}
            WHERE (timezone('America/New_York', timestamp)::TIME >= '18:00'
                OR timezone('America/New_York', timestamp)::TIME < '02:30')
        ),
        asia_fc AS (
            SELECT trading_date,
                MAX(high) AS fc_hi, MIN(low) AS fc_lo,
                (MAX(high) + MIN(low)) / 2 AS fc_mid
            FROM asia_raw WHERE t >= '18:00' AND t < '19:30' GROUP BY 1
        ),
        asia_var AS (
            SELECT trading_date, MAX(high) AS var_hi, MIN(low) AS var_lo
            FROM asia_raw WHERE t >= '19:30' OR t < '02:30' GROUP BY 1
        ),
        lon_raw AS (
            SELECT CAST(timezone('America/New_York', timestamp) AS DATE) AS d,
                timezone('America/New_York', timestamp)::TIME AS t,
                high, low
            FROM {table}
            WHERE timezone('America/New_York', timestamp)::TIME >= '02:30'
              AND timezone('America/New_York', timestamp)::TIME < '07:30'
        ),
        lon_fc AS (
            SELECT d, MAX(high) AS fc_hi, MIN(low) AS fc_lo, (MAX(high)+MIN(low))/2 AS fc_mid
            FROM lon_raw WHERE t >= '02:30' AND t < '03:30' GROUP BY 1
        ),
        lon_var AS (
            SELECT d, MAX(high) AS var_hi, MIN(low) AS var_lo
            FROM lon_raw WHERE t >= '03:30' AND t < '07:30' GROUP BY 1
        ),
        ny1_raw AS (
            SELECT CAST(timezone('America/New_York', timestamp) AS DATE) AS d,
                timezone('America/New_York', timestamp)::TIME AS t,
                high, low
            FROM {table}
            WHERE timezone('America/New_York', timestamp)::TIME >= '07:30'
              AND timezone('America/New_York', timestamp)::TIME < '11:30'
        ),
        ny1_fc AS (
            SELECT d, MAX(high) AS fc_hi, MIN(low) AS fc_lo, (MAX(high)+MIN(low))/2 AS fc_mid
            FROM ny1_raw WHERE t >= '07:30' AND t < '08:30' GROUP BY 1
        ),
        ny1_var AS (
            SELECT d, MAX(high) AS var_hi, MIN(low) AS var_lo
            FROM ny1_raw WHERE t >= '08:30' AND t < '11:30' GROUP BY 1
        )
        SELECT
            af.trading_date AS date,
            -- Asia
            CASE WHEN av.var_hi > af.fc_hi THEN TRUE
                 WHEN av.var_lo < af.fc_lo THEN FALSE ELSE NULL END AS asia_long,
            CASE WHEN av.var_hi > af.fc_hi AND av.var_lo >= af.fc_lo THEN TRUE
                 WHEN av.var_hi > af.fc_hi AND av.var_lo <  af.fc_lo THEN FALSE
                 WHEN av.var_lo < af.fc_lo AND av.var_hi <= af.fc_hi THEN TRUE
                 WHEN av.var_lo < af.fc_lo AND av.var_hi >  af.fc_hi THEN FALSE
                 ELSE NULL END AS asia_true,
            -- London
            CASE WHEN lv.var_hi > lf.fc_hi THEN TRUE
                 WHEN lv.var_lo < lf.fc_lo THEN FALSE ELSE NULL END AS lon_long,
            CASE WHEN lv.var_hi > lf.fc_hi AND lv.var_lo >= lf.fc_lo THEN TRUE
                 WHEN lv.var_hi > lf.fc_hi AND lv.var_lo <  lf.fc_lo THEN FALSE
                 WHEN lv.var_lo < lf.fc_lo AND lv.var_hi <= lf.fc_hi THEN TRUE
                 WHEN lv.var_lo < lf.fc_lo AND lv.var_hi >  lf.fc_hi THEN FALSE
                 ELSE NULL END AS lon_true,
            -- NY1
            CASE WHEN n1v.var_hi > n1f.fc_hi THEN TRUE
                 WHEN n1v.var_lo < n1f.fc_lo THEN FALSE ELSE NULL END AS ny1_long,
            CASE WHEN n1v.var_hi > n1f.fc_hi AND n1v.var_lo >= n1f.fc_lo THEN TRUE
                 WHEN n1v.var_hi > n1f.fc_hi AND n1v.var_lo <  n1f.fc_lo THEN FALSE
                 WHEN n1v.var_lo < n1f.fc_lo AND n1v.var_hi <= n1f.fc_hi THEN TRUE
                 WHEN n1v.var_lo < n1f.fc_lo AND n1v.var_hi >  n1f.fc_hi THEN FALSE
                 ELSE NULL END AS ny1_true,
            -- OU (midline)
            af.fc_mid AS asia_ou,
            lf.fc_mid AS lon_ou,
            n1f.fc_mid AS ny1_ou
        FROM asia_fc   af
        JOIN asia_var  av  ON av.trading_date = af.trading_date
        JOIN lon_fc    lf  ON lf.d  = af.trading_date
        JOIN lon_var   lv  ON lv.d  = af.trading_date
        JOIN ny1_fc    n1f ON n1f.d = af.trading_date
        JOIN ny1_var   n1v ON n1v.d = af.trading_date
    """)

    # ── OU line hits ──────────────────────────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ou_hits AS
        SELECT
            sv.date,
            sv.asia_ou,  sv.lon_ou,  sv.ny1_ou,
            -- Asia OU hit: did price cross midline after 02:30?
            CASE WHEN MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '02:30'
                                          AND  timezone('America/New_York', timestamp)::TIME <  '09:30') <= sv.asia_ou
                  AND MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '02:30'
                                          AND  timezone('America/New_York', timestamp)::TIME <  '09:30') >= sv.asia_ou
                 THEN TRUE ELSE FALSE END AS asia_ou_hit,
            -- London OU hit: did price cross midline after 07:30?
            CASE WHEN MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '07:30'
                                          AND  timezone('America/New_York', timestamp)::TIME <  '11:30') <= sv.lon_ou
                  AND MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '07:30'
                                          AND  timezone('America/New_York', timestamp)::TIME <  '11:30') >= sv.lon_ou
                 THEN TRUE ELSE FALSE END AS lon_ou_hit,
            -- NY1 OU hit: did price cross midline after 11:30?
            CASE WHEN MIN(low)  FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '11:30'
                                          AND  timezone('America/New_York', timestamp)::TIME <  '16:15') <= sv.ny1_ou
                  AND MAX(high) FILTER (WHERE timezone('America/New_York', timestamp)::TIME >= '11:30'
                                          AND  timezone('America/New_York', timestamp)::TIME <  '16:15') >= sv.ny1_ou
                 THEN TRUE ELSE FALSE END AS ny1_ou_hit
        FROM session_vars sv
        JOIN {table} m ON CAST(timezone('America/New_York', m.timestamp) AS DATE) = sv.date
        GROUP BY sv.date, sv.asia_ou, sv.lon_ou, sv.ny1_ou
    """)

    print(f"[{symbol}] Running pre-CPI comparisons…")

    # ── ANALYSIS 1: Day type distribution ─────────────────────────────────
    def day_type_dist(where_clause):
        rows = con.execute(f"""
            SELECT classification, COUNT(*) AS n
            FROM day_class
            WHERE {where_clause}
            GROUP BY classification ORDER BY classification
        """).fetchall()
        total = sum(r[1] for r in rows)
        return {r[0]: {"n": r[1], "pct": pct(r[1], total)} for r in rows}, total

    pre_dist, pre_n   = day_type_dist(f"date IN ({dates_sql})")
    all_dist, all_n   = day_type_dist("1=1")
    other_dist, other_n = day_type_dist(f"date NOT IN ({dates_sql})")

    # ── ANALYSIS 2: Session range medians ─────────────────────────────────
    def range_medians(where_clause):
        row = con.execute(f"""
            SELECT
                MEDIAN(rth_range)    AS rth,
                MEDIAN(asia_range)   AS asia,
                MEDIAN(london_range) AS london,
                MEDIAN(ny1_range)    AS ny1,
                MEDIAN(ny2_range)    AS ny2,
                COUNT(*)             AS n
            FROM session_ranges
            WHERE rth_range IS NOT NULL AND {where_clause}
        """).fetchone()
        if row:
            return {"rth": round(float(row[0] or 0), 1), "asia": round(float(row[1] or 0), 1),
                    "london": round(float(row[2] or 0), 1), "ny1": round(float(row[3] or 0), 1),
                    "ny2": round(float(row[4] or 0), 1), "n": row[5]}
        return {}

    pre_ranges   = range_medians(f"date IN ({dates_sql})")
    all_ranges   = range_medians("1=1")

    # ── ANALYSIS 3: HOD/LOD timing buckets ───────────────────────────────
    def hod_lod_buckets(where_clause):
        results = {}
        for label, t_start, t_end in TIME_BUCKETS:
            if t_start > t_end:  # overnight wrap
                cond_hod = f"(hod_t >= '{t_start}' OR hod_t <= '{t_end}')"
                cond_lod = f"(lod_t >= '{t_start}' OR lod_t <= '{t_end}')"
            else:
                cond_hod = f"hod_t BETWEEN '{t_start}' AND '{t_end}'"
                cond_lod = f"lod_t BETWEEN '{t_start}' AND '{t_end}'"
            hod_n = con.execute(f"SELECT COUNT(*) FROM hod_lod WHERE {cond_hod} AND {where_clause}").fetchone()[0]
            lod_n = con.execute(f"SELECT COUNT(*) FROM hod_lod WHERE {cond_lod} AND {where_clause}").fetchone()[0]
            results[label] = {"hod": hod_n, "lod": lod_n}
        total = con.execute(f"SELECT COUNT(*) FROM hod_lod WHERE {where_clause}").fetchone()[0]
        return results, total

    pre_hl, pre_hl_n = hod_lod_buckets(f"date IN ({dates_sql})")
    all_hl, all_hl_n = hod_lod_buckets("1=1")

    # ── ANALYSIS 4: Session false rates ───────────────────────────────────
    def false_rates(where_clause):
        row = con.execute(f"""
            SELECT
                COUNT(*) AS n,
                SUM(CASE WHEN asia_long IS NOT NULL THEN 1 ELSE 0 END)  AS asia_valid,
                SUM(CASE WHEN asia_true = FALSE    THEN 1 ELSE 0 END)  AS asia_false,
                SUM(CASE WHEN lon_long  IS NOT NULL THEN 1 ELSE 0 END)  AS lon_valid,
                SUM(CASE WHEN lon_true  = FALSE    THEN 1 ELSE 0 END)  AS lon_false,
                SUM(CASE WHEN ny1_long  IS NOT NULL THEN 1 ELSE 0 END)  AS ny1_valid,
                SUM(CASE WHEN ny1_true  = FALSE    THEN 1 ELSE 0 END)  AS ny1_false
            FROM session_vars
            WHERE {where_clause}
        """).fetchone()
        if row:
            return {
                "n": row[0],
                "asia_false_pct": pct(row[2], row[1]),
                "lon_false_pct":  pct(row[4], row[3]),
                "ny1_false_pct":  pct(row[6], row[5]),
            }
        return {}

    pre_sv  = false_rates(f"date IN ({dates_sql})")
    all_sv  = false_rates("1=1")

    # ── ANALYSIS 5: OU hit rates ───────────────────────────────────────────
    def ou_rates(where_clause):
        row = con.execute(f"""
            SELECT
                COUNT(*) AS n,
                SUM(CASE WHEN asia_ou_hit THEN 1 ELSE 0 END) AS asia_hits,
                SUM(CASE WHEN lon_ou_hit  THEN 1 ELSE 0 END) AS lon_hits,
                SUM(CASE WHEN ny1_ou_hit  THEN 1 ELSE 0 END) AS ny1_hits
            FROM ou_hits
            WHERE {where_clause}
        """).fetchone()
        if row:
            return {
                "n": row[0],
                "asia_pct": pct(row[1], row[0]),
                "lon_pct":  pct(row[2], row[0]),
                "ny1_pct":  pct(row[3], row[0]),
            }
        return {}

    pre_ou  = ou_rates(f"date IN ({dates_sql})")
    all_ou  = ou_rates("1=1")

    # ── ANALYSIS 6: HOD/LOD mode and median ───────────────────────────────
    def hod_lod_mode_median(where_clause):
        hod = con.execute(f"""
            SELECT CAST(hod_t AS VARCHAR), COUNT(*) AS n
            FROM hod_lod WHERE {where_clause} AND hod_t IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC LIMIT 1
        """).fetchone()
        lod = con.execute(f"""
            SELECT CAST(lod_t AS VARCHAR), COUNT(*) AS n
            FROM hod_lod WHERE {where_clause} AND lod_t IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC LIMIT 1
        """).fetchone()
        return {
            "hod_mode": hod[0] if hod else None,
            "lod_mode": lod[0] if lod else None,
        }

    pre_mode = hod_lod_mode_median(f"date IN ({dates_sql})")
    all_mode = hod_lod_mode_median("1=1")

    # ── Build matched pre-CPI sample list ────────────────────────────────
    matched = con.execute(f"""
        SELECT date FROM day_class WHERE date IN ({dates_sql}) ORDER BY date
    """).fetchall()
    matched_dates = [r[0] for r in matched]

    return {
        "symbol": symbol,
        "pre_cpi_dates_analysed": len(matched_dates),
        "pre_cpi_dates_in_db": matched_dates,
        "all_trading_days": all_n,
        "day_type": {
            "pre_cpi": pre_dist,
            "all_days": all_dist,
        },
        "session_ranges": {
            "pre_cpi": pre_ranges,
            "all_days": all_ranges,
        },
        "hod_lod_buckets": {
            "pre_cpi": {"buckets": pre_hl, "n": pre_hl_n},
            "all_days": {"buckets": all_hl, "n": all_hl_n},
        },
        "hod_lod_mode": {
            "pre_cpi": pre_mode,
            "all_days": all_mode,
        },
        "session_false_rates": {
            "pre_cpi": pre_sv,
            "all_days": all_sv,
        },
        "ou_hit_rates": {
            "pre_cpi": pre_ou,
            "all_days": all_ou,
        },
    }


def print_report(r: dict):
    sym   = r["symbol"]
    n     = r["pre_cpi_dates_analysed"]
    all_n = r["all_trading_days"]

    def delta(pre_val, all_val, invert=False):
        d = pre_val - all_val
        if invert: d = -d
        sym_str = "▲" if d > 0 else ("▼" if d < 0 else "–")
        return f"{sym_str}{abs(d):.1f}pp"

    print(f"\n{'='*65}")
    print(f"  PRE-CPI DAY ANALYSIS  ·  {sym}  ·  {n} events vs {all_n} all days")
    print(f"{'='*65}")

    # ── Day types ────────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  DAY TYPE DISTRIBUTION")
    print(f"{'─'*65}")
    print(f"  {'TYPE':<12}  {'PRE-CPI':>9}  {'ALL DAYS':>9}  {'DELTA':>8}  BAR")
    print(f"  {'─'*12}  {'─'*9}  {'─'*9}  {'─'*8}  {'─'*28}")
    for dt in ["Range1", "DWP", "DNP", "Range2"]:
        pre_pct = r["day_type"]["pre_cpi"].get(dt, {}).get("pct", 0)
        all_pct = r["day_type"]["all_days"].get(dt, {}).get("pct", 0)
        pre_nn  = r["day_type"]["pre_cpi"].get(dt, {}).get("n", 0)
        d_str   = delta(pre_pct, all_pct)
        b       = bar(pre_nn, n, 28)
        print(f"  {dt:<12}  {pre_pct:>8.1f}%  {all_pct:>8.1f}%  {d_str:>8}  {b}")

    # ── Session ranges ────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  SESSION MEDIAN RANGES  (pre-CPI vs all days, in points)")
    print(f"{'─'*65}")
    sr_pre = r["session_ranges"]["pre_cpi"]
    sr_all = r["session_ranges"]["all_days"]
    print(f"  {'SESSION':<12}  {'PRE-CPI':>9}  {'ALL DAYS':>9}  {'% OF ALL':>9}")
    print(f"  {'─'*12}  {'─'*9}  {'─'*9}  {'─'*9}")
    for sess in ["rth", "asia", "london", "ny1", "ny2"]:
        pre_v = sr_pre.get(sess, 0)
        all_v = sr_all.get(sess, 1)
        ratio = round(pre_v / all_v * 100, 1) if all_v else 0
        flag  = " ◀ COMPRESSED" if ratio < 88 else (" ◀ EXPANDED" if ratio > 112 else "")
        print(f"  {sess.upper():<12}  {pre_v:>9.1f}  {all_v:>9.1f}  {ratio:>8.1f}%{flag}")

    # ── Session false rates ───────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  SESSION FALSE RATES  (price reverses after FC breakout)")
    print(f"{'─'*65}")
    sv_pre = r["session_false_rates"]["pre_cpi"]
    sv_all = r["session_false_rates"]["all_days"]
    print(f"  {'SESSION':<12}  {'PRE-CPI':>9}  {'ALL DAYS':>9}  {'DELTA':>8}")
    print(f"  {'─'*12}  {'─'*9}  {'─'*9}  {'─'*8}")
    for sess, key in [("Asia", "asia_false_pct"), ("London", "lon_false_pct"), ("NY1", "ny1_false_pct")]:
        pre_v = sv_pre.get(key, 0)
        all_v = sv_all.get(key, 0)
        d_str = delta(pre_v, all_v)
        print(f"  {sess:<12}  {pre_v:>8.1f}%  {all_v:>8.1f}%  {d_str:>8}")

    # ── OU hit rates ──────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  OU LINE HIT RATES  (FC midline taken after variable phase)")
    print(f"{'─'*65}")
    ou_pre = r["ou_hit_rates"]["pre_cpi"]
    ou_all = r["ou_hit_rates"]["all_days"]
    print(f"  {'SESSION':<12}  {'PRE-CPI':>9}  {'ALL DAYS':>9}  {'DELTA':>8}")
    print(f"  {'─'*12}  {'─'*9}  {'─'*9}  {'─'*8}")
    for sess, key in [("Asia OU", "asia_pct"), ("London OU", "lon_pct"), ("NY1 OU", "ny1_pct")]:
        pre_v = ou_pre.get(key, 0)
        all_v = ou_all.get(key, 0)
        d_str = delta(pre_v, all_v)
        print(f"  {sess:<12}  {pre_v:>8.1f}%  {all_v:>8.1f}%  {d_str:>8}")

    # ── HOD/LOD timing ────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  HOD / LOD TIMING BUCKETS")
    print(f"{'─'*65}")
    hl_pre   = r["hod_lod_buckets"]["pre_cpi"]
    hl_all   = r["hod_lod_buckets"]["all_days"]
    hl_pre_n = hl_pre["n"]
    hl_all_n = hl_all["n"]
    print(f"  {'WINDOW':<18}  {'HOD pre':>7}  {'HOD all':>7}  {'LOD pre':>7}  {'LOD all':>7}")
    print(f"  {'─'*18}  {'─'*7}  {'─'*7}  {'─'*7}  {'─'*7}")
    for label in [b[0] for b in TIME_BUCKETS]:
        hod_pre = pct(hl_pre["buckets"].get(label, {}).get("hod", 0), hl_pre_n)
        hod_all = pct(hl_all["buckets"].get(label, {}).get("hod", 0), hl_all_n)
        lod_pre = pct(hl_pre["buckets"].get(label, {}).get("lod", 0), hl_pre_n)
        lod_all = pct(hl_all["buckets"].get(label, {}).get("lod", 0), hl_all_n)
        flag = ""
        if label == "09:30–10:29" and hod_pre > hod_all + 3: flag = " ◀ HOD ELEVATED"
        if label == "09:30–10:29" and lod_pre > lod_all + 3: flag = " ◀ LOD ELEVATED"
        print(f"  {label:<18}  {hod_pre:>6.1f}%  {hod_all:>6.1f}%  {lod_pre:>6.1f}%  {lod_all:>6.1f}%{flag}")

    # ── Mode summary ─────────────────────────────────────────────────────
    pm = r["hod_lod_mode"]
    print(f"\n{'─'*65}")
    print(f"  HOD/LOD MODE TIMES")
    print(f"{'─'*65}")
    print(f"  {'':18}  {'PRE-CPI':>12}  {'ALL DAYS':>12}")
    print(f"  HOD mode         {pm['pre_cpi'].get('hod_mode','—'):>12}  {pm['all_days'].get('hod_mode','—'):>12}")
    print(f"  LOD mode         {pm['pre_cpi'].get('lod_mode','—'):>12}  {pm['all_days'].get('lod_mode','—'):>12}")

    # ── Takeaways ─────────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  KEY TAKEAWAYS")
    print(f"{'─'*65}")

    range1_pre = r["day_type"]["pre_cpi"].get("Range1", {}).get("pct", 0)
    range1_all = r["day_type"]["all_days"].get("Range1", {}).get("pct", 0)
    range2_pre = r["day_type"]["pre_cpi"].get("Range2", {}).get("pct", 0)
    range2_all = r["day_type"]["all_days"].get("Range2", {}).get("pct", 0)
    dnp_pre    = r["day_type"]["pre_cpi"].get("DNP", {}).get("pct", 0)
    dnp_all    = r["day_type"]["all_days"].get("DNP", {}).get("pct", 0)
    rth_ratio  = round(sr_pre.get("rth", 0) / sr_all.get("rth", 1) * 100, 1)

    observations = []
    if range1_pre > range1_all + 3:
        observations.append(f"✔  Range1 ELEVATED on pre-CPI ({range1_pre:.1f}% vs {range1_all:.1f}% baseline) — price keeps returning to 9:30 open")
    if range2_pre > range2_all + 2:
        observations.append(f"✔  Range2 ELEVATED on pre-CPI ({range2_pre:.1f}% vs {range2_all:.1f}% baseline) — large opening range, close near open")
    if dnp_pre < dnp_all - 2:
        observations.append(f"✔  DNP SUPPRESSED on pre-CPI ({dnp_pre:.1f}% vs {dnp_all:.1f}% baseline) — clean trend days are rare")
    if rth_ratio < 90:
        observations.append(f"✔  RTH range COMPRESSED ({rth_ratio:.1f}% of typical) — market parking ahead of binary event")
    if sv_pre.get("ny1_false_pct", 0) > sv_all.get("ny1_false_pct", 0) + 3:
        observations.append(f"✔  NY1 false rate ELEVATED ({sv_pre.get('ny1_false_pct',0):.1f}% vs {sv_all.get('ny1_false_pct',0):.1f}%) — fade the 9:30 move has edge")
    if sv_pre.get("asia_false_pct", 0) > sv_all.get("asia_false_pct", 0) + 3:
        observations.append(f"✔  Asia false rate ELEVATED ({sv_pre.get('asia_false_pct',0):.1f}% vs {sv_all.get('asia_false_pct',0):.1f}%) — overnight direction unreliable")

    if not observations:
        observations.append("  No strong deviations detected vs baseline — sample may be small")

    for obs in observations:
        print(f"  {obs}")

    print(f"\n{'='*65}\n")


def main():
    parser = argparse.ArgumentParser(description="Pre-CPI day statistical analysis")
    parser.add_argument("--symbol", default="NQ", choices=["NQ", "ES", "both"])
    parser.add_argument("--output", default=None, help="Write JSON results to this file")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Set DB_PATH at the top of this script to your candle_science.duckdb path.")
        return

    con = duckdb.connect(str(DB_PATH))
    symbols = ["NQ", "ES"] if args.symbol == "both" else [args.symbol]

    pre_cpi = get_pre_cpi_dates()
    print(f"\nPre-CPI dates in calendar: {len(pre_cpi)}")
    print(f"Date range: {pre_cpi[0]} → {pre_cpi[-1]}")

    results = {}
    for sym in symbols:
        result = analyse(sym, con)
        results[sym] = result
        print_report(result)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, indent=2, default=str))
        print(f"JSON written to {out_path}")

    con.close()


if __name__ == "__main__":
    main()
