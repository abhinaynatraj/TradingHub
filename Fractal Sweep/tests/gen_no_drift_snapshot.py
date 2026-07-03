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
        sub = [t for t in trades if (t.get("direction") or "").lower() == direction]
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


def _parse_full_key(full_key):
    """JSON full key like '1H_5M_PREV_CISD' → (model_key, sweep_mode, cisd_mode)."""
    parts = full_key.rsplit("_", 2)
    return parts[0], parts[1], parts[2]


_PARQUET_CACHE = {"df": None}

def _trades_for_period(full_key, profile_key, period):
    """Read trade rows from model_stats.parquet for the canonical period.

    Day counts (730/365/182/91/30) match engine's _compute_by_tf exactly.
    Excludes EXPIRED outcomes to match the old JSON recent_trades semantics.
    """
    import pandas as pd
    if _PARQUET_CACHE["df"] is None:
        _PARQUET_CACHE["df"] = pd.read_parquet(ROOT / "model_stats.parquet")
    df = _PARQUET_CACHE["df"]
    model_key, sweep_mode, cisd_mode = _parse_full_key(full_key)
    df = df[
        (df["model_key"] == model_key)
        & (df["sweep_mode"] == sweep_mode)
        & (df["cisd_mode"] == cisd_mode)
        & (df["profile_key"] == profile_key)
    ]
    df = df[df["outcome"] != "EXPIRED"]
    if period != "all":
        days = {"2y": 730, "1y": 365, "6m": 182, "3m": 91, "1m": 30}[period]
        dates = pd.to_datetime(df["date"])
        cutoff = dates.max() - pd.Timedelta(days=days)
        df = df[dates >= cutoff]
    if df.empty:
        return []
    return df.where(df.notna(), None).to_dict("records")


def build_snapshot():
    snap = {}
    for model in MODELS:
        snap[model] = {}
        for period in PERIODS:
            trades = _trades_for_period(model, PROFILE, period)
            snap[model][period] = {
                "n_trades": len(trades),
                "verdict_inputs": _verdict_score(None, trades),
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
