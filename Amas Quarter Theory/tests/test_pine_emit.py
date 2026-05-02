"""Tests for the Pine emitter.

The emitter takes parquet-shape DataFrames and produces a Pine source string
with hashed state-keys and per-state probability arrays. We don't validate
Pine syntax (TradingView's parser is the source of truth there); we validate
the structural shape, hash determinism, quantization, and size-budget assert.
"""
from __future__ import annotations

import re

import pandas as pd
import pytest

from engine import pine_emit
from engine.state_vector import canonical_hash


# Build a minimal-but-valid v1 state_key for tests. Format must match
# build_triad_key / build_hour_key — we hand-craft keys here so the tests
# don't depend on those helpers' internals.
def _triad_key(suffix: str = "a") -> str:
    return (
        f"v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up|c2q=Q1|"
        f"c2vh=inside|c2vl=inside|c2sw_c1h=N|c2sw_c1l=N|c2_inside=N|"
        f"midhr=untouched|mid3h=untouched|box_react=none|tag={suffix}"
    )


def _hour_key(suffix: str = "a") -> str:
    return (
        f"v1|sym=NQ|tf=hour|block=09-12|hour_idx=1|q=Q1|"
        f"q1cls=in-stat-low|q2cls=inside|q3cls=inside|q4cls=inside|"
        f"sweep_set=none|midhr=untouched|box_react=none|tag={suffix}"
    )


def _sweep_h_key(suffix: str = "a") -> str:
    return _hour_key(suffix).replace("|tf=hour|", "|tf=sweep_h|")


def _sweep_l_key(suffix: str = "a") -> str:
    return _hour_key(suffix).replace("|tf=hour|", "|tf=sweep_l|")


def _ext_up_key(suffix: str = "a") -> str:
    return _hour_key(suffix).replace("|tf=hour|", "|tf=ext_up|")


def _ext_dn_key(suffix: str = "a") -> str:
    return _hour_key(suffix).replace("|tf=hour|", "|tf=ext_dn|")


def _pair_key(suffix: str = "a") -> str:
    return _triad_key(suffix).replace("|tf=triad|", "|tf=pair|") + "|prior_class=line-up"


def _row(state_key: str, outcome: str, p: float, n: int) -> dict:
    return {
        "state_key": state_key, "outcome": outcome,
        "p": p, "ci_lo": max(0.0, p - 0.1), "ci_hi": min(1.0, p + 0.1), "n": n,
    }


# ── Triad emission shape ─────────────────────────────────────────────────

