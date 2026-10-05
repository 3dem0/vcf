"""Stdlib-only local HTTPS probes. Credentials are not passed in argv or printed."""
import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = "/api/v1/compatibility/openai/v1"


def read_env(path):
    # Deliberately RAW, just like Compose's env_file format: raw.
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Invalid .env line; expected KEY=value")
        key, value = line.split("=", 1)
        values[key.strip()] = value
    return values


class LocalHTTPSConnection(http.client.HTTPSConnection):
    """Dial locally, but validate the configured public DNS name and certificate."""
    def __init__(self, hostname, port, dial_host, context, timeout):
        super().__init__(hostname, port, context=context, timeout=timeout)
        self.dial_host = dial_host

    def connect(self):
        raw = socket.create_connection((self.dial_host, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class Probe:
    def __init__(self, env, root=ROOT, container=False):
        self.env = env
        self.hostname = env.get("PUBLIC_HOSTNAME", "")
        if not self.hostname or self.hostname.endswith(".invalid"):
            raise ValueError("Configure a real PUBLIC_HOSTNAME matching the certificate SAN")
        self.port = 8443 if container else int(env.get("PUBLIC_PORT", "8443"))
        self.dial_host = "127.0.0.1" if container else env.get("PUBLIC_BIND_ADDRESS", "0.0.0.0")
        if self.dial_host == "0.0.0.0":
            self.dial_host = "127.0.0.1"
        elif self.dial_host == "::":
            self.dial_host = "::1"
        cert = Path(env.get("TLS_CERT_FILE", "/certs/cert.pem"))
        if not container:
            if not str(cert).startswith("/certs/"):
                raise ValueError("Local probes require TLS_CERT_FILE under /certs/")
            cert = Path(root) / "certs" / cert.relative_to("/certs")
        # Verify chain AND DNS name, including the exact migrated self-signed cert.
        # Do not enable optional strict-CA extensions that reject older lab certificates.
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.load_default_certs()
        self.context.load_verify_locations(cafile=str(cert))
        self.timeout = int(env.get("READ_TIMEOUT_SECONDS", "600")) + 30

    def open(self, path, body=None, auth=True, timeout=None):
        connection = LocalHTTPSConnection(self.hostname, self.port, self.dial_host,
                                          self.context, timeout or self.timeout)
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if auth:
            headers["Authorization"] = "Bearer " + self.env["PUBLIC_API_KEY"]
        raw = None
        if body is not None:
            raw = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        try:
            connection.request("POST" if body is not None else "GET", path, body=raw, headers=headers)
            return connection, connection.getresponse()
        except BaseException:
            connection.close()
            raise

    def json(self, path, body=None, auth=True, expected=200, timeout=None):
        connection, response = self.open(path, body, auth, timeout)
        try:
            raw = response.read(4194305)
            if len(raw) > 4194304:
                raise RuntimeError("Probe response exceeds 4 MiB")
            if response.status != expected:
                raise RuntimeError(f"{path}: HTTP {response.status}, expected {expected}")
            return json.loads(raw)
        finally:
            connection.close()

    def health(self):
        data = self.json("/healthz", auth=False, timeout=5)
        if data.get("service") != "vcf-ai-openai-bridge" or data.get("version") != "1.0.0-rc1":
            raise RuntimeError("Unexpected service/version listening on the bridge port")
        return data

    def models(self):
        payload = self.json(BASE + "/models")
        models = payload.get("data")
        if not isinstance(models, list) or not models:
            raise RuntimeError("Bridge /models returned an empty or invalid model list")
        return models

    def chat(self, model):
        body = {"model": model, "messages": [{"role": "user", "content": "Reply with only OK"}],
                "temperature": 0, "max_tokens": 128, "stream": False}
        data = self.json(BASE + "/chat/completions", body)
        message = data["choices"][0]["message"]
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            raise RuntimeError("Chat returned no textual answer; inspect model settings")
        print("PASS: chat returned a non-empty answer")

    def stream(self, model):
        body = {"model": model, "messages": [{"role": "user", "content": "Reply with only OK"}],
                "temperature": 0, "max_tokens": 128, "stream": True}
        connection, response = self.open(BASE + "/chat/completions", body)
        try:
            if response.status != 200 or "text/event-stream" not in response.getheader("Content-Type", ""):
                raise RuntimeError(f"Streaming: expected SSE HTTP 200, received HTTP {response.status}")
            done, content_seen, total = False, False, 0
            while True:
                line = response.readline(65537)
                total += len(line)
                if len(line) > 65536 or total > 4194304:
                    raise RuntimeError("SSE probe response exceeds safety limit")
                if not line:
                    break
                if line.startswith(b"data:"):
                    part = line[5:].strip()
                    if part == b"[DONE]":
                        done = True
                        break
                    item = json.loads(part)
                    if "error" in item:
                        raise RuntimeError("Upstream returned an SSE error")
                    for choice in item.get("choices", []):
                        content_seen = content_seen or bool(choice.get("delta", {}).get("content"))
            if not done or not content_seen:
                raise RuntimeError("SSE incomplete: missing answer or [DONE]")
            print("PASS: SSE returned content and [DONE]")
        finally:
            connection.close()

    def tools(self, model):
        nonce = secrets.token_hex(4)
        tools = [{"type": "function", "function": {"name": "bridge_echo",
            "description": "Echo a test value; has no external side effects.",
            "parameters": {"type": "object", "properties": {"value": {"type": "string"}},
                           "required": ["value"], "additionalProperties": False}}}]
        messages = [{"role": "user", "content": f"Call bridge_echo with value {nonce}. After the tool reply, return only its value."}]
        body = {"model": model, "messages": messages, "tools": tools,
                "tool_choice": {"type": "function", "function": {"name": "bridge_echo"}},
                "temperature": 0, "max_tokens": 256, "stream": False}
        reply = self.json(BASE + "/chat/completions", body)["choices"][0]["message"]
        calls = reply.get("tool_calls") or []
        if len(calls) != 1 or calls[0]["function"]["name"] != "bridge_echo":
            raise RuntimeError("Model did not return the requested tool call")
        arguments = json.loads(calls[0]["function"]["arguments"])
        if arguments.get("value") != nonce:
            raise RuntimeError("Model returned incorrect tool arguments")
        messages.extend([{"role": "assistant", "content": reply.get("content"), "tool_calls": calls},
                         {"role": "tool", "tool_call_id": calls[0]["id"],
                          "content": json.dumps({"value": nonce})}])
        final = self.json(BASE + "/chat/completions", {**body, "messages": messages, "tool_choice": "none"})
        if nonce not in (final["choices"][0]["message"].get("content") or ""):
            raise RuntimeError("Model did not use the tool result in the second turn")
        print("PASS: tool call, JSON arguments and tool-result round trip (simulated echo, not a VCF skill)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument("--container", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--tools", action="store_true")
    args = parser.parse_args()
    try:
        env = dict(os.environ) if args.container else read_env(ROOT / ".env")
        probe = Probe(env, container=args.container)
        probe.health()
        if args.health_only:
            return 0
        print("PASS: local HTTPS, certificate, hostname and version")
        probe.json(BASE + "/models", auth=False, expected=401)
        print("PASS: requests without API key are rejected")
        models = probe.models()
        print("PASS: /models:", ", ".join(m["id"] for m in models))
        probe.json("/readyz")
        print("PASS: upstream readiness (no inference)")
        if args.chat or args.stream or args.tools:
            model = args.model or env.get("SMOKE_MODEL", "")
            if not model and len(models) == 1:
                model = models[0]["id"]
            if model not in {m["id"] for m in models}:
                raise RuntimeError("Choose an exposed model with --model; no inference was started")
            if args.chat:
                probe.chat(model)
            if args.stream:
                probe.stream(model)
            if args.tools:
                probe.tools(model)
        print("SMOKE OK")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError, http.client.HTTPException) as exc:
        # Application errors are controlled strings; network exceptions can include private addresses.
        detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(f"FAIL: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
