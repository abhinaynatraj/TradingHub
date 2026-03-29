#!/usr/bin/env python3
"""
Candle Science — Initial Data Fetcher
======================================
Downloads historical 1-minute OHLCV data from Databento for NQ and ES,
year by year, and stores in DuckDB.

  NQ: from 2010-06-06  (stype=continuous, symbol=NQ.c.0)
  ES: from 2014-09-01  (stype=continuous, symbol=ES.c.0)

Usage:
    python3 fetch_data.py              # fetch all instruments
    python3 fetch_data.py --symbol NQ  # fetch one instrument
    python3 fetch_data.py --cost-only  # estimate total cost, no download
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

# ── CONFIG — edit these ───────────────────────────────────────────────────────
DB_PATH  = Path(__file__).parent / "candle_science.duckdb"
API_KEY  = os.environ.get("DATABENTO_API_KEY", "")
DATASET  = "GLBX.MDP3"
SCHEMA   = "ohlcv-1m"
STYPE    = "continuous"

INSTRUMENTS = {
    "NQ": {"symbol": "NQ.c.0", "table": "nq_1m", "start": "2014-09-01"},
    "ES": {"symbol": "ES.c.0", "table": "es_1m", "start": "2014-09-01"},
}
# ─────────────────────────────────────────────────────────────────────────────


def ensure_table(con, table):
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            timestamp TIMESTAMPTZ NOT NULL UNIQUE,
            open      DOUBLE,
            high      DOUBLE,
            low       DOUBLE,
            close     DOUBLE,
            volume    BIGINT
        )
    """)


def parse_dbn(store) -> pd.DataFrame:
    """Parse a DBNStore into a clean OHLCV DataFrame."""
    df = store.to_df().reset_index()
    df = df.rename(columns={"ts_event": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["volume"]    = df["volume"].astype("int64")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    # continuous stype may still return multiple rows per timestamp near roll dates
    before = len(df)
    df = (df.sort_values("volume", ascending=False)
            .drop_duplicates(subset="timestamp", keep="first")
            .sort_values("timestamp")
            .reset_index(drop=True))
    if before != len(df):
        print(f"    deduped {before - len(df):,} overlapping rows")
    return df


def year_chunks(start_str: str):
    """Yield (start, end) string pairs one year at a time from start_str to now."""
    from dateutil.relativedelta import relativedelta
    start = datetime.strptime(start_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    now   = datetime.now(timezone.utc)
    cur   = start
    while cur < now:
        nxt = min(cur + relativedelta(years=1), now)
        yield cur.strftime("%Y-%m-%dT%H:%M:%S"), nxt.strftime("%Y-%m-%dT%H:%M:%S")
        cur = nxt


def fetch_instrument(key: str, cost_only: bool = False):
    try:
        import databento as db
    except ImportError:
        print("ERROR: databento not installed — pip install databento")
        sys.exit(1)

    cfg    = INSTRUMENTS[key]
    symbol = cfg["symbol"]
    table  = cfg["table"]
    start  = cfg["start"]

    print(f"\n{'='*60}")
    print(f"  Instrument : {key}  ({symbol})")
    print(f"  Dataset    : {DATASET} / {SCHEMA} / stype={STYPE}")
    print(f"  Start      : {start}")

    if not API_KEY:
        print("ERROR: DATABENTO_API_KEY environment variable not set")
        sys.exit(1)
    client = db.Historical(API_KEY)

    # ── Cost estimate ──────────────────────────────────────────────────────────
    if cost_only:
        try:
            cost = client.metadata.get_cost(
                dataset  = DATASET,
                symbols  = [symbol],
                schema   = SCHEMA,
                stype_in = STYPE,
                start    = start,
            )
            print(f"  Estimated cost (full history) : ${cost:.4f}")
        except Exception as e:
            print(f"  Cost estimate failed: {e}")
        return

    # ── Connect and find resume point ─────────────────────────────────────────
    con = duckdb.connect(str(DB_PATH))
    ensure_table(con, table)
    last_ts = con.execute(f"SELECT MAX(timestamp) FROM {table}").fetchone()[0]

    if last_ts is not None:
        fetch_start = pd.Timestamp(last_ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S")
        print(f"  Resuming from : {fetch_start}")
    else:
        fetch_start = start
        print(f"  Full download from {fetch_start}")

    # ── Download year by year ─────────────────────────────────────────────────
    chunks         = list(year_chunks(fetch_start))
    total_inserted = 0

    for i, (chunk_start, chunk_end) in enumerate(chunks):
        print(f"  [{i+1}/{len(chunks)}] {chunk_start[:10]} → {chunk_end[:10]} … ", end="", flush=True)

        dbn_path = Path(__file__).parent / f"{key.lower()}_chunk.dbn"
        dbn_path.unlink(missing_ok=True)  # ensure clean slate

        try:
            client.timeseries.get_range(
                dataset  = DATASET,
                symbols  = [symbol],
                schema   = SCHEMA,
                stype_in = STYPE,
                start    = chunk_start,
                end      = chunk_end,
                path     = str(dbn_path),
            )
        except Exception as e:
            print(f"SKIP — {e}")
            continue

        if not dbn_path.exists() or dbn_path.stat().st_size < 100:
            print("empty")
            dbn_path.unlink(missing_ok=True)
            continue

        try:
            df = parse_dbn(db.DBNStore.from_file(str(dbn_path)))
        except Exception as e:
            print(f"parse error — {e}")
            dbn_path.unlink(missing_ok=True)
            continue

        if df.empty:
            print("0 rows")
            dbn_path.unlink(missing_ok=True)
            continue

        min_ts = df["timestamp"].min()
        con.execute(f"DELETE FROM {table} WHERE timestamp >= '{min_ts}'")
        con.execute(f"INSERT INTO {table} SELECT * FROM df")
        total_inserted += len(df)
        print(f"{len(df):,} rows")
        dbn_path.unlink(missing_ok=True)

    total_in_db = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    con.close()

    print(f"\n  Inserted this run : {total_inserted:,}")
    print(f"  Total rows in DB  : {total_in_db:,}")
    print(f"  ✅ {key} done")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=list(INSTRUMENTS.keys()),
                        help="Fetch only this instrument (default: all)")
    parser.add_argument("--cost-only", action="store_true",
                        help="Print estimated cost without downloading")
    args = parser.parse_args()

    keys = [args.symbol] if args.symbol else list(INSTRUMENTS.keys())
    for key in keys:
        fetch_instrument(key, cost_only=args.cost_only)

    print(f"\nAll done. DB: {DB_PATH}")


if __name__ == "__main__":
    main()
