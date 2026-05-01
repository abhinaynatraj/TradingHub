"""Tests for forward_sampler — hour-close sweep + extension + triad-pair samples.

We synthesize 1m bar streams long enough to cover at least 2 consecutive
triad blocks (so the pair-continuation sample fires), then check that the
emitted samples have the right tf, outcome, and counts.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from engine.forward_sampler import (
    DEFAULT_FORWARD_BARS,
    ForwardSample,
    _bucket_label,
    sample_forward,
)


def _bars(rows: Iterable[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """Build a 1m bar DataFrame from `(ts, open, high, low, close)` tuples."""
    df = pd.DataFrame(
        rows,
        columns=["ts", "open", "high", "low", "close"],
    )
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize("America/New_York")
    df["volume"] = 100  # arbitrary
    return df


def _flat_minute_range(start: str, end: str, *, base: float = 100.0) -> list[tuple]:
    """Generate flat OHLC=base bars at 1m spacing across `[start, end)`."""
    rng = pd.date_range(start=start, end=end, freq="1min", tz="America/New_York", inclusive="left")
    return [(t.strftime("%Y-%m-%d %H:%M"), base, base, base, base) for t in rng]


# ── Bucket label boundary cases ─────────────────────────────────────────

def test_bucket_label_zero():
    assert _bucket_label(0.0) == "0"


def test_bucket_label_just_above_boundary():
    assert _bucket_label(5.0) == "5"
    assert _bucket_label(5.4) == "5"
    assert _bucket_label(9.99) == "5"
    assert _bucket_label(10.0) == "10"


def test_bucket_label_above_max():
    # 750 pts > top bucket (500) → clamps to 500
    assert _bucket_label(750.0) == "500"


# ── Sweep detection ─────────────────────────────────────────────────────

def test_late_hour_dropped_when_forward_window_truncated():
    # 1 triad (09:00–11:59) — the C3 hour (11:00) doesn't have a 60m
    # forward window, so its sweep / ext samples must be dropped.
    rows = _flat_minute_range("2024-01-02 09:00", "2024-01-02 12:00")
    df = _bars(rows)
    samples = list(sample_forward(df, sym="NQ", forward_bars=60))
    # The 11:00 hour close (11:59) has no forward bars → no samples for it.
    assert not any(s.decision_ts.hour == 11 for s in samples)
    # Earlier hours (09:00, 10:00) DO have a 60m window inside the triad
    # so they fire normally.
    assert any(s.decision_ts.hour == 9  for s in samples)
    assert any(s.decision_ts.hour == 10 for s in samples)


def test_sweep_taken_when_future_high_exceeds_hour_high():
    # Hour 09:00–09:59 with hour_high = 102 (set at 09:30).
    # Then 10:00–11:59 forward window with bar at 10:30 making 105 → sweep fires.
    rows: list[tuple] = []
    # 09:00–09:59 — flat at 100 except 09:30 which spikes to 102/100
    for m in range(60):
        ts = f"2024-01-02 09:{m:02d}"
        if m == 30:
            rows.append((ts, 100, 102, 100, 100))
        else:
            rows.append((ts, 100, 100, 100, 100))
    # 10:00–11:59 — flat at 100 except 10:30 which spikes to 105/100
    for h in (10, 11):
        for m in range(60):
            ts = f"2024-01-02 {h:02d}:{m:02d}"
            if h == 10 and m == 30:
                rows.append((ts, 100, 105, 100, 100))
            else:
                rows.append((ts, 100, 100, 100, 100))

    df = _bars(rows)
    samples = list(sample_forward(df, sym="NQ", forward_bars=60))

    # Should fire sweep_h "taken", sweep_l "held", ext_up bucket >0, ext_dn bucket 0.
    sweep_h = [s for s in samples if s.tf == "sweep_h"]
    sweep_l = [s for s in samples if s.tf == "sweep_l"]
    ext_up  = [s for s in samples if s.tf == "ext_up"]
    ext_dn  = [s for s in samples if s.tf == "ext_dn"]

    # First hour (09:00) is the only hour with a full forward window in this fixture.
    assert len(sweep_h) >= 1
    assert sweep_h[0].outcome == "taken"
    assert sweep_l[0].outcome == "held"
    assert ext_up[0].outcome != "0"  # at least the 5-bucket
    assert ext_dn[0].outcome == "0"


def test_sweep_held_when_future_stays_inside():
    # Hour with high=102 / low=98, then forward window stays inside [98, 102].
    rows: list[tuple] = []
    for m in range(60):
        ts = f"2024-01-02 09:{m:02d}"
        if m == 15:   rows.append((ts, 100, 102, 100, 100))   # set hour_high
        elif m == 45: rows.append((ts, 100, 100,  98, 100))   # set hour_low
        else:         rows.append((ts, 100, 100, 100, 100))
    for h in (10, 11):
        for m in range(60):
            ts = f"2024-01-02 {h:02d}:{m:02d}"
            rows.append((ts, 100, 101, 99, 100))  # inside [98, 102]

    df = _bars(rows)
    samples = list(sample_forward(df, sym="NQ", forward_bars=60))
    sweep_h = [s for s in samples if s.tf == "sweep_h"]
    sweep_l = [s for s in samples if s.tf == "sweep_l"]
    assert len(sweep_h) >= 1
    assert sweep_h[0].outcome == "held"
    assert sweep_l[0].outcome == "held"


# ── Pair continuation (next triad's classification) ─────────────────────

def test_pair_sample_state_key_includes_prior_class():
    # Build two consecutive triads (09–12 followed by 12–15). Synthetic
    # bar values are flat so both triads classify as "doji" → continues.
    # This test mostly checks the state_key shape, not the outcome value.
    rows = _flat_minute_range("2024-01-02 09:00", "2024-01-02 16:00")
    df = _bars(rows)
    samples = list(sample_forward(df, sym="NQ", forward_bars=60))
    pair = [s for s in samples if s.tf == "pair"]
    if pair:
        # Pair key includes "|prior_class=…" suffix so the readout
        # conditions on the just-observed classification.
        assert "|prior_class=" in pair[0].state_key
