# Phase 4 — Quarter-Pair Backtest

> **Sub-skill:** Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** For every (state_key, decision_point) combination, find the historically-best (entry_q, stop_q, direction) quarter-pair recommendation. Top-1 per state by EV. Output mapped into a Pine table.

**Prereq:** Phase 1, 2, 3 complete.

**Restrictions for v1 (per spec):**
- Decision points: quarter-close boundaries only (12 per triad).
- Stops must be in a CLOSED quarter at entry time (no same-quarter stops).
- Entry trigger: close of the entry quarter.
- Target: fixed at 2R (R = entry-to-stop distance).
- Same-bar tie → SL.
- `OUTCOME_MAX_BARS = 1440`. Expired excluded from WR/EV.

---

### Task 4.1: TradeDef + outcome resolver

**Files:**
- Create: `engine/quarter_pair_backtest.py`
- Create: `tests/test_quarter_pair.py`

- [ ] **Step 1: Write failing test for outcome resolver**

File: `tests/test_quarter_pair.py`

```python
"""Tests for the quarter-pair backtest.

Trade definition: (entry_q, stop_q, direction). Entry on close of entry_q.
Stop = stop_q's high (short) or low (long). Target = 2R from entry.
Same-bar tie → SL. Expired (> OUTCOME_MAX_BARS) excluded from WR.
"""
from __future__ import annotations

import pandas as pd

from engine.quarter_pair_backtest import (
    TradeDef, resolve_trade_outcome, TradeOutcome,
)


def _bar(ts: str, h: float, l: float) -> dict:
    return {"ts": pd.Timestamp(ts, tz="America/New_York"),
            "open": l, "high": h, "low": l, "close": h, "volume": 100}


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    return df


def test_long_hits_target_at_2r():
    df = _frame([
        _bar("2024-01-02 09:14", h=100.0, l=99.0),  # entry close = 100.0
        _bar("2024-01-02 09:15", h=102.5, l=99.5),  # 2R from stop=99 → target=102 — hits
    ])
    outcome = resolve_trade_outcome(
        bars=df,
        entry_ts=pd.Timestamp("2024-01-02 09:14", tz="America/New_York"),
        entry_price=100.0,
        stop_price=99.0,
        direction="long",
    )
    assert outcome.won is True
    assert outcome.r_realized == 2.0


def test_long_stops_out_at_1r_loss():
    df = _frame([
        _bar("2024-01-02 09:14", h=100.0, l=99.0),
        _bar("2024-01-02 09:15", h=100.5, l=98.5),  # hits stop at 99
    ])
    outcome = resolve_trade_outcome(
        bars=df,
        entry_ts=pd.Timestamp("2024-01-02 09:14", tz="America/New_York"),
        entry_price=100.0, stop_price=99.0, direction="long",
    )
    assert outcome.won is False
    assert outcome.r_realized == -1.0


def test_short_hits_target():
    df = _frame([
        _bar("2024-01-02 09:14", h=100.0, l=99.0),
        _bar("2024-01-02 09:15", h=100.2, l=97.5),  # short entry 100, stop 101, target 98 — hits
    ])
    outcome = resolve_trade_outcome(
        bars=df,
        entry_ts=pd.Timestamp("2024-01-02 09:14", tz="America/New_York"),
        entry_price=100.0, stop_price=101.0, direction="short",
    )
    assert outcome.won is True
    assert outcome.r_realized == 2.0


def test_same_bar_tie_resolves_to_stop():
    # Same bar touches both stop and target — must resolve to STOP.
    df = _frame([
        _bar("2024-01-02 09:14", h=100.0, l=99.0),
        _bar("2024-01-02 09:15", h=102.5, l=98.5),  # touches stop 99 AND target 102
    ])
    outcome = resolve_trade_outcome(
        bars=df,
        entry_ts=pd.Timestamp("2024-01-02 09:14", tz="America/New_York"),
        entry_price=100.0, stop_price=99.0, direction="long",
    )
    assert outcome.won is False  # tie → SL


def test_expired_when_neither_level_reached_within_max_bars():
    rows = [_bar("2024-01-02 09:14", h=100.0, l=99.0)]
    # 1500 bars all printing 99.5..100.5 (no resolution)
    for i in range(1500):
        ts = pd.Timestamp("2024-01-02 09:15", tz="America/New_York") + pd.Timedelta(minutes=i)
        rows.append({
            "ts": ts, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0,
            "volume": 100,
        })
    df = _frame(rows)
    outcome = resolve_trade_outcome(
        bars=df,
        entry_ts=pd.Timestamp("2024-01-02 09:14", tz="America/New_York"),
        entry_price=100.0, stop_price=99.0, direction="long",
    )
    assert outcome.expired is True
    assert outcome.won is False
```

