# Phase 3 — Empirical Aggregator

> **Sub-skill:** Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Walk every historical triad in `nq_1m` / `es_1m`, sample state vectors at decision points, aggregate `(state_key, outcome)` into `P(outcome | state_key)` with Wilson CIs and `n`. Produce parquet outputs that drive the Pine table.

**Prereq:** Phase 1, Phase 2 complete.

---

### Task 3.1: Wilson CI helper (copied from Amas Models)

**Files:**
- Create: `engine/stats.py`
- Create: `tests/test_stats.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_stats.py`

```python
"""Tests for stats helpers — Wilson CI and outcome aggregation."""
from engine.stats import wilson_ci


def test_wilson_ci_zero_n_returns_zero_zero():
    lo, hi = wilson_ci(wins=0, n=0)
    assert lo == 0.0 and hi == 0.0


def test_wilson_ci_perfect_score_smaller_than_one():
    # 10/10 wins. Wilson upper bound < 1.0 (CI accounts for sample size).
    lo, hi = wilson_ci(wins=10, n=10)
    assert hi < 1.0
    assert 0.6 < lo < 1.0


def test_wilson_ci_centered_around_observed_rate():
    lo, hi = wilson_ci(wins=50, n=100)
    assert 0.40 < lo < 0.50
    assert 0.50 < hi < 0.60


def test_wilson_ci_widens_with_smaller_n():
    lo_big, hi_big = wilson_ci(wins=500, n=1000)
    lo_small, hi_small = wilson_ci(wins=5, n=10)
    assert (hi_small - lo_small) > (hi_big - lo_big)
```

- [ ] **Step 2: Verify FAIL → run pytest.**

- [ ] **Step 3: Implement `engine/stats.py`** (port from `Amas Models/engine/stats.py`):

```python
"""Stats helpers: Wilson CI for binomial proportions.

Adapted from Amas Models/engine/stats.py — same formula, same conventions.
"""
from __future__ import annotations

import math


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Return (lo, hi) of the Wilson 95%-CI for wins / n. (0, 0) when n=0."""
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)
```

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Commit.**

```bash
git add engine/stats.py tests/test_stats.py
git commit -m "feat(quarter-theory): add Wilson CI helper (port from Amas Models)"
```

---

### Task 3.2: Triad walker — iterate every historical triad

**Files:**
- Create: `engine/walker.py`
- Create: `tests/test_walker.py`

- [ ] **Step 1: Write failing test using a synthetic in-memory frame**

File: `tests/test_walker.py`

```python
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
```

- [ ] **Step 2: Verify FAIL.**

- [ ] **Step 3: Implement `engine/walker.py`**

```python
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
```

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Commit.**

```bash
git add engine/walker.py tests/test_walker.py
git commit -m "feat(quarter-theory): add historical triad walker"
```

---

### Task 3.3: Decision-point sampler (causal — no lookahead)

**Files:**
- Create: `engine/sampler.py`
- Create: `tests/test_sampler.py`

The sampler produces `(state_key, eventual_outcome)` pairs from a TriadEpisode, evaluating state at every decision point with strict causality.

- [ ] **Step 1: Write failing test for causal sampling**

File: `tests/test_sampler.py`

```python
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
    assert all(s.outcome == "line-up" for s in samples)


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
```

- [ ] **Step 2: Verify FAIL.**

- [ ] **Step 3: Implement `engine/sampler.py`**

The sampler iterates the episode's bars in order. At each decision-point predicate (quarter close, hour close, triad close, sweep mid-quarter, midline reaction confirmed, band rejection confirmed, 05-box close), it builds a fresh state vector using **only bars seen so far** and the current running aggregations.

