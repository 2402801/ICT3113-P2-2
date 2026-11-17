#!/usr/bin/env python3
"""Tiny hand-shake server between P1 (SUT laptop) and P2 (load-generator laptop). Standard library only.

P1's scripts start it (port 8099) and publish the run state; P2's loop polls it, runs JMeter when a run is READY and
reports DONE. It never touches the triage service, Ollama or the database.

  GET  /state            current state (JSON)
  POST /state            P1 publishes {"state": "READY"|"IDLE"|"FINISHED", "run_id": ..., ...}; resets "done"
  POST /done             P2 reports {"run_id": ..., "sent": ..., ...}; accepted only for the current run_id
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
STATE = {"state": "IDLE", "done": False}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        with LOCK:
            self._send(200, STATE)

    def do_POST(self):
        try:
            body = self._body()
        except ValueError:
            return self._send(400, {"error": "bad json"})
        with LOCK:
            if self.path == "/state":
                STATE.clear()
                STATE.update(body)
                STATE["done"] = False
                return self._send(200, STATE)
            if self.path == "/done":
                if body.get("run_id") != STATE.get("run_id"):
                    return self._send(409, {"error": "run_id does not match the current run", "current": STATE.get("run_id")})
                STATE["done"] = True
                STATE["result"] = body
                return self._send(200, STATE)
        self._send(404, {"error": "unknown path"})

    def log_message(self, fmt, *args):
        sys.stderr.write("[control] " + (fmt % args) + "\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    print(f"A2 control server on 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
