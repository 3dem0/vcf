"""Local deployment controller. Never runs broad compose-down/prune commands."""
import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from urllib.parse import urlsplit

from probe import Probe, read_env

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local" / "migration.json"
PROJECT = "vcf-ai-openai-bridge"


def run(args, capture=False, check=True, env=None):
    return subprocess.run([str(x) for x in args], check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None, env=env)


def save_private(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(data)
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def save_state(state):
    save_private(STATE, json.dumps(state, indent=2) + "\n")


def get_state():
    if not STATE.is_file():
        raise RuntimeError("No migration state; use migrate first")
    return json.loads(STATE.read_text())


def docker_inspect(name):
    result = run(["docker", "inspect", "--type", "container", name], capture=True)
    return json.loads(result.stdout)[0]


def compose(*args, check=True, capture=False):
    # Avoid inherited COMPOSE_FILE/PROJECT or old exported .env values selecting another stack.
    env = dict(os.environ)
    for name in read_env(ROOT / ".env.example"):
        env.pop(name, None)
    for name in list(env):
        if name.startswith("COMPOSE_"):
            env.pop(name)
    # Only non-secret deployment values participate in Compose interpolation.
    # Passing /dev/null prevents the CLI from parsing the raw credential file as shell-style .env.
    values = read_env(ROOT / ".env")
    for name in ("PUBLIC_BIND_ADDRESS", "PUBLIC_PORT", "CONTAINER_UID", "CONTAINER_GID"):
        if name in values:
            env[name] = values[name]
    return run(["docker", "compose", "--project-name", PROJECT,
                "--project-directory", ROOT, "--env-file", os.devnull,
                "-f", ROOT / "compose.yaml", *args], check=check, capture=capture, env=env)


def prerequisites():
    if os.geteuid() == 0:
        raise RuntimeError("Run as your normal Docker-enabled user, not sudo/root")
    for command in ("docker", "openssl"):
        if not shutil.which(command):
            raise RuntimeError(f"Missing required command: {command}")
    raw = run(["docker", "compose", "version", "--short"], capture=True).stdout
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
    if not match or tuple(map(int, match.groups())) < (2, 30, 0):
        raise RuntimeError("Docker Compose >= 2.30.0 is required (raw env_file)")
    run(["docker", "info", "--format", "{{.ServerVersion}}"], capture=True)


def write_env(values):
    template = (ROOT / ".env.example").read_text()
    result = []
    for line in template.splitlines():
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=", 1)[0]
            value = str(values.get(key, line.split("=", 1)[1]))
            if "\n" in value or "\r" in value:
                raise RuntimeError(f"Multiline values are not supported: {key}")
            line = key + "=" + value
        result.append(line)
    save_private(ROOT / ".env", "\n".join(result) + "\n")


def validate_host(host):
    if (not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host)
            or "." not in host or ".." in host or host.endswith(".invalid")):
        raise RuntimeError("Use a real FQDN, without a scheme, port or wildcard")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise RuntimeError("PUBLIC_HOSTNAME must be a DNS name, not an IP address")


def certificate_hostname(cert):
    result = run(["openssl", "x509", "-in", cert, "-noout", "-ext", "subjectAltName"], capture=True)
    names = re.findall(r"DNS:([^,\s]+)", result.stdout)
    names = [n for n in names if "*" not in n]
    if not names:
        raise RuntimeError("Cannot infer a hostname from certificate SAN; pass --public-hostname")
    return validate_host(names[0])


