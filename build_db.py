#!/usr/bin/env python3
"""
build_db.py — Import Chart-nq.csv + Chart-ES.csv into candle_science.duckdb
=============================================================================
Sources: Chart-nq.csv, Chart-ES.csv  (1m OHLC, timestamps in +03:00)
Output:  Fractal Sweep/candle_science.duckdb

Tables created:
  nq_1m  — populated from Chart-nq.csv
  es_1m  — populated from Chart-ES.csv

Timestamps are converted from UTC+3 -> America/Toronto, stored as
TIMESTAMPTZ — matching the schema every engine script expects.

Usage:
    python build_db.py
    python build_db.py --replace   # drop & rebuild if DB exists
"""

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

NQ_CSV  = Path(__file__).parent / "Chart-nq.csv"
ES_CSV  = Path(__file__).parent / "Chart-ES.csv"
DB_PATH = Path(__file__).parent / "Fractal Sweep" / "candle_science.duckdb"

TORONTO_TZ = "America/New_York"

SCHEMA_DDL = """
    timestamp TIMESTAMPTZ NOT NULL,
    open      DOUBLE       NOT NULL,
    high      DOUBLE       NOT NULL,
    low       DOUBLE       NOT NULL,
    close     DOUBLE       NOT NULL,
    volume    BIGINT       NOT NULL
"""


def log(msg):
    print(msg, flush=True)


def load_csv(path: Path) -> pd.DataFrame:
    log(f"  Reading {path.name}  ({path.stat().st_size / 1_048_576:.1f} MB) ...")
    df = pd.read_csv(
        path,
        usecols=["DateTime", "Open", "High", "Low", "Close"],
        dtype={"Open": "float64", "High": "float64", "Low": "float64", "Close": "float64"},
    )
    log(f"  Loaded {len(df):,} rows")

    df["timestamp"] = (
        pd.to_datetime(df["DateTime"], format="mixed", dayfirst=False, utc=True)
          .dt.tz_convert(TORONTO_TZ)
    )
    df = df.drop(columns=["DateTime"])
    df["volume"] = 0

    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"})
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df = (df.sort_values("timestamp")
            .drop_duplicates(subset="timestamp", keep="last")
            .reset_index(drop=True))
    log(f"  {len(df):,} rows after dedup")
    return df


def build(replace: bool):
    if DB_PATH.exists():
        if replace:
            log(f"Removing existing DB: {DB_PATH}")
            DB_PATH.unlink()
        else:
            log(f"DB already exists: {DB_PATH}")
            log("Use --replace to rebuild it from scratch.")
            sys.exit(0)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    log("Loading NQ ...")
    nq = load_csv(NQ_CSV)

    log("Loading ES ...")
    es = load_csv(ES_CSV)

    log(f"Creating {DB_PATH} ...")
    con = duckdb.connect(str(DB_PATH))

    log("Writing nq_1m ...")
    con.execute(f"CREATE TABLE nq_1m ({SCHEMA_DDL})")
    con.execute("INSERT INTO nq_1m SELECT * FROM nq")

    log("Writing es_1m ...")
    con.execute(f"CREATE TABLE es_1m ({SCHEMA_DDL})")
    con.execute("INSERT INTO es_1m SELECT * FROM es")

    nq_count  = con.execute("SELECT COUNT(*) FROM nq_1m").fetchone()[0]
    es_count  = con.execute("SELECT COUNT(*) FROM es_1m").fetchone()[0]
    nq_min_ts = con.execute("SELECT MIN(timezone('America/New_York', timestamp)) FROM nq_1m").fetchone()[0]
    nq_max_ts = con.execute("SELECT MAX(timezone('America/New_York', timestamp)) FROM nq_1m").fetchone()[0]
    es_min_ts = con.execute("SELECT MIN(timezone('America/New_York', timestamp)) FROM es_1m").fetchone()[0]
    es_max_ts = con.execute("SELECT MAX(timezone('America/New_York', timestamp)) FROM es_1m").fetchone()[0]
    con.close()

    log("")
    log("=" * 55)
    log(f"  Done.  {DB_PATH}")
    log(f"  nq_1m : {nq_count:,} rows  ({nq_min_ts.strftime('%Y-%m-%d')} -> {nq_max_ts.strftime('%Y-%m-%d')} ET)")
    log(f"  es_1m : {es_count:,} rows  ({es_min_ts.strftime('%Y-%m-%d')} -> {es_max_ts.strftime('%Y-%m-%d')} ET)")
    log("=" * 55)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="Drop and rebuild if DB exists")
    args = parser.parse_args()
    build(args.replace)
