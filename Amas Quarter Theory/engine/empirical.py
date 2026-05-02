"""Empirical probability aggregator.

Reduces a stream of DecisionPointSample → a DataFrame with columns:
  state_key | outcome | p | ci_lo | ci_hi | n
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

import pandas as pd

from engine.sampler import DecisionPointSample
from engine.stats import wilson_ci


def aggregate_samples(samples: Iterable[DecisionPointSample]) -> pd.DataFrame:
    """Aggregate samples into a probability table.

    Probability = outcome_count / total_for_state. Wilson CI on the proportion.
    """
    by_state: dict[str, Counter] = {}
    for s in samples:
        by_state.setdefault(s.state_key, Counter())[s.outcome] += 1

    rows = []
    for key, counts in by_state.items():
        n = sum(counts.values())
        for outcome, wins in counts.items():
            p = wins / n
            lo, hi = wilson_ci(wins=wins, n=n)
            rows.append({
                "state_key": key, "outcome": outcome,
                "p": p, "ci_lo": lo, "ci_hi": hi, "n": n,
            })
    return pd.DataFrame(rows)


def run_full_empirical(df_bars: pd.DataFrame, sym: str) -> pd.DataFrame:
    """End-to-end: bars → walk triads → sample decision points → aggregate.

    Combines two sample streams into one parquet-shape DataFrame:
      1. Per-episode samples (existing): triad/hour outcomes at each
         decision point (quarter close, hour close, sweep, midline, etc.).
      2. Forward-looking samples (new): hour-close sweep / extension and
         triad-close pair continuation. These need lookahead beyond the
         per-episode bars, so they have their own walker.

    Both streams write into the same `state_key | outcome | p | ci_lo |
    ci_hi | n` shape; the `tf=` token in the state-key distinguishes them
    on the consumer side.
    """
    from engine.walker import walk_triads
    from engine.sampler import sample_decision_points
    from engine.forward_sampler import sample_forward

    all_samples = []
    for episode in walk_triads(df_bars):
        all_samples.extend(sample_decision_points(episode, sym=sym))

    # Forward-looking stream: emits its own .tf field but we coerce all
    # samples into the same DecisionPointSample-compatible shape that
    # `aggregate_samples` consumes (it only needs state_key + outcome).
    from engine.sampler import DecisionPointSample
    for fs in sample_forward(df_bars, sym=sym):
        all_samples.append(DecisionPointSample(
            decision_ts=fs.decision_ts, tf=fs.tf,  # type: ignore[arg-type]
            state_key=fs.state_key, outcome=fs.outcome,
        ))
    return aggregate_samples(all_samples)
