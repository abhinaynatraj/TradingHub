"""
TradingHub local server
========================
Serves the static dashboards via HTTP and exposes /recalc and /data endpoints
so the HTML dashboards can trigger engine recalculations and load profile data
on demand (instead of fetching the full model_stats.json).

Run from repo root:
    python3 server.py

Dashboard URLs:
    http://localhost:8001/
    http://localhost:8001/Fractal Sweep/model_dashboard.html
    http://localhost:8001/TTrades Fractal Model Analysis/index.html
    http://localhost:8001/NPG Sweep/npg_dashboard.html
    http://localhost:8001/Amas Models/model_dashboard.html

Recalc endpoint (POST):
    /recalc?engine=fractal_sweep
    /recalc?engine=ttfm
    /recalc?engine=npg
    /recalc?engine=amas

Data endpoint (GET):
    /data?engine=fractal_sweep  → returns _meta + list of model keys
    /data?engine=fractal_sweep&model=1H_5M_PREV_CISD&profile=simple_1r → returns that profile
"""

import json
import subprocess
import sys
import socket
import threading
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).parent

ENGINES = {
    "fractal_sweep": [sys.executable, "Fractal Sweep/engine/model_stats.py"],
    "ttfm":          [sys.executable, "TTrades Fractal Model Analysis/ttfm_backtest.py"],
    "npg":           [sys.executable, "NPG Sweep/engine/npg_stats.py"],
    "amas":          [sys.executable, "Amas Models/engine/model_stats.py"],
}

# ── Data cache ────────────────────────────────────────────────────────────────
_data_cache: dict[str, dict] = {}      # engine_key → full data
_last_data_mtimes: dict[str, float] = {}  # engine_key → mtime when loaded

def _get_data(engine: str) -> dict | None:
    """Load model_stats.json into memory, caching it. Returns full data dict."""
    json_paths = {
        "fractal_sweep": ROOT / "Fractal Sweep" / "model_stats.json",
        "amas":          ROOT / "Amas Models" / "model_stats.json",
        "ttfm":          ROOT / "TTrades Fractal Model Analysis" / "model_stats.json",
    }
    path = json_paths.get(engine)
    if not path or not path.exists():
        return None
    mtime = path.stat().st_mtime
    if engine not in _data_cache or _last_data_mtimes.get(engine) != mtime:
        with open(path, "r", encoding="utf-8") as f:
            _data_cache[engine] = json.load(f)
        _last_data_mtimes[engine] = mtime
    return _data_cache.get(engine)


# ── Parquet trade cache ──────────────────────────────────────────────────────
_parquet_cache: dict[str, object] = {}        # engine → DataFrame
_last_parquet_mtimes: dict[str, float] = {}   # engine → mtime when loaded

def _parse_full_key(full_key: str) -> tuple[str, str, str]:
    """Decompose JSON-style key '1H_5M_PREV_CISD' into (model_key, sweep_mode, cisd_mode).

    Parquet stores these as 3 separate columns; the JSON dashboard concatenates them
    as `{model_key}_{sweep_mode}_{cisd_mode}`. Splitting from the right keeps the
    model name intact even when it contains underscores (e.g. '1H_5M').
    """
    parts = full_key.rsplit("_", 2)
    if len(parts) != 3:
        raise ValueError(f"unexpected full_key shape: {full_key!r}")
    return parts[0], parts[1], parts[2]


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
      model: JSON-style full key, e.g. '1H_5M_PREV_CISD'. Decomposed into
             (model_key, sweep_mode, cisd_mode) before filtering the parquet.
      period: one of '2y'|'1y'|'6m'|'3m'|'1m'|'all'. Anchored to MAX(date)
              in the parquet (NOT today() — keeps results reproducible).
              Day counts (730/365/182/91/30) match engine's _compute_by_tf.
      date_from, date_to: arbitrary YYYY-MM-DD window. XOR with `period`.
      limit: optional row cap (applied after sorting by date desc).

    Returns: {"trades": [...], "count": N} on success;
             {"error": "..."} on parameter validation failure;
             None if parquet not present for the engine.

    EXPIRED setups are filtered out to match JSON recent_trades semantics.
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

    # Re-read parquet if the file's mtime has changed (e.g. after a recalc).
    # Matches _get_data's pattern so /trades doesn't serve stale data.
    mtime = path.stat().st_mtime
    if engine not in _parquet_cache or _last_parquet_mtimes.get(engine) != mtime:
        _parquet_cache[engine] = pd.read_parquet(path)
        _last_parquet_mtimes[engine] = mtime

    df = _parquet_cache[engine]

    if model:
        try:
            model_key, sweep_mode, cisd_mode = _parse_full_key(model)
        except ValueError as exc:
            return {"error": str(exc)}
        df = df[
            (df["model_key"] == model_key)
            & (df["sweep_mode"] == sweep_mode)
            & (df["cisd_mode"] == cisd_mode)
        ]
    if profile:
        df = df[df["profile_key"] == profile]

    # Exclude EXPIRED setups — JSON recent_trades does the same.
    df = df[df["outcome"] != "EXPIRED"]

    if df.empty:
        return {"trades": [], "count": 0}

    dates = pd.to_datetime(df["date"])

    if has_period and period != "all":
        days_lookup = {"2y": 730, "1y": 365, "6m": 182, "3m": 91, "1m": 30}
        cutoff = dates.max() - pd.Timedelta(days=days_lookup[period])
        df = df[dates >= cutoff]

    if has_range:
        df = df[(dates >= pd.Timestamp(date_from)) & (dates <= pd.Timestamp(date_to + " 23:59:59"))]

    if limit is not None:
        df = df.sort_values("date", ascending=False).head(limit)

    if df.empty:
        return {"trades": [], "count": 0}

    records = df.to_dict("records")
    # Scrub NaN values to None. pandas can't store None in float-typed columns
    # (auto-coerces back to NaN), so we must do this on the plain-Python dicts
    # AFTER to_dict("records"). NaN in JSON output is invalid per RFC 7159 —
    # browsers reject it. Affects raw_measure rows where stop_price /
    # target_price are NaN (no SL/TP for measurement-only profile).
    import math
    for r in records:
        r["date"] = str(r["date"])[:19]
        for k in ("dow", "hr", "mn", "yr"):
            if r.get(k) is not None and not (isinstance(r[k], float) and math.isnan(r[k])):
                r[k] = int(r[k])
        for k, v in list(r.items()):
            if isinstance(v, float) and math.isnan(v):
                r[k] = None

    return {"trades": records, "count": len(records)}


