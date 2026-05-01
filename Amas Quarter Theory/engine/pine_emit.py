"""Pine emitter: empirical DataFrame → Pine `map.put()` source.

Inputs are the parquet-shape DataFrames produced by `engine.empirical.aggregate_samples`:

    state_key | outcome | p | ci_lo | ci_hi | n

The state_key embeds `tf=triad` or `tf=hour`, so a single empirical table can
contain both timeframes; we route by that token.

Output is a single Pine source string, designed to be pasted between
PASTE-REGION-START / PASTE-REGION-END sentinels in `pine/quarter_theory.pine`.

Map shapes (must match the design spec):
    Triad: `array.from(p_lup, p_ldn, p_aup, p_adn, p_doji, n)`  (6 floats)
    Hour:  `array.from(p_lup, p_ldn, p_doji, n)`                 (4 floats)

Probabilities are quantized to 1 decimal place (e.g. 0.4) to fit the source
under the 900 KB budget. `n` is rounded to integer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from engine.state_vector import canonical_hash


PASTE_START = "// PASTE-REGION-START"
PASTE_END   = "// PASTE-REGION-END"

# Hard size limit on the emitted file. 900 KB = 10% headroom under Pine's 1 MB.
MAX_BYTES = 900 * 1024

# Default minimum sample count for a state to be emitted. States with fewer
# samples have wide Wilson CIs and are filtered out via Pine's strip-order
# fallback to a coarser key. Spec calls this the "trustable readout"
# threshold; matches design doc mitigation #3.
DEFAULT_MIN_N = 30

# Outcome → array index, per timeframe.
_TRIAD_OUTCOMES = ("line-up", "line-down", "apex-up", "apex-down", "doji")
_HOUR_OUTCOMES  = ("line-up", "line-down", "doji")

# Sweep / pair maps emit a single binary outcome → keep p(taken)/p(continues).
_SWEEP_OUTCOMES = ("taken",)        # value array = [p_taken, n]
_PAIR_OUTCOMES  = ("continues",)    # value array = [p_continues, n]

# Extension buckets in points — must match forward_sampler.EXT_BUCKETS_PTS.
# Used to compute mean/median/mode for the EXT_UP / EXT_DN maps.
_EXT_BUCKETS = [0, 5, 10, 15, 20, 30, 50, 75, 100, 150, 200, 300, 500]


def _quantize_p(p: float) -> float:
    """Quantize probability to 1 decimal place (0.0–1.0)."""
    return round(float(p), 1)


def _pivot_per_state(df: pd.DataFrame, outcomes: tuple[str, ...]) -> dict[str, tuple[list[float], int]]:
    """Pivot one timeframe's rows into {state_key: ([probs...], n)}.

    Probability columns follow `outcomes` order, missing outcomes default to 0.
    `n` is the same per state (sum of all outcomes' counts) — we read it from
    any row.
    """
    out: dict[str, tuple[list[float], int]] = {}
    if df.empty:
        return out
    for state_key, group in df.groupby("state_key", sort=False):
        probs_by_outcome = dict(zip(group["outcome"], group["p"]))
        probs = [_quantize_p(probs_by_outcome.get(o, 0.0)) for o in outcomes]
        n = int(group["n"].iloc[0])
        out[state_key] = (probs, n)
    return out


def _format_array(probs: list[float], n: int) -> str:
    """Render a Pine `array.from(...)` literal."""
    parts = [f"{p:.1f}" for p in probs] + [f"{n:d}.0"]
    return f"array.from({', '.join(parts)})"


def _emit_map_block(
    map_name: str,
    states: dict[str, tuple[list[float], int]],
) -> str:
    """Render one `var map<string, array<float>> NAME` block + put calls."""
    lines = [
        f"var map<string, array<float>> {map_name} = map.new<string, array<float>>()",
        f"if barstate.isfirst",
    ]
    for state_key, (probs, n) in states.items():
        h = canonical_hash(state_key)
        lines.append(f'    map.put({map_name}, "{h}", {_format_array(probs, n)})')
    return "\n".join(lines)


def _pivot_binary(df: pd.DataFrame, target_outcome: str) -> dict[str, tuple[list[float], int]]:
    """Pivot rows where outcome ∈ {target, complement} into {state: ([p_target], n)}.

    Used for sweep_h / sweep_l / pair maps where there are exactly two
    outcomes and we only need to emit p(target) (its complement is 1-p).
    """
    out: dict[str, tuple[list[float], int]] = {}
    if df.empty:
        return out
    for state_key, group in df.groupby("state_key", sort=False):
        probs_by_outcome = dict(zip(group["outcome"], group["p"]))
        p_target = _quantize_p(probs_by_outcome.get(target_outcome, 0.0))
        n = int(group["n"].iloc[0])
        out[state_key] = ([p_target], n)
    return out


def _pivot_extension(df: pd.DataFrame) -> dict[str, tuple[list[float], int]]:
    """Compute mean / median / mode (in points) per state from the bucket
    distribution.

    Each row in `df` is `(state_key, bucket_label, p, n)` where bucket_label
    is the string form of an int from `_EXT_BUCKETS`. We weight bucket-points
    by p (probability mass) to get mean; cumulative for median; argmax-p for
    mode.
    """
    out: dict[str, tuple[list[float], int]] = {}
    if df.empty:
        return out
    for state_key, group in df.groupby("state_key", sort=False):
        # Sort by bucket value (numeric) so cumulative ops work in order.
        rows = sorted(
            ((int(o), float(p)) for o, p in zip(group["outcome"], group["p"])),
            key=lambda r: r[0],
        )
        n = int(group["n"].iloc[0])

        mean = sum(b * p for b, p in rows)
        # Median: cumulative-p crosses 0.5
        cum = 0.0
        median = float(rows[-1][0])
        for b, p in rows:
            cum += p
            if cum >= 0.5:
                median = float(b)
                break
        # Mode: highest-p bucket (ties broken by lower bucket value)
        mode = float(max(rows, key=lambda r: r[1])[0])

        out[state_key] = ([round(mean, 1), round(median, 1), round(mode, 1)], n)
    return out


def _emit_binary_block(
    map_name: str, states: dict[str, tuple[list[float], int]],
) -> str:
    """Render `array.from(p_target, n)` per state — 2-element value array."""
    return _emit_map_block(map_name, states)


def _emit_extension_block(
    map_name: str, states: dict[str, tuple[list[float], int]],
) -> str:
    """Render `array.from(mean, median, mode, n)` per state — 4-element."""
    return _emit_map_block(map_name, states)


def emit_pine_tables(
    nq_empirical: pd.DataFrame,
    es_empirical: pd.DataFrame,
    *,
    schema_version: str = "v1",
    generated_at: str | None = None,
    min_n: int = DEFAULT_MIN_N,
) -> str:
    """Render the full PASTE-REGION block as a single Pine source string.

    `nq_empirical` and `es_empirical` are the per-symbol parquet-shape outputs
    of `aggregate_samples` (one table per symbol; each contains both triad
    and hour rows, distinguished by `tf=` in the state_key).

    `min_n` filters out low-sample states (default 30) — they're statistically
    noisy and the Pine consumer falls back to coarser keys via strip-order.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    blocks: list[str] = [
        PASTE_START,
        f"// (auto-generated by engine/build.py — do not edit by hand)",
        f"// (schema={schema_version} · generated={generated_at} · min_n={min_n})",
        "",
    ]

    for sym, df in (("NQ", nq_empirical), ("ES", es_empirical)):
        # Apply min-n filter once (n is repeated per (state, outcome) row, so
        # filtering on n alone is safe — every row of a low-n state goes).
        if not df.empty:
            df = df[df["n"] >= min_n]

        # Existing per-state outcome maps.
        triad_df = df[df["state_key"].str.contains("|tf=triad|", regex=False)]
        hour_df  = df[df["state_key"].str.contains("|tf=hour|",  regex=False)]
        triad_states = _pivot_per_state(triad_df, _TRIAD_OUTCOMES)
        hour_states  = _pivot_per_state(hour_df,  _HOUR_OUTCOMES)

        # Forward-looking maps (new: sweep_h / sweep_l / ext_up / ext_dn / pair).
        sweep_h_df = df[df["state_key"].str.contains("|tf=sweep_h|", regex=False)]
        sweep_l_df = df[df["state_key"].str.contains("|tf=sweep_l|", regex=False)]
        ext_up_df  = df[df["state_key"].str.contains("|tf=ext_up|",  regex=False)]
        ext_dn_df  = df[df["state_key"].str.contains("|tf=ext_dn|",  regex=False)]
        pair_df    = df[df["state_key"].str.contains("|tf=pair|",    regex=False)]

        sweep_h_states = _pivot_binary(sweep_h_df, "taken")
        sweep_l_states = _pivot_binary(sweep_l_df, "taken")
        ext_up_states  = _pivot_extension(ext_up_df)
        ext_dn_states  = _pivot_extension(ext_dn_df)
        pair_states    = _pivot_binary(pair_df, "continues")

        blocks.append(f"// ── {sym} triad table ({len(triad_states)} states, n≥{min_n}) ──")
        blocks.append(_emit_map_block(f"EMPIRICAL_{sym}_TRIAD", triad_states))
        blocks.append("")
        blocks.append(f"// ── {sym} hour table ({len(hour_states)} states, n≥{min_n}) ──")
        blocks.append(_emit_map_block(f"EMPIRICAL_{sym}_HOUR", hour_states))
        blocks.append("")
        blocks.append(f"// ── {sym} hour-high sweep p% ({len(sweep_h_states)} states, n≥{min_n}) ──")
        blocks.append(_emit_binary_block(f"EMPIRICAL_{sym}_SWEEP_H", sweep_h_states))
        blocks.append("")
        blocks.append(f"// ── {sym} hour-low sweep p% ({len(sweep_l_states)} states, n≥{min_n}) ──")
        blocks.append(_emit_binary_block(f"EMPIRICAL_{sym}_SWEEP_L", sweep_l_states))
        blocks.append("")
        blocks.append(f"// ── {sym} forward extension up ({len(ext_up_states)} states, n≥{min_n}) ──")
        blocks.append(_emit_extension_block(f"EMPIRICAL_{sym}_EXT_UP", ext_up_states))
        blocks.append("")
        blocks.append(f"// ── {sym} forward extension dn ({len(ext_dn_states)} states, n≥{min_n}) ──")
        blocks.append(_emit_extension_block(f"EMPIRICAL_{sym}_EXT_DN", ext_dn_states))
        blocks.append("")
        blocks.append(f"// ── {sym} triad-pair continuation ({len(pair_states)} states, n≥{min_n}) ──")
        blocks.append(_emit_binary_block(f"EMPIRICAL_{sym}_PAIR", pair_states))
        blocks.append("")

    blocks.append(PASTE_END)
    return "\n".join(blocks) + "\n"


def assert_size_budget(pine_source: str, *, max_bytes: int = MAX_BYTES) -> None:
    """Raise AssertionError if the emitted source exceeds the budget.

    Called by `engine/build.py` so a too-large table fails the build loudly
    rather than silently producing a Pine file TradingView would refuse.
    """
    size = len(pine_source.encode("utf-8"))
    if size > max_bytes:
        raise AssertionError(
            f"emitted Pine source is {size:,} bytes — exceeds budget of "
            f"{max_bytes:,} bytes. See engine/pine_emit.py mitigation list."
        )


def splice_into_pine_file(
    pine_path: str,
    paste_block: str,
) -> None:
    """Replace the PASTE-REGION-{START,END} block inside an existing .pine file.

    The target file must already contain both sentinel comments. Raises
    ValueError if either is missing — we don't auto-create them, since the
    placement matters and is hand-curated.
    """
    with open(pine_path, "r", encoding="utf-8") as f:
        text = f.read()

    start = text.find(PASTE_START)
    end   = text.find(PASTE_END)
    if start < 0 or end < 0 or end < start:
        raise ValueError(
            f"{pine_path}: missing or out-of-order PASTE-REGION sentinels "
            f"({PASTE_START!r}, {PASTE_END!r})"
        )

    end_lineend = text.find("\n", end)
    if end_lineend < 0:
        end_lineend = len(text)

    new_text = text[:start] + paste_block.rstrip("\n") + text[end_lineend:]
    with open(pine_path, "w", encoding="utf-8") as f:
        f.write(new_text)
