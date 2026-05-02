"""Shared pytest fixtures for Amas Quarter Theory engine tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Make `engine` importable from tests without a package install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
