"""Optional isolated integration test: needs free local 8443, OpenSSL and runtime deps.
Never run on the production/migration VM: this test is for a disposable test environment.
No credentials or certificates are retained. No Docker commands are executed.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from probe import Probe

PUBLIC = "integration-public-" + "a" * 40
PRIVATE = "integration-upstream-" + "b" * 40
MODEL = "integration-chat-model"


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_json(self, payload, status=200):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer " + PRIVATE:
            return self.send_json({"error": "auth"}, 401)
        if self.path != "/v1/models":
            return self.send_json({"error": "route"}, 404)
        self.send_json({"object": "list", "data": [{"id": MODEL, "created": 123, "owned_by": "test", "object": "model"}]})

    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer " + PRIVATE:
            return self.send_json({"error": "auth"}, 401)
        if self.path != "/v1/chat/completions":
            return self.send_json({"error": "route"}, 404)
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            for content in ("O", "K"):
                raw = json.dumps({"choices": [{"index": 0, "delta": {"content": content}}]}).encode()
                self.wfile.write(b"data: " + raw + b"\n\n")
                self.wfile.flush()
                time.sleep(0.35)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        if isinstance(payload.get("tool_choice"), dict):
            prompt = payload["messages"][0]["content"]
            nonce = prompt.split("with value ")[1].split(".")[0]
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "call-integration",
                      "type": "function", "function": {"name": "bridge_echo", "arguments": json.dumps({"value": nonce})}}]}
        elif payload.get("tool_choice") == "none":
            value = json.loads(payload["messages"][-1]["content"])["value"]
            message = {"role": "assistant", "content": value}
        else:
            message = {"role": "assistant", "content": "OK"}
        self.send_json({"id": "chat-test", "object": "chat.completion", "choices": [{"index": 0, "message": message}]})


def main():
    check = socket.socket()
    try:
        check.bind(("0.0.0.0", 8443))
    except OSError:
        raise SystemExit("8443 is in use: integration test aborted; no service was stopped")
    finally:
        check.close()
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix="bridge-integration-") as tmp:
        root = Path(tmp)
        certs = root / "certs"
        certs.mkdir()
        # Same certificate shape as the initial prototype, to catch Python/TLS regressions.
        subprocess.run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-sha256", "-days", "2",
                        "-keyout", str(certs / "key.pem"), "-out", str(certs / "cert.pem"),
                        "-subj", "/CN=bridge.test", "-addext", "subjectAltName=DNS:bridge.test"],
                       check=True, capture_output=True)
        env = {**os.environ, "PUBLIC_HOSTNAME": "bridge.test", "PUBLIC_PORT": "8443",
               "PUBLIC_API_KEY": PUBLIC, "UPSTREAM_API_KEY": PRIVATE,
               "UPSTREAM_BASE_URL": f"http://127.0.0.1:{upstream.server_port}/v1",
               "TLS_CERT_FILE": str(certs / "cert.pem"), "TLS_KEY_FILE": str(certs / "key.pem")}
        with (root / "bridge.log").open("w+") as logs:
            process = subprocess.Popen([sys.executable, "-m", "bridge"], cwd=ROOT, env=env,
                                       stdout=logs, stderr=subprocess.STDOUT)
            try:
                probe = Probe({**env, "TLS_CERT_FILE": "/certs/cert.pem"}, root=root)
                for _ in range(50):
                    try:
                        probe.health()
                        break
                    except Exception:
                        time.sleep(0.1)
                else:
                    logs.seek(0)
                    raise RuntimeError("HTTPS server failed to start: " + logs.read())
                print("PASS: real HTTPS service + legacy self-signed certificate + hostname validation")
                probe.json("/v1/models", auth=False, expected=401)
                assert probe.models()[0]["id"] == MODEL
                probe.chat(MODEL)
                probe.stream(MODEL)
                probe.tools(MODEL)
                body = {"model": MODEL, "messages": [{"role": "user", "content": "stream timing test"}], "stream": True}
                start = time.monotonic()
                connection, response = probe.open("/v1/chat/completions", body)
                try:
                    first = response.readline()
                    first_latency = time.monotonic() - start
                    remainder = response.read()
                finally:
                    connection.close()
                duration = time.monotonic() - start
                assert first.startswith(b"data:") and b"[DONE]" in remainder
                assert duration - first_latency > 0.4, (first_latency, duration)
                print(f"PASS: incremental SSE; first event {first_latency:.3f}s, total {duration:.3f}s")
                result = subprocess.run([sys.executable, str(ROOT / "tools/probe.py"), "--container", "--health-only"], env=env)
                assert result.returncode == 0
            finally:
                process.terminate()
                process.wait(timeout=10)
                upstream.shutdown()
                logs.seek(0)
                text = logs.read()
                assert PUBLIC not in text and PRIVATE not in text
                assert "stream timing test" not in text
        print("INTEGRATION HTTPS OK: service, auth, discovery, JSON, SSE, tool round trip, Docker healthcheck command, safe logs")


if __name__ == "__main__":
    main()