```python
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
from engine.box_05 import build_box_05, band_levels, detect_band_rejection
from engine.classifier import (
    HourClass, TriadClass, classify_hour, classify_triad, detect_sweeps_in_hour,
)
from engine.midline import (
    MidlineReaction, detect_midline_reaction, resolve_midline_source,
)
from engine.state_vector import (
    HourStateInputs, TriadStateInputs, build_hour_key, build_triad_key,
)
from engine.walker import TriadEpisode


@dataclass(frozen=True)
class DecisionPointSample:
    decision_ts: pd.Timestamp
    tf: Literal["triad", "hour"]
    state_key: str
    outcome: str                # "line-up" | "line-down" | "apex-up" | "apex-down" | "doji" (triad)
                                # or "line-up" | "line-down" | "doji" (hour)


def sample_decision_points(episode: TriadEpisode, sym: str) -> Iterator[DecisionPointSample]:
    """Yield (state_key, outcome) at every decision point in the triad. Causal."""
    bars = episode.bars
    block_id = episode.block_id
    triad_outcome = episode.classification

    # Running state. Rebuilt as we walk.
    triad = TriadAgg(block_id=block_id, anchor_ts=episode.anchor_ts)
    prior_hour: HourAgg | None = None    # the hour that just closed before this one
    prior_triad: TriadAgg | None = None  # not used in v1 (mid3h based on within-triad only)

    sweep_set_emitted: set[str] = set()
    midhr_state = "untouched"
    mid3h_state = "untouched"
    box_react_state = "none"

    for _, bar in bars.iterrows():
        ts = bar["ts"]
        hour_idx = tp.hour_index_in_triad(ts)
        if hour_idx is None:
            continue
        hour = getattr(triad, f"c{hour_idx}")
        if hour is None:
            hour = HourAgg(anchor_ts=tp.hour_anchor_ts(ts))
            setattr(triad, f"c{hour_idx}", hour)

        q_idx = tp.quarter_of(ts)
        quarter = getattr(hour, f"q{q_idx}")
        if quarter is None:
            quarter = QuarterAgg(quarter_idx=q_idx, anchor_ts=tp.quarter_anchor_ts(ts))
            setattr(hour, f"q{q_idx}", quarter)
        quarter.update(ts, bar["open"], bar["high"], bar["low"], bar["close"])

        # 05-box state for this hour
        if ts.minute in (0, 1, 2, 3, 4):
            seen_minutes = {ts.minute}
            if hour.box_05_high is None:
                hour.box_05_high = bar["high"]; hour.box_05_low = bar["low"]
            else:
                hour.box_05_high = max(hour.box_05_high, bar["high"])
                hour.box_05_low = min(hour.box_05_low, bar["low"])
            if ts.minute == 4:
                hour.box_05_locked = True

        # Detect new sweeps that appeared on this bar
        all_sweeps = detect_sweeps_in_hour(hour)
        for s in all_sweeps:
            label = f"Q{s.by_q}_swept_Q{s.target_q}_{s.side}"
            if label not in sweep_set_emitted:
                sweep_set_emitted.add(label)
                yield from _emit(
                    sym, block_id, hour_idx, ts, hour, triad,
                    triad_outcome, prior_hour,
                    sweep_set_emitted, midhr_state, mid3h_state, box_react_state,
                )

        # Midline reactions (1h)
        if prior_hour is not None or hour.high is not None:
            prior_hi = prior_hour.high if prior_hour else None
            prior_lo = prior_hour.low if prior_hour else None
            mid, _src = resolve_midline_source(
                current_high=hour.high, current_low=hour.low,
                prior_high=prior_hi, prior_low=prior_lo,
            )
            r = detect_midline_reaction(mid, bar["open"], bar["high"], bar["low"], bar["close"])
            if r is not None:
                midhr_state = r.value
                yield from _emit(
                    sym, block_id, hour_idx, ts, hour, triad,
                    triad_outcome, prior_hour,
                    sweep_set_emitted, midhr_state, mid3h_state, box_react_state,
                )

        # Band rejection (after 05-box locked)
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
                    sym, block_id, hour_idx, ts, hour, triad,
                    triad_outcome, prior_hour,
                    sweep_set_emitted, midhr_state, mid3h_state, box_react_state,
                )

        # Quarter close
        if ts.minute in (14, 29, 44, 59):
            yield from _emit(
                sym, block_id, hour_idx, ts, hour, triad,
                triad_outcome, prior_hour,
                sweep_set_emitted, midhr_state, mid3h_state, box_react_state,
            )

        # Hour close
        if ts.minute == 59:
            prior_hour = hour
            sweep_set_emitted = set()
            midhr_state = "untouched"
            box_react_state = "none"


def _emit(
    sym, block_id, hour_idx, decision_ts, hour, triad, triad_outcome,
    prior_hour, sweep_set_emitted, midhr_state, mid3h_state, box_react_state,
) -> Iterator[DecisionPointSample]:
    """Emit one triad-level and one hour-level sample at decision_ts."""
    # Triad-level state
    c1cls = classify_hour(triad.c1) if triad.c1 is not None else "doji"
    if c1cls == "pending":
        c1cls = "doji"  # fallback for keys built mid-C1

    c2 = triad.c2
    c2q = "closed" if hour_idx > 2 else (f"Q{tp.quarter_of(decision_ts)}" if hour_idx == 2 else "Q1")
    if hour_idx == 2 and c2 is not None and c2.q4 is not None and decision_ts.minute == 59:
        c2q = "closed"

    c2sw_c1h = c2sw_c1l = c2_inside = False
    c2vh = c2vl = "na"
    if hour_idx >= 2 and triad.c1 is not None and triad.c2 is not None and triad.c2.high is not None:
        c1_hi, c1_lo = triad.c1.high, triad.c1.low
        c2_hi, c2_lo = triad.c2.high, triad.c2.low
        c2sw_c1h = c2_hi > c1_hi
        c2sw_c1l = c2_lo < c1_lo
        c2_inside = (c2_hi < c1_hi) and (c2_lo > c1_lo)
        c2vh = "above" if c2_hi > c1_hi else ("below" if c2_hi < c1_hi else "inside")
        c2vl = "above" if c2_lo > c1_lo else ("below" if c2_lo < c1_lo else "inside")

    triad_inputs = TriadStateInputs(
        sym=sym, block=block_id, c1cls=c1cls if c1cls != "pending" else "doji",
        c2q=c2q, c2vh=c2vh, c2vl=c2vl,
        c2sw_c1h=c2sw_c1h, c2sw_c1l=c2sw_c1l, c2_inside=c2_inside,
        midhr=midhr_state, mid3h=mid3h_state, box_react=box_react_state,
    )
    yield DecisionPointSample(
        decision_ts=decision_ts, tf="triad",
        state_key=build_triad_key(triad_inputs),
        outcome=triad_outcome,
    )

    # Hour-level state — outcome = the eventual classification of `hour`.
    hour_outcome = classify_hour(hour) if hour.q4 is not None else None
    if hour_outcome is not None and hour_outcome != "pending":
        q_now = f"Q{tp.quarter_of(decision_ts)}" if decision_ts.minute < 59 else "closed"
        qcls = []
        for q_idx in range(1, 5):
            q = getattr(hour, f"q{q_idx}")
            if q is None:
                qcls.append("inside")
            elif q_idx in (1, 4) and q.high == hour.high:
                qcls.append("in-stat-high")
            elif q_idx in (1, 4) and q.low == hour.low:
                qcls.append("in-stat-low")
            elif q_idx in (2, 3) and q.high == hour.high:
                qcls.append("out-stat-high")
            elif q_idx in (2, 3) and q.low == hour.low:
                qcls.append("out-stat-low")
            else:
                qcls.append("inside")
        hour_inputs = HourStateInputs(
            sym=sym, block=block_id, hour_idx=hour_idx, q=q_now,
            q1cls=qcls[0], q2cls=qcls[1], q3cls=qcls[2], q4cls=qcls[3],
            sweep_set=tuple(sorted(sweep_set_emitted)),
            midhr=midhr_state, box_react=box_react_state,
        )
        yield DecisionPointSample(
            decision_ts=decision_ts, tf="hour",
            state_key=build_hour_key(hour_inputs),
            outcome=hour_outcome,
        )
```

