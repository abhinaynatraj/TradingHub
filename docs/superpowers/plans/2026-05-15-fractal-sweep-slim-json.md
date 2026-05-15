# Fractal Sweep — Slim JSON Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip `recent_trades` out of `Fractal Sweep/model_stats.json` (270 MB → ~30-50 MB) by routing all trade-row reads through the parquet-backed `/trades` endpoint, with zero stat drift verified by snapshot tests and shadow-mode runtime asserts.

**Architecture:** Engine still writes both JSON and Parquet from the same DataFrame; JSON keeps the 29 precomputed aggregate keys per profile but drops `recent_trades` at both the top level and inside every `by_tf` sub-slice. Server's `_get_trades()` extends to accept `period=2y|1y|6m|3m|1m|all` (anchored to `MAX(date)` in parquet) or arbitrary `from=&to=` windows (XOR-validated). Frontend gains a `loadTrades` cache keyed by `(model, profile, period|range)`; six JS consumers adapt to parquet-native column names (β — no server-side renames).

**Tech Stack:** Python 3.14, pandas, DuckDB 1.4.4, Python stdlib `http.server`, vanilla ES modules, pytest.

**Reference spec:** [docs/superpowers/specs/2026-05-15-fractal-sweep-slim-json-design.md](../specs/2026-05-15-fractal-sweep-slim-json-design.md)

---

## Phase 1 — Baseline snapshot (BEFORE any code changes)

This phase locks in the current dashboard behavior so we can detect drift after migration. Run this entire phase on `main` against the existing JSON, before touching any code.

### Task 1: Snapshot generator script

**Files:**
- Create: `Fractal Sweep/tests/gen_no_drift_snapshot.py`
- Create: `Fractal Sweep/tests/fixtures/no_drift_snapshot.json` (output)

- [ ] **Step 1: Write the script**

```python
"""
Generate a baseline snapshot of dashboard-equivalent computations from
model_stats.json BEFORE the slim-JSON migration. Re-run after migration
and compare via test_no_drift.py.

Output: tests/fixtures/no_drift_snapshot.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "model_stats.json"
OUT_PATH = ROOT / "tests" / "fixtures" / "no_drift_snapshot.json"

# Fixed coverage: every model × simple_1r × every canonical period.
MODELS = ["1H_5M_PREV_CISD", "30M_3M_PREV_CISD", "15M_1M_PREV_CISD"]
PROFILE = "simple_1r"
PERIODS = ["all", "2y", "1y", "6m", "3m", "1m"]


def _percentile(xs, p):
    """Linear-interp percentile (matches numpy default)."""
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def _dir_summary(trades):
    """Compute dir_summary {long: {wr, ev, pf}, short: {...}} from trade rows."""
    out = {}
    for direction in ("long", "short"):
        sub = [t for t in trades if t.get("direction") == direction]
        n = len(sub)
        if n == 0:
            out[direction] = {"n": 0, "wr": None, "ev": None, "pf": None}
            continue
        wins = [t for t in sub if t.get("outcome") == "WIN"]
        sum_win = sum(t.get("r", 0) for t in wins)
        sum_loss = sum(abs(t.get("r", 0)) for t in sub if t.get("outcome") == "LOSS")
        wr = len(wins) / n
        ev = (sum_win - sum_loss) / n
        pf = sum_win / sum_loss if sum_loss > 0 else None
        out[direction] = {
            "n": n,
            "wr": round(wr, 4),
            "ev": round(ev, 4),
            "pf": round(pf, 4) if pf is not None else None,
        }
    return out


def _by_hour(trades):
    """Count trades by hour (0-23)."""
    out = {}
    for t in trades:
        h = t.get("hr")
        if h is None:
            continue
        out[str(h)] = out.get(str(h), 0) + 1
    return out


def _top_combos(trades, n=5):
    """Top 5 (hr, dow, direction) combos by EV, min 6 trades."""
    combos = {}
    for t in trades:
        hr, dow, dir_ = t.get("hr"), t.get("dow"), t.get("direction")
        if hr is None or dow is None:
            continue
        key = f"{hr}_{dow}_{dir_}"
        c = combos.setdefault(key, {"hr": hr, "dow": dow, "direction": dir_, "n": 0, "sum_r": 0.0, "wins": 0})
        c["n"] += 1
        c["sum_r"] += t.get("r", 0)
        if t.get("outcome") == "WIN":
            c["wins"] += 1
    rows = [c for c in combos.values() if c["n"] >= 6]
    for c in rows:
        c["ev"] = round(c["sum_r"] / c["n"], 4)
        c["wr"] = round(c["wins"] / c["n"], 4)
    rows.sort(key=lambda r: r["ev"], reverse=True)
    return rows[:n]


def _excursion_pcts(trades, field):
    """Return {p50, p75, p90} of a percent field across all trades."""
    vals = [t.get(field) for t in trades if t.get(field) is not None]
    return {
        "p50": _percentile(vals, 0.50),
        "p75": _percentile(vals, 0.75),
        "p90": _percentile(vals, 0.90),
    }


def _verdict_score(profile_data, trades):
    """Mirror what verdict.js produces — a single composite score.

    The exact formula lives in verdict.js. For drift detection we capture
    the inputs that feed the score so post-migration we can verify identity.
    """
    if not trades:
        return None
    wins = [t for t in trades if t.get("outcome") == "WIN"]
    n = len(trades)
    wr = len(wins) / n
    sum_win = sum(t.get("r", 0) for t in wins)
    sum_loss = sum(abs(t.get("r", 0)) for t in trades if t.get("outcome") == "LOSS")
    ev = (sum_win - sum_loss) / n
    pf = sum_win / sum_loss if sum_loss > 0 else None
    return {
        "n": n,
        "wr": round(wr, 4),
        "ev": round(ev, 4),
        "pf": round(pf, 4) if pf is not None else None,
    }


def _trades_for_period(profile_data, period):
    """Pull the trade rows the JSON currently exposes for a given period."""
    if period == "all":
        return profile_data.get("recent_trades", [])
    by_tf = profile_data.get("by_tf", {})
    slice_ = by_tf.get(period)
    if not slice_:
        return []
    return slice_.get("recent_trades", [])


def build_snapshot():
    if not JSON_PATH.exists():
        raise SystemExit(f"missing: {JSON_PATH}. Run engine/model_stats.py first.")
    with open(JSON_PATH) as f:
        data = json.load(f)

    snap = {}
    for model in MODELS:
        model_data = data.get(model)
        if not model_data:
            continue
        profile_data = model_data.get("profiles", {}).get(PROFILE)
        if not profile_data:
            continue
        snap[model] = {}
        for period in PERIODS:
            trades = _trades_for_period(profile_data, period)
            snap[model][period] = {
                "n_trades": len(trades),
                "verdict_inputs": _verdict_score(profile_data, trades),
                "dir_summary": _dir_summary(trades),
                "by_hour_counts": _by_hour(trades),
                "top_combos": _top_combos(trades, 5),
                "mae_pct": _excursion_pcts(trades, "mae_pct"),
                "mfe_pct": _excursion_pcts(trades, "mfe_pct"),
            }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(snap, f, indent=2, sort_keys=True)
    print(f"snapshot written: {OUT_PATH}")
    print(f"models covered: {list(snap.keys())}")


if __name__ == "__main__":
    build_snapshot()
```

