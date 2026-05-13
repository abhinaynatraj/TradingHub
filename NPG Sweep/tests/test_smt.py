"""Tests for SMT (NQ-ES divergence): NQ swept its HTF level, ES did NOT sweep its corresponding level."""
import numpy as np
import pytest
import filters as f


class TestSmt:
    def test_nq_swept_es_did_not_is_smt(self):
        """SMT TRUE when NQ sweep extreme exceeds ES's corresponding HTF extreme."""
        # NQ Wick Lick: bearish, swept prev_high=24050, sweep_extreme=24070
        # ES window during NQ sweep: prev_high=5000, max(es_high)=4995 → did NOT sweep
        is_smt = f.is_smt(
            direction='SHORT',
            es_window_high=4995.0, es_window_low=4970.0,
            es_prev_high=5000.0, es_prev_low=4960.0,
        )
        assert is_smt is True

    def test_es_also_swept_not_smt(self):
        # Both swept → no divergence
        is_smt = f.is_smt(
            direction='SHORT',
            es_window_high=5005.0, es_window_low=4970.0,
            es_prev_high=5000.0, es_prev_low=4960.0,
        )
        assert is_smt is False

    def test_bullish_smt(self):
        is_smt = f.is_smt(
            direction='LONG',
            es_window_high=5005.0, es_window_low=4965.0,
            es_prev_high=5010.0, es_prev_low=4960.0,
        )
        assert is_smt is True
