import gzip
import json
import logging
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from bridge.app import create_app, Capacity, SSEInspector
from bridge.config import Settings, ConfigError

PUBLIC = "test-public-" + "a" * 40
UPSTREAM = "test-upstream-" + "b" * 40
AUTH = {"Authorization": "Bearer " + PUBLIC}
BASE = "/api/v1/compatibility/openai/v1"
MODEL = {"id": "chat-model", "object": "model", "created": 123, "owned_by": "test"}
PAYLOAD = {"model": "chat-model", "messages": [{"role": "user", "content": "secret-prompt"}]}


def settings(**changes):
    return replace(Settings.from_env({"UPSTREAM_BASE_URL": "https://provider.example.invalid/v1",
                                      "PUBLIC_API_KEY": PUBLIC, "UPSTREAM_API_KEY": UPSTREAM}), **changes)


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks, self.closed = chunks, False
    async def __aiter__(self):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk
    async def aclose(self):
        self.closed = True


def client(handler, config=None):
    return TestClient(create_app(config or settings(), httpx.MockTransport(handler)))


def json_response(obj, status=200):
    return httpx.Response(status, json=obj)


@pytest.mark.parametrize("path", ["/v1/models", BASE + "/models"])
def test_model_paths_and_credentials(path):
    seen = []
    def upstream(request):
        seen.append(request)
        return json_response({"object": "list", "data": [MODEL]})
    with client(upstream) as test:
        result = test.get(path, headers={**AUTH, "Cookie": "private", "X-API-Key": "other",
                                         "X-Internal-Routing": "never-forward"})
        assert result.status_code == 200
        assert result.json()["data"][0] == {**MODEL, "model_type": "COMPLETIONS", "model_engine": "OPENAI", "status": "AVAILABLE"}
        assert seen[0].url.path == "/v1/models"
        assert seen[0].headers["authorization"] == "Bearer " + UPSTREAM
        assert "cookie" not in seen[0].headers
        assert "x-api-key" not in seen[0].headers
        assert "x-internal-routing" not in seen[0].headers
        assert result.headers["cache-control"] == "no-store"
        assert result.headers["x-request-id"]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"X-API-Key": "wrong"}])
def test_unauthorized_never_touches_upstream(headers):
    def forbidden(_):
        pytest.fail("Unauthorized request reached upstream")
    with client(forbidden) as test:
        assert test.get(BASE + "/models", headers=headers).status_code == 401
        assert test.post(BASE + "/chat/completions", json=PAYLOAD, headers=headers).status_code == 401


@pytest.mark.parametrize("name", ["X-API-Key", "api-key"])
def test_alternative_public_auth(name):
    with client(lambda _: json_response({"data": [MODEL]})) as test:
        assert test.get("/v1/models", headers={name: PUBLIC}).status_code == 200


def test_health_does_not_call_upstream():
    with client(lambda _: pytest.fail("Health must be local")) as test:
        response = test.get("/healthz")
        assert response.json()["version"] == "1.0.0-rc1"
        assert response.json()["status"] == "ok"
        assert test.get("/readyz").status_code == 401


def test_model_allowlist_applies_to_discovery_and_inference():
    def upstream(request):
        assert request.method == "GET"
        return json_response({"data": [MODEL, {**MODEL, "id": "not-allowed"}]})
    with client(upstream, settings(expose_models=frozenset({"chat-model"}))) as test:
        assert len(test.get("/v1/models", headers=AUTH).json()["data"]) == 1
        assert test.get("/v1/models/not-allowed", headers=AUTH).status_code == 404
        assert test.post("/v1/chat/completions", json={**PAYLOAD, "model": "not-allowed"}, headers=AUTH).status_code == 403


def test_slash_in_model_id_does_not_change_upstream_path():
    def upstream(request):
        assert request.url.path == "/v1/models"
        return json_response({"data": [{**MODEL, "id": "org/model"}]})
    with client(upstream) as test:
        assert test.get("/v1/models/org/model", headers=AUTH).json()["id"] == "org/model"


