"""Restricted OpenAI HTTP bridge. Model discovery is the only response adaptation."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hmac
import json
import logging
import time
import uuid

import anyio
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException

from . import __version__
from .config import Settings

log = logging.getLogger("bridge.audit")
PREFIXES = ("/v1", "/api/v1/compatibility/openai/v1")


def emit(event, **fields):
    log.info(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields},
                        ensure_ascii=True, separators=(",", ":")))


class BridgeError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class Capacity:
    def __init__(self, maximum):
        self.maximum, self.active = maximum, 0
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            if self.active >= self.maximum:
                raise BridgeError(503, "bridge_busy", "Bridge capacity reached; try later")
            self.active += 1

    async def release(self):
        async with self.lock:
            self.active -= 1


async def close_and_release(response, capacity):
    # Close sockets even if the downstream disconnects/cancels during streaming.
    with anyio.CancelScope(shield=True):
        try:
            if response is not None:
                await response.aclose()
        finally:
            await capacity.release()


class ClosingStream(StreamingResponse):
    def __init__(self, *args, upstream, capacity, **kwargs):
        super().__init__(*args, **kwargs)
        self.upstream, self.capacity = upstream, capacity

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await close_and_release(self.upstream, self.capacity)


class AuditMiddleware:
    """No bodies, arguments, model IDs, URLs, query strings, IPs or auth headers."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        start = time.monotonic()
        rid = uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["audit"] = {"request_id": rid, "operation": "unmatched"}
        status, sent_bytes = 500, 0

        async def wrapped(message):
            nonlocal status, sent_bytes
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.extend([(b"x-request-id", rid.encode()), (b"cache-control", b"no-store"),
                                (b"x-content-type-options", b"nosniff")])
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body":
                sent_bytes += len(message.get("body", b""))
            await send(message)
        try:
            await self.app(scope, receive, wrapped)
        finally:
            audit = state["audit"]
            if audit["operation"] != "health":
                emit("request_complete", **audit, http_status=status,
                     duration_ms=round((time.monotonic() - start) * 1000, 1), response_bytes=sent_bytes)


async def read_limited(response, limit):
    parts, size = [], 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise BridgeError(502, "upstream_response_too_large", "Upstream response exceeds configured limit")
        parts.append(chunk)
    return b"".join(parts)


def parse_json(raw):
    def invalid_constant(_):
        raise ValueError("non-finite JSON")
    try:
        return json.loads(raw, parse_constant=invalid_constant)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise BridgeError(502, "invalid_upstream_json", "Upstream returned invalid JSON") from None


def transform_model(model, config):
    if config.discovery_mode == "passthrough":
        return dict(model)
    result = {"id": model["id"], "object": "model",
              "created": model.get("created") if type(model.get("created")) is int else 0,
              "owned_by": config.model_owner_override or str(model.get("owned_by") or ""),
              "model_type": config.model_type, "model_engine": config.model_engine}
    # Legacy prototype field, not a live health assertion. Empty value omits it.
    if config.model_status:
        result["status"] = config.model_status
    return result


async def upstream_send(client, config, method, path, rid, body=None):
    try:
        return await client.send(client.build_request(method, config.upstream_base_url + path,
                                headers=config.upstream_headers(rid), content=body), stream=True)
    except httpx.TimeoutException:
        raise BridgeError(504, "upstream_timeout", "Upstream request timed out") from None
    except httpx.RequestError:
        raise BridgeError(502, "upstream_connection_error", "Unable to reach upstream") from None


def check_status(response):
    if 200 <= response.status_code < 300:
        return
    if 300 <= response.status_code < 400:
        raise BridgeError(502, "upstream_redirect_blocked", "Upstream redirects are not followed")
    # Keep the upstream HTTP status; never leak its body/headers/URL/credentials.
    raise BridgeError(response.status_code, "upstream_error", "Upstream rejected the request; check provider logs")


async def fetch_models(client, config, rid):
    response = await upstream_send(client, config, "GET", "/models", rid)
    try:
        check_status(response)
        payload = parse_json(await read_limited(response, min(config.max_response_bytes, 4194304)))
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise BridgeError(502, "invalid_model_list", "Upstream /models must contain data[]")
        valid = []
        for model in payload["data"]:
            if not isinstance(model, dict) or not isinstance(model.get("id"), str) or not model["id"]:
                raise BridgeError(502, "invalid_model_list", "Upstream contains an invalid model entry")
            if not config.expose_models or model["id"] in config.expose_models:
                valid.append(transform_model(model, config))
        return valid
    except httpx.TimeoutException:
        raise BridgeError(504, "upstream_timeout", "Upstream response timed out") from None
    except httpx.RequestError:
        raise BridgeError(502, "upstream_read_error", "Unable to read upstream response") from None
    finally:
        with anyio.CancelScope(shield=True):
            await response.aclose()


