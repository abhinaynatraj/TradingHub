"""Iterate completed historical triads in a 1m DataFrame.

Yields TriadEpisode objects with built aggregations and the eventual
classification. Skips the excluded 15:00-18:00 gap entirely.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import pandas as pd

from engine import constants as C
from engine import time_primitives as tp
from engine.aggregations import HourAgg, QuarterAgg, TriadAgg
from engine.box_05 import build_box_05
from engine.classifier import TriadClass, classify_triad


@dataclass
class TriadEpisode:
    block_id: str
    anchor_ts: pd.Timestamp                 # C1 anchor (start of block)
    triad: TriadAgg
    classification: TriadClass              # final, after C3 closes
    bars: pd.DataFrame                      # all 1m bars in the triad


def walk_triads(df: pd.DataFrame) -> Iterator[TriadEpisode]:
    """Yield one TriadEpisode per fully-formed historical triad in df.

    df must have ts, open, high, low, close, volume; sorted by ts.
    """
    if df.empty:
        return

    # Group bars by (block_anchor_ts). Excluded-gap bars produce None block id and are skipped.
    df = df.copy()
    df["block_anchor"] = df["ts"].apply(lambda t: tp.triad_anchor_ts(t) if tp.block_id_of(t) is not None else pd.NaT)
    df = df.dropna(subset=["block_anchor"])

    for block_anchor, block_df in df.groupby("block_anchor", sort=True):
        # Build the triad if all three hours have at least one bar each.
        block_id = tp.block_id_of(block_anchor)
        triad = TriadAgg(block_id=block_id, anchor_ts=block_anchor)

        for hour_offset in range(3):
            hour_anchor = block_anchor + pd.Timedelta(hours=hour_offset)
            hour_bars = block_df[(block_df["ts"] >= hour_anchor) &
                                 (block_df["ts"] < hour_anchor + pd.Timedelta(hours=1))]
            if hour_bars.empty:
                break

            hour = HourAgg(anchor_ts=hour_anchor)
            for q_idx in range(1, 5):
                q_start_min = (q_idx - 1) * 15
                q_anchor = hour_anchor + pd.Timedelta(minutes=q_start_min)
                q_bars = hour_bars[(hour_bars["ts"] >= q_anchor) &
                                   (hour_bars["ts"] < q_anchor + pd.Timedelta(minutes=15))]
                if q_bars.empty:
                    continue
                q = QuarterAgg(quarter_idx=q_idx, anchor_ts=q_anchor)
                for _, bar in q_bars.iterrows():
                    q.update(bar["ts"], bar["open"], bar["high"], bar["low"], bar["close"])
                setattr(hour, f"q{q_idx}", q)

            # 05-box from minutes 0-4 of this hour
            box = build_box_05(hour_bars.to_dict("records"), hour_anchor_ts=hour_anchor)
            hour.box_05_high = box.high if box.high != float("-inf") else None
            hour.box_05_low = box.low if box.low != float("inf") else None
            hour.box_05_locked = box.locked

            setattr(triad, f"c{hour_offset+1}", hour)
        else:
            cls = classify_triad(triad)
            if cls != "pending":
                yield TriadEpisode(
                    block_id=block_id,
                    anchor_ts=block_anchor,
                    triad=triad,
                    classification=cls,
                    bars=block_df.drop(columns=["block_anchor"]).reset_index(drop=True),
                )