def test_triad_emits_six_element_array():
    df = pd.DataFrame([
        _row(_triad_key("t1"), "line-up",   0.4, 100),
        _row(_triad_key("t1"), "line-down", 0.1, 100),
        _row(_triad_key("t1"), "apex-up",   0.2, 100),
        _row(_triad_key("t1"), "apex-down", 0.1, 100),
        _row(_triad_key("t1"), "doji",      0.2, 100),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())  # NQ has data, ES empty
    h = canonical_hash(_triad_key("t1"))
    expected = f'map.put(EMPIRICAL_NQ_TRIAD, "{h}", Probs.new(array.from(0.4, 0.1, 0.2, 0.1, 0.2, 100.0)))'
    assert expected in out


def test_hour_emits_four_element_array():
    df = pd.DataFrame([
        _row(_hour_key("h1"), "line-up",   0.5, 50),
        _row(_hour_key("h1"), "line-down", 0.2, 50),
        _row(_hour_key("h1"), "doji",      0.3, 50),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    h = canonical_hash(_hour_key("h1"))
    expected = f'map.put(EMPIRICAL_NQ_HOUR, "{h}", Probs.new(array.from(0.5, 0.2, 0.3, 50.0)))'
    assert expected in out


def test_missing_outcome_defaults_to_zero():
    # Triad row with only line-up + doji recorded; the other 3 outcomes
    # should default to 0.0 (no NaN, no exception).
    df = pd.DataFrame([
        _row(_triad_key("partial"), "line-up", 0.7, 30),
        _row(_triad_key("partial"), "doji",    0.3, 30),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    h = canonical_hash(_triad_key("partial"))
    expected = f'map.put(EMPIRICAL_NQ_TRIAD, "{h}", Probs.new(array.from(0.7, 0.0, 0.0, 0.0, 0.3, 30.0)))'
    assert expected in out


# ── Probabilities are quantized to 1 decimal place ──────────────────────

def test_probabilities_quantized_to_one_decimal():
    df = pd.DataFrame([_row(_hour_key("q"), "line-up", 0.4567, 30)])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    # 0.4567 → 0.5 (one-decimal rounding)
    assert "0.5" in out
    assert "0.4567" not in out


# ── Both NQ and ES sections present ─────────────────────────────────────

def test_both_symbols_emit_independent_blocks():
    nq = pd.DataFrame([_row(_hour_key("nq"), "line-up", 0.4, 50)])
    es = pd.DataFrame([_row(_hour_key("es"), "doji",    0.6, 40)])
    out = pine_emit.emit_pine_tables(nq, es)
    assert "EMPIRICAL_NQ_HOUR" in out
    assert "EMPIRICAL_NQ_TRIAD" in out
    assert "EMPIRICAL_ES_HOUR" in out
    assert "EMPIRICAL_ES_TRIAD" in out


def test_paste_region_sentinels_present():
    out = pine_emit.emit_pine_tables(pd.DataFrame(columns=["state_key","outcome","p","ci_lo","ci_hi","n"]),
                                     pd.DataFrame(columns=["state_key","outcome","p","ci_lo","ci_hi","n"]))
    assert pine_emit.PASTE_START in out
    assert pine_emit.PASTE_END   in out
    # START must precede END.
    assert out.index(pine_emit.PASTE_START) < out.index(pine_emit.PASTE_END)


# ── Routing: tf=triad goes to triad map, tf=hour goes to hour map ───────

def test_triad_and_hour_keys_route_to_correct_maps():
    df = pd.DataFrame([
        _row(_triad_key("only_triad"), "line-up", 0.3, 40),
        _row(_hour_key("only_hour"),   "doji",    0.5, 35),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    triad_h = canonical_hash(_triad_key("only_triad"))
    hour_h  = canonical_hash(_hour_key("only_hour"))
    # Triad hash should appear in the TRIAD map block, not the HOUR map block.
    triad_block_start = out.index("EMPIRICAL_NQ_TRIAD")
    hour_block_start  = out.index("EMPIRICAL_NQ_HOUR")
    triad_section = out[triad_block_start:hour_block_start]
    hour_section  = out[hour_block_start:]
    assert triad_h in triad_section
    assert triad_h not in hour_section
    assert hour_h in hour_section
    assert hour_h not in triad_section


# ── Hash collisions: two different state_keys → two different hashes ────

def test_distinct_state_keys_produce_distinct_hashes():
    df = pd.DataFrame([
        _row(_triad_key("aaa"), "line-up", 0.5, 100),
        _row(_triad_key("bbb"), "line-up", 0.5, 100),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    h_a = canonical_hash(_triad_key("aaa"))
    h_b = canonical_hash(_triad_key("bbb"))
    assert h_a != h_b
    assert h_a in out
    assert h_b in out


# ── New: sweep / extension / pair maps ──────────────────────────────────

def test_sweep_h_emits_two_element_array():
    df = pd.DataFrame([
        _row(_sweep_h_key("s1"), "taken", 0.6, 50),
        _row(_sweep_h_key("s1"), "held",  0.4, 50),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    h = canonical_hash(_sweep_h_key("s1"))
    expected = f'map.put(EMPIRICAL_NQ_SWEEP_H, "{h}", Probs.new(array.from(0.6, 50.0)))'
    assert expected in out


def test_sweep_l_emits_two_element_array():
    df = pd.DataFrame([
        _row(_sweep_l_key("s1"), "taken", 0.3, 40),
        _row(_sweep_l_key("s1"), "held",  0.7, 40),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    h = canonical_hash(_sweep_l_key("s1"))
    expected = f'map.put(EMPIRICAL_NQ_SWEEP_L, "{h}", Probs.new(array.from(0.3, 40.0)))'
    assert expected in out


def test_pair_emits_two_element_array_with_prior_class_in_key():
    df = pd.DataFrame([
        _row(_pair_key("p1"), "continues", 0.4, 60),
        _row(_pair_key("p1"), "reverses",  0.6, 60),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    h = canonical_hash(_pair_key("p1"))
    expected = f'map.put(EMPIRICAL_NQ_PAIR, "{h}", Probs.new(array.from(0.4, 60.0)))'
    assert expected in out


def test_ext_up_emits_mean_median_mode_n_array():
    # Bucket distribution: half the mass at 10, half at 50.
    # mean = 0.5*10 + 0.5*50 = 30
    # median: cum hits 0.5 at first bucket → 10
    # mode: tie-break by lower-bucket value → 10
    df = pd.DataFrame([
        _row(_ext_up_key("e1"), "10", 0.5, 100),
        _row(_ext_up_key("e1"), "50", 0.5, 100),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    h = canonical_hash(_ext_up_key("e1"))
    # mean=30.0, median=10.0, mode=10.0, n=100.0
    expected = f'map.put(EMPIRICAL_NQ_EXT_UP, "{h}", Probs.new(array.from(30.0, 10.0, 10.0, 100.0)))'
    assert expected in out


def test_ext_dn_routing_does_not_collide_with_ext_up():
    df = pd.DataFrame([
        _row(_ext_up_key("a"), "20", 1.0, 50),
        _row(_ext_dn_key("a"), "5",  1.0, 40),
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    up_h  = canonical_hash(_ext_up_key("a"))
    dn_h  = canonical_hash(_ext_dn_key("a"))
    # Each hash must be put into its own map only (matched by the put-call
    # signature, not by string-region splitting which is fragile).
    assert f'map.put(EMPIRICAL_NQ_EXT_UP, "{up_h}"' in out
    assert f'map.put(EMPIRICAL_NQ_EXT_DN, "{dn_h}"' in out
    assert f'map.put(EMPIRICAL_NQ_EXT_UP, "{dn_h}"' not in out
    assert f'map.put(EMPIRICAL_NQ_EXT_DN, "{up_h}"' not in out


def test_all_six_maps_per_symbol_present():
    # Empty inputs still emit all 6 map declarations per symbol (so the
    # indicator can always do a lookup without na-checking the map itself).
    empty = pd.DataFrame(columns=["state_key","outcome","p","ci_lo","ci_hi","n"])
    out = pine_emit.emit_pine_tables(empty, empty)
    for sym in ("NQ", "ES"):
        assert f"EMPIRICAL_{sym}_TRIAD"   in out
        assert f"EMPIRICAL_{sym}_HOUR"    in out
        assert f"EMPIRICAL_{sym}_SWEEP_H" in out
        assert f"EMPIRICAL_{sym}_SWEEP_L" in out
        assert f"EMPIRICAL_{sym}_EXT_UP"  in out
        assert f"EMPIRICAL_{sym}_EXT_DN"  in out
        assert f"EMPIRICAL_{sym}_PAIR"    in out


# ── min_n filter drops low-sample states ────────────────────────────────

def test_min_n_filters_low_sample_states():
    df = pd.DataFrame([
        _row(_hour_key("low"),  "line-up", 0.5, 5),    # below default
        _row(_hour_key("high"), "line-up", 0.5, 100),  # above default
    ])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    low_h  = canonical_hash(_hour_key("low"))
    high_h = canonical_hash(_hour_key("high"))
    assert low_h not in out
    assert high_h in out


def test_min_n_zero_emits_everything():
    df = pd.DataFrame([_row(_hour_key("tiny"), "line-up", 0.5, 1)])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy(), min_n=0)
    assert canonical_hash(_hour_key("tiny")) in out


# ── Size budget assertion ───────────────────────────────────────────────

def test_size_budget_passes_for_small_input():
    df = pd.DataFrame([_row(_hour_key("small"), "line-up", 0.4, 30)])
    out = pine_emit.emit_pine_tables(df, df.iloc[0:0].copy())
    pine_emit.assert_size_budget(out)  # should not raise


def test_size_budget_raises_when_exceeded():
    out = "x" * (pine_emit.MAX_BYTES + 1)
    with pytest.raises(AssertionError, match="exceeds budget"):
        pine_emit.assert_size_budget(out)


# ── splice_into_pine_file: replaces between sentinels ───────────────────

def test_splice_replaces_paste_region(tmp_path):
    pine_file = tmp_path / "ind.pine"
    pine_file.write_text(
        "//@version=6\n"
        "indicator(\"x\")\n"
        f"{pine_emit.PASTE_START}\n"
        "// stale content here\n"
        f"{pine_emit.PASTE_END}\n"
        "// trailing code\n"
    )

    new_block = (
        f"{pine_emit.PASTE_START}\n"
        f"// fresh content\n"
        f"{pine_emit.PASTE_END}\n"
    )
    pine_emit.splice_into_pine_file(str(pine_file), new_block)

    text = pine_file.read_text()
    assert "stale content" not in text
    assert "fresh content" in text
    assert "// trailing code" in text  # surrounding code preserved
    # Indicator header still intact
    assert text.startswith("//@version=6\n")


def test_splice_raises_if_sentinels_missing(tmp_path):
    pine_file = tmp_path / "no_sentinels.pine"
    pine_file.write_text("//@version=6\nindicator(\"x\")\n")
    with pytest.raises(ValueError, match="missing or out-of-order"):
        pine_emit.splice_into_pine_file(str(pine_file), "// whatever\n")
