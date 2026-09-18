import json
import pathlib
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "deploy/van-trading-core/automation/provision-api.py"
API_KEY = "van-test-api-key-" + ("k" * 40)

class State:
    settings_calls = 0
    owner_ready = False
    key_created = False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _body(self):
        n = int(self.headers.get("content-length", "0"))
        return json.loads(self.rfile.read(n) or b"{}")

    def _json(self, status, body, cookie=False):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if cookie:
            self.send_header("Set-Cookie", "n8n-auth=session-token; Path=/; HttpOnly; Secure; SameSite=Lax")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _text(self, status, text):
        raw = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _session_ok(self):
        return "n8n-auth=session-token" in self.headers.get("Cookie", "")

    def do_GET(self):
        if self.path == "/rest/settings":
            State.settings_calls += 1
            if State.settings_calls == 1:
                self._text(503, "warming up")
            else:
                self._json(200, {"data": {"userManagement": {"showSetupOnFirstLoad": not State.owner_ready}}})
            return
        if self.path == "/rest/api-keys/scopes":
            if not self._session_ok():
                self._json(401, {"code": 401, "message": "unauthorized"})
            else:
                self._json(200, {"data": ["workflow:read", "workflow:list"]})
            return
        if self.path.startswith("/rest/api-keys?"):
            if not self._session_ok():
                self._json(401, {"code": 401, "message": "unauthorized"})
            else:
                self._json(200, {"data": {"items": [], "counts": {}, "totals": {}, "owners": []}})
            return
        if self.path.startswith("/api/v1/workflows"):
            if self.headers.get("X-N8N-API-KEY") == API_KEY:
                self._json(200, {"data": []})
            else:
                self._json(401, {"message": "invalid api key"})
            return
        self._json(404, {"message": "not found"})

    def do_POST(self):
        body = self._body()
        if self.path == "/rest/login":
            if not State.owner_ready:
                self._json(401, {"code": 401, "message": "Wrong username or password"})
            elif body.get("emailOrLdapLoginId") == "van-owner@dial.invalid":
                self._json(200, {"data": {"id": "owner"}}, cookie=True)
            else:
                self._json(401, {"code": 401, "message": "Wrong username or password"})
            return
        if self.path == "/rest/owner/setup":
            State.owner_ready = True
            self._json(201, {"data": {"id": "owner"}}, cookie=True)
            return
        if self.path == "/rest/api-keys":
            if not self._session_ok():
                self._json(401, {"code": 401, "message": "unauthorized"})
            else:
                State.key_created = True
                self._json(201, {"data": {"apiKey": "***", "rawApiKey": API_KEY}})
            return
        self._json(404, {"message": "not found"})

def test_n8n_provisioner_handles_startup_secure_cookie_and_wrapped_responses():
    State.settings_calls = 0
    State.owner_ready = False
    State.key_created = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as td:
            secrets = pathlib.Path(td)
            (secrets / "n8n-owner-password").write_text("Strong-Test-Password-1234567890\n")
            cmd = [sys.executable, str(SCRIPT), "--base", f"http://127.0.0.1:{server.server_port}",
                   "--secrets-dir", str(secrets)]
            first = subprocess.run(cmd, text=True, capture_output=True, timeout=30)
            assert first.returncode == 0, first.stderr + first.stdout
            assert "N8N_API_KEY_GREEN" in first.stdout
            assert State.owner_ready
            assert State.key_created
            key_path = secrets / "n8n-hermes-api.key"
            assert key_path.read_text().strip() == API_KEY
            assert oct(key_path.stat().st_mode & 0o777) == "0o600"

            second = subprocess.run(cmd, text=True, capture_output=True, timeout=30)
            assert second.returncode == 0, second.stderr + second.stdout
            assert "N8N_API_KEY_PRESERVED" in second.stdout
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