def test_passthrough_discovery_and_optional_status():
    with client(lambda _: json_response({"data": [MODEL]}), settings(discovery_mode="passthrough")) as test:
        assert test.get("/v1/models", headers=AUTH).json()["data"] == [MODEL]
    with client(lambda _: json_response({"data": [MODEL]}), settings(model_status="")) as test:
        assert "status" not in test.get("/v1/models", headers=AUTH).json()["data"][0]


@pytest.mark.parametrize("payload", [[], {"data": None}, {"data": [None]}, {"data": [{"id": 2}]}])
def test_invalid_upstream_models(payload):
    with client(lambda _: json_response(payload)) as test:
        assert test.get("/v1/models", headers=AUTH).status_code == 502


def test_no_models_readiness_is_not_ready():
    with client(lambda _: json_response({"data": []})) as test:
        assert test.get("/v1/models", headers=AUTH).json()["data"] == []
        assert test.get("/readyz", headers=AUTH).status_code == 503


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_upstream_error_status_preserved_body_redacted(status, caplog):
    with caplog.at_level(logging.INFO, logger="bridge.audit"):
        with client(lambda _: httpx.Response(status, text=UPSTREAM + " secret-internal-host")) as test:
            response = test.post("/v1/chat/completions", headers=AUTH, json=PAYLOAD)
            assert response.status_code == status
            assert response.json()["error"]["code"] == "upstream_error"
            assert UPSTREAM not in response.text + caplog.text
            assert "secret-internal-host" not in response.text + caplog.text
            assert PUBLIC not in caplog.text
            assert "secret-prompt" not in caplog.text


