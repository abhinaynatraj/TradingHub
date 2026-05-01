"""Forward-looking decision-point samples.

Complements the per-episode `sampler.py` (which only sees bars inside one
triad) with samples that need lookahead beyond the triad — sweep
probabilities, extension distributions, and triad-pair continuation.

Three new outcome streams, all keyed off existing state-vector keys:

  - tf=sweep_h   outcome ∈ {"taken","held"}   (hour-high taken in next 60 min)
  - tf=sweep_l   outcome ∈ {"taken","held"}   (hour-low taken in next 60 min)
  - tf=ext_up    outcome = quantized bucket   (max forward upside in next 60 min)
  - tf=ext_dn    outcome = quantized bucket   (max forward downside in next 60 min)
  - tf=pair      outcome ∈ {"continues","reverses"} (next triad's class match)

The state_key for sweep / ext samples = the same hour state-vector key that
the per-episode sampler emits at hour-close — so the Pine consumer can use
ONE hour-state-key to look up both the unconditional hour outcome and the
sweep / extension probabilities.

The state_key for pair samples = the just-closed triad's state-vector key
plus the triad's classification appended (so we condition on what the
trader has just observed).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal

import pandas as pd

from engine import time_primitives as tp
from engine.aggregations import HourAgg, QuarterAgg, TriadAgg
from engine.classifier import classify_hour, classify_triad
from engine.state_vector import (
    HourStateInputs,
    TriadStateInputs,
    build_hour_key,
    build_triad_key,
)
from engine.walker import TriadEpisode, walk_triads


# Forward window for sweep / extension samples (in 1m bars).
DEFAULT_FORWARD_BARS = 60

# Quantization grid for extension-magnitude outcomes (in price points).
# Outcome is the *bucket label* — aggregator computes mean/median/mode of
# the bucket distribution per state.
EXT_BUCKETS_PTS = [0, 5, 10, 15, 20, 30, 50, 75, 100, 150, 200, 300, 500]


def _bucket_label(pts: float) -> str:
    """Return a string label for the largest bucket boundary ≤ pts."""
    label = "0"
    for b in EXT_BUCKETS_PTS:
        if pts >= b:
            label = str(b)
        else:
            break
    return label


@dataclass(frozen=True)
class ForwardSample:
    decision_ts: pd.Timestamp
    tf: Literal["sweep_h", "sweep_l", "ext_up", "ext_dn", "pair"]
    state_key: str
    outcome: str


def _hour_state_key(
    sym: str,
    block_id: str,
    hour_idx: int,
    hour: HourAgg,
    sweep_set: tuple[str, ...],
    midhr_state: str,
    box_react_state: str,
) -> str:
    """Build the hour state-key for a CLOSED hour.

    Mirrors the per-episode sampler's hour-close key construction (q='closed'
    plus per-quarter classification).
    """
    h_hi = hour.high
    h_lo = hour.low
    qcls: list[str] = []
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

    return build_hour_key(HourStateInputs(
        sym=sym, block=block_id, hour_idx=hour_idx, q="closed",
        q1cls=qcls[0], q2cls=qcls[1], q3cls=qcls[2], q4cls=qcls[3],
        sweep_set=sweep_set, midhr=midhr_state, box_react=box_react_state,
    ))


def _triad_state_key(
    sym: str,
    block_id: str,
    triad: TriadAgg,
    midhr_state: str,
    mid3h_state: str,
    box_react_state: str,
) -> str:
    """Build the triad state-key for a CLOSED triad."""
    c1 = triad.c1
    c1cls_raw = classify_hour(c1) if c1 is not None else "doji"
    c1cls = c1cls_raw if c1cls_raw != "pending" else "doji"

    c2 = triad.c2
    c2sw_c1h = c2sw_c1l = c2_inside = False
    c2vh = c2vl = "na"
    if c1 is not None and c2 is not None and c2.high is not None:
        c1_hi, c1_lo = c1.high, c1.low
        c2_hi, c2_lo = c2.high, c2.low
        if c1_hi is not None and c1_lo is not None:
            c2sw_c1h = c2_hi > c1_hi
            c2sw_c1l = c2_lo < c1_lo
            c2_inside = (c2_hi < c1_hi) and (c2_lo > c1_lo)
            c2vh = "above" if c2_hi > c1_hi else ("below" if c2_hi < c1_hi else "inside")
            c2vl = "above" if c2_lo > c1_lo else ("below" if c2_lo < c1_lo else "inside")

    return build_triad_key(TriadStateInputs(
        sym=sym, block=block_id, c1cls=c1cls, c2q="closed",
        c2vh=c2vh, c2vl=c2vl, c2sw_c1h=c2sw_c1h, c2sw_c1l=c2sw_c1l,
        c2_inside=c2_inside, midhr=midhr_state, mid3h=mid3h_state,
        box_react=box_react_state,
    ))


def sample_forward(
    df_bars: pd.DataFrame, sym: str,
    *, forward_bars: int = DEFAULT_FORWARD_BARS,
) -> Iterator[ForwardSample]:
    """Walk full bar series and yield forward-looking samples.

    Samples fire at:
      - each hour close (sweep + extension)
      - each triad close (pair-continuation)

    Causal: only uses bars at-or-before the decision timestamp for state-key
    construction; only uses bars STRICTLY AFTER for outcome resolution.
    """
    if df_bars.empty:
        return

    # Pre-index by timestamp for O(1) forward lookups.
    df = df_bars.set_index("ts", drop=False).sort_index()
    bars_high = df["high"].to_numpy()
    bars_low  = df["low"].to_numpy()
    bars_ts   = df.index.to_numpy()

    episodes = list(walk_triads(df_bars))
    if not episodes:
        return

    prior_episode: TriadEpisode | None = None

    for episode in episodes:
        # ── Per-hour close samples (sweep + extension) ───────────────────────
        for hour_idx in (1, 2, 3):
            hour: HourAgg | None = getattr(episode.triad, f"c{hour_idx}")
            if hour is None or hour.high is None or hour.low is None or hour.q4 is None:
                continue

            close_ts = hour.anchor_ts + pd.Timedelta(minutes=59)
            # The :59 bar's close is what we project from. Find it via index.
            try:
                pos = df.index.get_loc(close_ts)
            except KeyError:
                continue
            if not isinstance(pos, int):
                continue

            close_px = float(df.iloc[pos]["close"])
            future_end = pos + 1 + forward_bars
            if future_end > len(df):
                continue  # not enough forward data — drop

            future_high = bars_high[pos+1:future_end]
            future_low  = bars_low[pos+1:future_end]
            if len(future_high) == 0:
                continue

            h_taken = bool(future_high.max() > hour.high)
            l_taken = bool(future_low.min()  < hour.low)
            max_up_pts = max(0.0, float(future_high.max()) - close_px)
            max_dn_pts = max(0.0, close_px - float(future_low.min()))

            # Hour state-key. We don't have the full midline / box_react
            # state from the per-episode sampler here; they require running
            # the same accumulator logic. For v1 we use "untouched"/"none"
            # placeholders — Pine consumer applies the same defaults.
            hour_key = _hour_state_key(
                sym=sym, block_id=episode.block_id, hour_idx=hour_idx,
                hour=hour, sweep_set=(),
                midhr_state="untouched", box_react_state="none",
            )

            # Per-stream state_keys. We start from the canonical hour key
            # (tf=hour) and rewrite the tf token so pine_emit can route
            # each stream into its own map by greping `|tf=…|`.
            for tf, outcome in (
                ("sweep_h", "taken" if h_taken else "held"),
                ("sweep_l", "taken" if l_taken else "held"),
                ("ext_up",  _bucket_label(max_up_pts)),
                ("ext_dn",  _bucket_label(max_dn_pts)),
            ):
                key = hour_key.replace("|tf=hour|", f"|tf={tf}|")
                yield ForwardSample(decision_ts=close_ts, tf=tf, state_key=key,
                                    outcome=outcome)

        # ── Triad-close pair-continuation sample ─────────────────────────────
        # Need the NEXT triad's classification. We look ahead one episode
        # and see if its block_id is the immediately-following block.
        # episodes are sorted by anchor_ts.
        c3 = episode.triad.c3
        if c3 is None or c3.q4 is None:
            prior_episode = episode
            continue
        c3_close = c3.anchor_ts + pd.Timedelta(minutes=59)

        next_idx = episodes.index(episode) + 1
        if next_idx < len(episodes):
            next_ep = episodes[next_idx]
            # Only emit if the next episode is the immediately-adjacent block
            # (no overnight or weekend gap that breaks continuity).
            expected_next_anchor = episode.anchor_ts + pd.Timedelta(hours=3)
            if next_ep.anchor_ts == expected_next_anchor:
                cur_class  = episode.classification
                next_class = next_ep.classification
                # "Continues" = next triad's classification matches the
                # just-closed one (line-up→line-up, line-down→line-down,
                # apex-up→apex-up, apex-down→apex-down, doji→doji).
                continues = (cur_class == next_class)
                triad_key = _triad_state_key(
                    sym=sym, block_id=episode.block_id, triad=episode.triad,
                    midhr_state="untouched", mid3h_state="untouched",
                    box_react_state="none",
                )
                # Rewrite tf=triad → tf=pair, append the just-observed
                # classification so the readout conditions on it.
                pair_key = (
                    triad_key.replace("|tf=triad|", "|tf=pair|")
                    + f"|prior_class={cur_class}"
                )
                yield ForwardSample(
                    decision_ts=c3_close, tf="pair", state_key=pair_key,
                    outcome="continues" if continues else "reverses",
                )

        prior_episode = episode