class SSEInspector:
    """Best-effort, bounded metadata inspection; forwarded bytes are never modified."""
    def __init__(self):
        self.buffer = b""
        self.tool_indexes = set()
        self.done = False
        self.disabled = False

    def feed(self, chunk):
        if self.disabled:
            return
        self.buffer += chunk
        if len(self.buffer) > 65536:
            self.buffer = b""
            self.disabled = True
            return
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                self.done = True
                continue
            try:
                obj = json.loads(data)
                for choice in obj.get("choices", []):
                    for tool in choice.get("delta", {}).get("tool_calls", []) or []:
                        index = (choice.get("index", 0), tool.get("index", 0))
                        if len(self.tool_indexes) < 4096:
                            self.tool_indexes.add(index)
            except (ValueError, TypeError, AttributeError):
                pass


def create_app(config=None, transport=None):
    @asynccontextmanager
    async def lifespan(app):
        settings = config or Settings.from_env()
        app.state.settings = settings
        app.state.capacity = Capacity(settings.max_inflight)
        timeout = httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout,
                                pool=settings.connect_timeout)
        async with httpx.AsyncClient(verify=settings.tls_context(), timeout=timeout,
                                     trust_env=settings.upstream_trust_env, follow_redirects=False,
                                     limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
                                     transport=transport) as client:
            app.state.client = client
            emit("service_started", version=__version__, discovery_mode=settings.discovery_mode,
                 tls_verified=bool(settings.upstream_verify_tls or settings.upstream_ca_bundle))
            yield
            emit("service_stopped")

    app = FastAPI(title="VCF AI OpenAI Bridge", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    app.add_middleware(AuditMiddleware)

    @app.exception_handler(BridgeError)
    async def bridge_error(request, exc):
        request.state.audit["error_code"] = exc.code
        return JSONResponse({"error": {"message": exc.message, "type": "bridge_error", "code": exc.code}},
                            status_code=exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"error": {"message": "Route or method not supported", "code": "unsupported_route"}},
                            status_code=exc.status_code)

    def authorize(request, operation):
        request.state.audit["operation"] = operation
        settings = app.state.settings
        raw = request.headers.get("authorization", "")
        # One explicit credential. Other credential headers are supported for API clients.
        candidate = raw[7:].strip() if raw.lower().startswith("bearer ") else ""
        candidate = candidate or request.headers.get("x-api-key", "") or request.headers.get("api-key", "")
        if not hmac.compare_digest(candidate.encode(), settings.public_api_key.encode()):
            raise BridgeError(401, "invalid_api_key", "Invalid API key")
        if request.url.query:
            raise BridgeError(400, "query_not_supported", "Query parameters are not supported")
        return settings

    @app.get("/health")
    @app.get("/healthz")
    async def health(request: Request):
        request.state.audit["operation"] = "health"
        return {"status": "ok", "service": "vcf-ai-openai-bridge", "version": __version__}

    @app.get("/readyz")
    async def ready(request: Request):
        settings = authorize(request, "ready")
        await app.state.capacity.acquire()
        try:
            models = await fetch_models(app.state.client, settings, request.state.audit["request_id"])
            if not models:
                raise BridgeError(503, "no_models", "No model is exposed by the bridge")
            return {"status": "ready", "model_count": len(models)}
        finally:
            await close_and_release(None, app.state.capacity)

    async def models(request: Request):
        settings = authorize(request, "models")
        await app.state.capacity.acquire()
        try:
            data = await fetch_models(app.state.client, settings, request.state.audit["request_id"])
            request.state.audit["model_count"] = len(data)
            return {"object": "list", "data": data}
        finally:
            await close_and_release(None, app.state.capacity)

    async def model_detail(model_id: str, request: Request):
        settings = authorize(request, "model_detail")
        await app.state.capacity.acquire()
        try:
            data = await fetch_models(app.state.client, settings, request.state.audit["request_id"])
            for model in data:
                if model["id"] == model_id:
                    return model
            raise BridgeError(404, "model_not_found", "Model not found")
        finally:
            await close_and_release(None, app.state.capacity)

    async def chat(request: Request):
        settings = authorize(request, "chat_completions")
        audit = request.state.audit
        if request.headers.get("content-type", "").split(";")[0].lower().strip() != "application/json":
            raise BridgeError(415, "json_required", "Content-Type must be application/json")
        if request.headers.get("content-encoding", "identity").lower() != "identity":
            raise BridgeError(415, "compressed_request_not_supported", "Compressed request bodies are not supported")
        await app.state.capacity.acquire()
        upstream = None
        streaming_owns_cleanup = False
        try:
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > settings.max_body_bytes:
                    raise BridgeError(413, "request_too_large", "Request exceeds configured size limit")
                chunks.append(chunk)
            body = b"".join(chunks)
            try:
                payload = parse_json(body)
            except BridgeError:
                raise BridgeError(400, "invalid_request_json", "Request must contain valid JSON") from None
            if (not isinstance(payload, dict) or not isinstance(payload.get("model"), str)
                    or not payload["model"] or not isinstance(payload.get("messages"), list)):
                raise BridgeError(400, "invalid_chat_request", "model and messages[] are required")
            if "stream" in payload and type(payload["stream"]) is not bool:
                raise BridgeError(400, "invalid_stream", "stream must be a boolean")
            if settings.expose_models and payload["model"] not in settings.expose_models:
                raise BridgeError(403, "model_not_allowed", "Requested model is not exposed")
            audit["stream_requested"] = payload.get("stream", False)
            audit["tools_offered"] = len(payload["tools"]) if isinstance(payload.get("tools"), list) else 0
            audit["tool_results_in_history"] = sum(1 for m in payload["messages"]
                                                    if isinstance(m, dict) and m.get("role") == "tool")
            # Send the original bytes, preserving tools/tool_choice/extra model parameters.
            upstream = await upstream_send(app.state.client, settings, "POST", "/chat/completions",
                                           audit["request_id"], body)
            audit["upstream_status"] = upstream.status_code
            check_status(upstream)
            content_type = upstream.headers.get("content-type", "").split(";")[0].lower()
            if content_type == "text/event-stream":
                # Identity encoding requested upstream. Reject compressed SSE instead of corrupting it.
                if upstream.headers.get("content-encoding", "identity").lower() != "identity":
                    raise BridgeError(502, "compressed_sse", "Upstream must support identity-encoded SSE")
                inspector = SSEInspector()

                async def stream_body():
                    try:
                        async for chunk in upstream.aiter_raw():
                            inspector.feed(chunk)
                            yield chunk
                    except httpx.RequestError:
                        audit["error_code"] = "upstream_stream_interrupted"
                        # Headers are already sent; abort rather than manufacture a successful [DONE].
                        raise RuntimeError("Upstream stream interrupted") from None
                    finally:
                        audit["tool_calls_returned"] = len(inspector.tool_indexes)
                        audit["sse_done"] = inspector.done
                        audit["sse_inspection_limited"] = inspector.disabled

                result = ClosingStream(stream_body(), status_code=upstream.status_code,
                                       media_type="text/event-stream", headers={"X-Accel-Buffering": "no"},
                                       upstream=upstream, capacity=app.state.capacity)
                streaming_owns_cleanup = True
                return result
            if content_type != "application/json" and not content_type.endswith("+json"):
                raise BridgeError(502, "unexpected_content_type", "Upstream did not return JSON or SSE")
            data = await read_limited(upstream, settings.max_response_bytes)
            parsed = parse_json(data)
            if not isinstance(parsed, dict):
                raise BridgeError(502, "invalid_upstream_chat", "Upstream chat response must be an object")
            choices = parsed.get("choices", [])
            audit["tool_calls_returned"] = sum(len(c.get("message", {}).get("tool_calls") or [])
                for c in choices if isinstance(c, dict) and isinstance(c.get("message"), dict)) if isinstance(choices, list) else 0
            return Response(data, status_code=upstream.status_code, media_type="application/json")
        except httpx.TimeoutException:
            raise BridgeError(504, "upstream_timeout", "Upstream response timed out") from None
        except httpx.RequestError:
            raise BridgeError(502, "upstream_read_error", "Unable to read upstream response") from None
        finally:
            if not streaming_owns_cleanup:
                await close_and_release(upstream, app.state.capacity)

    for prefix in PREFIXES:
        app.add_api_route(prefix + "/models", models, methods=["GET"])
        app.add_api_route(prefix + "/models/{model_id:path}", model_detail, methods=["GET"])
        app.add_api_route(prefix + "/chat/completions", chat, methods=["POST"])
    return app
