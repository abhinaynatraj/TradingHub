"""Tests for the historical triad walker.

The walker reads bars (a DataFrame with ts, OHLC) and yields one TriadEpisode
per fully-formed historical triad. Each episode includes:
  - block_id
  - C1, C2, C3 fully-built HourAgg objects
  - the eventual triad classification
  - all 1m bars in the triad (for downstream decision-point sampling)
"""
from __future__ import annotations

import pandas as pd

from engine.walker import walk_triads, TriadEpisode


def _bar(ts: str, h: float, l: float, o: float | None = None, c: float | None = None) -> dict:
    return {
        "ts": pd.Timestamp(ts, tz="America/New_York"),
        "open": o if o is not None else l,
        "high": h, "low": l,
        "close": c if c is not None else h,
        "volume": 100,
    }


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    return df


def _full_triad_frame(date: str, block_start_h: int, hi_per_hour: list[float], lo_per_hour: list[float]) -> pd.DataFrame:
    rows = []
    for hour_offset in range(3):
        h_idx = block_start_h + hour_offset
        for minute in range(60):
            rows.append(_bar(
                f"{date} {h_idx:02d}:{minute:02d}",
                h=hi_per_hour[hour_offset], l=lo_per_hour[hour_offset],
            ))
    return _frame(rows)


def test_walker_yields_one_episode_per_complete_triad():
    df = _full_triad_frame("2024-01-02", block_start_h=9,
                           hi_per_hour=[100, 102, 104], lo_per_hour=[99, 100, 101])
    episodes = list(walk_triads(df))
    assert len(episodes) == 1
    e = episodes[0]
    assert e.block_id == "09-12"
    assert e.classification == "line-up"


def test_walker_skips_excluded_15h_block():
    # Bars in 15:00-18:00 must NOT produce an episode.
    rows = []
    for h in range(15, 18):
        for m in range(60):
            rows.append(_bar(f"2024-01-02 {h:02d}:{m:02d}", h=100, l=99))
    df = _frame(rows)
    episodes = list(walk_triads(df))
    assert episodes == []


def test_walker_skips_incomplete_triad():
    # Only C1 and C2 of the 09-12 block; missing C3 → no episode.
    rows = []
    for h in (9, 10):
        for m in range(60):
            rows.append(_bar(f"2024-01-02 {h:02d}:{m:02d}", h=100, l=99))
    df = _frame(rows)
    episodes = list(walk_triads(df))
    assert episodes == []


def test_walker_handles_multiple_triads():
    df1 = _full_triad_frame("2024-01-02", block_start_h=9,
                            hi_per_hour=[100, 102, 104], lo_per_hour=[99, 100, 101])
    df2 = _full_triad_frame("2024-01-02", block_start_h=12,
                            hi_per_hour=[105, 103, 101], lo_per_hour=[100, 99, 98])
    df = pd.concat([df1, df2], ignore_index=True)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    episodes = list(walk_triads(df))
    assert len(episodes) == 2
    assert {e.block_id for e in episodes} == {"09-12", "12-15"}
