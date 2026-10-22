"""Loopback-only deterministic fixtures. No real model or external network."""
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@contextmanager
def mock_server():
    counts, lock = {}, threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_POST(self):
            if self.path != "/chat/completions":
                return self.respond(404, {})
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                return self.respond(413, {})
            try:
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict) or "messages" not in request:
                    raise ValueError()
            except ValueError:
                return self.respond(400, {})
            behavior = self.headers.get("X-Mock-Behavior", "normal")
            request_id = self.headers.get("X-Request-Id", "")
            with lock:
                counts[request_id] = counts.get(request_id, 0) + 1
                count = counts[request_id]
            if behavior == "auth_failure":
                return self.respond(401, {"error": "fixture"})
            if behavior == "always_busy":
                return self.respond(503, {"error": "fixture"})
            if behavior in {"retry_once", "rate_limit_once"} and count == 1:
                return self.respond(503 if behavior == "retry_once" else 429, {"error": "fixture"})
            if behavior == "slow":
                time.sleep(.15)
            if behavior == "malformed_protocol":
                return self.respond(200, b"not-json")
            content = {"normal": '{"name":"demo","skills":["Python"]}',
                       "labels": '{"labels":["AI","Python"]}',
                       "number": '{"value":4}', "boolean": '{"ok":true}',
                       "text": "Python is a programming language.",
                       "invalid_json": "{invalid", "missing_key": '{"other":1}',
                       "empty": "", "html": '{"name":"<script>alert(1)</script>"}'}.get(
                           behavior, '{"name":"demo","skills":["Python"]}')
            response = {"choices": [{"message": {"role": "assistant", "content": content},
                                           "finish_reason": "stop"}],
                        "usage": {"total_tokens": 32}}
            if behavior == "no_usage":
                response.pop("usage")
            self.respond(200, response)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
