"""Episode-owned cgroup supervision, independent of SDK/RPC locks.

This module never starts a model. Callers must put every episode writer and
its exclusively leased model worker in the registered user services.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from .storage import atomic_write, json_bytes

VERSION = "software-benchmark-supervision-v054"
UNIT = re.compile(r"proworksim-v054-episode-[a-f0-9]{32}-[a-z]+\.service")


def _systemctl(*arguments):
    return subprocess.run(
        ["systemctl", "--user", *arguments], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15).stdout


def properties(unit):
    if not UNIT.fullmatch(unit):
        raise ValueError("Only a dedicated v054 episode service may be supervised")
    fields = ("Id", "InvocationID", "MainPID", "ControlGroup", "ActiveState",
              "SubState", "KillMode", "SendSIGKILL", "Result")
    text = _systemctl("show", unit, "--property=" + ",".join(fields))
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def process_identity(pid):
    """Host identity; an internal namespace PID=1 is never accepted as host PID."""
    raw = Path(f"/proc/{int(pid)}/stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return {"pid": int(pid), "start_ticks": int(fields[19])}


def _populated(cgroup):
    if not cgroup.startswith("/user.slice/") or ".." in cgroup.split("/"):
        raise ValueError("Unexpected episode cgroup path")
    events = Path("/sys/fs/cgroup" + cgroup) / "cgroup.events"
    try:
        values = dict(line.split() for line in events.read_text().splitlines())
    except FileNotFoundError:
        return False
    return values.get("populated") != "0"


def launch_owned(command, *, claim_id, role, runtime_seconds=6000, stop_seconds=5,
                 stdin=None, stdout=None, stderr=None):
    """Return outer launcher and actual host service identity, preserving pipes."""
    if not re.fullmatch(r"[a-f0-9]{32}", claim_id) or not re.fullmatch(r"[a-z]+", role):
        raise ValueError("Invalid episode ownership identity")
    unit = f"proworksim-v054-episode-{claim_id}-{role}.service"
    process = subprocess.Popen([
        "systemd-run", "--user", "--quiet", "--pipe", "--wait", "--unit=" + unit,
        "--property=KillMode=control-group", "--property=SendSIGKILL=yes",
        "--property=TimeoutStopSec=" + str(stop_seconds),
        "--property=RuntimeMaxSec=" + str(runtime_seconds),
        "--", *map(str, command),
    ], stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True)
    launcher = process_identity(process.pid)
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            try:
                state = properties(unit)
            except subprocess.CalledProcessError:
                state = {}  # systemd-run and user manager registration are asynchronous.
            if int(state.get("MainPID", "0")) and state.get("ControlGroup"):
                return process, {
                    "unit": unit, "claim_id": claim_id, "role": role,
                    "invocation_id": state["InvocationID"], "cgroup": state["ControlGroup"],
                    "main": process_identity(int(state["MainPID"])), "outer_launcher": launcher,
                    "runtime_seconds": runtime_seconds, "stop_seconds": stop_seconds,
                }
            if process.poll() is not None:
                raise RuntimeError("Owned service exited before identity admission")
            time.sleep(0.05)
        raise TimeoutError("No owned service identity within admission deadline")
    except BaseException:
        # The launcher is a client, not the service. Stop both even when initial
        # identity acquisition failed. The UUID name was created by this call.
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        try:
            _systemctl("stop", unit)
        except subprocess.CalledProcessError:
            pass  # Unit was never registered.
        raise


def assert_quiet(scope):
    state = properties(scope["unit"])
    if state.get("InvocationID") not in ("", scope["invocation_id"]):
        raise ValueError("A reused unit is not the registered process")
    if (state.get("KillMode") != "control-group"
            or state.get("ActiveState") not in {"inactive", "failed"}
            or int(state.get("MainPID", "0")) != 0 or _populated(scope["cgroup"])):
        raise RuntimeError("Episode service or a descendant is still alive")
    return {"unit": scope["unit"], "invocation_id": scope["invocation_id"],
            "cgroup": scope["cgroup"], "populated": False,
            "active_state": state["ActiveState"], "result": state.get("Result"),
            "main_pid": 0}


def assert_outer_launcher_exited(scope):
    """The Popen owner must wait/reap the outer pipe client before candidate lock."""
    expected = scope["outer_launcher"]
    try:
        actual = process_identity(expected["pid"])
    except FileNotFoundError:
        return
    if actual == expected:
        raise RuntimeError("Reap the registered outer launcher before candidate export")


def stop_owned(scope):
    """No Python RPC lock or worker acknowledgement is involved in this stop."""
    state = properties(scope["unit"])
    if state.get("InvocationID") == "" and state.get("ActiveState") == "inactive":
        return assert_quiet(scope)
    if (state.get("InvocationID") != scope["invocation_id"]
            or state.get("ControlGroup") not in ("", scope["cgroup"])):
        raise ValueError("Refusing to stop a different invocation")
    if int(state.get("MainPID", "0")):
        if process_identity(int(state["MainPID"])) != scope["main"]:
            raise ValueError("Registered host process identity changed")
    # --no-block avoids tying supervision to a hung process or closed-ack.
    _systemctl("stop", "--no-block", scope["unit"])
    deadline = time.monotonic() + float(scope["stop_seconds"]) + 10
    while time.monotonic() < deadline:
        try:
            return assert_quiet(scope)
        except RuntimeError:
            time.sleep(0.05)
    _systemctl("kill", "--kill-who=all", "--signal=KILL", scope["unit"])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            return assert_quiet(scope)
        except RuntimeError:
            time.sleep(0.05)
    raise TimeoutError("Failed to prove that every episode descendant exited")


def watchdog(spec_path, receipt_path):
    """Run in a separate host process, outside all supervised cgroups."""
    spec = json.loads(Path(spec_path).read_text())
    if not spec["scopes"] or any(
            scope["claim_id"] != spec["claim_id"] for scope in spec["scopes"]):
        raise ValueError("Watchdog requires a complete bound scope inventory")
    receipt_path = Path(receipt_path)
    if receipt_path.exists():
        raise FileExistsError("Watchdog receipts cannot be overwritten")
    while True:
        guard = json.loads(Path(spec["guard_path"]).read_text())
        if guard["claim_id"] != spec["claim_id"]:
            raise ValueError("Cross-episode watchdog guard")
        deadline = min(spec["hard_at"], guard.get("request_deadline") or spec["hard_at"])
        if guard["stop_requested"] or time.monotonic() >= deadline:
            reason = ("close_requested" if guard["stop_requested"] else
                      "request_timeout" if deadline < spec["hard_at"] else "hard_deadline")
            break
        time.sleep(0.05)
    reports, errors = [], []
    for scope in spec["scopes"]:
        try:
            reports.append(stop_owned(scope))
        except Exception as error:
            errors.append({"unit": scope["unit"], "error": repr(error)})
    result = {
        "version": VERSION, "claim_id": spec["claim_id"], "reason": reason,
        "scopes": spec["scopes"], "stopped": reports, "errors": errors,
        "all_quiet": not errors and len(reports) == len(spec["scopes"]),
        "monotonic_finished": time.monotonic(), "rpc_close_used_for_stop": False,
        "usage_reconstructed": False, "unknown_cost_zeroed": False,
    }
    atomic_write(receipt_path, json_bytes(result))
    return result


def start_watchdog(spec, directory):
    directory = Path(directory)
    spec_path, receipt = directory / "watchdog-spec.json", directory / "quiescence.json"
    with spec_path.open("xb") as stream:
        stream.write(json_bytes(spec))
    process = subprocess.Popen([
        os.sys.executable, "-m", __name__, "--watch", str(spec_path),
        "--receipt", str(receipt),
    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=(directory / "watchdog.stderr").open("xb"), start_new_session=True)
    return process, receipt


def claim_nonce():
    return uuid.uuid4().hex


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", required=True)
    parser.add_argument("--receipt", required=True)
    options = parser.parse_args()
    result = watchdog(options.watch, options.receipt)
    raise SystemExit(0 if result["all_quiet"] else 1)
