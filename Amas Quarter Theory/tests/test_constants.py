"""Tests for engine.constants — single source of truth for time/instrument constants."""
from engine import constants as C


def test_schema_version_is_v1():
    assert C.SCHEMA_VERSION == "v1"


def test_block_ids_excludes_15h_block():
    # NY-time 3h blocks. The 15:00-18:00 block is excluded by spec.
    assert C.BLOCK_IDS == ("00-03", "03-06", "06-09", "09-12", "12-15", "18-21", "21-00")
    assert "15-18" not in C.BLOCK_IDS


def test_block_for_hour_round_trip():
    assert C.block_for_hour(0) == "00-03"
    assert C.block_for_hour(2) == "00-03"
    assert C.block_for_hour(3) == "03-06"
    assert C.block_for_hour(11) == "09-12"
    assert C.block_for_hour(14) == "12-15"
    assert C.block_for_hour(18) == "18-21"
    assert C.block_for_hour(23) == "21-00"


def test_block_for_hour_excludes_15h():
    # Hours 15, 16, 17 are the excluded gap. block_for_hour returns None for them.
    assert C.block_for_hour(15) is None
    assert C.block_for_hour(16) is None
    assert C.block_for_hour(17) is None


def test_quarter_for_minute():
    assert C.quarter_for_minute(0) == 1
    assert C.quarter_for_minute(14) == 1
    assert C.quarter_for_minute(15) == 2
    assert C.quarter_for_minute(29) == 2
    assert C.quarter_for_minute(30) == 3
    assert C.quarter_for_minute(44) == 3
    assert C.quarter_for_minute(45) == 4
    assert C.quarter_for_minute(59) == 4


def test_outcome_max_bars_matches_amas_models():
    assert C.OUTCOME_MAX_BARS == 1440


def test_supported_symbols():
    assert set(C.SUPPORTED_SYMBOLS) == {"NQ", "ES"}
    assert C.TABLE_FOR_SYMBOL["NQ"] == "nq_1m"
    assert C.TABLE_FOR_SYMBOL["ES"] == "es_1m"


def test_band_offsets():
    # Bands: ±0.05% and ±0.10% from 05-box high/low
    assert C.BAND_OFFSETS == (0.0005, 0.0010)