- [ ] **Step 2: Run it**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 tests/gen_no_drift_snapshot.py
```

Expected: prints `snapshot written: ...` and `models covered: ['1H_5M_PREV_CISD', '30M_3M_PREV_CISD', '15M_1M_PREV_CISD']`. Creates `tests/fixtures/no_drift_snapshot.json`.

- [ ] **Step 3: Verify the snapshot is non-trivial**

```bash
python3 -c "
import json
d = json.load(open('tests/fixtures/no_drift_snapshot.json'))
for model, periods in d.items():
    for p, vals in periods.items():
        assert vals['n_trades'] > 0 or p == '1m', f'empty: {model}/{p}'
print('snapshot OK')
"
```

Expected: `snapshot OK`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/tests/gen_no_drift_snapshot.py" "Fractal Sweep/tests/fixtures/no_drift_snapshot.json"
git commit -m "test(fractal-sweep): baseline snapshot for slim-JSON drift detection"
```

---

### Task 2: Drift test (loads against parquet-sourced trades)

**Files:**
- Create: `Fractal Sweep/tests/test_no_drift.py`

This test will be GREEN against current main (since it reproduces the same numbers from the same source). After Phase 4 migration, it must still be GREEN — sourcing from the parquet path. It is the regression gate.

- [ ] **Step 1: Write the test**

```python
"""
Regression test: dashboard-equivalent computations must match the baseline
snapshot generated by tests/gen_no_drift_snapshot.py.

Phase 1: this test reads from model_stats.json — passes trivially.
Phase 4: this test reads from model_stats.parquet via the same logic that
the frontend will use, and must still pass byte-for-byte (within tolerance).

The "source of trades" function is parameterized so the same test body
verifies both paths.
"""
import json
import math
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SNAP_PATH = HERE / "fixtures" / "no_drift_snapshot.json"

MODELS = ["1H_5M_PREV_CISD", "30M_3M_PREV_CISD", "15M_1M_PREV_CISD"]
PROFILE = "simple_1r"
PERIODS = ["all", "2y", "1y", "6m", "3m", "1m"]


def _load_snapshot():
    if not SNAP_PATH.exists():
        pytest.skip(f"snapshot missing: {SNAP_PATH}. Run gen_no_drift_snapshot.py first.")
    return json.load(open(SNAP_PATH))


def _percentile(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def _trades_from_json(model, period):
    with open(ROOT / "model_stats.json") as f:
        data = json.load(f)
    prof = data[model]["profiles"][PROFILE]
    if period == "all":
        return prof.get("recent_trades", [])
    slice_ = prof.get("by_tf", {}).get(period)
    return (slice_ or {}).get("recent_trades", [])


def _trades_from_parquet(model, period):
    """Parquet-sourced trades using the same period anchor (MAX(date)) the server uses."""
    import pandas as pd
    pq = ROOT / "model_stats.parquet"
    if not pq.exists():
        pytest.skip(f"parquet missing: {pq}")
    df = pd.read_parquet(pq)
    df = df[(df["model_key"] == model) & (df["profile_key"] == PROFILE)]
    if period != "all":
        years = {"2y": 2, "1y": 1, "6m": 0.5, "3m": 0.25, "1m": 1/12}[period]
        max_date = pd.to_datetime(df["date"]).max()
        cutoff = max_date - pd.Timedelta(days=int(round(years * 365)))
        df = df[pd.to_datetime(df["date"]) >= cutoff]
    return df.where(df.notna(), None).to_dict("records")


def _dir_summary(trades):
    out = {}
    for direction in ("long", "short"):
        sub = [t for t in trades if t.get("direction") == direction]
        n = len(sub)
        if n == 0:
            out[direction] = {"n": 0, "wr": None, "ev": None, "pf": None}
            continue
        wins = [t for t in sub if t.get("outcome") == "WIN"]
        sum_win = sum(t.get("r", 0) for t in wins)
        sum_loss = sum(abs(t.get("r", 0)) for t in sub if t.get("outcome") == "LOSS")
        wr = len(wins) / n
        ev = (sum_win - sum_loss) / n
        pf = sum_win / sum_loss if sum_loss > 0 else None
        out[direction] = {
            "n": n,
            "wr": round(wr, 4),
            "ev": round(ev, 4),
            "pf": round(pf, 4) if pf is not None else None,
        }
    return out


def _close(a, b, rel=1e-3, abs_=1e-4):
    """0.1% relative tolerance for floats; exact for None/int."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if a == 0 and b == 0:
        return True
    return abs(a - b) <= abs_ + rel * max(abs(a), abs(b))


@pytest.fixture(scope="module")
def snapshot():
    return _load_snapshot()


@pytest.fixture(
    params=["json", "parquet"],
    ids=["src=json", "src=parquet"],
)
def trade_source(request):
    """Phase 1: only 'json' runs (parquet test skips if columns mismatch).
    Phase 4: both must pass."""
    return request.param


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("period", PERIODS)
def test_dir_summary_matches_snapshot(snapshot, trade_source, model, period):
    if model not in snapshot:
        pytest.skip(f"model not in snapshot: {model}")
    expected = snapshot[model][period]["dir_summary"]
    trades = _trades_from_json(model, period) if trade_source == "json" else _trades_from_parquet(model, period)
    actual = _dir_summary(trades)
    for direction in ("long", "short"):
        for field in ("n", "wr", "ev", "pf"):
            e = expected[direction][field]
            a = actual[direction][field]
            assert _close(e, a), f"{model}/{period}/{direction}.{field}: expected {e}, got {a}"


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("period", PERIODS)
def test_n_trades_matches(snapshot, trade_source, model, period):
    if model not in snapshot:
        pytest.skip(f"model not in snapshot: {model}")
    expected = snapshot[model][period]["n_trades"]
    trades = _trades_from_json(model, period) if trade_source == "json" else _trades_from_parquet(model, period)
    assert len(trades) == expected, f"{model}/{period}: expected {expected} trades, got {len(trades)}"


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("period", PERIODS)
def test_excursion_percentiles_match(snapshot, trade_source, model, period):
    if model not in snapshot:
        pytest.skip(f"model not in snapshot: {model}")
    trades = _trades_from_json(model, period) if trade_source == "json" else _trades_from_parquet(model, period)
    for field in ("mae_pct", "mfe_pct"):
        expected = snapshot[model][period][field]
        for q, p in (("p50", 0.50), ("p75", 0.75), ("p90", 0.90)):
            vals = [t.get(field) for t in trades if t.get(field) is not None]
            actual = _percentile(vals, p)
            assert _close(expected[q], actual), f"{model}/{period}/{field}.{q}: expected {expected[q]}, got {actual}"
```