def migrate(args):
    prerequisites()
    if (ROOT / ".env").exists() or STATE.exists():
        raise RuntimeError("Migration already initialized; .env/state will not be overwritten. Use deploy or rollback")
    old_dir = Path(args.old_dir).expanduser().resolve()
    if old_dir == ROOT or ROOT.is_relative_to(old_dir):
        raise RuntimeError("New project must not be inside the old project directory")
    if not (old_dir / ".env").is_file():
        raise RuntimeError("The old directory does not contain .env")
    info = docker_inspect(args.old_container)
    if not info["State"]["Running"]:
        raise RuntimeError("The old container must be running for this migration")
    bound = info.get("HostConfig", {}).get("PortBindings", {})
    ports = {p.get("HostPort") for entries in bound.values() if entries for p in entries}
    if str(args.port) not in ports:
        raise RuntimeError("Requested port is not published by the selected old container; refusing to stop it")
    old_env = dict(x.split("=", 1) for x in info["Config"].get("Env", []) if "=" in x)
    required = ("UPSTREAM_BASE_URL", "SHIM_API_KEY")
    if any(not old_env.get(key) for key in required):
        raise RuntimeError("Old container must expose UPSTREAM_BASE_URL and SHIM_API_KEY")
    if old_env.get("UPSTREAM_CA_BUNDLE"):
        raise RuntimeError("Old custom CA needs an explicit migration; no services were stopped")
    old_cert_dir = old_dir / "certs"
    mounted_certs = [m.get("Source") for m in info.get("Mounts", []) if m.get("Destination") == "/certs"]
    if len(mounted_certs) != 1 or Path(mounted_certs[0]).resolve() != old_cert_dir.resolve():
        raise RuntimeError("--old-dir does not match the selected container's /certs mount")
    for filename in ("cert.pem", "key.pem"):
        if not (old_cert_dir / filename).is_file():
            raise RuntimeError(f"Missing old certificate file: {filename}")
    host = validate_host(args.public_hostname) if args.public_hostname else certificate_hostname(old_cert_dir / "cert.pem")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = ROOT / ".local" / "backups" / stamp
    backup_dir.mkdir(parents=True, mode=0o700)
    os.chmod(ROOT / ".local", 0o700)
    archive = backup_dir / "previous-bridge.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(old_dir, arcname=old_dir.name)
    os.chmod(archive, 0o600)
    (ROOT / "certs").mkdir(exist_ok=True)
    (ROOT / "ca").mkdir(exist_ok=True)
    for filename in ("cert.pem", "key.pem"):
        target = ROOT / "certs" / filename
        shutil.copyfile(old_cert_dir / filename, target)
        os.chmod(target, 0o600 if filename == "key.pem" else 0o644)
    values = read_env(ROOT / ".env.example")
    for name in values:
        if name in old_env:
            values[name] = old_env[name]
    values.update(PUBLIC_API_KEY=old_env["SHIM_API_KEY"], PUBLIC_HOSTNAME=host,
                  PUBLIC_PORT=str(args.port), CONTAINER_UID=str(os.getuid()), CONTAINER_GID=str(os.getgid()))
    # Import the effective container values, not a stale shell-exported .env.
    values["UPSTREAM_API_KEY"] = old_env.get("UPSTREAM_API_KEY", "")
    values["DISCOVERY_MODE"] = "enriched"
    values["MODEL_STATUS"] = "AVAILABLE"
    write_env(values)
    state = {"phase": "prepared", "old_id": info["Id"], "old_name": info["Name"].lstrip("/"),
             "old_dir": str(old_dir), "old_image": info["Image"], "old_was_running": True,
             "old_restart_policy": info["HostConfig"]["RestartPolicy"], "backup": str(archive)}
    save_state(state)
    print("MIGRATION PREPARED. No container has been stopped.")
    print("Effective upstream credentials and existing public key imported; keys not displayed.")
    print("Certificate/key copied; originals unchanged. Private backup:", archive)
    if values.get("UPSTREAM_VERIFY_TLS", "true").lower() in {"false", "0", "no"}:
        print("WARNING: inherited UPSTREAM_VERIFY_TLS=false; configure trust before publishing/deploying permanently.")
    print("Next: ./bridgectl deploy")


def restore_old(state):
    compose("stop", "--timeout", "30", "bridge", check=False)
    policy = state["old_restart_policy"]
    value = policy.get("Name") or "no"
    if value == "on-failure" and policy.get("MaximumRetryCount", 0):
        value += ":" + str(policy["MaximumRetryCount"])
    run(["docker", "update", "--restart", value, state["old_id"]], capture=True)
    if state["old_was_running"]:
        run(["docker", "start", state["old_id"]], capture=True)
        if not docker_inspect(state["old_id"])["State"]["Running"]:
            raise RuntimeError("Old container did not restart; inspect its Docker logs")
    state["phase"] = "rolled-back"
    save_state(state)
    print("ROLLBACK OK: candidate stopped; original container and restart policy restored.")


