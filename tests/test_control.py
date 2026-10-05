import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import control
from probe import read_env


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / ".env.example").write_text("PUBLIC_PORT=8443\nPUBLIC_API_KEY=placeholder\nUPSTREAM_BASE_URL=https://example.invalid/v1\n")
    (tmp_path / ".env").write_text("PUBLIC_PORT=8443\nPUBLIC_API_KEY=" + "a" * 40 + "\nPUBLIC_HOSTNAME=bridge.example.invalid\n")
    monkeypatch.setattr(control, "ROOT", tmp_path)
    monkeypatch.setattr(control, "STATE", tmp_path / ".local/migration.json")
    return tmp_path


def test_raw_env_handles_dollar_hash_quotes(tmp_path):
    file = tmp_path / ".env"
    file.write_text("# comment\nKEY=abc$def#ghi\nOTHER=literal'quote\n")
    assert read_env(file) == {"KEY": "abc$def#ghi", "OTHER": "literal'quote"}


def test_env_file_private_and_values_not_evaluated(root):
    control.write_env({"PUBLIC_API_KEY": "abc$SECRET#value", "PUBLIC_PORT": 8443})
    assert read_env(root / ".env")["PUBLIC_API_KEY"] == "abc$SECRET#value"
    assert (root / ".env").stat().st_mode & 0o777 == 0o600