- [ ] **Step 2: Run the test against JSON source**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 -m pytest tests/test_no_drift.py -v -k "src=json" 2>&1 | tail -30
```

Expected: All `src=json` tests PASS. Parquet tests may fail or skip in Phase 1 — that's fine, they're the Phase 4 gate.

- [ ] **Step 3: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/tests/test_no_drift.py"
git commit -m "test(fractal-sweep): drift test (gates slim-JSON migration)"
```

---

## Phase 2 — Extend `/trades` server endpoint (additive only, no behavior change for old callers)

### Task 3: Add `period` parameter to `_get_trades`

**Files:**
- Modify: `server.py:70-108` (`_get_trades` function)
- Modify: `server.py:230-240` (`/trades` route in `do_GET`)
- Create: `Fractal Sweep/tests/test_trades_endpoint.py`

- [ ] **Step 1: Write the failing test**

```python
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
    # All trades must fall within 2 years of the parquet's MAX(date)
    import pandas as pd
    df = pd.read_parquet(ROOT / "Fractal Sweep" / "model_stats.parquet")
    df = df[(df["model_key"] == "1H_5M_PREV_CISD") & (df["profile_key"] == "simple_1r")]
    max_date = pd.to_datetime(df["date"]).max()
    cutoff = max_date - pd.Timedelta(days=int(round(2 * 365)))
    for t in result["trades"]:
        assert pd.to_datetime(t["date"]) >= cutoff


def test_get_trades_period_all_returns_all(parquet_exists):
    result_all = server._get_trades("fractal_sweep", "1H_5M_PREV_CISD", "simple_1r",
                                     period="all", date_from=None, date_to=None, limit=None)
    import pandas as pd
    df = pd.read_parquet(ROOT / "Fractal Sweep" / "model_stats.parquet")
    df = df[(df["model_key"] == "1H_5M_PREV_CISD") & (df["profile_key"] == "simple_1r")]
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
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m pytest "Fractal Sweep/tests/test_trades_endpoint.py" -v 2>&1 | tail -25
```

Expected: tests FAIL because `_get_trades` does not accept `period`, `date_from`, `date_to` parameters yet.

- [ ] **Step 3: Update `_get_trades` to accept the new params**

Open `server.py` and replace the entire `_get_trades` function (currently at lines 73-108) with:

```python
def _get_trades(
    engine: str,
    model: str | None,
    profile: str | None,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = None,
) -> dict | None:
    """Slice the engine's parquet trade table.

    Args:
      period: one of '2y'|'1y'|'6m'|'3m'|'1m'|'all'. Anchored to MAX(date)
              in the parquet (NOT today() — keeps results reproducible).
      date_from, date_to: arbitrary YYYY-MM-DD window. XOR with `period`.
      limit: optional row cap.

    Returns: {"trades": [...], "count": N} on success;
             {"error": "..."} on parameter validation failure;
             None if parquet not present for the engine.
    """
    import pandas as pd

    pq_paths = {
        "fractal_sweep": ROOT / "Fractal Sweep" / "model_stats.parquet",
    }
    path = pq_paths.get(engine)
    if not path or not path.exists():
        return None

    # XOR: exactly one of (period) or (date_from AND date_to)
    has_period = period is not None
    has_range = date_from is not None or date_to is not None
    if has_period and has_range:
        return {"error": "specify either period OR from/to, not both"}
    if not has_period and not has_range:
        return {"error": "specify period or from/to"}
    if has_range and not (date_from and date_to):
        return {"error": "from and to are both required"}

    VALID_PERIODS = {"all", "2y", "1y", "6m", "3m", "1m"}
    if has_period and period not in VALID_PERIODS:
        return {"error": f"invalid period '{period}'. Valid: {sorted(VALID_PERIODS)}"}

    if engine not in _parquet_cache:
        _parquet_cache[engine] = pd.read_parquet(path)

    df = _parquet_cache[engine]
    if model:
        df = df[df["model_key"] == model]
    if profile:
        df = df[df["profile_key"] == profile]

    if df.empty:
        return {"trades": [], "count": 0}

    dates = pd.to_datetime(df["date"])

    if has_period and period != "all":
        years_lookup = {"2y": 2, "1y": 1, "6m": 0.5, "3m": 0.25, "1m": 1/12}
        years = years_lookup[period]
        cutoff = dates.max() - pd.Timedelta(days=int(round(years * 365)))
        df = df[dates >= cutoff]

    if has_range:
        df = df[(dates >= pd.Timestamp(date_from)) & (dates <= pd.Timestamp(date_to + " 23:59:59"))]

    if limit is not None:
        df = df.sort_values("date", ascending=False).head(limit)

    if df.empty:
        return {"trades": [], "count": 0}

    records = df.where(pd.notna(df), None).to_dict("records")
    for r in records:
        r["date"] = str(r["date"])[:19]
        for k in ("dow", "hr", "mn", "yr"):
            if r.get(k) is not None:
                r[k] = int(r[k])

    return {"trades": records, "count": len(records)}
```