def deploy():
    prerequisites()
    state = get_state()
    if state["phase"] == "candidate-active":
        raise RuntimeError("Candidate is already active. Use restart/reconfigure, or rollback before another deploy")
    info = docker_inspect(state["old_id"])
    if not info["State"]["Running"]:
        raise RuntimeError("Old container is not running. Run rollback before deploying")
    print("1/4 Building image and running unit tests. Existing 8443 service remains online.", flush=True)
    compose("build", "bridge")
    print("2/4 Preflight: one-shot container WITHOUT published ports; TLS files and upstream /models.", flush=True)
    compose("run", "--rm", "--no-deps", "-T", "bridge", "python", "-m", "bridge.preflight")
    print("3/4 Cutover on the same port. Only the selected old bridge is stopped.", flush=True)
    state["phase"] = "cutover-pending"
    save_state(state)
    try:
        # Prevent the retained rollback container from competing for the port after a reboot.
        run(["docker", "update", "--restart", "no", state["old_id"]], capture=True)
        run(["docker", "stop", "-t", "30", state["old_id"]], capture=True)
        compose("up", "-d", "--no-build", "--no-deps", "bridge")
        env = read_env(ROOT / ".env")
        probe = Probe(env, ROOT)
        deadline = time.monotonic() + 90
        last_type = "startup"
        while time.monotonic() < deadline:
            try:
                probe.health()
                break
            except Exception as exc:
                last_type = type(exc).__name__
                time.sleep(2)
        else:
            raise RuntimeError(f"Candidate did not pass HTTPS health probe ({last_type})")
        print("4/4 Checking authentication and real model discovery through host port.", flush=True)
        probe.json("/api/v1/compatibility/openai/v1/models", auth=False, expected=401)
        models = probe.models()
        state["phase"] = "candidate-active"
        save_state(state)
        print(f"DEPLOY OK: candidate on port {env['PUBLIC_PORT']}; {len(models)} models. No inference was requested.")
        print("Keep the existing VCF endpoint and API key. Next: ./bridgectl smoke")
    except BaseException:
        print("Cutover failed/interrupted. Restoring previous bridge...", file=sys.stderr, flush=True)
        try:
            restore_old(state)
        except Exception:
            print("Automatic rollback failed. Run ./bridgectl rollback; do not delete the old container.", file=sys.stderr)
        raise


def initialize(args):
    prerequisites()
    if (ROOT / ".env").exists():
        raise RuntimeError(".env exists; refusing to overwrite it")
    from getpass import getpass
    host = validate_host(args.public_hostname)
    url = input("Real provider base URL (usually includes /v1): ").strip()
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.query or parts.fragment:
        raise RuntimeError("Invalid provider URL")
    upstream_key = getpass("Provider API key (blank for an unauthenticated local server): ")
    public_key = getpass("Public bridge key (blank to generate a random key): ") or secrets.token_hex(32)
    values = read_env(ROOT / ".env.example")
    values.update(PUBLIC_HOSTNAME=host, PUBLIC_API_KEY=public_key, UPSTREAM_BASE_URL=url,
                  UPSTREAM_API_KEY=upstream_key, PUBLIC_PORT=str(args.port),
                  CONTAINER_UID=str(os.getuid()), CONTAINER_GID=str(os.getgid()))
    write_env(values)
    for folder in ("certs", "ca"):
        (ROOT / folder).mkdir(exist_ok=True)
    cert, key = ROOT / "certs/cert.pem", ROOT / "certs/key.pem"
    if cert.exists() or key.exists():
        if not (cert.is_file() and key.is_file()):
            raise RuntimeError("Both cert.pem and key.pem must exist; no certificate was overwritten")
        print("Existing certificate files preserved.")
    else:
        run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:3072", "-sha256", "-days", "365",
             "-keyout", key, "-out", cert, "-subj", f"/CN={host}",
             "-addext", f"subjectAltName=DNS:{host}", "-addext", "basicConstraints=critical,CA:FALSE",
             "-addext", "keyUsage=critical,digitalSignature,keyEncipherment",
             "-addext", "extendedKeyUsage=serverAuth"], capture=True)
    os.chmod(key, 0o600)
    print("Initialized .env and TLS. Replace self-signed TLS with an organizational certificate for long-term use.")
    print("For a NEW installation only: ./bridgectl up")


