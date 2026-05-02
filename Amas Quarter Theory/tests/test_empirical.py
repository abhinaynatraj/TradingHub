"""Tests for empirical aggregator. We feed in synthetic samples and assert
the aggregated parquet output has correct probabilities, Wilson CIs, and n."""
from __future__ import annotations

import pandas as pd

from engine.empirical import aggregate_samples
from engine.sampler import DecisionPointSample


def _s(key: str, outcome: str, ts: str = "2024-01-02 09:14") -> DecisionPointSample:
    return DecisionPointSample(
        decision_ts=pd.Timestamp(ts, tz="America/New_York"),
        tf="triad", state_key=key, outcome=outcome,
    )


def test_aggregate_one_state_one_outcome():
    samples = [_s("KEY_A", "line-up") for _ in range(10)]
    df = aggregate_samples(samples)
    row = df[(df["state_key"] == "KEY_A") & (df["outcome"] == "line-up")].iloc[0]
    assert row["n"] == 10
    assert row["p"] == 1.0
    assert row["ci_hi"] < 1.0  # Wilson never goes to 1.0


def test_aggregate_normalized_probabilities():
    samples = [_s("KEY_A", "line-up")] * 6 + [_s("KEY_A", "doji")] * 4
    df = aggregate_samples(samples)
    sub = df[df["state_key"] == "KEY_A"]
    assert sub["n"].iloc[0] == 10
    p_total = sub["p"].sum()
    assert abs(p_total - 1.0) < 1e-9


def test_multiple_states_independent():
    samples = ([_s("KEY_A", "line-up")] * 5 +
               [_s("KEY_B", "doji")] * 5)
    df = aggregate_samples(samples)
    assert df[df["state_key"] == "KEY_A"]["n"].iloc[0] == 5
    assert df[df["state_key"] == "KEY_B"]["n"].iloc[0] == 5
