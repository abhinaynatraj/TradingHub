"""Per spec invariant H.4: same code + same DB + same args → byte-identical JSON output
(modulo meta.generated_at).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.model_stats import run, write


@pytest.mark.skipif(
    not (Path(__file__).resolve().parent.parent.parent / "Fractal Sweep" / "candle_science.duckdb").exists(),
    reason="Shared DB not present",
)
def test_engine_reproducibility(tmp_path):
    """Engine produces byte-identical JSON across runs (excluding generated_at)."""
    r1 = run(table="nq_1m")
    r2 = run(table="nq_1m")

    # Strip volatile fields
    r1["meta"].pop("generated_at", None)
    r2["meta"].pop("generated_at", None)

    s1 = json.dumps(r1, sort_keys=True, default=str)
    s2 = json.dumps(r2, sort_keys=True, default=str)
    assert s1 == s2, "Engine output is not reproducible — there's nondeterminism somewhere"
