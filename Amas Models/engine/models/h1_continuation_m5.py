"""H1 Continuation detector — M5 entry-timeframe variant.

Same H1 anchor logic, draw, direction, validation filters, and risk gate as
`engine/models/h1_continuation.py`. Two differences:

1. Entry-pattern detection runs on **M5 bars** (resampled from M1) instead of M1.
2. The post-close window extends **the full next H1** (`[close_ts, close_ts + 1h)`)
   rather than the 10-minute macro slice, so the M5 detector has 12 bars to work
   with instead of 2.

Filters retained: macro_010, top3_macros, avoid_lunch, target_after_42,
no_opposite_struct_h1, no_htf_rejection, aggressive_body, distribution_candle, smt.

Filter dropped: `within_5m_structure`. That filter rejects M1 entries whose
distance to the draw is M5-structure-scale; here the entry IS M5-native, so the
filter is semantically void.

Outcome resolution still runs on the M1 bars passed to the orchestrator —
M5 entries are scored against M1 SL/TP touches, which is more accurate than
re-using M5 bars for resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from engine import anchors
from engine import h1_filters
from engine import m1_patterns
from engine.constants import MAX_RISK_PTS
from engine.outcomes import Setup


# Window covers the entire next H1 — gives the M5 detector 12 bars to find a pattern.
POST_CLOSE_WINDOW = pd.Timedelta("1h")

# OB tightening — same thresholds as the M1 model. Body-ratio is timeframe-
# invariant; break-displacement may want re-tuning on M5 since 1pt is a smaller
# fraction of typical M5 range than M1 range. Left at 1.0 for v1; flagged
# for parameter sweep in Phase 4.
OB_MIN_BODY_RATIO = 0.5
OB_MIN_BREAK_DISPLACEMENT_PTS = 1.0


@dataclass(frozen=True)
class _H1ContinuationM5Setup(Setup):
    anchor_ts: Optional[pd.Timestamp] = None
    draw_price: float = 0.0
    entry_pattern: str = ""
    passes_macro_010: bool = False
    passes_top3_macros: bool = False
    passes_avoid_lunch: bool = False
    passes_target_after_42: bool = False
    passes_no_opposite_struct_h1: bool = False
    passes_no_htf_rejection: bool = False
    passes_aggressive_body: bool = False
    passes_distribution_candle: bool = False
    passes_smt: bool = False


_FLAG_NAMES = (
    "passes_macro_010",
    "passes_top3_macros",
    "passes_avoid_lunch",
    "passes_target_after_42",
    "passes_no_opposite_struct_h1",
    "passes_no_htf_rejection",
    "passes_aggressive_body",
    "passes_distribution_candle",
    "passes_smt",
)


def _resample_to_m5(bars: pd.DataFrame) -> pd.DataFrame:
    """Resample tz-aware NY-time M1 bars into M5 bars.

    Returns the same column shape as the M1 input (`ts, open, high, low, close,
    volume`) so `m1_patterns.find_*` detectors accept it without modification.
    `ts` on each output row is the start of the M5 window (label="left",
    closed="left") — half-open interval `[ts, ts+5min)`, matching how the rest
    of the engine treats time windows.

    Empty input → empty output. M5 windows that contain no M1 bars are dropped
    (`dropna(subset=['open'])`) so we never emit NaN-OHLC rows.
    """
    if len(bars) == 0:
        return bars.iloc[0:0].copy()
    s = bars.set_index("ts")
    agg = s.resample("5min", label="left", closed="left").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open"])
    out = agg.reset_index()
    out["volume"] = out["volume"].astype("int64")
    return out


def _post_close_slice(bars: pd.DataFrame, close_ts: pd.Timestamp) -> pd.DataFrame:
    """Return bars in [close_ts, close_ts + POST_CLOSE_WINDOW). Half-open."""
    end_ts = close_ts + POST_CLOSE_WINDOW
    ts_col = bars["ts"]
    lo = ts_col.searchsorted(close_ts, side="left")
    hi = ts_col.searchsorted(end_ts, side="left")
    return bars.iloc[lo:hi]


def detect_setups(
    bars: pd.DataFrame,
    es_bars: Optional[pd.DataFrame] = None,
    h4_bars: Optional[pd.DataFrame] = None,
    daily_bars: Optional[pd.DataFrame] = None,
) -> list[Setup]:
    """Detect H1 Continuation setups using M5 entry triggers.

    Args:
        bars: NQ 1m bars. Resampled internally to M5 for pattern detection.
              The M1 bars are also used for H1-anchor build (via `anchors.build_h1_anchors`).
        es_bars: ES 1m bars for SMT divergence. None → passes_smt=False.
        h4_bars: H4 anchors (optional). None → passes_no_htf_rejection skipped.
        daily_bars: daily anchors (optional). None → passes_no_htf_rejection skipped.

    Returns:
        List of `_H1ContinuationM5Setup`. Sorted by (anchor_ts, direction).
    """
    if len(bars) == 0:
        return []

    nq_h1 = anchors.build_h1_anchors(bars)
    if len(nq_h1) < 2:
        return []

    nq_m5 = _resample_to_m5(bars)

    es_h1 = None
    if es_bars is not None and len(es_bars) > 0:
        es_h1 = anchors.build_h1_anchors(es_bars)
        if len(es_h1) == 0:
            es_h1 = None

    setups: list[_H1ContinuationM5Setup] = []
    seen_keys: set[tuple] = set()

    for k in range(1, len(nq_h1)):
        prior = nq_h1.iloc[k - 1]
        current = nq_h1.iloc[k]

        if current["close"] > prior["high"]:
            direction = "long"
            draw = float(prior["high"])
        elif current["close"] < prior["low"]:
            direction = "short"
            draw = float(prior["low"])
        else:
            continue

        close_ts = current["close_ts"]
        slice_m5 = _post_close_slice(nq_m5, close_ts)
        if len(slice_m5) < 2:
            continue  # need at least 2 M5 bars to form an OB

        candidates: list[m1_patterns.M1Pattern] = []
        candidates.extend(m1_patterns.find_order_blocks(
            slice_m5, direction,
            min_body_ratio=OB_MIN_BODY_RATIO,
            min_break_displacement_pts=OB_MIN_BREAK_DISPLACEMENT_PTS,
        ))
        candidates.extend(m1_patterns.find_breakers(
            slice_m5, direction,
            min_body_ratio=OB_MIN_BODY_RATIO,
            min_break_displacement_pts=OB_MIN_BREAK_DISPLACEMENT_PTS,
        ))
        if not candidates:
            continue
        candidates.sort(key=lambda p: p.formed_ts)

        chosen: Optional[m1_patterns.M1Pattern] = None
        for cand in candidates:
            if direction == "long":
                if cand.entry_price >= draw:
                    continue
                if cand.invalidation_price >= cand.entry_price:
                    continue
            else:
                if cand.entry_price <= draw:
                    continue
                if cand.invalidation_price <= cand.entry_price:
                    continue
            risk_pts = abs(cand.entry_price - cand.invalidation_price)
            if risk_pts > MAX_RISK_PTS:
                continue
            chosen = cand
            break

        if chosen is None:
            continue

        entry_ts = chosen.formed_ts
        entry_price = float(chosen.entry_price)
        sl_price = float(chosen.invalidation_price)
        if direction == "long":
            tp_price = entry_price + (entry_price - sl_price)
        else:
            tp_price = entry_price - (sl_price - entry_price)

        f_macro_010 = bool(h1_filters.passes_macro_010(entry_ts))
        f_top3 = bool(h1_filters.passes_top3_macros(entry_ts))
        f_avoid_lunch = bool(h1_filters.passes_avoid_lunch(entry_ts))
        f_t42 = bool(h1_filters.passes_target_after_42(prior, direction))
        f_no_os = bool(h1_filters.passes_no_opposite_struct_h1(current))
        f_no_htf = bool(h1_filters.passes_no_htf_rejection(current, h4_bars, daily_bars, direction))
        f_agg_body = bool(h1_filters.passes_aggressive_body(current))
        f_dist = bool(h1_filters.passes_distribution_candle(current, direction))

        f_smt = False
        if es_h1 is not None:
            es_match = es_h1[es_h1["anchor_ts"] == current["anchor_ts"]]
            es_prior_match = es_h1[es_h1["anchor_ts"] == prior["anchor_ts"]]
            if len(es_match) == 1 and len(es_prior_match) == 1:
                es_prior_row = es_prior_match.iloc[0]
                es_anchor = current["anchor_ts"]
                es_end = es_anchor + pd.Timedelta("1h")
                es_lo = es_bars["ts"].searchsorted(es_anchor, side="left")
                es_hi = es_bars["ts"].searchsorted(es_end, side="left")
                es_h1_window = es_bars.iloc[es_lo:es_hi]
                if direction == "long":
                    prior_es_extreme = float(es_prior_row["high"])
                else:
                    prior_es_extreme = float(es_prior_row["low"])
                f_smt = bool(h1_filters.passes_smt(
                    nq_h1=current,
                    prior_nq_extreme=draw,
                    es_h1_window=es_h1_window,
                    prior_es_extreme=prior_es_extreme,
                    direction=direction,
                ))

        setup = _H1ContinuationM5Setup(
            entry_ts=entry_ts,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            direction=direction,
            anchor_ts=current["anchor_ts"],
            draw_price=draw,
            entry_pattern=chosen.kind,
            passes_macro_010=f_macro_010,
            passes_top3_macros=f_top3,
            passes_avoid_lunch=f_avoid_lunch,
            passes_target_after_42=f_t42,
            passes_no_opposite_struct_h1=f_no_os,
            passes_no_htf_rejection=f_no_htf,
            passes_aggressive_body=f_agg_body,
            passes_distribution_candle=f_dist,
            passes_smt=f_smt,
        )

        key = (setup.anchor_ts, setup.direction)
        assert key not in seen_keys, (
            f"h1_continuation_m5: duplicate setup at {key} — internal logic error"
        )
        seen_keys.add(key)
        setups.append(setup)

    for s in setups:
        for flag in _FLAG_NAMES:
            assert hasattr(s, flag), f"setup missing flag {flag!r}"
            v = getattr(s, flag)
            assert v is not None, f"flag {flag!r} is None on setup {s.anchor_ts}/{s.direction}"
            assert isinstance(v, bool), (
                f"flag {flag!r} is not bool ({type(v).__name__}) on setup "
                f"{s.anchor_ts}/{s.direction}"
            )
        assert s.risk_pts <= MAX_RISK_PTS, (
            f"setup risk_pts={s.risk_pts} > MAX_RISK_PTS={MAX_RISK_PTS} at "
            f"{s.anchor_ts}/{s.direction} — risk-gate filter failed"
        )

    keys = [(s.anchor_ts, s.direction) for s in setups]
    assert len(keys) == len(set(keys)), (
        f"h1_continuation_m5: dedup invariant violated; duplicates in {keys}"
    )

    return setups
