"""Tests for the decision-point sampler.

Critical invariant: the state-key produced at decision-point T must depend
ONLY on bars with ts ≤ T. We test by perturbing bars > T and asserting the
key is unchanged.
"""
from __future__ import annotations

import pandas as pd
from copy import deepcopy

from engine.sampler import sample_decision_points, DecisionPointSample
from engine.walker import walk_triads


def _bar(ts: str, h: float, l: float) -> dict:
    return {
        "ts": pd.Timestamp(ts, tz="America/New_York"),
        "open": l, "high": h, "low": l, "close": h, "volume": 100,
    }


def _make_triad_df(highs_per_hour: list[float], lows_per_hour: list[float]) -> pd.DataFrame:
    rows = []
    for hour_offset, (hi, lo) in enumerate(zip(highs_per_hour, lows_per_hour)):
        h_idx = 9 + hour_offset
        for m in range(60):
            rows.append(_bar(f"2024-01-02 {h_idx:02d}:{m:02d}", h=hi, l=lo))
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype("float64")
    return df


def test_sampler_yields_at_least_one_sample_per_episode():
    df = _make_triad_df([100, 102, 104], [99, 100, 101])
    episode = next(walk_triads(df))
    samples = list(sample_decision_points(episode, sym="NQ"))
    assert len(samples) >= 1
    assert all(isinstance(s, DecisionPointSample) for s in samples)


def test_sampler_outcomes_are_final_triad_class():
    df = _make_triad_df([100, 102, 104], [99, 100, 101])  # line-up
    episode = next(walk_triads(df))
    samples = list(sample_decision_points(episode, sym="NQ"))
    triad_samples = [s for s in samples if s.tf == "triad"]
    assert all(s.outcome == "line-up" for s in triad_samples)


def test_sampler_is_causal_no_lookahead():
    """Modify bars AFTER the first quarter-close decision point — keys must NOT change."""
    df_a = _make_triad_df([100, 102, 104], [99, 100, 101])
    df_b = df_a.copy()
    # Tamper with bars at 11:00..11:59 (last hour). The 09:14 decision point
    # cannot legitimately depend on these.
    mask = (df_b["ts"] >= pd.Timestamp("2024-01-02 11:00", tz="America/New_York"))
    df_b.loc[mask, "high"] = 999.0
    df_b.loc[mask, "low"] = 0.5

    ep_a = next(walk_triads(df_a))
    ep_b = next(walk_triads(df_b))

    samples_a = [s for s in sample_decision_points(ep_a, sym="NQ")
                 if s.decision_ts <= pd.Timestamp("2024-01-02 09:30", tz="America/New_York")]
    samples_b = [s for s in sample_decision_points(ep_b, sym="NQ")
                 if s.decision_ts <= pd.Timestamp("2024-01-02 09:30", tz="America/New_York")]

    # Same number of samples in the early window; same state keys.
    assert len(samples_a) == len(samples_b)
    for a, b in zip(samples_a, samples_b):
        assert a.state_key == b.state_key, f"causality violated at {a.decision_ts}"
