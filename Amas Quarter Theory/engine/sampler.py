"""Decision-point sampler. CAUSAL — uses only bars ≤ decision_ts.

Iterates the bars of a TriadEpisode and yields a DecisionPointSample each
time a decision-point predicate fires. Each sample's state_key is the v1
state-vector key for the live state at that moment.

Decision points (one sample fires per qualifying event on a bar):
  1. quarter close (last bar of a quarter — minute 14, 29, 44, 59)
  2. hour close (last bar of the hour — minute 59)
  3. triad close (close of C3 = minute 59 of last hour)
  4. sweep event (any new sweep flagged on this bar)
  5. midline reaction (support / reject confirmed on this bar's close)
  6. band rejection (confirmed on this bar's close)
  7. 05-box close (the :04 minute bar of each hour)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal

import pandas as pd

from engine import time_primitives as tp
from engine.aggregations import HourAgg, QuarterAgg, TriadAgg
from engine.box_05 import band_levels, detect_band_rejection
from engine.classifier import (
    classify_hour,
    classify_triad,
    detect_sweeps_in_hour,
)
from engine.midline import (
    detect_midline_reaction,
    resolve_midline_source,
)
from engine.state_vector import (
    HourStateInputs,
    TriadStateInputs,
    build_hour_key,
    build_triad_key,
)
from engine.walker import TriadEpisode


@dataclass(frozen=True)
class DecisionPointSample:
    decision_ts: pd.Timestamp
    tf: Literal["triad", "hour"]
    state_key: str
    outcome: str  # "line-up" | "line-down" | "apex-up" | "apex-down" | "doji" (triad)
    # or "line-up" | "line-down" | "doji" (hour)


def sample_decision_points(
    episode: TriadEpisode, sym: str
) -> Iterator[DecisionPointSample]:
    """Yield (state_key, outcome) at every decision point in the triad. Causal."""
    bars = episode.bars
    block_id = episode.block_id
    triad_outcome = episode.classification

    # Running state. Rebuilt as we walk bars in order.
    triad = TriadAgg(block_id=block_id, anchor_ts=episode.anchor_ts)
    prior_hour: HourAgg | None = None

    sweep_set_emitted: set[str] = set()
    midhr_state = "untouched"
    mid3h_state = "untouched"
    box_react_state = "none"
    last_midhr_reaction: str | None = None  # track last value to avoid re-firing

    for _, bar in bars.iterrows():
        ts: pd.Timestamp = bar["ts"]
        hour_idx = tp.hour_index_in_triad(ts)
        if hour_idx is None:
            continue

        # Get or create the current HourAgg
        hour: HourAgg | None = getattr(triad, f"c{hour_idx}")
        if hour is None:
            hour = HourAgg(anchor_ts=tp.hour_anchor_ts(ts))
            setattr(triad, f"c{hour_idx}", hour)

        # Get or create the current QuarterAgg
        q_idx = tp.quarter_of(ts)
        quarter: QuarterAgg | None = getattr(hour, f"q{q_idx}")
        if quarter is None:
            quarter = QuarterAgg(quarter_idx=q_idx, anchor_ts=tp.quarter_anchor_ts(ts))
            setattr(hour, f"q{q_idx}", quarter)

        # Update quarter with this bar
        quarter.update(ts, bar["open"], bar["high"], bar["low"], bar["close"])

        # 05-box accumulation (minutes :00..:04 of each hour)
        if ts.minute in (0, 1, 2, 3, 4):
            if hour.box_05_high is None:
                hour.box_05_high = bar["high"]
                hour.box_05_low = bar["low"]
            else:
                hour.box_05_high = max(hour.box_05_high, bar["high"])
                hour.box_05_low = min(hour.box_05_low, bar["low"])
            if ts.minute == 4:
                hour.box_05_locked = True

        # ── Decision point: sweep event ───────────────────────────────────────
        all_sweeps = detect_sweeps_in_hour(hour)
        for s in all_sweeps:
            label = f"Q{s.by_q}_swept_Q{s.target_q}_{s.side}"
            if label not in sweep_set_emitted:
                sweep_set_emitted.add(label)
                yield from _emit(
                    sym=sym,
                    block_id=block_id,
                    hour_idx=hour_idx,
                    decision_ts=ts,
                    hour=hour,
                    triad=triad,
                    triad_outcome=triad_outcome,
                    prior_hour=prior_hour,
                    sweep_set_emitted=sweep_set_emitted,
                    midhr_state=midhr_state,
                    mid3h_state=mid3h_state,
                    box_react_state=box_react_state,
                )

        # ── Decision point: midline reaction ─────────────────────────────────
        prior_hi = prior_hour.high if prior_hour is not None else None
        prior_lo = prior_hour.low if prior_hour is not None else None
        cur_hi = hour.high
        cur_lo = hour.low
        if cur_hi is not None and cur_lo is not None:
            mid, _src = resolve_midline_source(
                current_high=cur_hi,
                current_low=cur_lo,
                prior_high=prior_hi,
                prior_low=prior_lo,
            )
            r = detect_midline_reaction(
                mid, bar["open"], bar["high"], bar["low"], bar["close"]
            )
            if r is not None:
                new_reaction = r.value
                if new_reaction != last_midhr_reaction:
                    last_midhr_reaction = new_reaction
                    midhr_state = new_reaction
                    yield from _emit(
                        sym=sym,
                        block_id=block_id,
                        hour_idx=hour_idx,
                        decision_ts=ts,
                        hour=hour,
                        triad=triad,
                        triad_outcome=triad_outcome,
                        prior_hour=prior_hour,
                        sweep_set_emitted=sweep_set_emitted,
                        midhr_state=midhr_state,
                        mid3h_state=mid3h_state,
                        box_react_state=box_react_state,
                    )

        # ── Decision point: band rejection (after 05-box locked) ─────────────
        if hour.box_05_locked and hour.box_05_high is not None:
            bands = band_levels(hour.box_05_high, hour.box_05_low)
            br = detect_band_rejection(
                {"high": bar["high"], "low": bar["low"], "close": bar["close"]},
                bands,
            )
            if br is not None:
                token = f"{br.level}{'up' if br.side == 'upper' else 'dn'}_rejected"
                if box_react_state in ("none", token):
                    box_react_state = token
                else:
                    box_react_state = "multi"
                yield from _emit(
                    sym=sym,
                    block_id=block_id,
                    hour_idx=hour_idx,
                    decision_ts=ts,
                    hour=hour,
                    triad=triad,
                    triad_outcome=triad_outcome,
                    prior_hour=prior_hour,
                    sweep_set_emitted=sweep_set_emitted,
                    midhr_state=midhr_state,
                    mid3h_state=mid3h_state,
                    box_react_state=box_react_state,
                )

        # ── Decision point: 05-box close (minute :04) ────────────────────────
        if ts.minute == 4 and hour.box_05_locked:
            yield from _emit(
                sym=sym,
                block_id=block_id,
                hour_idx=hour_idx,
                decision_ts=ts,
                hour=hour,
                triad=triad,
                triad_outcome=triad_outcome,
                prior_hour=prior_hour,
                sweep_set_emitted=sweep_set_emitted,
                midhr_state=midhr_state,
                mid3h_state=mid3h_state,
                box_react_state=box_react_state,
            )

        # ── Decision point: quarter close (minutes :14, :29, :44, :59) ───────
        if ts.minute in (14, 29, 44, 59):
            yield from _emit(
                sym=sym,
                block_id=block_id,
                hour_idx=hour_idx,
                decision_ts=ts,
                hour=hour,
                triad=triad,
                triad_outcome=triad_outcome,
                prior_hour=prior_hour,
                sweep_set_emitted=sweep_set_emitted,
                midhr_state=midhr_state,
                mid3h_state=mid3h_state,
                box_react_state=box_react_state,
            )

        # ── Hour boundary reset (after processing the :59 bar) ───────────────
        if ts.minute == 59:
            prior_hour = hour
            sweep_set_emitted = set()
            midhr_state = "untouched"
            last_midhr_reaction = None
            box_react_state = "none"


def _emit(
    sym: str,
    block_id: str,
    hour_idx: int,
    decision_ts: pd.Timestamp,
    hour: HourAgg,
    triad: TriadAgg,
    triad_outcome: str,
    prior_hour: HourAgg | None,
    sweep_set_emitted: set[str],
    midhr_state: str,
    mid3h_state: str,
    box_react_state: str,
) -> Iterator[DecisionPointSample]:
    """Emit one triad-level sample (and optionally one hour-level sample) at decision_ts."""

    # ── Triad-level state ─────────────────────────────────────────────────────
    c1 = triad.c1
    c1cls_raw = classify_hour(c1) if c1 is not None else "doji"
    # "pending" means C1 is still forming (not all 4 quarters closed)
    c1cls: str = c1cls_raw if c1cls_raw != "pending" else "doji"

    # c2q: how far has C2 progressed?
    if hour_idx > 2:
        # We're in C3 — C2 is fully closed
        c2q = "closed"
    elif hour_idx == 2:
        # We're in C2 — report current quarter progress
        c2q = f"Q{tp.quarter_of(decision_ts)}"
        # Override to "closed" if we're at the very last bar of C2 (:59)
        c2 = triad.c2
        if c2 is not None and c2.q4 is not None and decision_ts.minute == 59:
            c2q = "closed"
    else:
        # We're in C1 — C2 hasn't started yet; use "Q1" as the initial placeholder
        c2q = "Q1"

    # C2 vs C1 relational flags (only meaningful when C2 has some data)
    c2sw_c1h = c2sw_c1l = c2_inside = False
    c2vh = c2vl = "na"
    c2_obj = triad.c2
    if hour_idx >= 2 and c1 is not None and c2_obj is not None and c2_obj.high is not None:
        c1_hi = c1.high
        c1_lo = c1.low
        c2_hi = c2_obj.high
        c2_lo = c2_obj.low
        if c1_hi is not None and c1_lo is not None:
            c2sw_c1h = c2_hi > c1_hi
            c2sw_c1l = c2_lo < c1_lo
            c2_inside = (c2_hi < c1_hi) and (c2_lo > c1_lo)
            c2vh = "above" if c2_hi > c1_hi else ("below" if c2_hi < c1_hi else "inside")
            c2vl = "above" if c2_lo > c1_lo else ("below" if c2_lo < c1_lo else "inside")

    triad_inputs = TriadStateInputs(
        sym=sym,
        block=block_id,
        c1cls=c1cls,
        c2q=c2q,
        c2vh=c2vh,
        c2vl=c2vl,
        c2sw_c1h=c2sw_c1h,
        c2sw_c1l=c2sw_c1l,
        c2_inside=c2_inside,
        midhr=midhr_state,
        mid3h=mid3h_state,
        box_react=box_react_state,
    )
    yield DecisionPointSample(
        decision_ts=decision_ts,
        tf="triad",
        state_key=build_triad_key(triad_inputs),
        outcome=triad_outcome,
    )

    # ── Hour-level state ──────────────────────────────────────────────────────
    # Only emit an hour sample once the hour has all 4 quarters (fully closed)
    if hour.q4 is None:
        return

    hour_outcome_raw = classify_hour(hour)
    if hour_outcome_raw == "pending":
        return

    # Which quarter is this decision at within the hour?
    q_now = (
        "closed"
        if decision_ts.minute == 59
        else f"Q{tp.quarter_of(decision_ts)}"
    )

    # Per-quarter classification labels
    h_hi = hour.high
    h_lo = hour.low
    qcls = []
    for qi in range(1, 5):
        q = getattr(hour, f"q{qi}")
        if q is None:
            qcls.append("inside")
        elif qi in (1, 4) and q.high == h_hi:
            qcls.append("in-stat-high")
        elif qi in (1, 4) and q.low == h_lo:
            qcls.append("in-stat-low")
        elif qi in (2, 3) and q.high == h_hi:
            qcls.append("out-stat-high")
        elif qi in (2, 3) and q.low == h_lo:
            qcls.append("out-stat-low")
        else:
            qcls.append("inside")

    hour_inputs = HourStateInputs(
        sym=sym,
        block=block_id,
        hour_idx=hour_idx,
        q=q_now,
        q1cls=qcls[0],
        q2cls=qcls[1],
        q3cls=qcls[2],
        q4cls=qcls[3],
        sweep_set=tuple(sorted(sweep_set_emitted)),
        midhr=midhr_state,
        box_react=box_react_state,
    )
    yield DecisionPointSample(
        decision_ts=decision_ts,
        tf="hour",
        state_key=build_hour_key(hour_inputs),
        outcome=hour_outcome_raw,
    )
