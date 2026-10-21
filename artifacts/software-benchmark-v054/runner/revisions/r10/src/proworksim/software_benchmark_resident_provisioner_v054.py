"""Durable once-only deployment preparation; no benchmark task claims or retries."""
from __future__ import annotations

import copy
import fcntl
import json
from pathlib import Path
import secrets
import subprocess
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_resident_pool_v054 import (
    ADMISSION_VERSION, append_event, now, read_pool, read_ref,
    ref_completion_evidence, validate_pool_policy,
)
from .software_benchmark_supervision_v054 import process_identity
from .storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[2]
HOST_PYTHON = ROOT / ".venv/bin/python"
VERSION = "v054-dynamic-resident-provisioner-v1"


def unit_state(unit):
    result = subprocess.run(["systemctl", "--user", "show", unit,
        "--property=MainPID,InvocationID,ControlGroup,ActiveState,ExecMainStatus,Result"],
        capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        return {"ActiveState": "missing", "MainPID": "0"}
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def launch(unit, argv, root):
    return subprocess.run(["systemd-run", "--user", "--unit=" + unit,
        "--property=Restart=no", "--property=KillMode=control-group",
        "--property=WorkingDirectory=" + str(ROOT),
        "--property=StandardOutput=append:" + str(root / "stdout.log"),
        "--property=StandardError=append:" + str(root / "stderr.log"),
        "--setenv=PYTHONPATH=" + str(ROOT / "src") + ":" + str(ROOT), *argv],
        capture_output=True, text=True, timeout=30, check=False)


def make_deployment(policy_ref, card, attempt):
    """Materialize precise startup/configuration and a separate two-call permit."""
    policy = validate_pool_policy(policy_ref)
    declaration = read_ref(policy["match_template_declaration"])
    template = read_ref(declaration["source_spec"])
    root = Path(policy["pool_root"]) / "devices" / card["uuid"] / f"attempt-{attempt}"
    root.mkdir(parents=True, exist_ok=False)
    token = secrets.token_hex(4)
    resident_id = f"mp-g{card['index']}-{token}"
    unit = f"proworksim-v054-resident-mp-g{card['index']}-{token}.service"
    short = ROOT / "runs/v054-gpu" / token
    owner_root = root / "resident"
    dual = policy.get("MP_session_protocol") == "mp-interleave-v1"
    if dual:
        from tools.check_match_interleave_v054 import preparation_permit
        permit = preparation_permit(resident_id=resident_id, gpu_index=card["index"],
                                    gpu_uuid=card["uuid"], source_manifest=policy["source_manifest"])
    else:
        permit = copy.deepcopy(read_ref(template["preparation_permit"]))
    if not dual:
        permit.update(deployment={"resident_id": resident_id, "gpu_uuid": card["uuid"],
                                  "gpu_index": card["index"], "pool_policy": policy_ref},
                      prior_preparation_authorization=template["preparation_permit"],
                      separate_device_preparation=True)
    permit_ref = write_new(root / "preparation-permit.json", permit)
    source = read_ref(policy["source_manifest"])
    source_by_path = {str(Path(item["path"]).resolve()): item for item in source["files"]}
    required = ["tools/run_match_resident_v054.py", "tools/serve_resident_owner_v054.py",
                "src/proworksim/software_benchmark_resident_owner_v054.py",
                "src/proworksim/software_benchmark_resident_pool_v054.py",
                "src/proworksim/software_benchmark_deployment_gpu_v054.py"]
    if dual:
        required.extend(["tools/serve_interleaved_owner_v054.py", "tools/check_match_interleave_v054.py",
                         "src/proworksim/software_benchmark_interleaved_owner_v054.py",
                         "src/proworksim/software_benchmark_interleaved_transport_v054.py"])
    sources = [source_by_path[str(ROOT / name)] for name in required]
    protocol = {"session_protocol": "mp-interleave-v1", "maximum_sessions": 2} if dual else {}
    spec = {**template, "version": "v054-match-resident-spec-v3" if dual else "v054-match-resident-spec-v2",
            **protocol,
            **({"source_manifest": policy["source_manifest"]} if dual else {}),
            **({"owner_entrypoint": source_by_path[str(ROOT / "tools/serve_interleaved_owner_v054.py")]} if dual else {}),
            "resident_id": resident_id,
            "pool_policy": policy_ref, "unit": unit, "card": card,
            "root": str(owner_root), "short": str(short),
            "identity_path": str(owner_root / "identity.json"),
            "ready_path": str(owner_root / "ready.json"),
            "preparation_permit": permit_ref, "sources": sources,
            "capacity_evidence_reuse": {
                "original_receipt": template["capacity_receipt"],
                "same_model_and_numerical_contract": True,
                "same_gpu_model_required": policy["allowed_gpu_names"],
                "full_capacity_retested_on_this_device": False,
                "this_device_requires_fresh_startup_and_two_session_check": True,
                "co_residency_is_not_model_quality_evidence": True}}
    spec_ref = write_new(root / "spec.json", spec)
    declaration_ref = write_new(root / "declaration.json", {
        "version": "v054-resident-declaration-v2", **protocol, "resident_id": resident_id,
        "pool_policy": policy_ref, "mode": "MATCH_PROJECT", "gpu_index": card["index"],
        "gpu_uuid": card["uuid"], "unit": unit, "source_spec": spec_ref,
        "ready_path": spec["ready_path"], "identity_path": spec["identity_path"],
        "session_lock_path": str(owner_root / "session.lock"),
        "admin": {"socket_path": str(short / "admin.sock")}})
    return {"resident_id": resident_id, "unit": unit, "root": str(root),
            "declaration": declaration_ref, "spec": spec_ref, "attempt": attempt,
            "status": "startup_intent", "created_utc": now(), "created_epoch": time.time(),
            "model_load_attempted": False, "formal_slots_claimed": 0}


def admission(policy_ref, declaration_ref, check_ref, resident_id, *, inherited=False):
    declaration = read_ref(declaration_ref)
    dual = declaration.get("session_protocol") == "mp-interleave-v1"
    return {"version": ADMISSION_VERSION, "kind": "inherited_live_resident" if inherited else
                "new_interleaved_model_device" if dual else "new_same_model_device",
            **({"interleaving_check_receipt": check_ref} if dual else {}),
            "passed": True, "pool_policy": policy_ref, "resident_id": resident_id,
            "declaration": declaration_ref, "source_spec": declaration["source_spec"],
            "ready": reference(declaration["ready_path"]), "check_receipt": check_ref,
            "model_reloaded": False if inherited else None,
            "formal_slots_claimed": 0, "full_capacity_retested": False,
            "numerical_capacity_evidence_reused": True,
            "new_device_two_session_check_required_and_passed": not inherited,
            "created_utc": now()}


def register(policy_ref, declaration_ref, admission_ref, resident_id):
    declaration = read_ref(declaration_ref)
    return append_event(policy_ref, {"event": "register", "resident_id": resident_id,
        "mode": declaration["mode"], "gpu_index": declaration["gpu_index"],
        "gpu_uuid": declaration["gpu_uuid"], "source_spec": declaration["source_spec"],
        "declaration": declaration_ref, "admission": admission_ref})


def import_existing(policy_ref):
    """Preserve already loaded processes; original receipts are not rerun."""
    from .software_benchmark_resident_session_v054 import admitted_resident
    policy = validate_pool_policy(policy_ref)
    registry, old = read_ref(policy["inherited_registry"]), read_ref(policy["inherited_admission"])
    if old["registry"] != policy["inherited_registry"]:
        raise ValueError("Inherited admission belongs to another original registry")
    root = Path(policy["pool_root"]) / "inherited"
    root.mkdir(parents=True, exist_ok=True)
    for mode, declaration_ref in registry["residents"].items():
        if mode not in policy.get("inherit_modes", ["REF", "MATCH_PROJECT"]):
            continue
        resident_id = "inherited-" + mode.lower()
        pool = read_pool(policy_ref)
        if resident_id in pool["active"]:
            continue
        # After a completed REF retirement it must never be re-imported.
        if any(read_ref(item).get("resident_id") == resident_id for item in pool["events"]):
            continue
        observed = admitted_resident(declaration_ref)
        if observed is None:
            raise ValueError("Existing service is not ready; never reload it implicitly")
        path = root / (mode + "-admission.json")
        evidence = (reference(path) if path.exists() else write_new(path, admission(
            policy_ref, declaration_ref, old["admitted_modes"][mode]["check_receipt"], resident_id, inherited=True)))
        register(policy_ref, declaration_ref, evidence, resident_id)


class Provisioner:
    def __init__(self, policy_ref):
        self.policy_ref, self.policy = policy_ref, validate_pool_policy(policy_ref)
        self.root = Path(self.policy["pool_root"])
        self.path = self.root / "provisioner-state.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {
            "version": VERSION, "pool_policy": policy_ref, "devices": {}, "conversion": None,
            "formal_slots_claimed": 0, "automatically_replayed_formal_episodes": 0}
        if self.state["pool_policy"] != policy_ref:
            raise ValueError("An existing monitor belongs to another frozen deployment policy")

    def save(self):
        self.state["updated_utc"] = now()
        atomic_write(self.path, json_bytes(self.state))

    def fail(self, job, message):
        job.update(status="failed_manual_action_required", error=message, automatic_retry=False)
        self.save()

    def start(self, card, previous=None):
        job = make_deployment(self.policy_ref, card, 1 if previous is None else previous["attempt"] + 1)
        self.state["devices"][card["uuid"]] = job
        self.save()  # An ambiguous intent is never automatically replayed.
        spec = job["spec"]
        result = launch(job["unit"], [str(HOST_PYTHON), str(ROOT / "tools/run_match_resident_v054.py"),
                        "--spec", spec["path"], "--sha256", spec["sha256"]], Path(job["root"]))
        job["launch"] = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        if result.returncode:
            self.fail(job, "Resident unit start failed; no automatic attempt replay")
        else:
            job["status"] = "loading"
            self.save()

    def poll(self, job):
        if job["status"] not in {"startup_intent", "loading", "handoff_intent", "checking"}:
            return
        root = Path(job["root"])
        declaration = read_ref(job["declaration"])
        spec = read_ref(job["spec"])
        launcher = Path(spec["root"]) / "launcher-started.json"
        job["model_load_attempted"] = launcher.exists()
        status_path = Path(spec["root"]) / "status.json"
        state = unit_state(job["unit"])
        active = state.get("ActiveState") in {"active", "activating", "deactivating"}
        if not active:
            status = json.loads(status_path.read_text()) if status_path.exists() else {}
            if (status.get("status") == "resource_not_ready" and not job["model_load_attempted"]
                    and status.get("model_load_started") is False and status.get("model_calls") == 0
                    and status.get("reason_code") in {"gpu_capacity_gate", "gpu_lease_busy"}):
                job.update(status="resource_wait", reason=status["reason_code"], retry_after=time.time() + 30,
                           pre_model_refusal=reference(status_path))
                self.save()
                return
            self.fail(job, "Resident stopped before registration: " + json.dumps(state))
            return
        if job["status"] in {"startup_intent", "loading"}:
            if not Path(declaration["ready_path"]).exists():
                if time.time() - job["created_epoch"] > 2400:
                    self.fail(job, "Readiness deadline exceeded; unit retained for explicit diagnosis, not restarted")
                return
            from .software_benchmark_resident_session_v054 import admitted_resident
            observed = admitted_resident(job["declaration"])
            if observed is None or observed["status"].get("active_claims", []) or observed["status"].get("active_claim") is not None:
                raise ValueError("A new unregistered resident is unexpectedly occupied")
            job.update(status="handoff_intent", resident_ready=observed["ready_reference"],
                       check_unit="proworksim-v054-check-" + job["resident_id"] + ".service")
            self.save()
            result = launch(job["check_unit"], [str(HOST_PYTHON),
                str(ROOT / ("tools/check_match_interleave_v054.py" if spec.get("session_protocol") == "mp-interleave-v1"
                            else "tools/check_match_resident_handoff_v054.py")),
                "--declaration", job["declaration"]["path"],
                "--authorization", spec["preparation_permit"]["path"],
                "--output", str(root / "handoff")], root)
            job["check_launch"] = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
            if result.returncode:
                self.fail(job, "Two-session control launch ambiguous/failed; do not replay")
            else:
                job["status"] = "checking"
                self.save()
            return
        control = unit_state(job["check_unit"])
        if control.get("ActiveState") in {"active", "activating", "deactivating"}:
            return
        receipt = root / "handoff/receipt.json"
        if (control.get("ExecMainStatus") != "0" or not receipt.exists()
                or json.loads(receipt.read_text()).get("status") != "passed"):
            # Preserve the resident and physical leases after an unknown call.
            try:
                from .software_benchmark_resident_session_v054 import admitted_resident, suspend_registered
                observed = admitted_resident(job["declaration"], query=False)
                if observed:
                    job["failed_control_suspension"] = suspend_registered(observed["declaration"], observed["ready"])
            except (OSError, ValueError, RuntimeError) as error:
                job["suspension_error"] = str(error)
            self.fail(job, "Actual two-session qualification failed; preserved without reload/reuse")
            return
        evidence = root / "admission.json"
        admission_ref = reference(evidence) if evidence.exists() else write_new(evidence, admission(
            self.policy_ref, job["declaration"], reference(receipt), job["resident_id"]))
        existing = read_pool(self.policy_ref)["active"].get(job["resident_id"])
        event = existing["event_reference"] if existing else register(
            self.policy_ref, job["declaration"], admission_ref, job["resident_id"])
        job.update(status="qualified_registered", admission=admission_ref, registration=event,
                   weights_kept_resident=True, formal_slots_claimed=0)
        self.save()

    def convert_ref(self, pool):
        refs = [x for x in pool["active"].values() if x["mode"] == "REF"]
        if not refs or self.state.get("conversion") is not None:
            return
        queue = json.loads(Path(self.policy["queue_state_path"]).read_text())
        evidence = ref_completion_evidence(queue, read_ref(self.policy["slots"]))
        if not evidence["eligible"]:
            return
        # Queue closure and official scores alone do not erase a prior unknown
        # cost. Check only the already retained small controller ledgers once,
        # at the conversion boundary; never re-run a task or grader.
        for row in queue["rows"]:
            if row["slot"]["arm"] != "REF":
                continue
            controller = read_ref(row["generation"]["actual_cost_ledger"])
            ledger = controller["ledger"]
            model = ledger.get("model", ledger)
            if (controller.get("execution_integrity_failure") or model.get("integrity_failure")
                    or model.get("inflight") or model.get("held_tokens", 0)
                    or ("complete_actual_tokens" in model and model["complete_actual_tokens"] is None)):
                raise ValueError("An original REF accounting entry is still unknown; no conversion")
        from .software_benchmark_resident_session_v054 import admitted_resident
        event = refs[0]
        observed = admitted_resident(event["declaration"])
        if observed is None:
            raise RuntimeError("REF completed, but its registered resident is missing")
        status = observed["status"]
        if status.get("active_claim") is not None or status.get("inflight") != 0 or status.get("poisoned") is not False:
            return
        directory = self.root / "ref-to-mp-conversion"
        directory.mkdir(exist_ok=False)
        snapshot = write_new(directory / "queue-state.json", queue)
        ready = observed["ready"]
        intent = write_new(directory / "intent.json", {"registration": event["event_reference"],
            "queue_snapshot": snapshot, "completion": evidence, "resident_status": status,
            "ready": observed["ready_reference"], "unit_state": observed["unit_state"],
            "same_gpu_uuid": event["gpu_uuid"], "created_utc": now()})
        self.state["conversion"] = {"status": "retirement_intent", "intent": intent}
        self.save()
        # All REF slots and scoring are permanently closed; no new REF session
        # can be scheduled. Stop only the exact attested existing service.
        state = unit_state(observed["declaration"]["unit"])
        if (state.get("InvocationID") != ready["invocation_id"]
                or int(state.get("MainPID", "0")) != ready["host_process"]["pid"]):
            raise ValueError("REF invocation changed before the one-time conversion")
        result = subprocess.run(["systemctl", "--user", "stop", observed["declaration"]["unit"]],
                                capture_output=True, text=True, timeout=120, check=False)
        after = unit_state(observed["declaration"]["unit"])
        group = Path("/sys/fs/cgroup" + ready["cgroup"])
        populated = (any(path.read_text().strip() for path in group.rglob("cgroup.procs")) if group.exists() else False)
        try:
            gone = process_identity(ready["host_process"]["pid"]) != ready["host_process"]
        except (FileNotFoundError, ProcessLookupError):
            gone = True
        if (result.returncode != 0 or after.get("MainPID", "0") != "0" or populated or not gone
                or after.get("ActiveState") not in {"inactive", "failed", "missing"}):
            raise RuntimeError("Old REF process tree was not proven stopped; MP conversion blocked")
        closure = write_new(directory / "closure.json", {"registration": event["event_reference"],
            "intent": intent, "all_500_ref_scored": True, "resident_session_idle": True,
            "old_unit_stopped": True, "old_cgroup_empty": True, "old_launcher_gone": True,
            "post_stop_unit": after, "stop_returncode": result.returncode,
            "created_utc": now(), "different_user_processes_stopped": 0})
        retirement = append_event(self.policy_ref, {"event": "retire", "resident_id": event["resident_id"],
            "registration": event["event_reference"], "closure": closure})
        self.state["conversion"].update(status="ref_retired_waiting_for_mp_capacity",
                                         closure=closure, retirement=retirement)
        self.save()

    def tick(self):
        from .software_benchmark_deployment_gpu_v054 import eligible_match_cards
        from tools.prepare_model_capacity_v054 import gpu_rows
        for job in list(self.state["devices"].values()):
            try:
                self.poll(job)
            except Exception as error:
                self.fail(job, f"{type(error).__name__}: {error}")
        queue = json.loads(Path(self.policy["queue_state_path"]).read_text())
        if not any(row["slot"]["arm"] in {"MATCH", "PROJECT"}
                   and row["generation"]["status"] == "pending" for row in queue["rows"]):
            self.state["waiting"] = "no_pending_MATCH_PROJECT_inventory; existing services unchanged"
            self.save()
            return
        self.state.pop("waiting", None)
        pool = read_pool(self.policy_ref)
        try:
            self.convert_ref(pool)
        except Exception as error:
            self.state["conversion"] = {"status": "failed_manual_action_required", "error": repr(error),
                                         "automatic_retry": False, "previous": self.state.get("conversion")}
            self.save()
        pool = read_pool(self.policy_ref)
        cards = gpu_rows()
        self.state["last_gpu_observation"] = cards
        owned = {item["gpu_uuid"] for item in pool["active"].values()}
        blocked = {key for key, item in self.state["devices"].items() if item["status"] != "resource_wait"}
        for card in eligible_match_cards(cards, self.policy):
            if card["uuid"] in owned | blocked:
                continue
            # GPU7 must still be protected after an interrupted/failed retirement.
            conversion = self.state.get("conversion")
            if card["index"] == 7 and (not conversion or conversion["status"] != "ref_retired_waiting_for_mp_capacity"):
                continue
            old = self.state["devices"].get(card["uuid"])
            if old and time.time() < old["retry_after"]:
                continue
            try:
                self.start(card, old)
            except Exception as error:
                job = self.state["devices"].setdefault(card["uuid"], {"formal_slots_claimed": 0})
                self.fail(job, f"{type(error).__name__}: {error}")
        self.save()

    def run(self, *, once=False):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / "provisioner.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Verify small frozen source once; never rehash weights or image layers.
            for item in read_ref(self.policy["source_manifest"])["files"]:
                checked(item)
            import_existing(self.policy_ref)
            while True:
                self.tick()
                if once:
                    return
                time.sleep(30)