- [ ] **Step 4: PASS.** (The sampler is intricate; expect to iterate. The 3 tests in `test_sampler.py` are the gate — once they pass, move on.)

- [ ] **Step 5: Commit.**

```bash
git add engine/sampler.py tests/test_sampler.py
git commit -m "feat(quarter-theory): add causal decision-point sampler"
```

---

### Task 3.4: Empirical aggregator — turn samples into P-tables

**Files:**
- Create: `engine/empirical.py`
- Create: `tests/test_empirical.py`

- [ ] **Step 1: Write failing test using a tiny synthetic dataset**

File: `tests/test_empirical.py`

```python
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
```

- [ ] **Step 2: Verify FAIL.**

- [ ] **Step 3: Implement `engine/empirical.py`**

```python
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

    Wraps walk_triads + sample_decision_points + aggregate_samples for callers
    that just want the final parquet-shape DataFrame.
    """
    from engine.walker import walk_triads
    from engine.sampler import sample_decision_points

    all_samples = []
    for episode in walk_triads(df_bars):
        all_samples.extend(sample_decision_points(episode, sym=sym))
    return aggregate_samples(all_samples)
```

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Commit.**

```bash
git add engine/empirical.py tests/test_empirical.py
git commit -m "feat(quarter-theory): add empirical probability aggregator with Wilson CIs"
```

