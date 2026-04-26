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


# The registry. Populated by Phase 3+.
MODELS: dict[str, ModelDefinition] = {}
