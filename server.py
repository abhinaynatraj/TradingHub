"""
TradingHub local server
========================
Serves the static dashboards via HTTP and exposes a /recalc endpoint
so the HTML dashboards can trigger engine recalculations.

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
"""

import subprocess
import sys
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
        if parsed.path == "/recalc/status":
            qs = parse_qs(parsed.query)
            engine = (qs.get("engine") or [""])[0]
            with _recalc_lock:
                state = dict(_recalc_state.get(engine, {"status": "idle"}))
            state.pop("stderr", None)
            self._json(200, state)
            return
        super().do_GET()

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