---

### Task 3.5: Strip-order ranker (mutual information per field → fallback order)

**Files:**
- Create: `engine/strip_order.py`
- Create: `tests/test_strip_order.py`

- [ ] **Step 1: Write failing test**

File: `tests/test_strip_order.py`

```python
"""Tests for strip-order ranking (MI of each field with outcome).

The strip order determines fallback when full state-key has too few samples.
The least-informative field (lowest MI) is stripped first.
"""
from __future__ import annotations

import pandas as pd

from engine.strip_order import compute_strip_order


def test_strip_order_returns_all_fields_in_ranked_order():
    # Fabricate samples where field "a" perfectly predicts outcome and "b"
    # is random. Strip order should place "a" LAST (highest MI = most informative).
    rows = []
    for i in range(100):
        rows.append({"a": "X", "b": i % 2, "outcome": "lup"})
        rows.append({"a": "Y", "b": i % 2, "outcome": "ldn"})
    df = pd.DataFrame(rows)
    order = compute_strip_order(df, fields=["a", "b"])
    assert order == ["b", "a"]  # "b" stripped first (less informative)


def test_strip_order_handles_constant_field():
    # Field with only one value carries 0 MI; strip first.
    rows = [
        {"a": "X", "b": "1", "outcome": "lup"},
        {"a": "X", "b": "2", "outcome": "ldn"},
        {"a": "Y", "b": "1", "outcome": "lup"},
        {"a": "Y", "b": "2", "outcome": "ldn"},
    ]
    df = pd.DataFrame(rows)
    order = compute_strip_order(df, fields=["a", "b"])
    assert order[0] == "a"  # "a" has MI=0 with outcome
```

- [ ] **Step 2: Verify FAIL.**

- [ ] **Step 3: Implement `engine/strip_order.py`**

```python
"""Mutual information ranking of state-vector fields.

The empirical aggregator emits state keys as concatenations. To compute MI,
we need samples broken out into individual fields. compute_strip_order takes
a long-form DataFrame with one column per field and one outcome column.

Strip order = ascending by MI (least informative field stripped first).
"""
from __future__ import annotations

import math
from typing import Iterable

import pandas as pd


def _mutual_information(df: pd.DataFrame, field: str, outcome_col: str = "outcome") -> float:
    """Standard MI(X; Y) in nats."""
    n = len(df)
    if n == 0:
        return 0.0
    pxy = df.groupby([field, outcome_col]).size() / n
    px = df.groupby(field).size() / n
    py = df.groupby(outcome_col).size() / n
    mi = 0.0
    for (x, y), p in pxy.items():
        if p > 0:
            mi += p * math.log(p / (px[x] * py[y]))
    return mi


def compute_strip_order(df: pd.DataFrame, fields: Iterable[str], outcome_col: str = "outcome") -> list[str]:
    """Return field names sorted ascending by MI with outcome.
    Lowest-MI field is stripped first in fallback."""
    scored = [(f, _mutual_information(df, f, outcome_col)) for f in fields]
    scored.sort(key=lambda x: x[1])
    return [f for f, _ in scored]
```

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Commit.**

```bash
git add engine/strip_order.py tests/test_strip_order.py
git commit -m "feat(quarter-theory): add MI-based strip-order ranker"
```

---

### Phase 3 smoke test

- [ ] **Run all tests.** Expect ~85+ passed.

```bash
python3 -m pytest tests/ -q
```

- [ ] **End-to-end smoke run on real data (small slice):**

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from engine.db import load_bars
from engine.empirical import run_full_empirical

df = load_bars('nq_1m', start='2024-01-02', end='2024-01-09')
print(f'Loaded {len(df)} bars')
result = run_full_empirical(df, sym='NQ')
print(f'Aggregated {len(result)} (state_key, outcome) rows')
print(result.head(10))
print(f'Unique state keys: {result.state_key.nunique()}')
print(f'Total samples: {result.n.sum() / 5}')  # /5 because each sample contributes to 5 outcomes (rough)
"
```
Expected: bar count ~5,000, several hundred state keys, sample sums sensible.

**End of Phase 3.** Move to [Phase 4 — Quarter-pair backtest](phase-4-quarter-pair-backtest.md).
