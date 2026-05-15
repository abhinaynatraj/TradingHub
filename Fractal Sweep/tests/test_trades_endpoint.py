"""Tests for server.py /trades endpoint extensions."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


@pytest.fixture(scope="module")
def parquet_exists():
    if not (ROOT / "Fractal Sweep" / "model_stats.parquet").exists():
        pytest.skip("parquet not present")
    return True


def test_get_trades_period_2y_anchored_to_max_date(parquet_exists):
    """period=2y must anchor to MAX(date) in the parquet, not today()."""
    result = server._get_trades(
        engine="fractal_sweep",
        model="1H_5M_PREV_CISD",
        profile="simple_1r",
        period="2y",
        date_from=None, date_to=None,
        limit=None,
    )
    assert result is not None
    assert "trades" in result
    assert "count" in result
    assert result["count"] == len(result["trades"])
    assert result["count"] > 0
    import pandas as pd
    df = pd.read_parquet(ROOT / "Fractal Sweep" / "model_stats.parquet")
    df = df[(df["model_key"] == "1H_5M") & (df["sweep_mode"] == "PREV") & (df["cisd_mode"] == "CISD") & (df["profile_key"] == "simple_1r")]
    df = df[df["outcome"] != "EXPIRED"]
    max_date = pd.to_datetime(df["date"]).max()
    cutoff = max_date - pd.Timedelta(days=730)
    for t in result["trades"]:
        assert pd.to_datetime(t["date"]) >= cutoff


def test_get_trades_period_all_returns_all(parquet_exists):
    result_all = server._get_trades("fractal_sweep", "1H_5M_PREV_CISD", "simple_1r",
                                     period="all", date_from=None, date_to=None, limit=None)
    import pandas as pd
    df = pd.read_parquet(ROOT / "Fractal Sweep" / "model_stats.parquet")
    df = df[(df["model_key"] == "1H_5M") & (df["sweep_mode"] == "PREV") & (df["cisd_mode"] == "CISD") & (df["profile_key"] == "simple_1r")]
    df = df[df["outcome"] != "EXPIRED"]
    assert result_all["count"] == len(df)


def test_get_trades_invalid_period_returns_error(parquet_exists):
    result = server._get_trades("fractal_sweep", "1H_5M_PREV_CISD", "simple_1r",
                                 period="banana", date_from=None, date_to=None, limit=None)
    assert result is not None
    assert "error" in result


def test_get_trades_from_to_window(parquet_exists):
    result = server._get_trades("fractal_sweep", "1H_5M_PREV_CISD", "simple_1r",
                                 period=None, date_from="2022-01-01", date_to="2022-12-31",
                                 limit=None)
    import pandas as pd
    assert result["count"] > 0
    for t in result["trades"]:
        d = pd.to_datetime(t["date"])
        assert pd.Timestamp("2022-01-01") <= d <= pd.Timestamp("2022-12-31 23:59:59")


def test_get_trades_xor_violation_period_and_from(parquet_exists):
    result = server._get_trades("fractal_sweep", "1H_5M_PREV_CISD", "simple_1r",
                                 period="2y", date_from="2022-01-01", date_to=None,
                                 limit=None)
    assert "error" in result


def test_get_trades_xor_violation_neither(parquet_exists):
    result = server._get_trades("fractal_sweep", "1H_5M_PREV_CISD", "simple_1r",
                                 period=None, date_from=None, date_to=None,
                                 limit=None)
    assert "error" in result


def test_get_trades_native_parquet_schema(parquet_exists):
    """No column renames — stop_price (not sl_price), no dow_name."""
    result = server._get_trades("fractal_sweep", "1H_5M_PREV_CISD", "simple_1r",
                                 period="1m", date_from=None, date_to=None, limit=None)
    if result["count"] == 0:
        pytest.skip("no trades in last month")
    row = result["trades"][0]
    assert "stop_price" in row, "parquet-native: must expose stop_price"
    assert "sl_price" not in row, "schema bridge β: no JSON-style aliases"
    assert "dow" in row
    assert "dow_name" not in row, "schema bridge β: dow_name derived JS-side"
    assert "model_key" in row
    assert "profile_key" in row


def test_get_trades_excludes_expired(parquet_exists):
    """Match JSON recent_trades semantics: EXPIRED setups excluded."""
    result = server._get_trades("fractal_sweep", "1H_5M_PREV_CISD", "simple_1r",
                                 period="all", date_from=None, date_to=None, limit=None)
    for t in result["trades"]:
        assert t["outcome"] != "EXPIRED", f"EXPIRED row leaked: {t}"


def test_get_trades_malformed_model_returns_error(parquet_exists):
    """Malformed full key (e.g. fewer than 3 underscore-separated parts) must
    return a clean error dict, not raise ValueError."""
    result = server._get_trades("fractal_sweep", "1H5M", "simple_1r",
                                 period="all", date_from=None, date_to=None, limit=None)
    assert result is not None
    assert "error" in result, f"expected error dict, got: {result}"
