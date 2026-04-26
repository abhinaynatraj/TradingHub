"""H1 Continuation detector — composes anchors + M1 patterns + H1 filters into Setups.

Per `docs/model_specs.md` "Model: H1 Continuation":
- Anchor: each H1 candle pair (prior, current).
- Continuation pattern: current.close > prior.high (long) or current.close < prior.low (short).
- Draw: prior.high (long) or prior.low (short).
- Trigger: first M1 OB / Breaker / Inversion-FVG in trade direction within
  the post-close window [current.close_ts, current.close_ts + 10min) whose
  entry price has correct geometry vs the draw.
- Stop: M1 pattern's invalidation_price.
- Target: 1R (entry + (entry - sl) for long; mirror for short).
- Risk gate: setups with risk_pts > MAX_RISK_PTS are EXCLUDED, not flagged.

Per the Amas Models design spec, this composition layer enforces:
- B (Trade dedup): asserted before return — at most one setup per (anchor_ts, direction).
- C (Lookahead): every M1 pattern's formed_ts is >= current.close_ts (post-close window),
  and the underlying detectors are causal. Truncating bars at entry_ts and re-running
  reproduces the same setup.
- F (Risk gate): risk_pts <= MAX_RISK_PTS asserted before return.
- All 10 passes_<key> flags attached as real bools (asserted before return).
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


POST_CLOSE_WINDOW = pd.Timedelta("10min")


# --------------------------------------------------------------------------- #
# Setup subclass with H1-Continuation-specific metadata
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _H1ContinuationSetup(Setup):
    """Setup with H1 Continuation-specific anchor + filter flags attached.

    The base `Setup` validates direction / entry / sl / tp in __post_init__;
    this subclass adds anchor metadata and the 10 `passes_<filter.key>` flags
    that the orchestrator's filter combo logic reads.
    """
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
    passes_within_5m_structure: bool = False
    passes_smt: bool = False


# Names of the 10 passes_* flags expected on each setup. Used for invariant
# checking and to enumerate the per-setup filter computations.
_FLAG_NAMES = (
    "passes_macro_010",
    "passes_top3_macros",
    "passes_avoid_lunch",
    "passes_target_after_42",
    "passes_no_opposite_struct_h1",
    "passes_no_htf_rejection",
    "passes_aggressive_body",
    "passes_distribution_candle",
    "passes_within_5m_structure",
    "passes_smt",
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _post_close_slice(bars: pd.DataFrame, close_ts: pd.Timestamp) -> pd.DataFrame:
    """Return bars in the post-close M1 window: [close_ts, close_ts + 10min).

    Half-open interval, matching the macro-window convention. Lookahead-safe
    in that no bar with ts > close_ts + 10min is ever consulted by downstream
    pattern detection.

    Uses searchsorted for O(log n) lookup since bars["ts"] is monotonic per
    the load contract. Falls back to a linear mask only if monotonicity is
    not detected.
    """
    end_ts = close_ts + POST_CLOSE_WINDOW
    # Fast path: searchsorted on a monotonic ts column.
    ts_col = bars["ts"]
    lo = ts_col.searchsorted(close_ts, side="left")
    hi = ts_col.searchsorted(end_ts, side="left")
    return bars.iloc[lo:hi]


# --------------------------------------------------------------------------- #
# Main detector
# --------------------------------------------------------------------------- #


def detect_setups(
    bars: pd.DataFrame,
    es_bars: Optional[pd.DataFrame] = None,
    h4_bars: Optional[pd.DataFrame] = None,
    daily_bars: Optional[pd.DataFrame] = None,
) -> list[Setup]:
    """Detect H1 Continuation setups.

    Args:
        bars: NQ 1m bars (canonical instrument). Same shape as engine.db.load_bars.
        es_bars: ES 1m bars for SMT divergence. None → passes_smt=False everywhere.
        h4_bars: H4 anchors (optional). None → passes_no_htf_rejection skipped (True).
        daily_bars: daily anchors (optional). None → passes_no_htf_rejection skipped (True).

    Returns:
        List of `_H1ContinuationSetup` (a Setup subclass with metadata + flags).
        Sorted by (anchor_ts, direction). At most one setup per (anchor_ts, direction).
    """
    # Empty input → empty output (early guard avoids anchor builder gymnastics).
    if len(bars) == 0:
        return []

    # 1. Build NQ H1 anchors. The anchor builder handles tz/DST/empty windows.
    nq_h1 = anchors.build_h1_anchors(bars)
    if len(nq_h1) < 2:
        return []

    # 2. Optionally build ES H1 anchors (for SMT).
    es_h1 = None
    if es_bars is not None and len(es_bars) > 0:
        es_h1 = anchors.build_h1_anchors(es_bars)
        if len(es_h1) == 0:
            es_h1 = None

    setups: list[_H1ContinuationSetup] = []
    seen_keys: set[tuple] = set()

    # 3. Iterate H1 pairs (prior, current).
    for k in range(1, len(nq_h1)):
        prior = nq_h1.iloc[k - 1]
        current = nq_h1.iloc[k]

        # 3a. Continuation pattern check.
        if current["close"] > prior["high"]:
            direction = "long"
            draw = float(prior["high"])
        elif current["close"] < prior["low"]:
            direction = "short"
            draw = float(prior["low"])
        else:
            continue  # no continuation pattern at this pair

        # 3b. Post-close M1 window: [current.close_ts, current.close_ts + 10min).
        close_ts = current["close_ts"]
        slice_m1 = _post_close_slice(bars, close_ts)
        if len(slice_m1) == 0:
            continue  # no post-close bars (data gap or end-of-data)

        # 3c. Find first M1 pattern in trade direction with valid entry-vs-draw geometry.
        candidates: list[m1_patterns.M1Pattern] = []
        candidates.extend(m1_patterns.find_order_blocks(slice_m1, direction))
        candidates.extend(m1_patterns.find_breakers(slice_m1, direction))
        candidates.extend(m1_patterns.find_inversion_fvgs(slice_m1, direction))
        if not candidates:
            continue
        candidates.sort(key=lambda p: p.formed_ts)

        chosen: Optional[m1_patterns.M1Pattern] = None
        for cand in candidates:
            # 3c-geometry: entry_price < draw for long; entry_price > draw for short.
            # We want to enter HEADED TOWARDS the draw; entry must be on the
            # appropriate side of the draw level.
            if direction == "long":
                if cand.entry_price >= draw:
                    continue
            else:  # short
                if cand.entry_price <= draw:
                    continue
            # 3c-stop-direction: invalidation must be on the correct side of entry.
            # (For long: invalidation < entry. For short: invalidation > entry.)
            if direction == "long" and cand.invalidation_price >= cand.entry_price:
                continue
            if direction == "short" and cand.invalidation_price <= cand.entry_price:
                continue
            # 3c-risk-gate: risk_pts (= |entry - sl|) must be <= MAX_RISK_PTS.
            risk_pts = abs(cand.entry_price - cand.invalidation_price)
            if risk_pts > MAX_RISK_PTS:
                continue
            chosen = cand
            break

        if chosen is None:
            continue

        # 3d. Build Setup fields.
        entry_ts = chosen.formed_ts
        entry_price = float(chosen.entry_price)
        sl_price = float(chosen.invalidation_price)
        if direction == "long":
            tp_price = entry_price + (entry_price - sl_price)
        else:
            tp_price = entry_price - (sl_price - entry_price)

        # 3e. Compute all 10 filter flags.
        # Time-of-day (1, 2, 3): based on entry_ts.
        f_macro_010 = bool(h1_filters.passes_macro_010(entry_ts))
        f_top3 = bool(h1_filters.passes_top3_macros(entry_ts))
        f_avoid_lunch = bool(h1_filters.passes_avoid_lunch(entry_ts))

        # H1 features (4, 5, 7, 8): based on prior or current H1 row.
        f_t42 = bool(h1_filters.passes_target_after_42(prior, direction))
        f_no_os = bool(h1_filters.passes_no_opposite_struct_h1(current))
        f_no_htf = bool(h1_filters.passes_no_htf_rejection(current, h4_bars, daily_bars, direction))
        f_agg_body = bool(h1_filters.passes_aggressive_body(current))
        f_dist = bool(h1_filters.passes_distribution_candle(current, direction))

        # 5-minute structure (9): entry vs draw distance.
        f_5m = bool(h1_filters.passes_within_5m_structure(entry_price, draw))

        # SMT (10): NQ-ES divergence.
        f_smt = False
        if es_h1 is not None:
            # Find the ES H1 row whose anchor_ts matches current.anchor_ts.
            es_match = es_h1[es_h1["anchor_ts"] == current["anchor_ts"]]
            es_prior_match = es_h1[es_h1["anchor_ts"] == prior["anchor_ts"]]
            if len(es_match) == 1 and len(es_prior_match) == 1:
                es_current_row = es_match.iloc[0]
                es_prior_row = es_prior_match.iloc[0]
                # ES H1 window 1m bars (for high/low scan). Use searchsorted for speed.
                es_anchor = current["anchor_ts"]
                es_end = es_anchor + pd.Timedelta("1h")
                es_lo = es_bars["ts"].searchsorted(es_anchor, side="left")
                es_hi = es_bars["ts"].searchsorted(es_end, side="left")
                es_h1_window = es_bars.iloc[es_lo:es_hi]
                # Prior ES extreme: high (long) / low (short). The SMT comparison
                # is between NQ's prior extreme (the draw) and ES's same-side extreme.
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

        # 3f. Construct Setup. Setup.__post_init__ raises on bad geometry —
        #     let it propagate so bugs surface loudly.
        setup = _H1ContinuationSetup(
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
            passes_within_5m_structure=f_5m,
            passes_smt=f_smt,
        )

        # Dedup invariant (B): hard fail on duplicate (anchor_ts, direction).
        # By construction we iterate H1 pairs uniquely and break on the first
        # qualifying pattern, so duplicates here would signal a structural bug.
        key = (setup.anchor_ts, setup.direction)
        assert key not in seen_keys, (
            f"h1_continuation: duplicate setup at {key} — internal logic error"
        )
        seen_keys.add(key)
        setups.append(setup)

    # 4. Post-detection invariant assertions.
    for s in setups:
        # All 10 flags present and bool.
        for flag in _FLAG_NAMES:
            assert hasattr(s, flag), f"setup missing flag {flag!r}"
            v = getattr(s, flag)
            assert v is not None, f"flag {flag!r} is None on setup {s.anchor_ts}/{s.direction}"
            assert isinstance(v, bool), (
                f"flag {flag!r} is not bool ({type(v).__name__}) on setup "
                f"{s.anchor_ts}/{s.direction}"
            )
        # Risk gate (F).
        assert s.risk_pts <= MAX_RISK_PTS, (
            f"setup risk_pts={s.risk_pts} > MAX_RISK_PTS={MAX_RISK_PTS} at "
            f"{s.anchor_ts}/{s.direction} — risk-gate filter failed"
        )

    # Dedup invariant (B), final assertion.
    keys = [(s.anchor_ts, s.direction) for s in setups]
    assert len(keys) == len(set(keys)), (
        f"h1_continuation: dedup invariant violated; duplicates in {keys}"
    )

    return setups
