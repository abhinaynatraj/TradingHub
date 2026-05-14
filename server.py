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
    http://localhost:8001/Amas Models/model_dashboard.html

Recalc endpoint (POST):
    /recalc?engine=fractal_sweep
    /recalc?engine=ttfm
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
_parquet_cache: dict[str, object] = {}  # engine → DataFrame

def _get_trades(
    engine: str,
    model: str | None,
    profile: str | None,
    limit: int,
) -> dict | None:
    import pandas as pd

    pq_paths = {
        "fractal_sweep": ROOT / "Fractal Sweep" / "model_stats.parquet",
    }
    path = pq_paths.get(engine)
    if not path or not path.exists():
        return None

    if engine not in _parquet_cache:
        _parquet_cache[engine] = pd.read_parquet(path)

    df = _parquet_cache[engine]
    if model:
        df = df[df["model_key"] == model]
    if profile:
        df = df[df["profile_key"] == profile]

    if df.empty:
        return {"trades": [], "count": 0}

    df = df.sort_values("date", ascending=False).head(limit)
    records = df.where(pd.notna(df), None).to_dict("records")
    for r in records:
        r["date"] = str(r["date"])[:19]
        for k in ("dow", "hr", "mn"):
            if r.get(k) is not None:
                r[k] = int(r[k])

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
            engine  = (qs.get("engine")  or [""])[0]
            model   = (qs.get("model")   or [None])[0]
            profile = (qs.get("profile") or [None])[0]
            limit   = int((qs.get("limit") or [12000])[0])
            result  = _get_trades(engine, model, profile, limit)
            if result is None:
                self._json(404, {"error": "No trade data found"})
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
    print(f"  Amas Models    →  http://localhost:{port}/Amas%20Models/model_dashboard.html")
    print(f"  Recalc API     →  POST http://localhost:{port}/recalc?engine={{fractal_sweep|ttfm|amas}}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