- [ ] **Step 4: Update the `/trades` route in `do_GET`**

Replace lines 230-240 in `server.py` with:

```python
        if parsed.path == "/trades":
            engine    = (qs.get("engine")    or [""])[0]
            model     = (qs.get("model")     or [None])[0]
            profile   = (qs.get("profile")   or [None])[0]
            period    = (qs.get("period")    or [None])[0]
            date_from = (qs.get("from")      or [None])[0]
            date_to   = (qs.get("to")        or [None])[0]
            limit_str = (qs.get("limit")     or [None])[0]
            limit     = int(limit_str) if limit_str else None
            result = _get_trades(engine, model, profile,
                                  period=period, date_from=date_from, date_to=date_to,
                                  limit=limit)
            if result is None:
                self._json(404, {"error": f"no parquet for engine '{engine}'"})
                return
            if "error" in result:
                self._json(400, result)
                return
            self._json(200, result)
            return
```

- [ ] **Step 5: Run the tests, must pass**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m pytest "Fractal Sweep/tests/test_trades_endpoint.py" -v 2>&1 | tail -20
```

Expected: All tests PASS.

- [ ] **Step 6: Smoke test the HTTP endpoint end-to-end**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
curl -s "http://localhost:8001/trades?engine=fractal_sweep&model=1H_5M_PREV_CISD&profile=simple_1r&period=1m" | python3 -c "import json,sys; d=json.load(sys.stdin); print('count:', d['count']); print('first keys:', list(d['trades'][0].keys())[:8] if d['trades'] else 'empty')"
curl -s -w "\nHTTP %{http_code}\n" "http://localhost:8001/trades?engine=fractal_sweep&model=1H_5M_PREV_CISD&profile=simple_1r&period=2y&from=2022-01-01&to=2022-12-31" -o /tmp/xor.json
cat /tmp/xor.json
kill $SERVER_PID 2>/dev/null
```

Expected: First curl prints non-zero `count` and parquet-native keys (`date, yr, dow, direction, ...`). Second curl returns `HTTP 400` with the XOR error.

- [ ] **Step 7: Verify Phase 4 drift test now runs against parquet too**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 -m pytest tests/test_no_drift.py -v 2>&1 | tail -20
```

Expected: `src=json` tests pass. `src=parquet` tests should now pass too — same trades, same math. If parquet tests fail, the period anchoring math is off and must be fixed before proceeding.

- [ ] **Step 8: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add server.py "Fractal Sweep/tests/test_trades_endpoint.py"
git commit -m "feat(server): /trades supports period= and from/to= window params"
```

---

## Phase 3 — Frontend: `loadTrades` cache + parquet-native consumers + shadow mode

### Task 4: Add `loadTrades` to `js/data.js`

**Files:**
- Modify: `Fractal Sweep/js/data.js` (add new function near existing `loadProfile`)

- [ ] **Step 1: Add the function**

After the `loadProfile` function (currently ending at line 131), insert:

```js
// ── Trade row fetcher ────────────────────────────────────────────────────────
// Trades live in model_stats.parquet, served by /trades. Cached per
// (fullKey, profile, periodOrRangeKey). Parquet column names are canonical —
// consumers must read stop_price (not sl_price) and derive dow_name from dow.
async function loadTrades(fullKey, profileKey, periodOrRange) {
  const cacheKey = typeof periodOrRange === 'string'
    ? periodOrRange
    : `${periodOrRange.from}:${periodOrRange.to}`;

  if (!DATA[fullKey]) DATA[fullKey] = { profiles: {} };
  if (!DATA[fullKey].trades) DATA[fullKey].trades = {};
  const cache = DATA[fullKey].trades;
  const profCache = cache[profileKey] || (cache[profileKey] = {});
  if (profCache[cacheKey]) return profCache[cacheKey];

  const qs = new URLSearchParams({
    engine: 'fractal_sweep',
    model: fullKey,
    profile: profileKey,
  });
  if (typeof periodOrRange === 'string') {
    qs.set('period', periodOrRange);
  } else {
    qs.set('from', periodOrRange.from);
    qs.set('to', periodOrRange.to);
  }
  const r = await fetch('/trades?' + qs.toString());
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const data = await r.json();
  profCache[cacheKey] = data.trades || [];
  return profCache[cacheKey];
}

function invalidateTradesCache(fullKey) {
  if (DATA[fullKey] && DATA[fullKey].trades) DATA[fullKey].trades = {};
}

export { loadTrades, invalidateTradesCache };
```

Also add `loadTrades` and `invalidateTradesCache` to the named export block at the bottom if the file uses one. (Check the current export style at end of file before adding.)

- [ ] **Step 2: Smoke test in browser console**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open http://localhost:8001/Fractal%20Sweep/model_dashboard.html and run in DevTools console:"
echo "  import('./js/data.js').then(m => m.loadTrades('1H_5M_PREV_CISD','simple_1r','1m')).then(t => console.log('rows:', t.length, 'first:', t[0]))"
echo "Press Enter when verified..."
read
kill $SERVER_PID
```

Expected: Console logs row count > 0 and parquet-native keys on `first` (must include `stop_price`, must NOT include `sl_price`).

- [ ] **Step 3: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/js/data.js"
git commit -m "feat(fractal-sweep): loadTrades fetches trade rows from /trades parquet endpoint"
```

---

### Task 5: Migrate `getFilteredD` to parquet-native columns + cached trades

**Files:**
- Modify: `Fractal Sweep/js/data.js:188-383` (`getFilteredD` function and helpers)

This is the highest-risk change. `getFilteredD` is the in-JS re-aggregator that recomputes by_hour/by_session/by_dow/dir_summary/by_year/top_combos/worst_combos when filter chips are toggled. Today it reads `D.recent_trades`. After this change it reads from the cache.

