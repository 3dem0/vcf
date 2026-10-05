"""Configuration: no deployment-specific endpoints, models or credentials."""
from dataclasses import dataclass, field
import os
import re
import ssl
from urllib.parse import urlsplit


class ConfigError(ValueError):
    """Messages must name the setting, never its secret value."""


def boolean(env: dict, name: str, default: str) -> bool:
    value = env.get(name, default).strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise ConfigError(f"Invalid boolean: {name}")
    return value in {"true", "1", "yes"}


def integer(env: dict, name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        result = int(env.get(name, str(default)))
    except ValueError:
        raise ConfigError(f"Invalid integer: {name}") from None
    if not minimum <= result <= maximum:
        raise ConfigError(f"Out of range: {name}")
    return result


@dataclass(frozen=True)
class Settings:
    upstream_base_url: str
    public_api_key: str = field(repr=False)
    upstream_api_key: str = field(default="", repr=False)
    upstream_auth_header: str = "Authorization"
    upstream_auth_prefix: str = "Bearer"
    upstream_verify_tls: bool = True
    upstream_ca_bundle: str = ""
    upstream_trust_env: bool = False
    connect_timeout: int = 15
    read_timeout: int = 600
    max_body_bytes: int = 8 * 1024 * 1024
    max_response_bytes: int = 32 * 1024 * 1024
    max_inflight: int = 8
    expose_models: frozenset[str] = frozenset()
    discovery_mode: str = "enriched"
    model_type: str = "COMPLETIONS"
    model_engine: str = "OPENAI"
    model_status: str = "AVAILABLE"
    model_owner_override: str = ""

    @classmethod
    def from_env(cls, env=None):
        env = dict(os.environ if env is None else env)
        url = env.get("UPSTREAM_BASE_URL", "").strip().rstrip("/")
        try:
            parts = urlsplit(url)
            _ = parts.port
        except ValueError:
            raise ConfigError("Invalid UPSTREAM_BASE_URL") from None
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username or parts.password or parts.query or parts.fragment
                or any(c.isspace() for c in url)):
            raise ConfigError("UPSTREAM_BASE_URL requires http(s), no userinfo/query/fragment")
        key = env.get("PUBLIC_API_KEY", "")
        if len(key) < 24 or len(key) > 4096 or any(c.isspace() for c in key):
            raise ConfigError("PUBLIC_API_KEY must contain 24-4096 non-whitespace characters")
        for name in ("PUBLIC_API_KEY", "UPSTREAM_API_KEY", "UPSTREAM_AUTH_PREFIX"):
            if any(ord(c) < 32 or ord(c) > 126 for c in env.get(name, "")):
                raise ConfigError(f"Only printable ASCII is supported: {name}")
        header = env.get("UPSTREAM_AUTH_HEADER", "Authorization").strip()
        if not re.fullmatch(r"[A-Za-z0-9-]+", header) or header.lower() in {
            "host", "content-length", "connection", "transfer-encoding", "cookie"
        }:
            raise ConfigError("Invalid UPSTREAM_AUTH_HEADER")
        mode = env.get("DISCOVERY_MODE", "enriched").strip()
        if mode not in {"enriched", "passthrough"}:
            raise ConfigError("DISCOVERY_MODE must be enriched or passthrough")
        for name, default in (("MODEL_TYPE", "COMPLETIONS"), ("MODEL_ENGINE", "OPENAI")):
            if not re.fullmatch(r"[A-Z0-9_]{1,64}", env.get(name, default)):
                raise ConfigError(f"Invalid {name}")
        return cls(
            upstream_base_url=url, public_api_key=key,
            upstream_api_key=env.get("UPSTREAM_API_KEY", ""),
            upstream_auth_header=header,
            upstream_auth_prefix=env.get("UPSTREAM_AUTH_PREFIX", "Bearer").strip(),
            upstream_verify_tls=boolean(env, "UPSTREAM_VERIFY_TLS", "true"),
            upstream_ca_bundle=env.get("UPSTREAM_CA_BUNDLE", "").strip(),
            upstream_trust_env=boolean(env, "UPSTREAM_TRUST_ENV", "false"),
            connect_timeout=integer(env, "CONNECT_TIMEOUT_SECONDS", 15, 1, 120),
            read_timeout=integer(env, "READ_TIMEOUT_SECONDS", 600, 1, 3600),
            max_body_bytes=integer(env, "MAX_REQUEST_BYTES", 8388608, 1024, 67108864),
            max_response_bytes=integer(env, "MAX_RESPONSE_BYTES", 33554432, 1024, 134217728),
            max_inflight=integer(env, "MAX_INFLIGHT_REQUESTS", 8, 1, 64),
            expose_models=frozenset(x.strip() for x in env.get("EXPOSE_MODELS", "").split(",") if x.strip()),
            discovery_mode=mode,
            model_type=env.get("MODEL_TYPE", "COMPLETIONS"),
            model_engine=env.get("MODEL_ENGINE", "OPENAI"),
            model_status=env.get("MODEL_STATUS", "AVAILABLE"),
            model_owner_override=env.get("MODEL_OWNER_OVERRIDE", ""),
        )

    def tls_context(self):
        if self.upstream_ca_bundle:
            return ssl.create_default_context(cafile=self.upstream_ca_bundle)
        return self.upstream_verify_tls

    def upstream_headers(self, request_id: str) -> dict[str, str]:
        # Deliberate allowlist. Never forward client credentials, cookies or routing headers.
        headers = {"Accept": "application/json, text/event-stream", "Accept-Encoding": "identity",
                   "Content-Type": "application/json", "X-Request-ID": request_id}
        if self.upstream_api_key:
            prefix = self.upstream_auth_prefix
            headers[self.upstream_auth_header] = (prefix + " " if prefix else "") + self.upstream_api_key
        return headers
