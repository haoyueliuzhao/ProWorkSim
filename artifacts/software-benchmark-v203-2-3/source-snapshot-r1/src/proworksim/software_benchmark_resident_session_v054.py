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
from .software_benchmark_deployment_gpu_v054 import validate_card_identity
from .software_benchmark_resident_pool_v054 import (
    declared_session_capacity, registrations, validate_registration, validate_pool_policy,
)
from .storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v054-resident-session-v1"
INTERLEAVE_PROTOCOL = "mp-interleave-v1"


def read_ref(item):
    return json.loads(checked(item).read_text())


def admin_client(declaration, identity, *, timeout=None):
    admin = declaration["admin"]
    if declaration["mode"] == "REF":
        from .software_benchmark_ref_resident_v054 import RefResidentClient
        return RefResidentClient(admin["endpoint"], admin["api_key_file"], timeout_seconds=timeout or 45)
    return OwnerClient(admin["socket_path"], identity, timeout=timeout or 5)


def session_capacity(declaration, *, ready=None, identity=None):
    return declared_session_capacity(declaration, ready=ready, identity=identity)


def session_lock_paths(declaration):
    base = Path(declaration["session_lock_path"])
    if session_capacity(declaration) == 1:
        return [base]
    return [base.with_name(base.name + ".slot-" + str(index)) for index in range(2)]


def lock_session_slot(declaration):
    """Two local leases match two owner slots; no GPU lease is reacquired."""
    for index, path in enumerate(session_lock_paths(declaration)):
        stream = path.open("a+")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stream.close()
        else:
            return stream, index
    raise BlockingIOError("All declared resident session slots are leased")


def interleaved_status(status):
    """Validate both isolated claims and the single dispatched numerical turn."""
    active = status.get("active_claims")
    sessions = status.get("sessions")
    if (status.get("resident") is not True or "poisoned" not in status
            or status["poisoned"] is not None or not isinstance(active, list)
            or not isinstance(sessions, dict) or len(active) > 2 or len(set(active)) != len(active)
            or any(not isinstance(claim, str) or not re.fullmatch(r"[a-f0-9]{32}", claim)
                   for claim in active)):
        raise ValueError("Invalid interleaved resident health or claim inventory")
    occupied = []
    for claim in active:
        entry = sessions.get(claim, {})
        slot = entry.get("session_slot")
        if (type(slot) is not int or slot not in (0, 1)
                or entry.get("phase") not in {"acquired", "collecting", "closing"}
                or any(value is not False and not isinstance(value, str)
                       for value in (entry.get("queued"), entry.get("dispatched")))):
            raise ValueError("An active interleaved claim lost its slot or turn identity")
        occupied.append(slot)
    if (len(set(occupied)) != len(occupied)
            or status.get("available_session_slots") != sorted({0, 1} - set(occupied))
            or status.get("state") != ("busy" if active else "idle")):
        raise ValueError("Interleaved slot availability differs from the active claims")
    inflight = status.get("inflight")
    dispatched = [(claim, sessions[claim]["dispatched"]) for claim in active
                  if sessions[claim]["dispatched"] is not False]
    if inflight is None:
        if dispatched:
            raise ValueError("A dispatched turn has no bound resident operation")
    elif (not isinstance(inflight, dict) or len(dispatched) != 1
          or (inflight.get("claim_id"), inflight.get("ticket_id")) != dispatched[0]
          or not isinstance(inflight.get("operation"), str)):
        raise ValueError("More than one turn, or an unbound turn, is executing")
    return list(active)


def require_interleaved_release(result, claim_id):
    proof = result.get("quiescence", {})
    if (result.get("state") != "released" or result.get("claim_id") != claim_id
            or any(proof.get(key) is not True for key in (
                "session_quiescent", "queued_removed", "learning_unchanged", "rng_restored_exactly",
                "session_rng_closed", "model_object_retained", "old_session_socket_removed",
                "resident_still_loaded"))
            or proof.get("own_inflight") != 0 or proof.get("weights_reloaded") is not False
            or not isinstance(proof.get("other_active_claims"), list)
            or claim_id in proof["other_active_claims"]
            or proof.get("resident_generator_active") == claim_id):
        raise ValueError("Interleaved release lacks this exact session's complete closure")
    return proof


