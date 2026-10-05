"""Run in a one-shot container with no published port, before stopping the old bridge."""
import asyncio
import os
import ssl
import sys
import httpx
from .config import Settings, ConfigError
from .app import fetch_models, BridgeError


async def check():
    settings = Settings.from_env()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(os.getenv("TLS_CERT_FILE", "/certs/cert.pem"),
                            os.getenv("TLS_KEY_FILE", "/certs/key.pem"))
    async with httpx.AsyncClient(verify=settings.tls_context(), follow_redirects=False,
                               trust_env=settings.upstream_trust_env,
                               timeout=httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout)) as client:
        models = await fetch_models(client, settings, "preflight")
    if not models:
        raise ConfigError("No exposed models; review EXPOSE_MODELS and provider permissions")
    print(f"PREFLIGHT OK: certificate/key readable; upstream /models OK; {len(models)} models")


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except ConfigError as exc:
        print(f"PREFLIGHT FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    except BridgeError as exc:
        print(f"PREFLIGHT FAILED: HTTP {exc.status} {exc.code}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"PREFLIGHT FAILED: {type(exc).__name__}; check configuration/certificates", file=sys.stderr)
        sys.exit(1)