- [ ] **Step 2: Verify FAIL.**

- [ ] **Step 3: Implement `engine/quarter_pair_backtest.py` — outcome resolver**

```python
"""Quarter-pair backtest. Same correctness invariants as Amas Models.

- Same-bar tie → SL.
- OUTCOME_MAX_BARS lookback. Expired excluded from WR/EV.
- Target fixed at 2R. R = |entry - stop|.
- Entry on close of entry quarter; stop in a closed prior quarter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from engine import constants as C


@dataclass(frozen=True)
class TradeDef:
    entry_q: int                # 1..12 (Q1 of C1 = 1, Q4 of C3 = 12)
    stop_q: int                 # 1..(entry_q - 1)
    direction: Literal["long", "short"]


@dataclass(frozen=True)
class TradeOutcome:
    won: bool
    r_realized: float           # +2.0 win, -1.0 loss, 0 if expired (and `expired=True`)
    expired: bool


def resolve_trade_outcome(
    bars: pd.DataFrame,
    entry_ts: pd.Timestamp,
    entry_price: float,
    stop_price: float,
    direction: Literal["long", "short"],
) -> TradeOutcome:
    """Walk bars after entry_ts; resolve when stop or target hit. Same-bar tie → SL."""
    r = abs(entry_price - stop_price)
    if direction == "long":
        target = entry_price + 2.0 * r
    else:
        target = entry_price - 2.0 * r

    after = bars[bars["ts"] > entry_ts].head(C.OUTCOME_MAX_BARS)
    for _, bar in after.iterrows():
        hi, lo = bar["high"], bar["low"]
        if direction == "long":
            stop_hit = lo <= stop_price
            target_hit = hi >= target
        else:
            stop_hit = hi >= stop_price
            target_hit = lo <= target

        if stop_hit and target_hit:
            return TradeOutcome(won=False, r_realized=-1.0, expired=False)  # tie → SL
        if stop_hit:
            return TradeOutcome(won=False, r_realized=-1.0, expired=False)
        if target_hit:
            return TradeOutcome(won=True, r_realized=2.0, expired=False)

    return TradeOutcome(won=False, r_realized=0.0, expired=True)
```

- [ ] **Step 4: PASS.** Run `python3 -m pytest tests/test_quarter_pair.py -v`.

- [ ] **Step 5: Commit.**

```bash
git add engine/quarter_pair_backtest.py tests/test_quarter_pair.py
git commit -m "feat(quarter-theory): add quarter-pair outcome resolver (same-bar tie → SL)"
```

---

### Task 4.2: Generate trade candidates from a triad episode

- [ ] **Step 1: Add failing test (append to `tests/test_quarter_pair.py`)**

```python
from engine.quarter_pair_backtest import enumerate_trade_candidates


def test_enumerate_candidates_returns_only_valid_pairs():
    # entry_q=2 → valid stop_q is 1 only (must be earlier and closed).
    # We expect: (2,1,long), (2,1,short).
    candidates = enumerate_trade_candidates(decision_quarter_idx=2)
    assert (2, 1, "long") in [(c.entry_q, c.stop_q, c.direction) for c in candidates]
    assert (2, 1, "short") in [(c.entry_q, c.stop_q, c.direction) for c in candidates]


def test_enumerate_candidates_no_same_quarter_stops():
    candidates = enumerate_trade_candidates(decision_quarter_idx=3)
    assert all(c.stop_q < c.entry_q for c in candidates)


def test_enumerate_candidates_for_q1_returns_empty():
    # No prior closed quarter exists for Q1.
    assert enumerate_trade_candidates(decision_quarter_idx=1) == []
```

- [ ] **Step 2: FAIL.**