def admitted_resident(declaration_reference, *, query=True, pool_policy_reference=None,
                      registration_reference=None):
    declaration = read_ref(declaration_reference)
    validate_card_identity({'index': declaration['gpu_index'], 'uuid': declaration['gpu_uuid']})
    registration = None
    if pool_policy_reference is not None or registration_reference is not None:
        if pool_policy_reference is None or registration_reference is None:
            raise ValueError('Both frozen pool policy and immutable registration are required')
        registration = validate_registration(read_ref(registration_reference), pool_policy_reference)
        if (registration['event_reference'] != registration_reference
                or registration['declaration'] != declaration_reference):
            raise ValueError('Resident declaration differs from its active admitted registration')
    elif declaration.get('version') == 'v054-resident-declaration-v2':
        # Read-only inspection before the independent device handoff control.
        # Formal session acquisition below still requires a current registration.
        policy = validate_pool_policy(declaration['pool_policy'])
        deployment = read_ref(declaration['source_spec'])
        if (deployment.get('version') not in {'v054-match-resident-spec-v2', 'v054-match-resident-spec-v3'}
                or deployment.get('pool_policy') != declaration['pool_policy']
                or deployment.get('resident_id') != declaration['resident_id']
                or declaration['mode'] != 'MATCH_PROJECT'
                or deployment['card']['index'] != declaration['gpu_index']
                or deployment['card']['uuid'] != declaration['gpu_uuid']
                or declaration['gpu_index'] not in policy['physical_gpus']):
            raise ValueError('New resident lacks its immutable pre-admission deployment identity')
    elif (declaration.get('version') != 'v054-resident-declaration-v1'
          or declaration['gpu_index'] != (7 if declaration['mode'] == 'REF' else 6)):
        raise ValueError('Unknown historical or dynamic resident deployment')
    if (declaration["mode"] not in {"REF", "MATCH_PROJECT"}
            or (declaration['mode'] == 'REF' and declaration['gpu_index'] != 7)):
        raise ValueError("Resident is outside its authorized GPU/mode assignment")
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
    if declaration['mode'] == 'MATCH_PROJECT':
        binding = identity.get('resource_binding', {})
        if (binding.get('gpu_index') != declaration['gpu_index']
                or binding.get('gpu_uuid') != declaration['gpu_uuid']
                or identity.get('actual_CalibrationActor') is not True
                or identity.get('original_generate_native') is not True
                or identity.get('numerical_methods_replaced') is not False):
            raise ValueError('Actual raw owner numerical/physical binding differs from registration')
    capacity = session_capacity(declaration, ready=ready, identity=identity)
    status = admin_client(declaration, identity).call("status") if query else None
    active_claims = None
    if status is not None:
        healthy = status.get("poisoned") is False
        if capacity == 2:
            active_claims = interleaved_status(status)
            healthy = True
        elif declaration["mode"] == "MATCH_PROJECT":
            # The raw-owner manager uses None for healthy and a diagnostic
            # object for poisoned; its occupied state is named "busy".
            active = status.get("active_claim")
            healthy = (status.get("resident") is True and "poisoned" in status
                       and status["poisoned"] is None
                       and ((status.get("state") == "idle" and active is None
                             and status.get("inflight") is None)
                            or (status.get("state") == "busy" and isinstance(active, str)
                                and re.fullmatch(r"[a-f0-9]{32}", active) is not None)))
        if not healthy:
            raise RuntimeError("Registered resident is poisoned or its health evidence is invalid; no automatic reuse")
        if capacity == 1:
            active_claims = [status["active_claim"]] if status.get("active_claim") is not None else []
    return {"session_capacity": capacity, "active_claims": active_claims,
            "declaration": declaration, "declaration_reference": declaration_reference,
            "ready": ready, "ready_reference": reference(ready_path), "identity": identity, "status": status,
            "unit_state": unit_state, 'registration': registration_reference,
            'resident_id': registration['resident_id'] if registration else declaration.get('resident_id'),
            'preparation_only': registration is None}


