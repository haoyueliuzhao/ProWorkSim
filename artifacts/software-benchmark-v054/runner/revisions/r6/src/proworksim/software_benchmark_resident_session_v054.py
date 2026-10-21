"""Trusted session leases for independently resident, permanently GPU-bound services."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_owner_ipc_v054 import OwnerClient
from .software_benchmark_supervision_v054 import process_identity
from .storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v054-resident-session-v1"


def read_ref(item):
    return json.loads(checked(item).read_text())


def admin_client(declaration, identity, *, timeout=None):
    admin = declaration["admin"]
    if declaration["mode"] == "REF":
        from .software_benchmark_ref_resident_v054 import RefResidentClient
        return RefResidentClient(admin["endpoint"], admin["api_key_file"], timeout_seconds=timeout or 45)
    return OwnerClient(admin["socket_path"], identity, timeout=timeout or 5)


def admitted_resident(declaration_reference, *, query=True):
    declaration = read_ref(declaration_reference)
    expected_gpu = 7 if declaration["mode"] == "REF" else 6
    if declaration["mode"] not in {"REF", "MATCH_PROJECT"} or declaration["gpu_index"] != expected_gpu:
        raise ValueError("Resident is outside the fixed GPU/mode assignment")
    checked(declaration["source_spec"])
    ready_path = Path(declaration["ready_path"])
    if not ready_path.exists():
        return None
    ready = json.loads(ready_path.read_text())
    if (ready.get("ready") is not True or ready.get("resident") is not True
            or ready.get("source_spec") != declaration["source_spec"]
            or ready.get("gpu_index") != declaration["gpu_index"]
            or ready.get("gpu_uuid") != declaration["gpu_uuid"]
            or ready.get("gpu_lease_held") is not True
            or (declaration["mode"] == "REF" and ready.get("endpoint_lease_held") is not True)
            or ready["identity"]["path"] != declaration["identity_path"]
            or process_identity(ready["host_process"]["pid"]) != ready["host_process"]):
        raise ValueError("Resident process, GPU lease or immutable deployment identity changed")
    unit = declaration["unit"]
    if not re.fullmatch(r"proworksim-v054-resident-[a-z0-9-]+\.service", unit):
        raise ValueError("Resident must be in an explicitly named project unit")
    unit_result = subprocess.run(["systemctl", "--user", "show", unit,
        "--property=MainPID,ControlGroup,InvocationID,ActiveState"],
        check=True, capture_output=True, text=True, timeout=5)
    unit_state = dict(line.split("=", 1) for line in unit_result.stdout.splitlines() if "=" in line)
    if (unit_state.get("ActiveState") != "active"
            or int(unit_state.get("MainPID", "0")) != ready["host_process"]["pid"]
            or not unit_state.get("ControlGroup", "").endswith("/" + unit)
            or (ready.get("invocation_id") is not None and ready["invocation_id"] != unit_state["InvocationID"])
            or (ready.get("cgroup") is not None and ready["cgroup"] != unit_state["ControlGroup"])):
        raise ValueError("Resident unit/cgroup invocation no longer owns the recorded process")
    identity = read_ref(ready["identity"])
    status = admin_client(declaration, identity).call("status") if query else None
    if status is not None and status.get("poisoned") is not False:
        raise RuntimeError("Registered resident is poisoned; no automatic reload or reuse")
    return {"declaration": declaration, "declaration_reference": declaration_reference,
            "ready": ready, "ready_reference": reference(ready_path), "identity": identity, "status": status,
            "unit_state": unit_state}


def available_residents(registry_reference):
    registry = read_ref(registry_reference)
    if registry.get("version") != "v054-resident-registry-v1" or set(registry["residents"]) != {"REF", "MATCH_PROJECT"}:
        raise ValueError("The two fixed independent resident declarations are required")
    available = {}
    for mode, item in registry["residents"].items():
        observed = admitted_resident(item)
        if observed is not None and observed["status"].get("active_claim") is None:
            declaration = observed["declaration"]
            if declaration["mode"] != mode:
                raise ValueError("Resident registry mode changed")
            available[declaration["gpu_index"]] = observed
    return available


def suspend_registered(declaration, ready):
    """Freeze only the attested resident cgroup; do not unload or auto-continue."""
    unit = declaration["unit"]
    if not re.fullmatch(r"proworksim-v054-resident-[a-z0-9-]+\.service", unit):
        raise ValueError("Unknown resident unit name")
    if process_identity(ready["host_process"]["pid"]) != ready["host_process"]:
        raise ValueError("Resident process no longer has the recorded identity")
    result = subprocess.run(["systemctl", "--user", "show", unit, "--property=MainPID", "--value"],
                            check=True, capture_output=True, text=True, timeout=5)
    if int(result.stdout.strip()) != ready["host_process"]["pid"]:
        raise ValueError("Resident unit main PID differs; refusing a stop signal")
    subprocess.run(["systemctl", "--user", "kill", "--kill-who=all", "--signal=STOP", unit],
                   check=True, capture_output=True, text=True, timeout=5)
    return {"unit": unit, "signal": "SIGSTOP", "all_unit_processes": True,
            "resident_memory_not_explicitly_released": True, "automatic_SIGCONT": False,
            "already_submitted_GPU_kernels_not_claimed_cancelled": True, "unsettled_usage": "unknown"}


def poison_session(session, reason):
    root = Path(session["session_root"])
    marker = root / "poison.json"
    if marker.exists():
        return json.loads(marker.read_text())
    declaration, ready = session["resident_declaration"], session["resident_ready"]
    value = {"claim_id": session["claim_id"], "poisoned": True, "reason": reason, "automatic_reuse": False}
    try:
        value["admin"] = admin_client(declaration, session["admin_identity"], timeout=2).call(
            "poison", claim_id=session["claim_id"], reason=reason)
    except BaseException as error:
        value["admin_error"] = {"type": type(error).__name__, "message": str(error)}
    # Unknown communication/usage cannot prove a generation has stopped. Keep
    # the physical lease and allocation, but prevent further CPU dispatch.
    if value.get("admin_error") or value.get("admin", {}).get("inflight") not in (0, False):
        try:
            value["suspended"] = suspend_registered(declaration, ready)
        except BaseException as error:
            value["suspension_error"] = {"type": type(error).__name__, "message": str(error)}
    atomic_write(marker, json_bytes(value))
    return value


class ResidentSession:
    """Acquire before the formal claim; release only after trusted model quiescence."""
    def __init__(self, declaration_reference, *, slot, claim_id, authorization, directory):
        self.lock = self.session = None
        self.directory = Path(directory)
        observed = admitted_resident(declaration_reference)
        if observed is None:
            raise BlockingIOError("Registered resident is not ready; no slot claimed")
        declaration = observed["declaration"]
        self.lock = Path(declaration["session_lock_path"]).open("a+")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            client = admin_client(declaration, observed["identity"])
            acquired = client.call("acquire", slot=slot, claim_id=claim_id, authorization=authorization,
                                   host_process=process_identity(os.getpid()))
            if acquired.get("state") == "busy":
                raise BlockingIOError("Registered resident session is already leased")
            if acquired.get("claim_id") != claim_id:
                raise ValueError("Resident acquired a different claim nonce")
            self.session = {"version": VERSION, "claim_id": claim_id, "slot": slot,
                            "resident_reference": declaration_reference, "resident_declaration": declaration,
                            "resident_ready": observed["ready"], "admin_identity": observed["identity"],
                            "host_process": process_identity(os.getpid()), "session_root": str(self.directory),
                            "acquired": acquired, "authorization": authorization}
            self.reference = write_new(self.directory / "session.json", self.session)
            identity = acquired["identity"] if declaration["mode"] == "REF" else acquired["session_identity"]
            write_new(self.directory / "session-identity.json", identity)
            write_new(self.directory / "session-ready.json", {"ready": True, "claim_id": claim_id,
                      "resident_session": self.reference, "weights_reloaded": False})
        except BaseException:
            if self.session is not None:
                poison_session(self.session, "acquire_receipt_failed")
            self.close()
            raise

    def config_fields(self):
        value = self.session["acquired"]
        if self.session["resident_declaration"]["mode"] == "REF":
            return {"ref_endpoint": value["ref_endpoint"], "ref_session_token": value["ref_session_token"]}
        return {"model_socket": value["session_socket"]}

    def release(self, *, controller_result, finish_receipt=None):
        ledger = controller_result["ledger"]
        ledger = ledger.get("model", ledger)
        if (controller_result.get("execution_integrity_failure") or ledger.get("integrity_failure")
                or ledger.get("inflight") or ledger.get("held_tokens", 0)
                or ("complete_actual_tokens" in ledger and ledger["complete_actual_tokens"] is None)):
            self.poison("unsettled_model_usage_at_closure")
            raise ValueError("Unsettled episode cannot release its resident for another task")
        session = self.session
        client = admin_client(session["resident_declaration"], session["admin_identity"])
        if session["resident_declaration"]["mode"] == "REF":
            result = client.call("release", claim_id=session["claim_id"],
                                 session_token=session["acquired"]["ref_session_token"])
            if (result.get("released") is not True or result.get("quiescent") is not True
                    or result.get("resident_still_loaded") is not True):
                raise ValueError("REF release did not prove cache/request quiescence")
        else:
            result = client.call("release", claim_id=session["claim_id"], finish_receipt=finish_receipt)
            proof = result.get("quiescence", {})
            if (result.get("state") != "released" or proof.get("owner_idle") is not True
                    or proof.get("model_busy") is not False or proof.get("active_session") is not None
                    or proof.get("learning_unchanged") is not True or proof.get("rng_restored_exactly") is not True
                    or proof.get("weights_reloaded") is not False):
                raise ValueError("Raw owner release did not prove independent-window restoration")
        if result.get("claim_id") != session["claim_id"]:
            raise ValueError("Release claim identity changed")
        path = self.directory / "release.json"
        if path.exists():
            raise ValueError("Session was already released")
        atomic_write(path, json_bytes({"session": self.reference, "result": result}))
        return reference(path)

    def poison(self, reason):
        return poison_session(self.session, reason) if self.session is not None else None

    def close(self):
        if self.session is not None and not (self.directory / "release.json").exists():
            self.poison("session_host_closed_without_release")
        if self.lock is not None:
            self.lock.close()
            self.lock = None


def sentinel_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--session-sha256", required=True)
    args = parser.parse_args()
    ref = reference(args.session)
    if ref["sha256"] != args.session_sha256:
        raise ValueError("Private session ticket changed")
    session = read_ref(ref)
    directory = Path(session["session_root"])
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopped:
            if (directory / "release.json").exists():
                if json.loads((directory / "release.json").read_text())["session"] != ref:
                    raise ValueError("Release belongs to another session")
                return 0
            if (process_identity(session["host_process"]["pid"]) != session["host_process"]
                    or process_identity(session["resident_ready"]["host_process"]["pid"])
                    != session["resident_ready"]["host_process"]):
                raise RuntimeError("Session host or resident process disappeared")
            time.sleep(.2)
        if (directory / "release.json").exists():
            return 0
        raise RuntimeError("Episode watchdog stopped its session sentinel before clean release")
    except BaseException as error:
        poison_session(session, str(error))
        return 1

