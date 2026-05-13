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
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

import duckdb
import pandas as pd
import pytz

load_dotenv()

# ── CONFIG ─────────────────────────────────────────────────────────────────────
DB_PATH    = Path(__file__).parent.parent / "candle_science.duckdb"
API_KEY    = os.environ.get("DATABENTO_API_KEY")
if not API_KEY:
    raise ValueError("DATABENTO_API_KEY environment variable is not set!")
DATASET    = "GLBX.MDP3"
SCHEMA     = "ohlcv-1m"
STYPE      = "continuous"
TIMEZONE   = "America/New_York"
MAC_NOTIFY = True

INSTRUMENTS = {
    "NQ": {"symbol": "NQ.c.0", "table": "nq_1m"},
    "ES": {"symbol": "ES.c.0", "table": "es_1m"},
}
# ───────────────────────────────────────────────────────────────────────────────


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def _extract_databento_cutoff(exc) -> "datetime | None":
    """Return the subscription-limit cutoff from a Databento exception, or None.

    Prefers the structured `end_time` attribute added in databento-python >= 0.37.
    Falls back to regex on the string representation for older SDK versions.
    Logs a warning when the fallback fires so we notice if the SDK changes format.
    """
    # Structured path: SDK exposes end_time on the exception object.
    end_time = getattr(exc, "end_time", None)
    if end_time is not None:
        ts = datetime.fromisoformat(str(end_time).rstrip("Z"))
        return ts.replace(tzinfo=pytz.UTC) - timedelta(minutes=1)

    # Regex fallback — fragile, but keeps things working on older SDK versions.
    m = re.search(r'end time before (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', str(exc))
    if m:
        log("WARNING: using regex fallback to parse Databento cutoff — consider upgrading databento-python")
        return datetime.fromisoformat(m.group(1)).replace(tzinfo=pytz.UTC) - timedelta(minutes=1)

    return None


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
        dbn_path = Path(__file__).parent.parent / "data" / f"{key.lower()}_1m_latest.dbn"

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
            cutoff = _extract_databento_cutoff(e)
            if cutoff is None:
                raise
            if cutoff <= fetch_from:
                log(f"[{key}] No data available past {fetch_from.strftime('%Y-%m-%d %H:%M')}"); return 0
            log(f"[{key}] Subscription limit — retrying with end={cutoff.strftime('%Y-%m-%d %H:%M')} UTC")
            _do_fetch(cutoff)

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
        con.execute("BEGIN TRANSACTION")
        con.execute(f"DELETE FROM {table} WHERE timestamp >= ?", [min_ts])
        con.execute(f"INSERT INTO {table} SELECT * FROM df")
        con.execute("COMMIT")
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


REPO_ROOT = Path(__file__).parent.parent.parent
BACKTESTS = [
    {
        "name": "Fractal Sweep",
        "script": Path(__file__).parent / "model_stats.py",
        "output": Path(__file__).parent.parent / "model_stats.json",
        "incremental": True,
    },
    {
        # NOTE: was previously rooted at Path(__file__).parent.parent which
        # resolves to Fractal Sweep/ (not repo root) — so TTrades had been
        # silently skipped with "SKIP — script not found" since the engine
        # moved into Fractal Sweep/engine/. REPO_ROOT fixes that.
        "name": "TTrades Fractal Model",
        "script": REPO_ROOT / "TTrades Fractal Model Analysis" / "ttfm_backtest.py",
        "output": REPO_ROOT / "TTrades Fractal Model Analysis" / "ttfm_results.json",
        "incremental": False,
    },
    {
        # NPG Sweep — Wick Lick + series-based CISD + 4-leg projections.
        # The engine uses local imports (resampling, wick_lick, etc.) so it
        # MUST run from within NPG Sweep/engine/. cwd kwarg handles that.
        "name": "NPG Sweep",
        "script": REPO_ROOT / "NPG Sweep" / "engine" / "npg_stats.py",
        "output": REPO_ROOT / "NPG Sweep" / "npg_stats.json",
        "incremental": False,
        "cwd": REPO_ROOT / "NPG Sweep",
    },
    {
        # Hourly Analysis — breakout + quarter studies. Writes parquet
        # files to Analysis/data/{breakout,quarters}/ plus manifest.json.
        "name": "Hourly Analysis",
        "script": REPO_ROOT / "Analysis" / "engine" / "run_all.py",
        "output": REPO_ROOT / "Analysis" / "data" / "manifest.json",
        "incremental": False,
    },
]

MODEL_STATS_JSON = Path(__file__).parent.parent / "model_stats.json"
# Incremental backtest: process only bars >= this many days before today as a safety buffer.
INCREMENTAL_LOOKBACK_DAYS = 5