def available_residents(pool_policy_reference):
    """Only active admitted registrations; occupancy never rechecks free GPU memory."""
    available = {}
    seen_devices = set()
    for registration in registrations(pool_policy_reference):
        item = registration['declaration']
        observed = admitted_resident(item, pool_policy_reference=pool_policy_reference,
                                     registration_reference=registration['event_reference'])
        if observed is not None and len(observed["active_claims"]) < observed["session_capacity"]:
            declaration = observed["declaration"]
            if declaration['gpu_uuid'] in seen_devices:
                raise ValueError('Two active residents claim the same physical GPU')
            seen_devices.add(declaration['gpu_uuid'])
            if declaration["mode"] != registration['mode']:
                raise ValueError("Resident registration mode changed")
            available[registration['resident_id']] = observed
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


def released_session_evidence(session):
    """A settled released claim cannot poison an independently idle resident."""
    root = Path(session["session_root"])
    path = root / "release.json"
    if not path.exists():
        return None
    ticket = reference(root / "session.json")
    if read_ref(ticket) != session:
        raise ValueError("Saved resident session identity differs from the released claim")
    release = json.loads(path.read_text())
    if release.get("session") != ticket:
        raise ValueError("Release is not bound to this exact saved session")
    result = release["result"]
    if result.get("claim_id") != session["claim_id"]:
        raise ValueError("Release claim identity changed")
    declaration = session["resident_declaration"]
    if declaration["mode"] == "REF":
        if (any(result.get(key) is not True for key in (
                "released", "quiescent", "resident_still_loaded", "engine_paused", "cache_reset"))
                or result.get("engine_unfinished") != 0 or result.get("weights_unloaded") is not False):
            raise ValueError("REF release does not prove fully settled model/cache state")
    elif session_capacity(declaration) == 2:
        require_interleaved_release(result, session["claim_id"])
    else:
        proof = result.get("quiescence", {})
        if (result.get("state") != "released" or proof.get("owner_idle") is not True
                or proof.get("model_busy") is not False or proof.get("active_session") is not None
                or proof.get("learning_unchanged") is not True
                or proof.get("rng_restored_exactly") is not True
                or proof.get("weights_reloaded") is not False):
            raise ValueError("Raw owner release does not prove independent-window closure")
    ready = session["resident_ready"]
    if process_identity(ready["host_process"]["pid"]) != ready["host_process"]:
        raise ValueError("Released resident process identity changed")
    status = admin_client(declaration, session["admin_identity"], timeout=2).call("status")
    if declaration["mode"] == "REF":
        idle = (status.get("poisoned") is False and status.get("phase") == "idle"
                and status.get("active_claim") is None and status.get("inflight") == 0)
    elif session_capacity(declaration) == 2:
        active = interleaved_status(status)
        own = status["sessions"].get(session["claim_id"])
        idle = (session["claim_id"] not in active and (own is None or (
            own.get("phase") == "closed" and own.get("queued") is False
            and own.get("dispatched") is False)))
    else:
        idle = (status.get("resident") is True and "poisoned" in status
                and status["poisoned"] is None and status.get("state") == "idle"
                and status.get("active_claim") is None and status.get("inflight") is None)
    if not idle:
        raise ValueError("The released session is not independently closed in a healthy resident")
    return {"release": reference(path), "session": ticket, "status": status,
            "resident_host_process": ready["host_process"]}