- [ ] **Step 1: Update column reads inside `getFilteredD`**

Open `Fractal Sweep/js/data.js` and find `getFilteredD` (currently starts at line 188). Make these specific changes:

**Change 1 — at the top of `getFilteredD`** (currently line 191): replace
```js
  const rawTrades = D?.recent_trades;
```
with
```js
  // Trades now come from the parquet cache populated by loadTrades.
  // For backward compatibility during rollout (Phase 3 → Phase 4), fall
  // back to D.recent_trades if cache is empty. This fallback is REMOVED
  // in Phase 5 (Task 12) once the engine stops writing recent_trades.
  const fullKey = activeFullKey();  // helper added below
  const periodKey = activeTF === 'custom'
    ? `${(customRanges[0]||{}).from}:${(customRanges[0]||{}).to}`
    : activeTF;
  const cached = DATA[fullKey]?.trades?.[activeProfile]?.[periodKey];
  const rawTrades = cached && cached.length ? cached : D?.recent_trades;
```

Add `activeFullKey` near the top of `data.js` (after the existing `activeTF` import):
```js
function activeFullKey() {
  return `${activeModel}_${activeMode}_${activeCisd}`;
}
```

(Make sure `activeModel`, `activeMode`, `activeCisd`, `activeProfile`, `customRanges` are imported from `./state.js` at the top of this file. Add to the existing import line if missing.)