def _last_backtest_date(json_path: Path) -> "str | None":
    """Return the latest trade_date found in model_stats.json, or None if unavailable."""
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text())
        latest = None
        for key, model in data.items():
            if key.startswith('_'):
                continue
            for profile in (model.get('profiles') or {}).values():
                for trade in (profile.get('recent_trades') or []):
                    d = str(trade.get('trade_date', '') or '')
                    if d and (latest is None or d > latest):
                        latest = d
        return latest
    except Exception:
        return None


def _merge_incremental(existing_path: Path, partial_path: Path) -> bool:
    """Merge partial (new-dates-only) model_stats into the existing full JSON.

    For each model key × profile key, append new recent_trades and recompute
    top-level stats. Returns True on success, False on any error.
    """
    try:
        existing = json.loads(existing_path.read_text())
        partial  = json.loads(partial_path.read_text())
    except Exception as e:
        log(f"[incremental] Failed to load JSON for merge: {e}")
        return False

    changed = False
    for key, pdata in partial.items():
        if key.startswith('_'):
            continue
        if key not in existing:
            existing[key] = pdata
            changed = True
            continue
        for pk, pstats in (pdata.get('profiles') or {}).items():
            eprofiles = existing[key].setdefault('profiles', {})
            if pk not in eprofiles:
                eprofiles[pk] = pstats
                changed = True
                continue
            new_trades = pstats.get('recent_trades') or []
            if not new_trades:
                continue
            existing_trades = eprofiles[pk].get('recent_trades') or []
            new_dates = {t.get('trade_date') for t in new_trades}
            kept = [t for t in existing_trades if t.get('trade_date') not in new_dates]
            eprofiles[pk]['recent_trades'] = kept + new_trades
            changed = True

    if changed:
        # Update top-level metadata
        existing['_meta'] = {
            'schema_version': partial.get('_meta', {}).get('schema_version', 1),
            'generated_at':   partial.get('_meta', {}).get('generated_at',
                              datetime.now(pytz.UTC).isoformat()),
        }
        existing_path.write_text(json.dumps(existing, indent=2, default=str))
        log("[incremental] Merged partial results into existing model_stats.json")
    return True


def run_backtests(incremental: bool = True):
    for bt in BACKTESTS:
        script = bt["script"]
        if not script.exists():
            log(f"[backtest] SKIP {bt['name']} — script not found: {script}")
            continue

        cmd = [sys.executable, str(script)]

        if incremental and bt.get("incremental") and bt.get("output"):
            since = _last_backtest_date(bt["output"])
            if since:
                # Step back INCREMENTAL_LOOKBACK_DAYS to catch setups that straddle the boundary.
                from datetime import date
                try:
                    since_dt = datetime.strptime(since, "%Y-%m-%d").date()
                    since_dt = since_dt - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)
                    since = str(since_dt)
                except ValueError:
                    pass
                partial_path = bt["output"].with_suffix('.partial.json')
                cmd += ["--since", since, "--output", str(partial_path)]
                log(f"[backtest] {bt['name']} — incremental since {since}")
            else:
                log(f"[backtest] {bt['name']} — no prior JSON, running full backtest")
                since = None
                partial_path = None
        else:
            since = None
            partial_path = None
            log(f"[backtest] Running {bt['name']} …")

        # Some engines (NPG) use local imports and must run from a specific
        # working directory; others run fine from the default cwd.
        run_cwd = str(bt["cwd"]) if bt.get("cwd") else None
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=run_cwd)
        if result.returncode == 0:
            log(f"[backtest] {bt['name']} — OK")
            if partial_path and partial_path.exists():
                if not _merge_incremental(bt["output"], partial_path):
                    log(f"[backtest] {bt['name']} — merge failed, keeping partial output as-is")
                partial_path.unlink(missing_ok=True)
        else:
            log(f"[backtest] {bt['name']} — FAILED (exit {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-5:]:
                    log(f"           {line}")
            if partial_path and partial_path.exists():
                partial_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=list(INSTRUMENTS.keys()),
                        help="Update only this instrument (default: all)")
    parser.add_argument("--no-backtest", action="store_true",
                        help="Skip backtest refresh after fetching bars")
    parser.add_argument("--full-backtest", action="store_true",
                        help="Force a full (non-incremental) backtest rerun")
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
        incremental = not args.full_backtest
        mode_label  = "full" if args.full_backtest else "incremental"
        log(f"Refreshing backtests ({mode_label}) …")
        run_backtests(incremental=incremental)
        notify("Backtests Refreshed", f"JSON outputs updated · {ts}")
        log("Backtests complete.")

    log("=" * 60)


if __name__ == "__main__":
    main()
