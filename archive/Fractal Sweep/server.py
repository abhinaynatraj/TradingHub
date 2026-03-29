#!/usr/bin/env python3
"""
Candle Science — Local Server
==============================
Serves the dashboard on http://localhost:8000 and exposes:

  POST /api/update   — runs daily_update.py, streams log lines as SSE
  GET  /api/status   — returns last update time from model_stats.json

Usage:
    python3 server.py
    python3 server.py --port 8080

This replaces `python3 -m http.server`. Run this instead.
"""

import sys
import json
import subprocess
import threading
import time
import argparse
import mimetypes
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

BASE_DIR     = Path(__file__).parent
UPDATE_SCRIPT = BASE_DIR / "daily_update.py"
PROBS_JSON   = BASE_DIR / "model_stats.json"
PYTHON       = sys.executable

# Track running update so we don't start two at once
_update_lock   = threading.Lock()
_update_running = False


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Suppress default per-request stdout noise
        pass

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    # ── GET ──────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/api/status":
            self._handle_status()
        elif path == "/api/update-stream":
            self._handle_update_stream()
        else:
            self._serve_file(path)

    # ── POST ─────────────────────────────────────────────────
    def do_POST(self):
        if self.path == "/api/update":
            self._handle_update_trigger()
        else:
            self.send_response(404)
            self.end_headers()

    # ── HANDLERS ─────────────────────────────────────────────
    def _handle_status(self):
        status = {"running": _update_running, "last_update": None, "error": None}
        if PROBS_JSON.exists():
            try:
                data = json.loads(PROBS_JSON.read_text())
                status["last_update"] = data.get("generated")
            except Exception as e:
                status["error"] = str(e)
        self.send_response(200)
        self.send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())

    def _handle_update_trigger(self):
        """Starts the update script in a background thread, returns immediately."""
        global _update_running
        if _update_running:
            self.send_response(409)  # Conflict — already running
            self.send_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Update already in progress"}).encode())
            return

        _update_running = True

        def run():
            global _update_running
            try:
                subprocess.run([PYTHON, str(UPDATE_SCRIPT)], check=False)
            finally:
                _update_running = False

        threading.Thread(target=run, daemon=True).start()

        self.send_response(202)  # Accepted
        self.send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"started": True}).encode())

    def _handle_update_stream(self):
        """
        Server-Sent Events stream — runs the update script and streams
        each line of stdout/stderr as an SSE event so the dashboard can
        show live progress.
        """
        global _update_running
        if _update_running:
            self.send_response(409)
            self.send_cors()
            self.end_headers()
            return

        self.send_response(200)
        self.send_cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def sse(msg):
            try:
                line = f"data: {json.dumps(msg)}\n\n"
                self.wfile.write(line.encode())
                self.wfile.flush()
            except BrokenPipeError:
                pass

        _update_running = True
        try:
            if not UPDATE_SCRIPT.exists():
                sse({"type": "error", "text": f"Script not found: {UPDATE_SCRIPT}"})
                sse({"type": "done", "success": False})
                return

            proc = subprocess.Popen(
                [PYTHON, str(UPDATE_SCRIPT)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in proc.stdout:
                sse({"type": "log", "text": line.rstrip()})

            proc.wait()
            success = proc.returncode == 0
            sse({"type": "done", "success": success, "returncode": proc.returncode})

        except Exception as e:
            sse({"type": "error", "text": str(e)})
            sse({"type": "done", "success": False})
        finally:
            _update_running = False

    def _serve_file(self, path):
        """Serve static files from BASE_DIR."""
        if path == "/":
            path = "/index.html"

        file_path = BASE_DIR / path.lstrip("/")

        # Security: prevent path traversal
        try:
            file_path.resolve().relative_to(BASE_DIR.resolve())
        except ValueError:
            self.send_response(403)
            self.end_headers()
            return

        if not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        mime, _ = mimetypes.guess_type(str(file_path))
        mime = mime or "application/octet-stream"

        content = file_path.read_bytes()
        self.send_response(200)
        self.send_cors()
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    parser = argparse.ArgumentParser(description="Candle Science local server")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = HTTPServer(("localhost", args.port), Handler)
    print()
    print(f"  🕯  Candle Science")
    print(f"  ─────────────────────────────")
    print(f"  Open: http://localhost:{args.port}")
    print(f"  Base: {BASE_DIR}")
    print(f"  Ctrl+C to stop")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()