- [ ] **Step 3: Append `enumerate_trade_candidates` to `engine/quarter_pair_backtest.py`**

```python
def enumerate_trade_candidates(decision_quarter_idx: int) -> list[TradeDef]:
    """Return all valid trade candidates entering on the close of decision_quarter_idx.

    decision_quarter_idx ∈ 1..12 is the global index (Q1 of C1=1, Q4 of C3=12).
    Stop quarters are all PRIOR quarters (must be closed at entry time).
    Both long and short directions are returned.
    """
    if decision_quarter_idx < 2:
        return []
    out: list[TradeDef] = []
    for stop_q in range(1, decision_quarter_idx):
        for direction in ("long", "short"):
            out.append(TradeDef(entry_q=decision_quarter_idx, stop_q=stop_q, direction=direction))
    return out
```

- [ ] **Step 4: PASS. Step 5: Commit.**

```bash
git add engine/quarter_pair_backtest.py tests/test_quarter_pair.py
git commit -m "feat(quarter-theory): enumerate quarter-pair trade candidates"
```

---

### Task 4.3: Top-1 EV pick per state

- [ ] **Step 1: Add failing test**

```python
from engine.quarter_pair_backtest import aggregate_qpair_outcomes, QPairRecord


def test_aggregate_qpair_picks_top_ev_per_state():
    """Synthetic: state KEY_A has two pairs.
    Pair P1: WR=80% over 50 trades, EV positive.
    Pair P2: WR=20% over 50 trades, EV negative.
    P1 must be the top pick.
    """
    rows = []
    for _ in range(40):
        rows.append({"state_key": "KEY_A", "pair_id": "P1", "won": True,  "r": 2.0, "expired": False})
    for _ in range(10):
        rows.append({"state_key": "KEY_A", "pair_id": "P1", "won": False, "r": -1.0, "expired": False})
    for _ in range(10):
        rows.append({"state_key": "KEY_A", "pair_id": "P2", "won": True,  "r": 2.0, "expired": False})
    for _ in range(40):
        rows.append({"state_key": "KEY_A", "pair_id": "P2", "won": False, "r": -1.0, "expired": False})
    import pandas as pd
    df = pd.DataFrame(rows)
    top = aggregate_qpair_outcomes(df, min_n=30)
    assert len(top) == 1
    rec = top[0]
    assert rec.state_key == "KEY_A"
    assert rec.pair_id == "P1"
    assert rec.n == 50
    assert rec.wr == 0.8


def test_aggregate_qpair_drops_pairs_below_min_n():
    rows = [{"state_key": "KEY_A", "pair_id": "P1", "won": True, "r": 2.0, "expired": False}] * 20
    import pandas as pd
    df = pd.DataFrame(rows)
    top = aggregate_qpair_outcomes(df, min_n=30)
    assert top == []  # n=20 < 30 threshold


def test_aggregate_qpair_excludes_expired_from_wr():
    rows = []
    for _ in range(40):
        rows.append({"state_key": "K", "pair_id": "P", "won": True,  "r": 2.0, "expired": False})
    for _ in range(10):
        rows.append({"state_key": "K", "pair_id": "P", "won": False, "r": 0.0, "expired": True})
    import pandas as pd
    df = pd.DataFrame(rows)
    top = aggregate_qpair_outcomes(df, min_n=30)
    # Expired excluded from WR, but counted in n? Per spec, expired excluded from WR/EV.
    assert top[0].n == 40    # only non-expired counted
    assert top[0].wr == 1.0
```

- [ ] **Step 2: FAIL.**

- [ ] **Step 3: Append to `engine/quarter_pair_backtest.py`**

