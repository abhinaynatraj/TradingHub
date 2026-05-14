"""Model registry for the Amas Models engine.

Each Amas model is one Python module under engine/models/ that exports a
detector function. This file collects them into a MODELS dict that
model_stats.py iterates over.

Adding a new model:
1. Create engine/models/<key>.py with a `detect_setups(bars_df, **kwargs)` function
   returning list[Setup] (from engine.outcomes).
2. Add an entry to MODELS below.
3. Write tests/test_<key>.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Filter:
    """A togglable confluence filter exposed in the dashboard chip bar.

    The detector attaches `passes_<key>: bool` to every trade row. The dashboard
    reads this list to render chips, and the filter combo logic in stats uses
    AND semantics.
    """
    key: str       # short code, e.g., "F1", "SMT"
    label: str     # human-readable, e.g., "Shallow Sweep"
    default: bool  # whether the chip is active by default in the dashboard


@dataclass(frozen=True)
class ModelDefinition:
    """Registration entry for one Amas model."""
    key: str                          # snake_case identifier; used in JSON, CLI --models, filenames
    label: str                        # human-readable name shown in dashboard
    detect: Callable                  # detect_setups(bars_df: pd.DataFrame, **kwargs) -> list[Setup]
    filters: list[Filter] = field(default_factory=list)
    spec_anchor: str = ""             # H2 heading slug in docs/model_specs.md for spec rendering


# Model imports. Each module exports a `detect_setups(bars, **kwargs) -> list[Setup]`.
# Filter `key` field on each Filter MUST match the field-name suffix on the
# detector's Setup subclass (orchestrator looks up `passes_<filter.key>` per row).
from engine.models import h1_continuation as _h1_continuation_module  # noqa: E402
from engine.models import h1_continuation_m5 as _h1_continuation_m5_module  # noqa: E402


# The registry. Populated by Phase 3+.
MODELS: dict[str, ModelDefinition] = {
    "h1_continuation": ModelDefinition(
        key="h1_continuation",
        label="H1 Continuation (Model 2 entry)",
        detect=_h1_continuation_module.detect_setups,
        filters=[
            Filter(key="macro_010", label="Macro window :50–:10", default=True),
            Filter(key="top3_macros", label="Top-3 macro hours", default=False),
            Filter(key="avoid_lunch", label="Avoid 12:50–13:10 lunch", default=False),
            Filter(key="target_after_42", label="Draw formed after :42", default=False),
            Filter(key="no_opposite_struct_h1", label="No opposite structure", default=False),
            Filter(key="no_htf_rejection", label="No HTF rejection", default=False),
            Filter(key="aggressive_body", label="Aggressive H1 body", default=False),
            Filter(key="distribution_candle", label="Distribution candle", default=False),
            Filter(key="within_5m_structure", label="Within M5 structure", default=False),
            Filter(key="smt", label="NQ-ES divergence", default=False),
        ],
        spec_anchor="model-h1-continuation",
    ),
    "h1_continuation_m5": ModelDefinition(
        key="h1_continuation_m5",
        label="H1 Continuation · M5 entries (full-hour window)",
        detect=_h1_continuation_m5_module.detect_setups,
        filters=[
            Filter(key="macro_010", label="Macro window :50–:10", default=False),
            Filter(key="top3_macros", label="Top-3 macro hours", default=False),
            Filter(key="avoid_lunch", label="Avoid 12:50–13:10 lunch", default=False),
            Filter(key="target_after_42", label="Draw formed after :42", default=False),
            Filter(key="no_opposite_struct_h1", label="No opposite structure", default=False),
            Filter(key="no_htf_rejection", label="No HTF rejection", default=False),
            Filter(key="aggressive_body", label="Aggressive H1 body", default=False),
            Filter(key="distribution_candle", label="Distribution candle", default=False),
            Filter(key="smt", label="NQ-ES divergence", default=False),
        ],
        spec_anchor="model-h1-continuation",
    ),
}
