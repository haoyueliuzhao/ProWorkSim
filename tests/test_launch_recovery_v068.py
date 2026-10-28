"""CPU-only command construction and launch ordering; no real user bus calls."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v068_launch_fixture", ROOT / "tools/launch_recovery_v068.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def fixture_scope(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in launcher.ENTRYPOINTS.values():
        (tools / name).write_text("# CPU fixture only\n")
    root = tmp_path / "recovery"
    auth = tmp_path / "authorization.json"
    auth.write_text("{}")
    events = []
    claim = {"owned": "API fixture only"}
    scope = SimpleNamespace(ROOT=tmp_path, BATCH_ROOT=root, PRIMARY_ROOT=root / "primary-coordinator",
        API_ROOT=root / "api-coordinator", PRIMARY_CURSOR=root / "primary-coordinator/cursor.json",
        PRIMARY_UNIT=launcher.UNITS["primary"], API_UNIT=launcher.UNITS["api"],
        AUTHORIZATION_FILE=auth, cpu_affinity=lambda: [164, 165, 166, 167],
        require_allowed=lambda operation: events.append(operation),
        reserve_api_coordinator=lambda: events.append("reserve_api") or claim)
    monkeypatch.setattr(launcher, "recovery_scope", lambda: scope)
    monkeypatch.setattr(launcher.primary, "cpu_set", lambda role: "0,1,2,3")
    monkeypatch.setattr(launcher, "user_manager_environment", lambda: {"PATH": "/usr/bin:/bin", "USER": "fixture"})
    return scope, events, claim


def test_prepare_and_commands_are_offline_fixed_user_units_without_key_in_arguments(tmp_path, monkeypatch):
    scope, events, _ = fixture_scope(tmp_path, monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-secret-never-forwarded")
    monkeypatch.setattr(launcher.subprocess, "run", lambda *args, **kwargs: pytest.fail("Preparation contacted the user manager"))
    prepared = launcher.prepare()
    commands = launcher.commands()
    assert prepared["runtime_operations"] == 0 and events == []
    for role, command in commands.items():
        assert command[:4] == ["systemd-run", "--user", "--collect", "--no-block"]
        assert "--unit=" + launcher.UNITS[role] in command
        assert "--property=CPUQuota=400%" in command
        assert "--property=MemoryMax=16G" in command
        assert "--property=MemorySwapMax=0" in command and "--property=TasksMax=512" in command
        assert "--property=Restart=no" in command
        expected = "0 1 2 3" if role == "primary" else "164 165 166 167"
        assert "--property=CPUAffinity=" + expected in command
        assert command[-5:] == [str(scope.ROOT / ".venv/bin/python"), "-B",
            str(scope.ROOT / "tools/run_offline_scorer_v058.py"),
            str(scope.ROOT / "tools" / launcher.ENTRYPOINTS[role]), "--execute"]
        assert "fixture-secret-never-forwarded" not in " ".join(command)
        assert all("sudo" not in item and "--replace" not in item for item in command)
    with monkeypatch.context() as privileged:
        privileged.setattr(launcher.os, "geteuid", lambda: 0)
        with pytest.raises(PermissionError, match="ordinary"):
            launcher.commands()


def test_launch_primary_first_retains_API_reservation_on_ambiguous_API_start(tmp_path, monkeypatch):
    scope, events, claim = fixture_scope(tmp_path, monkeypatch)
    launcher.prepare()
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert set(kwargs["env"]) == {"PATH", "USER"}
        if command[0] == "systemctl":
            return SimpleNamespace(returncode=0, stdout="LoadState=not-found\nActiveState=inactive\nSubState=dead\nMainPID=0\n", stderr="")
        if "--unit=" + launcher.UNITS["primary"] in command:
            scope.PRIMARY_CURSOR.write_text(json.dumps({"phase": "starting", "failure": None, "qualifications": {}}))
            return SimpleNamespace(returncode=0, stdout="", stderr="started fixture primary")
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        launcher.launch()
    assert events == ["v068.run", "v068.api.run", "reserve_api"]
    starts = [command for command in commands if command[0] == "systemd-run"]
    assert len(starts) == 2
    assert "--unit=" + launcher.UNITS["primary"] in starts[0]
    assert "--unit=" + launcher.UNITS["api"] in starts[1]
    assert json.loads((scope.PRIMARY_ROOT / "launch-result.json").read_text())["returncode"] == 0
    assert json.loads((scope.API_ROOT / "launch-intent.json").read_text())["api_coordinator_reservation"] == claim
    assert not (scope.API_ROOT / "launch-result.json").exists()
    assert all(not any(value in command for value in ("stop", "restart", "reset-failed")) for command in commands)


def test_active_primary_is_not_stopped_replaced_or_restarted(tmp_path, monkeypatch):
    scope, events, _ = fixture_scope(tmp_path, monkeypatch)
    launcher.prepare()
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="LoadState=loaded\nActiveState=active\nSubState=running\nMainPID=123\n", stderr="")

    monkeypatch.setattr(launcher.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="not proved inactive"):
        launcher.launch("primary")
    assert events == ["v068.run"]
    assert len(commands) == 1 and commands[0][0] == "systemctl"
    assert not (scope.PRIMARY_ROOT / "launch-intent.json").exists()