**Change 2 — `by_dow` DOW name derivation (currently line 293-302)**: replace
```js
  const DOW_NAMES_MAP = {0:'Sun',1:'Mon',2:'Tue',3:'Wed',4:'Thu',5:'Fri',6:'Sat'};
  const dowMap = {};
```
The block that follows already uses `t.dow_name` as fallback. Find the lines (within ~10 lines after the map declaration) and update the `dn` derivation to:
```js
    const dn = DOW_NAMES_MAP[t.dow] ?? t.dow_name ?? String(t.dow);
```
(Order matters: parquet's `dow` is canonical; only fall back to `dow_name` if `dow` is somehow missing.)

**Change 3 — `top_combos` derivation (currently line 361)**: replace
```js
      const dn = t.dow_name || DOW_NAMES[t.dow] || String(t.dow);
```
with
```js
      const dn = DOW_NAMES[t.dow] ?? t.dow_name ?? String(t.dow);
```

**Change 4 — equity sort by date (line 215)**: no change needed — parquet's `date` is still a string starting with `YYYY-MM-DD`.

- [ ] **Step 2: Verify by manual smoke**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open http://localhost:8001/Fractal%20Sweep/model_dashboard.html"
echo "1. Verify dashboard loads normally"
echo "2. Toggle SMT chip — by_hour/by_dow charts must update (recomputed from rawTrades)"
echo "3. Switch period to 2y — stats must update"
echo "4. Check console for errors"
echo "Press Enter when verified..."
read
kill $SERVER_PID
```

Expected: No console errors. SMT toggle still recomputes stats. The cache fallback to `D.recent_trades` means this works even before Task 6 hooks up `loadTrades` to the period switcher.

- [ ] **Step 3: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/js/data.js"
git commit -m "refactor(fractal-sweep): getFilteredD reads cached parquet trades, falls back to JSON during rollout"
```

---

### Task 6: Hook `loadTrades` into `switchTF` and `switchProfile`

**Files:**
- Modify: `Fractal Sweep/js/tabs/overview.js:26-33` (`switchProfile`)
- Modify: `Fractal Sweep/js/tabs/overview.js:86-98` (`switchTF`)

- [ ] **Step 1: Update `switchProfile`**

Replace the existing function:
```js
async function switchProfile(pk){
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  await loadProfile(fullKey, pk);
  await loadTrades(fullKey, pk, activeTF || 'all');
  setActiveProfile(pk);
  updateProfileSelectorsFromKey(pk);
  window.render();
}
```

Add `loadTrades` to the imports at the top of the file (already imports `loadProfile` from `../data.js`).

- [ ] **Step 2: Update `switchTF`**

Replace the existing function:
```js
async function switchTF(tf){
  setActiveTF(tf);
  const builder = document.getElementById('custom-range-builder');
  if (builder) builder.style.display = tf === 'custom' ? '' : 'none';
  if (tf === 'custom') {
    if (customRanges.length === 0) addCustomRange();
    renderRangeSlots();
  } else {
    const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
    await loadTrades(fullKey, activeProfile, tf);
  }
  localStorage.setItem('fractal-active-tf', tf);
  window.renderActive();
  window.updateTabVisibility();
  drawSetupViz();
}
```

- [ ] **Step 3: Update `initProfileData` in `data.js`** so the initial load primes the trade cache.

Find `initProfileData` (currently line 133) and replace:
```js
async function initProfileData() {
  const models = await loadModelList();
  const fullKey = '1H_5M_PREV_CISD';
  const target = models.includes(fullKey) ? fullKey : (models.find(k => k !== '_meta') || fullKey);
  await loadProfile(target, 'simple_1r');
  await loadTrades(target, 'simple_1r', 'all');
  return true;
}
```

- [ ] **Step 4: Verify in browser**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open http://localhost:8001/Fractal%20Sweep/model_dashboard.html"
echo "1. Page should load with stats populated"
echo "2. DevTools Network tab: expect ONE /trades request on initial load"
echo "3. Switch period 2y → 1y → 6m. Each switch triggers a /trades request"
echo "4. Switch back to 2y — should NOT trigger a request (cached)"
echo "Press Enter when verified..."
read
kill $SERVER_PID
```

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/js/tabs/overview.js" "Fractal Sweep/js/data.js"
git commit -m "feat(fractal-sweep): period/profile switchers prime loadTrades cache"
```

---

### Task 7: Migrate `verdict.js`, `walkforward.js`, edge/excursion/filters/app to cache reads

**Files:**
- Modify: `Fractal Sweep/js/verdict.js:74-78`
- Modify: `Fractal Sweep/js/walkforward.js:753-754` (and the custom-range fetch around line 2297)
- Modify: `Fractal Sweep/js/tabs/edge.js:331`
- Modify: `Fractal Sweep/js/tabs/excursion.js:238, 487`
- Modify: `Fractal Sweep/js/tabs/filters.js:4`
- Modify: `Fractal Sweep/js/app.js:130`

The migration pattern for each site is identical: replace `D.recent_trades` (or `pd.recent_trades`) with a lookup into the cache, with a fallback to `D.recent_trades` for the rollout transition.

- [ ] **Step 1: Add a shared accessor helper to `data.js`**

Inside `data.js`, after `getProfileData`:
```js
// Resolves trade rows for the current (fullKey, profile, period) view.
// Reads from the loadTrades cache; falls back to D.recent_trades during rollout.
function getActiveTrades(D) {
  const fullKey = activeFullKey();
  const periodKey = activeTF === 'custom'
    ? `${(customRanges[0]||{}).from}:${(customRanges[0]||{}).to}`
    : activeTF;
  const cached = DATA[fullKey]?.trades?.[activeProfile]?.[periodKey];
  if (cached && cached.length) return cached;
  // Per-TF JSON fallback (matches verdict.js's old by_tf lookup):
  if (D?.by_tf?.[activeTF]?.recent_trades) return D.by_tf[activeTF].recent_trades;
  return D?.recent_trades || [];
}
export { getActiveTrades };
```

- [ ] **Step 2: Update `verdict.js:74-78`**

Replace:
```js
    if (!pd || !pd.recent_trades) return null;
    let pt = pd.recent_trades;
    // ...
    if (!tradeDateSet && activeTF !== 'all' && pd.by_tf && pd.by_tf[activeTF] && pd.by_tf[activeTF].recent_trades) {
      pt = pd.by_tf[activeTF].recent_trades;
```
with:
```js
    let pt = getActiveTrades(pd);
    if (!pt || !pt.length) return null;
```
Add `getActiveTrades` to the import from `./data.js` at the top of the file.

- [ ] **Step 3: Update `walkforward.js:753-754`**

Replace:
```js
  if(!baseD || !baseD.recent_trades) return;
  const allTrades = getSmtFilteredTrades(baseD.recent_trades);
```
with:
```js
  const sourceTrades = getActiveTrades(baseD);
  if(!sourceTrades || !sourceTrades.length) return;
  const allTrades = getSmtFilteredTrades(sourceTrades);
```

Then find the custom-range path (around line 2297) where it reads `recent_trades` for walkforward — replace any `recent_trades` reads with an awaited `loadTrades(fullKey, activeProfile, {from, to})` and use the returned array. Exact line will surface during edit; the pattern is the same.

Add to imports: `getActiveTrades, loadTrades` from `../data.js` (already imports getFilteredD).

- [ ] **Step 4: Update `tabs/edge.js:331`, `tabs/excursion.js:238, 487`, `tabs/filters.js:4`, `app.js:130`**

For each file: find the line that reads `D?.recent_trades` and replace with `getActiveTrades(D)`. Add `getActiveTrades` to the import from `../data.js` (or `./data.js` for app.js).

- [ ] **Step 5: Verify in browser — every affected tab**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open http://localhost:8001/Fractal%20Sweep/model_dashboard.html"
echo "Verify every tab loads with stats:"
echo "  - Overview (verdict tile, hero stats)"
echo "  - Filters tab"
echo "  - Edge tab"
echo "  - Excursion tab (MAE/MFE charts)"
echo "  - Walk-Forward tab (custom range)"
echo "Check console — must be clean"
echo "Press Enter when verified..."
read
kill $SERVER_PID
```

- [ ] **Step 6: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/js/"
git commit -m "refactor(fractal-sweep): all trade-row consumers read from loadTrades cache"
```

---

### Task 8: Replace recalc reload path with `initProfileData`

**Files:**
- Modify: `Fractal Sweep/js/app.js:162-176`

- [ ] **Step 1: Replace the inner reload block in `pollRecalc`**

Find:
```js
      if(s.status==='ok'){
        clearInterval(iv);
        btn.textContent='✓ Done — reloading…';
        setTimeout(()=>{
          fetch('./model_stats.json').then(r=>r.json()).then(applyLoadedData).finally(()=>{
            btn.textContent='⟳ Recalculate';btn.disabled=false;
          });
        },400);
      }
```

Replace with:
```js
      if(s.status==='ok'){
        clearInterval(iv);
        btn.textContent='✓ Done — reloading…';
        setTimeout(async ()=>{
          // Invalidate trade cache (parquet was just regenerated) and refetch
          // aggregates + trades via the API instead of the full JSON.
          const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
          invalidateTradesCache(fullKey);
          DATA[fullKey] = { profiles: {} };  // force /data refetch
          try {
            await initProfileData();
            window.render();
          } finally {
            btn.textContent='⟳ Recalculate'; btn.disabled=false;
          }
        }, 400);
      }
```

Add to the imports at the top of `app.js`: `invalidateTradesCache, initProfileData, DATA` (some may already be imported).

- [ ] **Step 2: Verify in browser**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open http://localhost:8001/Fractal%20Sweep/model_dashboard.html"
echo "Click Recalculate. After ~30s when status flips to OK:"
echo "  - Dashboard reloads"
echo "  - DevTools Network: should NOT see a fetch for ./model_stats.json"
echo "  - Should see /data and /trades calls instead"
echo "Press Enter when verified..."
read
kill $SERVER_PID
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/js/app.js"
git commit -m "fix(fractal-sweep): post-recalc reload uses initProfileData not full JSON fetch"
```

---

### Task 9: Shadow-mode runtime asserts (`?shadow=1`)

**Files:**
- Create: `Fractal Sweep/js/shadow.js`
- Modify: `Fractal Sweep/js/app.js` (top of file — load shadow.js if `?shadow=1`)

- [ ] **Step 1: Create shadow.js**

```js
// shadow.js — runtime cross-check that parquet-sourced trades match what
// the JSON would have returned. Activated by `?shadow=1` in URL.
// Drops itself in Phase 5 once the engine stops writing recent_trades.

import { DATA, loadTrades } from './data.js';
import { activeModel, activeMode, activeCisd, activeProfile, activeTF } from './state.js';

const SAMPLE = 50;
let _checked = new Set();

function _key(fullKey, profile, period) {
  return `${fullKey}::${profile}::${period}`;
}

function _jsonTradesForPeriod(profileData, period) {
  if (!profileData) return null;
  if (period === 'all') return profileData.recent_trades || [];
  return profileData.by_tf?.[period]?.recent_trades || [];
}

// Map parquet column → JSON column to compare like-for-like.
// The JSON has `sl_price` and `dow_name`; the parquet has `stop_price` and `dow`.
function _normalize(row, source) {
  const r = { ...row };
  if (source === 'parquet') {
    r.sl_price = row.stop_price;
    r.dow_name = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][row.dow];
  }
  return r;
}