```python
import pandas as pd

from engine.stats import wilson_ci


@dataclass(frozen=True)
class QPairRecord:
    state_key: str
    pair_id: str               # "Q{entry}-Q{stop}-{long|short}"
    wr: float
    ev: float                  # WR*2 - (1-WR)*1 — i.e. WR*2R - LR*1R
    n: int
    ci_lo: float
    ci_hi: float


def pair_id_of(td: TradeDef) -> str:
    return f"Q{td.entry_q}-Q{td.stop_q}-{td.direction}"


def aggregate_qpair_outcomes(df: pd.DataFrame, min_n: int = 30) -> list[QPairRecord]:
    """Aggregate trades into top-1 by EV per state_key, with `n >= min_n`.

    df columns required: state_key, pair_id, won (bool), r (float), expired (bool).
    Expired rows are excluded from WR/EV/n.
    """
    df = df[~df["expired"]].copy()
    if df.empty:
        return []
    grp = df.groupby(["state_key", "pair_id"]).agg(
        n=("won", "size"),
        wins=("won", "sum"),
    ).reset_index()
    grp = grp[grp["n"] >= min_n]
    if grp.empty:
        return []
    grp["wr"] = grp["wins"] / grp["n"]
    grp["ev"] = grp["wr"] * 2.0 - (1.0 - grp["wr"]) * 1.0

    out: list[QPairRecord] = []
    for state_key, sub in grp.groupby("state_key"):
        top_row = sub.sort_values("ev", ascending=False).iloc[0]
        lo, hi = wilson_ci(wins=int(top_row["wins"]), n=int(top_row["n"]))
        out.append(QPairRecord(
            state_key=state_key,
            pair_id=top_row["pair_id"],
            wr=float(top_row["wr"]),
            ev=float(top_row["ev"]),
            n=int(top_row["n"]),
            ci_lo=lo, ci_hi=hi,
        ))
    return out
```

- [ ] **Step 4: PASS. Step 5: Commit.**

```bash
git add engine/quarter_pair_backtest.py tests/test_quarter_pair.py
git commit -m "feat(quarter-theory): top-1 EV pair pick per state with Wilson CI"
```

---

### Task 4.4: End-to-end backtest runner

- [ ] **Step 1: Append failing test (smoke test against live data is in Phase 5)**

```python
def test_run_full_qpair_smoke_synthetic():
    """Wire test — runs the full pipeline on a tiny synthetic frame and asserts
    the output schema. Detailed correctness covered by unit tests above."""
    import pandas as pd
    rows = []
    for d in range(2, 5):
        for h in range(9, 12):
            for m in range(60):
                rows.append({
                    "ts": pd.Timestamp(f"2024-01-{d:02d} {h:02d}:{m:02d}", tz="America/New_York"),
                    "open": 100.0 + h - 9, "high": 102.0 + h - 9,
                    "low": 99.0 + h - 9, "close": 101.0 + h - 9,
                    "volume": 100,
                })
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")

    from engine.quarter_pair_backtest import run_full_qpair
    records = run_full_qpair(df, sym="NQ", min_n=1)
    # Don't assert specific outcomes — just that it runs and returns proper records.
    for r in records:
        assert r.n >= 1
        assert -1.0 <= r.ev <= 2.0
```

- [ ] **Step 2: FAIL.**

- [ ] **Step 3: Append `run_full_qpair` to `engine/quarter_pair_backtest.py`**