def info():
    env = read_env(ROOT / ".env")
    host, port = env["PUBLIC_HOSTNAME"], env["PUBLIC_PORT"]
    print("Public key: configured (not displayed)")
    print("Upstream key:", "configured" if env.get("UPSTREAM_API_KEY") else "not configured")
    print(f"VCF API Endpoint: https://{host}:{port}/api/v1/compatibility/openai")
    print("The VCF endpoint intentionally has NO trailing /v1.")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    migration = sub.add_parser("migrate", help="Import the working prototype; no downtime")
    migration.add_argument("--old-dir", required=True)
    migration.add_argument("--old-container", required=True)
    migration.add_argument("--public-hostname")
    migration.add_argument("--port", type=int, default=8443)
    init = sub.add_parser("init", help="NEW deployment only; interactive credentials")
    init.add_argument("--public-hostname", required=True)
    init.add_argument("--port", type=int, default=8443)
    for name in ("deploy", "rollback", "status", "info", "build", "restart", "reconfigure", "up"):
        sub.add_parser(name)
    logs = sub.add_parser("logs")
    logs.add_argument("--follow", action="store_true")
    logs.add_argument("--since", default="5m")
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--model")
    for name in ("chat", "stream", "tools", "health-only"):
        smoke.add_argument("--" + name, action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "migrate":
            migrate(args)
        elif args.command == "init":
            initialize(args)
        elif args.command == "deploy":
            deploy()
        elif args.command == "rollback":
            restore_old(get_state())
        elif args.command == "build":
            prerequisites()
            compose("build", "bridge")
        elif args.command == "up":
            prerequisites()
            if STATE.exists():
                raise RuntimeError("Migration detected: use deploy instead of up")
            compose("build", "bridge")
            compose("run", "--rm", "--no-deps", "-T", "bridge", "python", "-m", "bridge.preflight")
            compose("up", "-d", "--no-build", "--no-deps", "bridge")
        elif args.command == "status":
            compose("ps", "--all")
            if STATE.exists():
                state = get_state()
                print("Migration phase:", state["phase"])
                print("Old bridge running:", docker_inspect(state["old_id"])["State"]["Running"])
        elif args.command == "info":
            info()
        elif args.command in {"restart", "reconfigure"}:
            if STATE.exists() and get_state()["phase"] != "candidate-active":
                raise RuntimeError("Candidate is not active; use deploy")
            if args.command == "restart":
                compose("restart", "--timeout", "30", "bridge")
            else:
                compose("run", "--rm", "--no-deps", "-T", "bridge", "python", "-m", "bridge.preflight")
                compose("up", "-d", "--no-build", "--no-deps", "--force-recreate", "bridge")
        elif args.command == "logs":
            opts = ["logs", "--tail", "100", "--since", args.since]
            if args.follow:
                opts.append("--follow")
            compose(*opts, "bridge")
        elif args.command == "smoke":
            opts = [sys.executable, ROOT / "tools/probe.py"]
            if args.model:
                opts += ["--model", args.model]
            for name in ("chat", "stream", "tools", "health_only"):
                if getattr(args, name):
                    opts.append("--" + name.replace("_", "-"))
            return run(opts, check=False).returncode
        return 0
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError:
        print("ERROR: Docker/OpenSSL command failed. Review the output above; no credentials are printed.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}; check permissions, Docker and .env", file=sys.stderr)
        return 1


if __name__ == "__main__":
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupted)
    sys.exit(main())
