import logging
import os
import ssl
import sys
import uvicorn
from .app import create_app
from .config import Settings, ConfigError


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    # These libraries otherwise log full upstream URLs. Bodies are never logged.
    for name in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        settings = Settings.from_env()
        cert = os.getenv("TLS_CERT_FILE", "/certs/cert.pem")
        key = os.getenv("TLS_KEY_FILE", "/certs/key.pem")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ssl.SSLError):
        print("Cannot load TLS certificate/key; check files and permissions", file=sys.stderr)
        return 2
    uvicorn.run(create_app(settings), host="0.0.0.0", port=8443, workers=1,
                ssl_certfile=cert, ssl_keyfile=key, ssl_version=ssl.PROTOCOL_TLS_SERVER,
                access_log=False, proxy_headers=False, server_header=False,
                timeout_keep_alive=5, timeout_graceful_shutdown=25,
                log_config=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
