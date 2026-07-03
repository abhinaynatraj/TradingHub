"""Tests for the model registry — ModelDefinition / Filter dataclasses."""
from __future__ import annotations

import pytest

from engine.models import ModelDefinition, Filter, MODELS


def test_models_registry_exists():
    assert isinstance(MODELS, dict)


def test_filter_dataclass_required_fields():
    f = Filter(key="F1", label="Shallow Sweep", default=False)
    assert f.key == "F1"
    assert f.label == "Shallow Sweep"
    assert f.default is False


def test_model_definition_required_fields():
    def dummy_detect(bars, **kwargs):
        return []
    md = ModelDefinition(
        key="dummy",
        label="Dummy Model",
        detect=dummy_detect,
        filters=[Filter(key="F1", label="Test Filter", default=False)],
        spec_anchor="model-dummy",
    )
    assert md.key == "dummy"
    assert callable(md.detect)
    assert len(md.filters) == 1
