#!/usr/bin/env python3
"""Generate tests/test_candles.duckdb — synthetic 1m bar data for integration tests.

Creates ~100 trading days of 1-minute NQ and ES bars covering RTH (07:00-16:00 ET).
Price series is deterministic: a slow drift with planted sweep+CISD patterns every ~10
days so the full detection pipeline can exercise actual setups.

Usage:
    python3 tests/generate_test_db.py
    python3 tests/generate_test_db.py --days 50  # faster, fewer patterns

The output file (tests/test_candles.duckdb) is gitignored.  Re-run whenever the
schema or test fixtures change.
"""

import argparse
from datetime import date, timedelta, datetime, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytz

# ── constants ────────────────────────────────────────────────────────────────
ET   = pytz.timezone("America/New_York")
TOR  = pytz.timezone("America/Toronto")  # stored timezone per CLAUDE.md
RTH_START = time(7, 0)
RTH_END   = time(16, 0)

NQ_BASE  = 18_000.0   # starting price
ES_BASE  =  5_000.0
NQ_TICK  =      0.25
ES_TICK  =      0.25

OUT_PATH = Path(__file__).parent / "test_candles.duckdb"


# ── helpers ───────────────────────────────────────────────────────────────────

def _trading_days(n: int) -> list[date]:
    """Return n consecutive weekdays starting from a fixed anchor date."""
    anchor = date(2023, 1, 3)  # Tuesday — avoids holiday edge cases
    days, d = [], anchor
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _rth_minutes(day: date) -> list[datetime]:
    """All 1-minute bar open times for RTH on *day* (07:00 inclusive, 16:00 inclusive)."""
    bars = []
    t = ET.localize(datetime.combine(day, RTH_START))
    end = ET.localize(datetime.combine(day, RTH_END))
    while t <= end:
        bars.append(t)
        t += timedelta(minutes=1)
    return bars


def _build_day_ohlcv(
    timestamps: list[datetime],
    base_price: float,
    rng: np.random.Generator,
    plant_sweep: bool = False,
    direction: str = "LONG",
    tick: float = 0.25,
) -> list[tuple]:
    """Build OHLCV rows for one day.

    When plant_sweep is True a sweep+CISD pattern is embedded around the
    2nd hour candle (bars ~60-75) so integration tests can detect real setups.
    """
    n = len(timestamps)
    rows = []
    price = base_price

    # Slow intraday drift: gentle random walk
    step_std = base_price * 0.0002

    # Build the prior HTF candle's high/low using the first hour of bars
    prior_high = price + base_price * 0.005   # +0.5%
    prior_low  = price - base_price * 0.005   # -0.5%

    sweep_done = False
    cisd_phase = 0   # 0=waiting, 1=opposing_run, 2=fired
    cisd_level = None

    for i, ts in enumerate(timestamps):
        drift = rng.normal(0, step_std)
        price = max(price + drift, tick)

        # Default bar: small random range
        bar_range = abs(rng.normal(0, base_price * 0.001)) + tick * 2
        o = round(price, 2)
        h = round(o + bar_range * 0.6, 2)
        l = round(o - bar_range * 0.4, 2)
        c = round(o + rng.uniform(-bar_range * 0.3, bar_range * 0.3), 2)
        h = max(h, o, c) + tick
        l = min(l, o, c) - tick
        vol = int(rng.integers(200, 1200))

        if plant_sweep and not sweep_done and i == 61:
            # Plant sweep: price breaks below prior_low (LONG setup)
            if direction == "LONG":
                l = round(prior_low - base_price * 0.003, 2)
                h = round(prior_low - base_price * 0.001, 2)
                o = round(prior_low - base_price * 0.002, 2)
                c = round(prior_low - base_price * 0.0015, 2)
                price = c
            else:
                h = round(prior_high + base_price * 0.003, 2)
                l = round(prior_high + base_price * 0.001, 2)
                o = round(prior_high + base_price * 0.002, 2)
                c = round(prior_high + base_price * 0.0015, 2)
                price = c
            sweep_done = True
            cisd_phase = 1

        elif plant_sweep and sweep_done and cisd_phase == 1 and i == 63:
            # Return inside range after sweep
            if direction == "LONG":
                o = round((prior_low + prior_high) * 0.5, 2)
                c = round(o + base_price * 0.001, 2)
                h = round(c + tick * 4, 2)
                l = round(prior_low - tick * 2, 2)
                cisd_level = l
                price = c
            else:
                o = round((prior_low + prior_high) * 0.5, 2)
                c = round(o - base_price * 0.001, 2)
                l = round(c - tick * 4, 2)
                h = round(prior_high + tick * 2, 2)
                cisd_level = h
                price = c
            cisd_phase = 2

        elif plant_sweep and cisd_phase == 2 and i == 65:
            # CISD fire bar
            if direction == "LONG":
                o = round(price, 2)
                c = round(price + base_price * 0.003, 2)
                h = round(c + tick * 2, 2)
                l = round(o - tick, 2)
                price = c
            else:
                o = round(price, 2)
                c = round(price - base_price * 0.003, 2)
                l = round(c - tick * 2, 2)
                h = round(o + tick, 2)
                price = c
            cisd_phase = 3

        rows.append((ts.astimezone(TOR), o, h, l, c, vol))

    return rows, prior_high, prior_low


def build_instrument(days: list[date], base: float, tick: float, rng: np.random.Generator) -> pd.DataFrame:
    """Generate all 1m bars for an instrument across all trading days."""
    all_rows = []
    price = base

    for idx, day in enumerate(days):
        timestamps = _rth_minutes(day)
        plant = (idx % 10 == 5)  # plant a sweep every 10th day
        direction = "LONG" if (idx // 10) % 2 == 0 else "SHORT"

        rows, ph, pl = _build_day_ohlcv(
            timestamps, price, rng,
            plant_sweep=plant, direction=direction, tick=tick,
        )
        all_rows.extend(rows)
        # carry forward end-of-day price with small overnight gap
        if rows:
            price = rows[-1][4] + rng.normal(0, base * 0.001)  # close of last bar

    df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    return df


def main(n_days: int = 100):
    rng = np.random.default_rng(42)  # deterministic

    print(f"Generating {n_days} trading days of synthetic 1m bars...")
    days = _trading_days(n_days)

    nq_df = build_instrument(days, NQ_BASE, NQ_TICK, rng)
    es_df = build_instrument(days, ES_BASE, ES_TICK, rng)

    print(f"  NQ: {len(nq_df):,} bars")
    print(f"  ES: {len(es_df):,} bars")

    OUT_PATH.unlink(missing_ok=True)
    con = duckdb.connect(str(OUT_PATH))
    con.execute("""
        CREATE TABLE nq_1m (
            timestamp TIMESTAMPTZ,
            open      DOUBLE,
            high      DOUBLE,
            low       DOUBLE,
            close     DOUBLE,
            volume    BIGINT
        )
    """)
    con.execute("""
        CREATE TABLE es_1m (
            timestamp TIMESTAMPTZ,
            open      DOUBLE,
            high      DOUBLE,
            low       DOUBLE,
            close     DOUBLE,
            volume    BIGINT
        )
    """)
    con.execute("INSERT INTO nq_1m SELECT * FROM nq_df")
    con.execute("INSERT INTO es_1m SELECT * FROM es_df")
    con.close()

    print(f"Written: {OUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate test_candles.duckdb")
    parser.add_argument("--days", type=int, default=100, help="Number of trading days to generate")
    args = parser.parse_args()
    main(args.days)