```python
def run_full_qpair(df_bars: pd.DataFrame, sym: str, min_n: int = 30) -> list[QPairRecord]:
    """End-to-end: bars → for each (state_key, decision quarter close, candidate pair)
    → resolve outcome → aggregate top-1 by EV per state_key.

    Decision points are the 12 quarter-close boundaries per triad. For each,
    we build the live state_key and enumerate candidate pairs that have a
    closed prior quarter.
    """
    from engine import time_primitives as tp
    from engine.aggregations import HourAgg, QuarterAgg, TriadAgg
    from engine.classifier import classify_hour, detect_sweeps_in_hour
    from engine.midline import detect_midline_reaction, resolve_midline_source
    from engine.box_05 import build_box_05, band_levels, detect_band_rejection
    from engine.state_vector import TriadStateInputs, build_triad_key
    from engine.walker import walk_triads

    rows = []
    for episode in walk_triads(df_bars):
        block_id = episode.block_id
        triad_bars = episode.bars

        # Reuse the sampler's logic minimally — only quarter-close events matter
        # for the backtest. Build per-quarter state keys at each quarter close.
        quarter_close_minutes = (14, 29, 44, 59)
        for hour_offset in range(3):
            hour_anchor = episode.anchor_ts + pd.Timedelta(hours=hour_offset)
            hour_bars = triad_bars[(triad_bars["ts"] >= hour_anchor) &
                                   (triad_bars["ts"] < hour_anchor + pd.Timedelta(hours=1))]
            for q_idx in range(1, 5):
                q_anchor = hour_anchor + pd.Timedelta(minutes=(q_idx - 1) * 15)
                q_close_ts = q_anchor + pd.Timedelta(minutes=14)
                q_close_bars = triad_bars[triad_bars["ts"] == q_close_ts]
                if q_close_bars.empty:
                    continue
                q_close_bar = q_close_bars.iloc[0]

                # Global decision-quarter index (1..12)
                decision_q_global = hour_offset * 4 + q_idx

                # Enumerate candidates
                candidates = enumerate_trade_candidates(decision_q_global)
                if not candidates:
                    continue

                # Build state_key (simplified — same fields as sampler)
                state_key = _build_state_key_at(
                    sym=sym, block_id=block_id, episode=episode,
                    decision_ts=q_close_ts, decision_q_global=decision_q_global,
                )

                entry_price = float(q_close_bar["close"])

                for td in candidates:
                    stop_hour = (td.stop_q - 1) // 4
                    stop_q_in_hour = ((td.stop_q - 1) % 4) + 1
                    stop_anchor = episode.anchor_ts + pd.Timedelta(hours=stop_hour, minutes=(stop_q_in_hour - 1) * 15)
                    stop_q_bars = triad_bars[(triad_bars["ts"] >= stop_anchor) &
                                             (triad_bars["ts"] < stop_anchor + pd.Timedelta(minutes=15))]
                    if stop_q_bars.empty:
                        continue
                    stop_high = float(stop_q_bars["high"].max())
                    stop_low = float(stop_q_bars["low"].min())
                    stop_price = stop_low if td.direction == "long" else stop_high

                    if (td.direction == "long" and stop_price >= entry_price) or \
                       (td.direction == "short" and stop_price <= entry_price):
                        continue  # invalid — stop on wrong side

                    outcome = resolve_trade_outcome(
                        bars=df_bars, entry_ts=q_close_ts,
                        entry_price=entry_price, stop_price=stop_price,
                        direction=td.direction,
                    )
                    rows.append({
                        "state_key": state_key,
                        "pair_id": pair_id_of(td),
                        "won": outcome.won,
                        "r": outcome.r_realized,
                        "expired": outcome.expired,
                    })

    if not rows:
        return []
    return aggregate_qpair_outcomes(pd.DataFrame(rows), min_n=min_n)


def _build_state_key_at(sym: str, block_id: str, episode, decision_ts, decision_q_global: int) -> str:
    """Lightweight state-key construction at a quarter close.

    For v1, we use a simplified state vector: (block, c1cls, decision_q_global).
    Full state vectors are used for the empirical table (Phase 3); the
    quarter-pair table can use a coarser key since trade ideas don't need
    sub-quarter resolution.
    """
    from engine.classifier import classify_hour
    c1cls = classify_hour(episode.triad.c1) if episode.triad.c1 else "doji"
    if c1cls == "pending":
        c1cls = "doji"
    # Coarse key: include only stable, broadly-applicable fields
    return f"v1|sym={sym}|tf=qpair|block={block_id}|c1cls={c1cls}|dq={decision_q_global}"
```

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Commit.**

```bash
git add engine/quarter_pair_backtest.py tests/test_quarter_pair.py
git commit -m "feat(quarter-theory): end-to-end quarter-pair backtest runner"
```

---

### Phase 4 smoke test

- [ ] **Run pytest:** `python3 -m pytest tests/ -q`. Expect ~95 passed.

- [ ] **Smoke run on real data:**

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from engine.db import load_bars
from engine.quarter_pair_backtest import run_full_qpair

df = load_bars('nq_1m', start='2024-01-02', end='2024-01-30')
records = run_full_qpair(df, sym='NQ', min_n=10)
print(f'{len(records)} state-key recommendations')
for r in records[:5]:
    print(f'  {r.state_key} → {r.pair_id} WR={r.wr:.1%} EV={r.ev:+.2f} n={r.n}')
"
```
Expected: a handful of records with sensible WR/EV/n values.

**End of Phase 4.** Move to [Phase 5 — Pine emit + build orchestrator](phase-5-pine-emit-build.md).