async function _check(fullKey, profile, period) {
  const k = _key(fullKey, profile, period);
  if (_checked.has(k)) return;
  _checked.add(k);

  const profData = DATA[fullKey]?.profiles?.[profile];
  const jsonTrades = _jsonTradesForPeriod(profData, period);
  let parquetTrades;
  try {
    parquetTrades = await loadTrades(fullKey, profile, period);
  } catch (e) {
    console.warn('[shadow]', k, 'parquet fetch failed:', e);
    return;
  }

  if (!jsonTrades || !jsonTrades.length) {
    console.info('[shadow]', k, 'JSON has no trades for this slice — skipping');
    return;
  }

  if (jsonTrades.length !== parquetTrades.length) {
    console.error('[shadow]', k, 'COUNT MISMATCH: json=', jsonTrades.length, 'parquet=', parquetTrades.length);
    return;
  }

  // Compare a sampled subset of rows on key fields. Both sorted by date desc.
  const sortByDate = (a, b) => (b.date || '').localeCompare(a.date || '');
  const jSorted = [...jsonTrades].sort(sortByDate);
  const pSorted = [...parquetTrades].sort(sortByDate);
  const FIELDS = ['date', 'direction', 'hr', 'dow', 'r', 'outcome', 'mae_pct', 'mfe_pct'];
  let mismatches = 0;
  for (let i = 0; i < Math.min(SAMPLE, jSorted.length); i++) {
    const j = jSorted[i];
    const p = _normalize(pSorted[i], 'parquet');
    for (const f of FIELDS) {
      const a = j[f], b = p[f];
      const ok = (a == null && b == null) || (typeof a === 'number'
        ? Math.abs((a||0) - (b||0)) < 1e-4
        : a === b);
      if (!ok) {
        console.error('[shadow]', k, `row ${i} field ${f}: json=${a} parquet=${b}`);
        mismatches++;
      }
    }
    if (mismatches > 5) {
      console.error('[shadow]', k, 'stopping at 5+ mismatches');
      return;
    }
  }
  if (mismatches === 0) {
    console.log('[shadow]', k, '✓ count + sampled rows match');
  }
}

// Public: hook called from key UI transitions.
export async function shadowCheck() {
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  await _check(fullKey, activeProfile, activeTF || 'all');
}

// Auto-poll on render (cheap because of _checked dedupe).
window.addEventListener('hashchange', shadowCheck);
const _origRenderActive = window.renderActive;
if (_origRenderActive) {
  window.renderActive = function() {
    _origRenderActive.apply(this, arguments);
    shadowCheck();
  };
}
console.log('[shadow] mode active — comparing parquet vs JSON trades');
```

- [ ] **Step 2: Wire it into `app.js`**

Near the top of `Fractal Sweep/js/app.js`, after the existing imports, add:
```js
// Shadow-mode runtime drift check — activated by ?shadow=1
if (new URLSearchParams(window.location.search).has('shadow')) {
  import('./shadow.js');
}
```

- [ ] **Step 3: Run a shadow session**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open http://localhost:8001/Fractal%20Sweep/model_dashboard.html?shadow=1"
echo "Open DevTools console. Cycle through:"
echo "  - Every period (2y, 1y, 6m, 3m, 1m, all)"
echo "  - simple_1r and raw_measure profiles"
echo "  - Each model (1H_5M_PREV_CISD, 30M_3M_PREV_CISD, 15M_1M_PREV_CISD)"
echo "  - Toggle SMT, F3, F4 chips"
echo "Console must show '[shadow] ✓ count + sampled rows match' lines, NO red errors"
echo "Press Enter when shadow session is clean..."
read
kill $SERVER_PID
```

If errors appear: fix the underlying drift (likely in `_get_trades` period anchoring or in JSON↔parquet field mapping) before continuing. **Do not proceed to Phase 4 with red shadow errors.**

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/js/shadow.js" "Fractal Sweep/js/app.js"
git commit -m "test(fractal-sweep): shadow.js runtime asserts for parquet/JSON parity"
```

---

## Phase 4 — Engine: stop writing `recent_trades` to JSON

### Task 10: Drop `recent_trades` from JSON output

**Files:**
- Modify: `Fractal Sweep/engine/model_stats.py:2256` (top-level profile dict)
- Modify: `Fractal Sweep/engine/model_stats.py:2395` (by_tf sub-slice dict)

- [ ] **Step 1: Remove `recent_trades` from top-level dict**

Open `Fractal Sweep/engine/model_stats.py`. Find line 2256 — the line in the profile dict that reads:
```python
        'recent_trades':    recent_trades,
```
Delete this entire line.

- [ ] **Step 2: Remove `recent_trades` from by_tf slice dict**

Find line 2395 — the line in `_build_slice_stats`:
```python
        'recent_trades':   recent_trades,
```
Delete this entire line.

- [ ] **Step 3: Add `date_start` and `date_end` to by_tf slice**

In `_build_slice_stats` (the function around line 2266), the function already receives `wl_sub` which is the filtered DataFrame for that period. Locate the return dict (the one that previously had `recent_trades`) and add these keys:
```python
        'date_start':      str(wl_sub['date'].min())[:10] if len(wl_sub) else None,
        'date_end':        str(wl_sub['date'].max())[:10] if len(wl_sub) else None,
```

(Add them anywhere in the return dict, e.g. right after `'r_hist'`.)

- [ ] **Step 4: Regenerate**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 engine/model_stats.py 2>&1 | tail -15
```

Expected: completes without errors. New `model_stats.json` is written.

