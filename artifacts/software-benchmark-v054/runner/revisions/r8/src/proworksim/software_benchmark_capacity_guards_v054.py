"""Finite CPU-only guards for the bounded model-capacity preparation service."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

MONITOR = re.compile(r"proworksim-v054-model-capacity-preparation-r[0-9]+\.service")
MODEL = re.compile(r"proworksim-v054-model-preparation-[a-f0-9]{12}\.service")


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".writing")
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def check_seal(seal):
    for frozen in seal["files"]:
        if reference(frozen["path"]) != frozen:
            raise ValueError("Preparation source/configuration changed after sealing: " + frozen["path"])
    return seal


def unit_state(unit):
    if not (MONITOR.fullmatch(unit) or MODEL.fullmatch(unit)):
        raise ValueError("Only a dedicated capacity preparation unit is accepted")
    fields = "Id,MainPID,InvocationID,ControlGroup,ActiveState,SubState,KillMode,SendSIGKILL,BindsTo,After"
    raw = subprocess.check_output(["systemctl", "--user", "show", unit,
                                   "--property=" + fields], text=True, timeout=20)
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def check_monitor(state, unit, *, pid=None, invocation=None):
    if (not MONITOR.fullmatch(unit) or state.get("Id") != unit
            or state.get("ActiveState") not in {"active", "activating"}
            or int(state.get("MainPID", "0")) <= 0
            or not re.fullmatch(r"[0-9a-f]{32}", state.get("InvocationID", ""))
            or not state.get("ControlGroup", "").startswith("/user.slice/")
            or not state["ControlGroup"].endswith("/" + unit)):
        raise ValueError("Caller is not a live registered capacity monitor service")
    if pid is not None and int(state["MainPID"]) != pid:
        raise ValueError("Only the registered monitor MainPID may dispatch preparation")
    if invocation is not None and state["InvocationID"] != invocation:
        raise ValueError("Monitor invocation changed")
    return {"unit": unit, "invocation_id": state["InvocationID"],
            "main_pid": int(state["MainPID"]), "cgroup": state["ControlGroup"]}


def require_monitor(unit, *, pid=None, invocation=None):
    return check_monitor(unit_state(unit), unit, pid=pid, invocation=invocation)


def register_model(unit, process, monitor, timeout=10):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        state = unit_state(unit)
        if int(state.get("MainPID", "0")) > 0:
            if (state.get("KillMode") != "control-group" or state.get("SendSIGKILL") != "yes"
                    or monitor["unit"] not in state.get("BindsTo", "").split()
                    or monitor["unit"] not in state.get("After", "").split()):
                raise ValueError("Model service lacks its registered monitor lifecycle binding")
            return {"unit": unit, "invocation_id": state["InvocationID"],
                    "main_pid": int(state["MainPID"]), "cgroup": state["ControlGroup"]}
        if process.poll() is not None:
            raise RuntimeError("Model service exited before registration")
        time.sleep(0.05)
    raise TimeoutError("Model service registration timed out")


def stop_registered(model, process):
    state = unit_state(model["unit"])
    if state.get("InvocationID") not in {"", model["invocation_id"]}:
        raise ValueError("Refusing to stop a replacement model service invocation")
    if state.get("ActiveState") not in {"inactive", "failed"}:
        if state.get("InvocationID") != model["invocation_id"]:
            raise ValueError("Active model service lost its registered invocation")
        subprocess.run(["systemctl", "--user", "stop", model["unit"]], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=65)
    process.wait(timeout=35)
    state = unit_state(model["unit"])
    if (state.get("InvocationID") not in {"", model["invocation_id"]}
            or int(state.get("MainPID", "0")) != 0
            or state.get("ActiveState") not in {"inactive", "failed"}):
        raise RuntimeError("Model unit did not terminate its registered invocation")
    cgroup = model["cgroup"]
    if not cgroup.startswith("/user.slice/") or not cgroup.endswith("/" + model["unit"]):
        raise ValueError("Unexpected registered model cgroup")
    events = Path("/sys/fs/cgroup" + cgroup) / "cgroup.events"
    if events.exists() and dict(line.split() for line in events.read_text().splitlines()).get("populated") != "0":
        raise RuntimeError("A model service descendant is still resident")
    return {**model, "main_pid": 0, "populated": False, "outer_launcher_reaped": True}


class SmokeLedger:
    def __init__(self, path):
        self.path, self.calls = Path(path), []
        if self.path.exists():
            raise FileExistsError("Smoke attempts cannot be silently reused")
        self.save()

    def save(self):
        write(self.path, self.summary())

    def prepare(self, ordinal, prompt_tokens, maximum_output):
        if ordinal != len(self.calls) + 1 or ordinal > 2:
            raise ValueError("At most two predeclared smoke attempts, without replay")
        self.calls.append({"ordinal": ordinal, "prompt_tokens": prompt_tokens,
                           "maximum_output_tokens": maximum_output,
                           "reserved_tokens": prompt_tokens + maximum_output,
                           "generation_dispatched": False, "usage": None, "status": "prepared"})
        self.save()

    def dispatched(self):
        self.calls[-1].update(generation_dispatched=True, status="dispatched_usage_unknown")
        self.save()  # Persist reservation before a possibly partial transport send.

    def settle(self, usage):
        current = self.calls[-1]
        if (type(usage.get("prompt_tokens")) is not int
                or usage["prompt_tokens"] != current["prompt_tokens"]
                or type(usage.get("completion_tokens")) is not int
                or not 0 < usage["completion_tokens"] <= current["maximum_output_tokens"]
                or type(usage.get("total_tokens")) is not int
                or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]):
            raise ValueError("Actual model accounting does not match the complete input")
        current.update(status="settled", usage=copy.deepcopy(usage))
        self.save()

    def summary(self):
        known = sum(call["usage"]["total_tokens"] for call in self.calls if call["usage"] is not None)
        uncertain = [call for call in self.calls if call["generation_dispatched"] and call["usage"] is None]
        return {"version": "v054-capacity-smoke-ledger-v1", "calls": copy.deepcopy(self.calls),
                "generation_calls": sum(call["generation_dispatched"] for call in self.calls),
                "known_actual_tokens": known, "actual_tokens": None if uncertain else known,
                "unsettled_reserved_tokens": sum(call["reserved_tokens"] for call in uncertain),
                "uncertain_attempts": [call["ordinal"] for call in uncertain],
                "unknown_cost_zeroed": False, "automatic_retry": False}