def poison_session(session, reason):
    root = Path(session["session_root"])
    marker = root / "poison.json"
    if marker.exists():
        return json.loads(marker.read_text())
    declaration, ready = session["resident_declaration"], session["resident_ready"]
    value = {"claim_id": session["claim_id"], "poisoned": True, "reason": reason, "automatic_reuse": False}
    try:
        settled = released_session_evidence(session)
    except BaseException as error:
        value["release_guard_error"] = {"type": type(error).__name__, "message": str(error)}
    else:
        if settled is not None:
            notice = {"claim_id": session["claim_id"], "poisoned": False,
                      "reason": reason, "resident_poison_skipped": ("exact_released_session_and_live_own_claim_closed"
                          if session_capacity(declaration) == 2 else "exact_released_session_and_live_idle"),
                      "administrative_episode_failure_preserved": True, "evidence": settled}
            atomic_write(root / "post-release-failure.json", json_bytes(notice))
            return notice
    if session_capacity(declaration) == 2:
        client = admin_client(declaration, session["admin_identity"], timeout=2)
        try:
            aborted = client.call("abort_session", claim_id=session["claim_id"], reason=reason)
            if (aborted.get("claim_id") != session["claim_id"]
                    or type(aborted.get("shared_poisoned")) is not bool):
                raise ValueError("Session abort lost its exact claim/shared-fault identity")
            if aborted["shared_poisoned"] is False:
                if (aborted.get("session_aborted") is not True
                        or aborted.get("own_dispatched") is not False
                        or aborted.get("resident_still_loaded") is not True
                        or not isinstance(aborted.get("not_dispatched_receipts"), list)):
                    raise ValueError("Session-local abort lacks proof that no own turn is dispatched")
                for item in aborted["not_dispatched_receipts"]:
                    checked(item)
                value.update(poisoned=False, session_aborted=True, shared_poisoned=False,
                             admin=aborted, other_sessions_undisturbed=True)
                atomic_write(marker, json_bytes(value))
                return value
            value.update(admin=aborted, shared_poisoned=True)
        except BaseException as error:
            value["admin_error"] = {"type": type(error).__name__, "message": str(error)}
            try:
                # A fresh administrative client is permitted solely to close
                # dispatch; it never retries a numerical request.
                value["shared_guard"] = admin_client(
                    declaration, session["admin_identity"], timeout=2).call(
                        "poison_shared", reason="unproved_session_abort: " + reason)
            except BaseException as guard_error:
                value["shared_guard_error"] = {"type": type(guard_error).__name__, "message": str(guard_error)}
        try:
            value["suspended"] = suspend_registered(declaration, ready)
        except BaseException as error:
            value["suspension_error"] = {"type": type(error).__name__, "message": str(error)}
        atomic_write(marker, json_bytes(value))
        return value
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
    def __init__(self, declaration_reference, *, slot, claim_id, authorization, directory,
                 pool_policy_reference, registration_reference):
        self.lock = self.session = None
        self.directory = Path(directory)
        if pool_policy_reference is None or registration_reference is None:
            raise ValueError('A formal session requires its active independently admitted registration')
        observed = admitted_resident(declaration_reference, pool_policy_reference=pool_policy_reference,
                                     registration_reference=registration_reference)
        if observed is None:
            raise BlockingIOError("Registered resident is not ready; no slot claimed")
        declaration = observed["declaration"]
        if declaration['mode'] != ('REF' if slot['arm'] == 'REF' else 'MATCH_PROJECT'):
            raise ValueError('A task arm cannot use another resident numerical mode')
        self.lock, session_slot = lock_session_slot(declaration)
        capacity = observed["session_capacity"]
        try:
            client = admin_client(declaration, observed["identity"])
            extra = {"session_slot": session_slot} if capacity == 2 else {}
            acquired = client.call("acquire", slot=slot, claim_id=claim_id, authorization=authorization,
                                   host_process=process_identity(os.getpid()), **extra)
            if acquired.get("state") == "busy":
                raise BlockingIOError("Registered resident session is already leased")
            if acquired.get("claim_id") != claim_id:
                raise ValueError("Resident acquired a different claim nonce")
            if capacity == 2 and (acquired.get("session_slot") != session_slot
                    or acquired.get("session_protocol") != INTERLEAVE_PROTOCOL
                    or acquired.get("maximum_sessions") != 2):
                raise ValueError("Acquired resident session differs from its leased slot/protocol")
            session_contract = ({"session_slot": session_slot, "maximum_sessions": 2,
                                 "session_protocol": INTERLEAVE_PROTOCOL} if capacity == 2 else {})
            self.session = {**session_contract, "version": VERSION, "claim_id": claim_id, "slot": slot,
                            "resident_reference": declaration_reference, "resident_declaration": declaration,
                            "resident_ready": observed["ready"], "admin_identity": observed["identity"],
                            "host_process": process_identity(os.getpid()), "session_root": str(self.directory),
                            'resident_id': observed['resident_id'], 'resident_pool_policy': pool_policy_reference,
                            'resident_registration': registration_reference,
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
            if session_capacity(session["resident_declaration"]) == 2:
                require_interleaved_release(result, session["claim_id"])
            else:
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

