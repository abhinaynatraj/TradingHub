#!/usr/bin/env python3
"""
Candle Science — Daily Update
===============================
1. Fetches missing 1m bars for each instrument from Databento
2. Upserts into candle_science.duckdb
3. Sends a Mac notification

Usage:
    python3 daily_update.py              # update all instruments
    python3 daily_update.py --symbol NQ  # update one instrument

Crontab (weekdays at 7:00 AM):
    0 7 * * 1-5 /usr/bin/python3 /FULL/PATH/TO/daily_update.py >> /FULL/PATH/TO/daily_update.log 2>&1
"""

import os
import re
import sys
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytz

# ── CONFIG ─────────────────────────────────────────────────────────────────────
DB_PATH    = Path(__file__).parent / "candle_science.duckdb"
API_KEY    = os.environ.get("DATABENTO_API_KEY", "")
DATASET    = "GLBX.MDP3"
SCHEMA     = "ohlcv-1m"
STYPE      = "continuous"
TIMEZONE   = "America/Toronto"
MAC_NOTIFY = True

INSTRUMENTS = {
    "NQ": {"symbol": "NQ.c.0", "table": "nq_1m"},
    "ES": {"symbol": "ES.c.0", "table": "es_1m"},
}
# ───────────────────────────────────────────────────────────────────────────────


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def fetch_new_bars(con, key: str, force: bool = False) -> int:
    try:
        import databento as db
    except ImportError:
        log("ERROR: databento not installed"); sys.exit(1)

    if not API_KEY:
        log("ERROR: DATABENTO_API_KEY environment variable not set"); sys.exit(1)

    cfg    = INSTRUMENTS[key]
    symbol = cfg["symbol"]
    table  = cfg["table"]
    tz     = pytz.timezone(TIMEZONE)
    now    = datetime.now(tz)

    if now.weekday() >= 5 and not force:
        log(f"[{key}] Weekend — skipping fetch"); return 0

    result  = con.execute(f"SELECT MAX(timestamp) FROM {table}").fetchone()
    last_ts = result[0]
    if last_ts is None:
        log(f"[{key}] No data — run fetch_data.py first"); return 0

    if last_ts.tzinfo is None:
        last_ts = tz.localize(last_ts)
    else:
        last_ts = last_ts.astimezone(tz)

    fetch_from = last_ts + timedelta(minutes=1)
    fetch_to   = now - timedelta(minutes=5)

    if fetch_to <= fetch_from:
        log(f"[{key}] Already up to date ({last_ts.strftime('%Y-%m-%d %H:%M')})"); return 0

    log(f"[{key}] Fetching {fetch_from.strftime('%Y-%m-%d %H:%M')} → {fetch_to.strftime('%Y-%m-%d %H:%M')}")

    try:
        client   = db.Historical(API_KEY)
        dbn_path = Path(__file__).parent / f"{key.lower()}_1m_latest.dbn"

        def _do_fetch(end_ts):
            if dbn_path.exists():
                dbn_path.unlink()
            client.timeseries.get_range(
                dataset  = DATASET,
                symbols  = [symbol],
                schema   = SCHEMA,
                stype_in = STYPE,
                start    = fetch_from.strftime("%Y-%m-%dT%H:%M:%S"),
                end      = end_ts.strftime("%Y-%m-%dT%H:%M:%S"),
                path     = str(dbn_path),
            )

        try:
            _do_fetch(fetch_to)
        except Exception as e:
            # Databento returns the available cutoff in the error message —
            # parse it and retry with that end time.
            m = re.search(r'end time before (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', str(e))
            if m:
                cutoff = datetime.fromisoformat(m.group(1)).replace(tzinfo=pytz.UTC) - timedelta(minutes=1)
                if cutoff <= fetch_from:
                    log(f"[{key}] No data available past {fetch_from.strftime('%Y-%m-%d %H:%M')}"); return 0
                log(f"[{key}] Subscription limit — retrying with end={cutoff.strftime('%Y-%m-%d %H:%M')} UTC")
                _do_fetch(cutoff)
            else:
                raise

        store = db.DBNStore.from_file(str(dbn_path))
        df    = store.to_df().reset_index()
        if "ts_event" in df.columns:
            df = df.rename(columns={"ts_event": "timestamp"})
        elif df.index.name == "ts_event":
            df = df.reset_index().rename(columns={"ts_event": "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(TIMEZONE)
        for col in ["open", "high", "low", "close"]:
            if df[col].dtype == "int64":
                df[col] = df[col] / 1_000_000_000
        df = df[["timestamp","open","high","low","close","volume"]].copy()

        if df.empty:
            log(f"[{key}] No new bars returned"); return 0

        # parent stype returns all contract legs — keep highest-volume bar per timestamp
        df = (df.sort_values("volume", ascending=False)
                .drop_duplicates(subset="timestamp", keep="first")
                .sort_values("timestamp")
                .reset_index(drop=True))

        min_ts = df["timestamp"].min()
        con.execute(f"DELETE FROM {table} WHERE timestamp >= ?", [min_ts])
        con.execute(f"INSERT INTO {table} SELECT * FROM df")
        log(f"[{key}] Inserted {len(df):,} new rows")
        return len(df)

    except Exception as e:
        log(f"[{key}] ERROR fetching: {e}"); return 0



def notify(title, message):
    if not MAC_NOTIFY: return
    try:
        subprocess.run(["terminal-notifier","-title",title,"-message",message,"-sound","default"],
                       check=True, capture_output=True)
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    try:
        subprocess.run(["osascript","-e",f'display notification "{message}" with title "{title}"'],
                       check=True, capture_output=True)
    except Exception:
        pass


BACKTESTS = [
    {
        "name": "Fractal Sweep",
        "script": Path(__file__).parent / "model_stats.py",
    },
    {
        "name": "TTrades Fractal Model",
        "script": Path(__file__).parent.parent / "TTrades Fractal Model Analysis" / "ttfm_backtest.py",
    },
]


def run_backtests():
    for bt in BACKTESTS:
        script = bt["script"]
        if not script.exists():
            log(f"[backtest] SKIP {bt['name']} — script not found: {script}")
            continue
        log(f"[backtest] Running {bt['name']} …")
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            log(f"[backtest] {bt['name']} — OK")
        else:
            log(f"[backtest] {bt['name']} — FAILED (exit {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-5:]:
                    log(f"           {line}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=list(INSTRUMENTS.keys()),
                        help="Update only this instrument (default: all)")
    parser.add_argument("--no-backtest", action="store_true",
                        help="Skip backtest refresh after fetching bars")
    parser.add_argument("--force", action="store_true",
                        help="Run even on weekends")
    args  = parser.parse_args()
    keys  = [args.symbol] if args.symbol else list(INSTRUMENTS.keys())

    log("=" * 60)
    log(f"Daily Update — {', '.join(keys)}")

    con      = duckdb.connect(str(DB_PATH))
    new_rows = {k: fetch_new_bars(con, k, force=args.force) for k in keys}
    con.close()

    total = sum(new_rows.values())
    ts    = datetime.now(pytz.timezone(TIMEZONE)).strftime("%b %d %H:%M")
    msg   = f"{total:,} new bars · {ts}" if total else f"No new data · {ts}"
    notify("Candle Science Updated", msg)
    log(f"Done. {msg}")

    if total > 0 and not args.no_backtest:
        log("-" * 60)
        log("Refreshing backtests …")
        run_backtests()
        notify("Backtests Refreshed", f"JSON outputs updated · {ts}")
        log("Backtests complete.")

    log("=" * 60)


if __name__ == "__main__":
    main()