def test_compose_isolated_from_shell_environment(root, monkeypatch):
    monkeypatch.setenv("COMPOSE_FILE", "/production/compose.yaml")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "production")
    monkeypatch.setenv("PUBLIC_PORT", "443")
    calls = []
    monkeypatch.setattr(control, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    control.compose("stop", "bridge")
    args, kwargs = calls[0]
    assert "COMPOSE_FILE" not in kwargs["env"]
    assert "COMPOSE_PROJECT_NAME" not in kwargs["env"]
    assert kwargs["env"]["PUBLIC_PORT"] == "8443"
    assert args[args.index("--env-file") + 1] == "/dev/null"
    assert "--project-name" in args and "vcf-ai-openai-bridge" in args
    assert str(root / "compose.yaml") in [str(a) for a in args]
    assert "/production/compose.yaml" not in [str(a) for a in args]


def state():
    return {"phase": "prepared", "old_id": "old-container-id", "old_name": "previous-bridge",
            "old_restart_policy": {"Name": "unless-stopped", "MaximumRetryCount": 0}, "old_was_running": True}


def test_rollback_only_stops_candidate_and_restores_original(root, monkeypatch):
    calls = []
    monkeypatch.setattr(control, "compose", lambda *args, **kwargs: calls.append(("compose", args)))
    monkeypatch.setattr(control, "run", lambda args, **kwargs: calls.append(("run", args)))
    monkeypatch.setattr(control, "docker_inspect", lambda _: {"State": {"Running": True}})
    control.restore_old(state())
    assert calls[0][1] == ("stop", "--timeout", "30", "bridge")
    assert calls[1][1] == ["docker", "update", "--restart", "unless-stopped", "old-container-id"]
    assert calls[2][1] == ["docker", "start", "old-container-id"]
    assert control.get_state()["phase"] == "rolled-back"
    assert not any("down" in c[1] or "prune" in c[1] for c in calls)


def test_build_failure_does_not_stop_old(root, monkeypatch):
    control.save_state(state())
    monkeypatch.setattr(control, "prerequisites", lambda: None)
    monkeypatch.setattr(control, "docker_inspect", lambda _: {"State": {"Running": True}})
    def fail(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "build")
    monkeypatch.setattr(control, "compose", fail)
    monkeypatch.setattr(control, "run", lambda *_a, **_k: pytest.fail("Old container was modified before successful build"))
    with pytest.raises(subprocess.CalledProcessError):
        control.deploy()
    assert control.get_state()["phase"] == "prepared"


def test_preflight_failure_does_not_stop_old(root, monkeypatch):
    control.save_state(state())
    monkeypatch.setattr(control, "prerequisites", lambda: None)
    monkeypatch.setattr(control, "docker_inspect", lambda _: {"State": {"Running": True}})
    def compose(*args, **_kwargs):
        if args[0] == "run":
            raise subprocess.CalledProcessError(1, "preflight")
    monkeypatch.setattr(control, "compose", compose)
    monkeypatch.setattr(control, "run", lambda *_a, **_k: pytest.fail("Old container modified before successful preflight"))
    with pytest.raises(subprocess.CalledProcessError):
        control.deploy()
    assert control.get_state()["phase"] == "prepared"


def test_cutover_failure_triggers_rollback(root, monkeypatch):
    control.save_state(state())
    monkeypatch.setattr(control, "prerequisites", lambda: None)
    monkeypatch.setattr(control, "docker_inspect", lambda _: {"State": {"Running": True}})
    calls = []
    def compose(*args, **_kwargs):
        calls.append(("compose", args))
        if args[0] == "up":
            raise subprocess.CalledProcessError(1, "up")
    monkeypatch.setattr(control, "compose", compose)
    monkeypatch.setattr(control, "run", lambda args, **_kwargs: calls.append(("run", args)))
    with pytest.raises(subprocess.CalledProcessError):
        control.deploy()
    assert ("run", ["docker", "stop", "-t", "30", "old-container-id"]) in calls
    assert ("run", ["docker", "start", "old-container-id"]) in calls
    assert control.get_state()["phase"] == "rolled-back"


def test_migration_imports_effective_credentials_and_preserves_originals(root, monkeypatch, capsys):
    from argparse import Namespace
    (root / ".env").unlink()
    (root / ".env.example").write_text(
        "PUBLIC_PORT=8443\nPUBLIC_API_KEY=placeholder\nPUBLIC_HOSTNAME=placeholder\n"
        "UPSTREAM_BASE_URL=placeholder\nUPSTREAM_API_KEY=placeholder\nMODEL_ENGINE=OPENAI\n"
        "MODEL_STATUS=AVAILABLE\nEXPOSE_MODELS=\nDISCOVERY_MODE=enriched\nCONTAINER_UID=1000\nCONTAINER_GID=1000\n")
    old = root.parent / (root.name + "-old")
    (old / "certs").mkdir(parents=True)
    (old / ".env").write_text("UPSTREAM_API_KEY=stale-file-key\n")
    (old / "certs/cert.pem").write_text("certificate-fixture")
    (old / "certs/key.pem").write_text("key-fixture")
    public = "effective-public-" + "a" * 32
    upstream = "effective-upstream-$#'" + "b" * 32
    info = {"Id": "old-id", "Name": "/previous-bridge", "Image": "old-image",
            "Mounts": [{"Destination": "/certs", "Source": str(old / "certs")}],
            "State": {"Running": True}, "HostConfig": {"PortBindings": {"8443/tcp": [{"HostPort": "8443"}]},
            "RestartPolicy": {"Name": "unless-stopped", "MaximumRetryCount": 0}},
            "Config": {"Env": ["UPSTREAM_BASE_URL=https://provider.example.test/v1",
                               "UPSTREAM_API_KEY=" + upstream, "SHIM_API_KEY=" + public,
                               "EXPOSE_MODELS=chat-a,chat-b"]}}
    monkeypatch.setattr(control, "prerequisites", lambda: None)
    monkeypatch.setattr(control, "docker_inspect", lambda _: info)
    monkeypatch.setattr(control, "certificate_hostname", lambda _: "bridge.example.test")
    control.migrate(Namespace(old_dir=str(old), old_container="previous-bridge", port=8443, public_hostname=None))
    new = read_env(root / ".env")
    assert new["UPSTREAM_API_KEY"] == upstream
    assert new["PUBLIC_API_KEY"] == public
    assert new["EXPOSE_MODELS"] == "chat-a,chat-b"
    assert (old / ".env").read_text() == "UPSTREAM_API_KEY=stale-file-key\n"
    assert (old / "certs/key.pem").read_text() == "key-fixture"
    state = control.get_state()
    assert state["phase"] == "prepared"
    assert Path(state["backup"]).is_file()
    output = capsys.readouterr().out
    assert public not in output and upstream not in output