def test_redirect_not_followed():
    requests = []
    def upstream(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example.invalid/steal"})
    with client(upstream) as test:
        assert test.get("/v1/models", headers=AUTH).status_code == 502
        assert len(requests) == 1


@pytest.mark.parametrize("error,status", [(httpx.ConnectError("private-url"), 502), (httpx.ReadTimeout("private-url"), 504)])
def test_upstream_connection_errors(error, status):
    def upstream(_):
        raise error
    with client(upstream) as test:
        response = test.get("/v1/models", headers=AUTH)
        assert response.status_code == status
        assert "private-url" not in response.text


def test_raw_chat_body_and_tools_preserved(caplog):
    payload = {**PAYLOAD, "tools": [{"type": "function", "function": {"name": "test-tool"}}],
               "tool_choice": "auto", "stream": False, "custom_field": {"keep": "me"}}
    raw = json.dumps(payload, indent=3).encode()
    answer = {"choices": [{"message": {"role": "assistant", "content": None,
                       "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "test-tool", "arguments": "{}"}}]}}]}
    raw_answer = json.dumps(answer, indent=4).encode()
    def upstream(request):
        assert request.content == raw
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, content=raw_answer, headers={"Content-Type": "application/json", "Set-Cookie": "secret-cookie"})
    with caplog.at_level(logging.INFO, logger="bridge.audit"):
        with client(upstream) as test:
            response = test.post(BASE + "/chat/completions", content=raw, headers={**AUTH, "Content-Type": "application/json"})
            assert response.content == raw_answer
            assert "set-cookie" not in response.headers
            assert '"tool_calls_returned":1' in caplog.text
            assert '"tools_offered":1' in caplog.text
            assert "secret-prompt" not in caplog.text
            assert "test-tool" not in caplog.text


def test_gzip_json_decompressed_consistently():
    body = b'{"choices":[{"message":{"role":"assistant","content":"OK"}}]}'
    with client(lambda _: httpx.Response(200, content=gzip.compress(body),
                                       headers={"Content-Type": "application/json", "Content-Encoding": "gzip"})) as test:
        response = test.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)
        assert response.content == body
        assert "content-encoding" not in response.headers


def test_sse_bytes_preserved_closed_and_tool_counts(caplog):
    pieces = [b'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"name":"echo"}}]}}]}\n\n',
              b'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{}"}}]}}]}\n\n',
              b'data: [DONE]\n\n']
    stream = Chunks(pieces)
    with caplog.at_level(logging.INFO, logger="bridge.audit"):
        with client(lambda _: httpx.Response(200, stream=stream, headers={"Content-Type": "text/event-stream"})) as test:
            response = test.post("/v1/chat/completions", json={**PAYLOAD, "stream": True}, headers=AUTH)
            assert response.content == b"".join(pieces)
            assert stream.closed
            assert test.app.state.capacity.active == 0
            assert '"tool_calls_returned":1' in caplog.text
            assert '"sse_done":true' in caplog.text


def test_stream_failure_releases_socket_and_capacity():
    stream = Chunks([b"data: {}\n\n", httpx.ReadError("private-detail")])
    with client(lambda _: httpx.Response(200, stream=stream, headers={"Content-Type": "text/event-stream"})) as test:
        with pytest.raises(Exception):
            test.post("/v1/chat/completions", json={**PAYLOAD, "stream": True}, headers=AUTH)
        assert stream.closed
        assert test.app.state.capacity.active == 0


def test_bounded_sse_inspection():
    inspector = SSEInspector()
    inspector.feed(b"x" * 70000)
    assert inspector.disabled and inspector.buffer == b""


@pytest.mark.parametrize("method,path", [("DELETE", "/v1/models/chat-model"), ("POST", "/v1/admin"),
    ("POST", "/api/v1/endpoints"), ("GET", "/v1/v1/models"), ("GET", "/docs"), ("GET", "/metrics")])
def test_unsupported_routes_never_proxied(method, path):
    with client(lambda _: pytest.fail("Unsupported operation was proxied")) as test:
        assert test.request(method, path, headers=AUTH).status_code in {404, 405}


@pytest.mark.parametrize("body", [b"{bad json", b"[]", b'{"model":"x","messages":[],"stream":"yes"}', b'{"messages":[]}'])
def test_invalid_chat_requests(body):
    with client(lambda _: pytest.fail("Bad request was proxied")) as test:
        assert test.post("/v1/chat/completions", content=body, headers={**AUTH, "Content-Type": "application/json"}).status_code == 400
        assert test.app.state.capacity.active == 0


def test_size_limit_and_media_type():
    with client(lambda _: pytest.fail("Oversized request was proxied"), settings(max_body_bytes=1024)) as test:
        assert test.post("/v1/chat/completions", content=b"x" * 2048, headers={**AUTH, "Content-Type": "application/json"}).status_code == 413
        assert test.post("/v1/chat/completions", content="text", headers=AUTH).status_code == 415
        assert test.app.state.capacity.active == 0


def test_no_upstream_key_does_not_leak_public_key():
    def upstream(request):
        assert "authorization" not in request.headers
        return json_response({"data": [MODEL]})
    with client(upstream, settings(upstream_api_key="")) as test:
        assert test.get("/v1/models", headers=AUTH).status_code == 200


def test_custom_upstream_auth_header():
    def upstream(request):
        assert request.headers["x-provider-key"] == UPSTREAM
        assert "authorization" not in request.headers
        return json_response({"data": [MODEL]})
    with client(upstream, settings(upstream_auth_header="X-Provider-Key", upstream_auth_prefix="")) as test:
        assert test.get("/v1/models", headers=AUTH).status_code == 200


def test_query_not_forwarded_or_logged(caplog):
    with caplog.at_level(logging.INFO, logger="bridge.audit"):
        with client(lambda _: pytest.fail("Query was proxied")) as test:
            assert test.get("/v1/models?key=sensitive-query", headers=AUTH).status_code == 400
            assert "sensitive-query" not in caplog.text


@pytest.mark.parametrize("url", ["", "file:///etc/passwd", "https://user:password@host/v1", "https://host/v1?api_key=secret", "https://host/v1#fragment"])
def test_invalid_config_urls(url):
    with pytest.raises(ConfigError):
        Settings.from_env({"UPSTREAM_BASE_URL": url, "PUBLIC_API_KEY": PUBLIC})


def test_config_missing_key_and_repr_redaction():
    with pytest.raises(ConfigError):
        Settings.from_env({"UPSTREAM_BASE_URL": "https://provider.example.invalid/v1"})
    assert PUBLIC not in repr(settings())
    assert UPSTREAM not in repr(settings())


def test_capacity_returns_503_without_forwarding():
    with client(lambda _: pytest.fail("Overload should not reach upstream")) as test:
        test.app.state.capacity.active = test.app.state.capacity.maximum
        assert test.get("/v1/models", headers=AUTH).status_code == 503
        test.app.state.capacity.active = 0