def _filter_data(full_data: dict, model: str | None, profile: str | None) -> dict | None:
    """Extract _meta and optionally model/profile slice from full data."""
    if model is None:
        return {"_meta": full_data.get("_meta"), "models": sorted(k for k in full_data if k != "_meta")}
    model_data = full_data.get(model)
    if model_data is None:
        return None
    if profile is None:
        keys = list(model_data.get("profiles", {}).keys())
        return {model: {"profiles": {k: None for k in keys}}}
    profiles = model_data.get("profiles", {})
    pd = profiles.get(profile)
    if pd is None and profiles:
        pd = next(iter(profiles.values()))
    if pd is None:
        return None
    return {model: {"profiles": {profile: pd}}}

_recalc_state: dict[str, dict] = {}
_recalc_lock = threading.Lock()


def _run_engine(engine_key: str, cmd: list[str]) -> None:
    with _recalc_lock:
        _recalc_state[engine_key] = {"status": "running", "started": time.time()}
    try:
        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
        with _recalc_lock:
            if result.returncode == 0:
                _recalc_state[engine_key] = {"status": "ok", "finished": time.time()}
            else:
                _recalc_state[engine_key] = {
                    "status": "error",
                    "finished": time.time(),
                    "stderr": result.stderr[-2000:],
                }
    except Exception as exc:
        with _recalc_lock:
            _recalc_state[engine_key] = {"status": "error", "error": str(exc)}


class Handler(SimpleHTTPRequestHandler):
    def handle(self):
        """
        Catch and ignore ConnectionResetErrors that occur when the browser 
        cancels a request (e.g., when clicking around or refreshing quickly).
        """
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, socket.error):
            # The client (browser) closed the connection before the server 
            # finished sending data. This is completely safe to ignore.
            pass
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def log_message(self, fmt, *args):
        # Log recalc API calls; suppress noisy static-asset requests.
        if "/recalc" in (self.path or "") or self.command in ("POST", "OPTIONS"):
            super().log_message(fmt, *args)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/recalc":
            self.send_error(404)
            return

        qs = parse_qs(parsed.query)
        engine = (qs.get("engine") or [""])[0]

        if engine not in ENGINES:
            self._json(400, {"error": f"Unknown engine '{engine}'. Valid: {list(ENGINES)}"})
            return

        with _recalc_lock:
            state = _recalc_state.get(engine, {})
            if state.get("status") == "running":
                self._json(409, {"status": "running", "message": "Already running"})
                return

        threading.Thread(target=_run_engine, args=(engine, ENGINES[engine]), daemon=True).start()
        self._json(202, {"status": "started", "engine": engine})

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/recalc/status":
            engine = (qs.get("engine") or [""])[0]
            with _recalc_lock:
                state = dict(_recalc_state.get(engine, {"status": "idle"}))
            state.pop("stderr", None)
            self._json(200, state)
            return

        if parsed.path == "/data":
            engine  = (qs.get("engine")  or [""])[0]
            model   = (qs.get("model")   or [None])[0]
            profile = (qs.get("profile") or [None])[0]
            full_data = _get_data(engine)
            if full_data is None:
                self._json(404, {"error": f"No data for engine '{engine}'. Run the engine first."})
                return
            result = _filter_data(full_data, model, profile)
            if result is None:
                self._json(404, {"error": f"Model '{model}' not found"})
                return
            self._json(200, result)
            return

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

        try:
            super().do_GET()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code: int, body: dict) -> None:
        import json
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    port = 8001
    server = HTTPServer(("", port), Handler)
    print(f"TradingHub server running at http://localhost:{port}/")
    print(f"  Fractal Sweep  →  http://localhost:{port}/Fractal%20Sweep/model_dashboard.html")
    print(f"  TTrades        →  http://localhost:{port}/TTrades%20Fractal%20Model%20Analysis/index.html")
    print(f"  NPG Sweep      →  http://localhost:{port}/NPG%20Sweep/npg_dashboard.html")
    print(f"  Amas Models    →  http://localhost:{port}/Amas%20Models/model_dashboard.html")
    print(f"  Recalc API     →  POST http://localhost:{port}/recalc?engine={{fractal_sweep|ttfm|npg|amas}}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