- [ ] **Step 5: Verify file shrunk**

```bash
ls -lh model_stats.json model_stats.parquet
python3 -c "
import json
d = json.load(open('model_stats.json'))
mk = [k for k in d if k != '_meta'][0]
prof = d[mk]['profiles']['simple_1r']
assert 'recent_trades' not in prof, 'recent_trades still in top-level'
for tf, slice_ in prof.get('by_tf', {}).items():
    assert 'recent_trades' not in slice_, f'recent_trades still in by_tf[{tf}]'
    assert 'date_start' in slice_, f'date_start missing in by_tf[{tf}]'
print('JSON cleaned successfully')
"
```

Expected: file size drops dramatically (target <50 MB). Script prints `JSON cleaned successfully`.

- [ ] **Step 6: Run drift test against new JSON + parquet**

```bash
python3 -m pytest tests/test_no_drift.py -v 2>&1 | tail -30
```

Expected: `src=parquet` tests still PASS (engine math unchanged). `src=json` tests will mostly SKIP or fail with KeyError for `recent_trades` — that's expected; the JSON no longer has those rows. The parquet path is now the ground truth.

- [ ] **Step 7: Run full pytest suite**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -10
```

Expected: pass (or same baseline as before this PR — none of the other tests depend on `recent_trades` in JSON).

- [ ] **Step 8: Verify dashboard in browser**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open http://localhost:8001/Fractal%20Sweep/model_dashboard.html"
echo "Walk every tab / filter / period. Stats must populate from /trades."
echo "Then http://...?shadow=1 — shadow will now find no JSON trades and skip gracefully."
echo "Press Enter when verified..."
read
kill $SERVER_PID
```

- [ ] **Step 9: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/engine/model_stats.py"
git commit -m "feat(fractal-sweep): drop recent_trades from JSON; trades sourced from parquet"
```

---

## Phase 5 — Remove fallbacks and shadow scaffolding

### Task 11: Remove `D.recent_trades` fallbacks

**Files:**
- Modify: `Fractal Sweep/js/data.js` (the `rawTrades` fallback in `getFilteredD` and the `getActiveTrades` fallback)

- [ ] **Step 1: Remove fallbacks in `getActiveTrades`**

Find `getActiveTrades` in `data.js` and replace with:
```js
function getActiveTrades(D) {
  const fullKey = activeFullKey();
  const periodKey = activeTF === 'custom'
    ? `${(customRanges[0]||{}).from}:${(customRanges[0]||{}).to}`
    : activeTF;
  return DATA[fullKey]?.trades?.[activeProfile]?.[periodKey] || [];
}
```

- [ ] **Step 2: Remove fallback in `getFilteredD`**

In `getFilteredD` (the change from Task 5 Step 1), replace:
```js
  const cached = DATA[fullKey]?.trades?.[activeProfile]?.[periodKey];
  const rawTrades = cached && cached.length ? cached : D?.recent_trades;
```
with:
```js
  const rawTrades = DATA[fullKey]?.trades?.[activeProfile]?.[periodKey] || [];
```

- [ ] **Step 3: Verify in browser**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open dashboard. Walk every tab/period/filter. Console must be clean."
echo "Press Enter when verified..."
read
kill $SERVER_PID
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/js/data.js"
git commit -m "refactor(fractal-sweep): remove rollout fallbacks to JSON recent_trades"
```

---

### Task 12: Delete shadow.js

**Files:**
- Delete: `Fractal Sweep/js/shadow.js`
- Modify: `Fractal Sweep/js/app.js` (remove shadow loader)

- [ ] **Step 1: Remove the shadow loader from app.js**

Delete these lines near the top of `app.js`:
```js
if (new URLSearchParams(window.location.search).has('shadow')) {
  import('./shadow.js');
}
```

- [ ] **Step 2: Delete shadow.js**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
rm "Fractal Sweep/js/shadow.js"
```

- [ ] **Step 3: Verify**

```bash
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open dashboard — must still work normally without shadow."
echo "Open ?shadow=1 URL — should now have no effect (no import error in console)."
echo "Press Enter when verified..."
read
kill $SERVER_PID
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/js/app.js" "Fractal Sweep/js/shadow.js"
git commit -m "chore(fractal-sweep): remove shadow.js scaffolding now that migration is verified"
```

---

## Final Verification

- [ ] **Step 1: Confirm JSON size reduction**

```bash
ls -lh "Fractal Sweep/model_stats.json" "Fractal Sweep/model_stats.parquet"
```

Expected: JSON < 50 MB (down from 270 MB).

- [ ] **Step 2: Full pytest run**

```bash
cd "Fractal Sweep"
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: All tests pass.

- [ ] **Step 3: Full dashboard walkthrough**

Smoke test every tab, profile, period, model, filter combo. Console clean.

- [ ] **Step 4: Document the wins**

Add a brief note to `Fractal Sweep/CLAUDE.md` under the "Engine" section noting that trade rows live in parquet, JSON contains aggregates only. (One sentence — do not duplicate the spec.)

---

## Self-Review

**Spec coverage:**
- [x] Goal 1 (270 MB → <30-50 MB): Task 10 strips `recent_trades` from both insertion points.
- [x] Goal 2 (frontend reads trades from parquet): Tasks 4-8 migrate every consumer.
- [x] Goal 3 (parquet-native schema, β): Server returns columns as-is (Task 3); JS reads `stop_price`, derives `dow_name` (Tasks 5, 7).
- [x] Goal 4 (snapshot + shadow): Tasks 1-2 (snapshot), Task 9 (shadow).
- [x] Non-goal "no engine math changes": Task 10 only deletes 2 lines and adds 2 date-range strings — no math changes.
- [x] XOR validation: Task 3 enforces and tests.
- [x] Cache key for custom ranges: Task 4 uses `from:to` string.
- [x] Failure modes (404 missing parquet, 400 XOR): Task 3 covered.
- [x] Recalc reload path fix: Task 8.

**Placeholder scan:** None.

**Type consistency:** `loadTrades(fullKey, profile, periodOrRange)`, `getActiveTrades(D)`, `invalidateTradesCache(fullKey)` — signatures consistent across tasks 4, 5, 6, 7, 8, 11.

Plan is ready.
