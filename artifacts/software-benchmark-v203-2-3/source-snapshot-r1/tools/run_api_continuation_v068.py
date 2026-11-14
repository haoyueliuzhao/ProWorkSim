"""Continue only original API slots beside the independently running Qwen queue."""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import sqlite3
import threading
import time

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT = policy.ROOT
BATCH_ROOT = ROOT / "runs/software-benchmark-v068/recovery-r1"
RUN_ROOT = BATCH_ROOT / "api-coordinator"
CONTROL_FILE = RUN_ROOT / "concurrency-control.json"
PRIMARY_CURSOR = BATCH_ROOT / "primary-coordinator/cursor.json"
LEDGER = policy.PREDECESSOR_ROOT / "api-budget/ledger.sqlite3"
VERSION = "v068-api-only-original-panel-continuation-r1"
DEFAULT_DESIRED_CONCURRENCY = 32
API_REQUEST_CAP = 64
_spec = importlib.util.spec_from_file_location("v068_frozen_coordinator", ROOT / "tools/run_full_benchmark_v066.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)


class NoQwenRuntime:
    """All lifecycle methods are inert; no local-model module is imported."""

    @staticmethod
    def start_residents():
        return []

    @staticmethod
    def ready_residents():
        return []

    @staticmethod
    def stop_residents():
        return []


def original_api_state(rows, inventory, inventory_ref):
    """Import the sealed merged history; only its current allowlist may enter."""
    api_rows = [row for row in rows if row["model_key"] == "DEEPSEEK"]
    identities = {row["slot_id"] for row in api_rows}
    allowed = identities & set(inventory["allowed_generation_slot_ids"])
    generation = {slot: value for slot, value in inventory["generation"].items() if slot in identities}
    retry = {slot: value for slot, value in inventory["retry_zero_generation"].items() if slot in identities}
    if len(identities) != len(api_rows) or not set(retry) <= generation.keys():
        raise ValueError("Original API identity or zero-call retry inventory is inconsistent")
    expected = identities - generation.keys() | retry.keys()
    if expected != allowed or inventory["API_ledger"] != str(LEDGER):
        raise ValueError("API eligibility or the sole original money ledger changed")
    for slot, proof in retry.items():
        if (proof.get("old_entry") != generation[slot]
                or proof.get("old_result") != generation[slot].get("result")
                or proof.get("new_attempt_reason") != "verified_zero_model_generation"):
            raise ValueError("Zero-call retry must bind its exact original failed attempt")
    state = {"generation": generation, "retry_zero_generation": retry, "inventory": inventory_ref,
        "scores": {slot: value for slot, value in inventory["scores"].items() if slot in identities},
        "deliveries": {slot: value for slot, value in inventory["deliveries"].items() if slot in identities},
        "exceptions": [item for item in inventory.get("exceptions", []) if item.get("slot_id") in identities]}
    return api_rows, state


def verify_primary_api_idle(rows, initial_state, *, cursor_path=PRIMARY_CURSOR,
                            claims_root=policy.BATCH_ROOT / "resource-claims", ledger=LEDGER):
    """Read-only admission proof: primary API paused, no consumed new API identity."""
    cursor = json.loads(Path(cursor_path).read_bytes())
    if cursor.get("failure") is not None:
        raise ValueError("The recovery primary has an unresolved shared safety stop")
    identities = {row["slot_id"] for row in rows}
    eligible = identities - initial_state["generation"].keys() | initial_state["retry_zero_generation"].keys()
    if identities & set(cursor.get("active_generation", [])):
        raise ValueError("Primary API generation is active")
    for row in rows:
        if row["slot_id"] in eligible and (Path(claims_root) / f"actor-{row['slot_index']}.json").exists():
            raise ValueError("A continuation API actor identity has already been consumed")
    for path in Path(claims_root).glob("active-actor-*.json"):
        claim = json.loads(path.read_bytes())
        if claim.get("spec", {}).get("slot_id") in identities:
            raise ValueError("An API actor reservation remains active")
    with sqlite3.connect(f"file:{Path(ledger).resolve()}?mode=ro", uri=True) as db:
        used = {item[0] for item in db.execute("SELECT DISTINCT slot_id FROM requests")}
    if eligible & used:
        raise ValueError("An eligible original API slot already has a provider request")
    return {"primary_cursor": str(cursor_path), "recovery_primary_API_activity": 0,
        "eligible_API_slots": len(eligible), "original_API_slots": len(rows),
        "new_API_actor_claims": 0, "new_API_request_overlap": 0, "ledger": str(ledger)}


class LiveQualification(dict):
    """A value survives execute_queue's shallow outer copy and refreshes on get."""

    def __init__(self, source, task, initial=None):
        super().__init__(initial or {"status": "waiting_for_primary_qualification"})
        self.source, self.task = source, task

    def get(self, key, default=None):
        if key == "status":
            self.source.refresh()
        return super().get(key, default)


class PrimaryQualifications:
    def __init__(self, tasks, *, cursor_path=PRIMARY_CURSOR, initial=None, poll_seconds=3):
        self.cursor_path, self.poll_seconds = Path(cursor_path), poll_seconds
        self.last_read, self.snapshot = float("-inf"), {}
        self.values = {task: LiveQualification(self, task, (initial or {}).get(task)) for task in tasks}

    def refresh(self):
        now = time.monotonic()
        if now - self.last_read < self.poll_seconds:
            return
        snapshot = json.loads(self.cursor_path.read_bytes())
        for task, entry in snapshot.get("qualifications", {}).items():
            if task not in self.values:
                continue
            if entry.get("status") not in {"qualified", "not_qualified"}:
                raise ValueError("Primary qualification is not a terminal environment decision")
            if entry["status"] == "qualified" and not isinstance(entry.get("qualification"), dict):
                raise ValueError("Primary qualified task lacks its evidence reference")
            current = self.values[task]
            previous = dict.get(current, "status")
            if previous in {"qualified", "not_qualified"} and dict(current) != entry:
                raise ValueError("An imported terminal environment qualification changed")
            current.clear()
            current.update(entry)
        self.snapshot, self.last_read = snapshot, now

    def materialize(self):
        return {task: dict(value) for task, value in self.values.items()}


def shared_capacity_snapshot(*, claims_root=policy.BATCH_ROOT / "resource-claims"):
    """Read existing allocation state under its existing lock; reserve nothing."""
    from proworksim.software_benchmark_episode_v066 import capacity
    directory = Path(claims_root)
    with (directory / "allocation.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        active = [json.loads(path.read_bytes()) for path in directory.glob("active-*.json")]
    cpu_fields = Path("/proc/stat").read_text().splitlines()[0].split()
    if cpu_fields[0] != "cpu" or len(cpu_fields) < 9:
        raise ValueError("Host aggregate CPU counters are unavailable")
    counters = [int(value) for value in cpu_fields[1:9]]
    return {"active": active, "physical": capacity(), "observed_unix": time.time(),
        "host_cpu_sample": {"total_ticks": sum(counters), "idle_ticks": counters[3] + counters[4],
            "monotonic_seconds": time.monotonic()}}


def cpu_utilization(previous, current):
    """Host aggregate busy fraction; the first sample is explicitly unknown."""
    if previous is None or current is None:
        return {"host_cpu_utilization_percent": None, "host_cpu_sample_interval_seconds": None}
    total = current["total_ticks"] - previous["total_ticks"]
    idle = current["idle_ticks"] - previous["idle_ticks"]
    elapsed = current["monotonic_seconds"] - previous["monotonic_seconds"]
    valid = total > 0 and 0 <= idle <= total and elapsed > 0
    return {"host_cpu_utilization_percent": round(100 * (total - idle) / total, 2) if valid else None,
        "host_cpu_sample_interval_seconds": elapsed if valid else None}


def resource_limit(snapshot, api_ids, qwen_reserved_lanes=2):
    """Calculate the total API actor ceiling from actual shared reservations."""
    active, physical = snapshot["active"], snapshot["physical"]
    actors = [item for item in active if item.get("spec", {}).get("role") == "actor"]
    own = sum(item["spec"].get("slot_id") in api_ids for item in actors)
    other = len(actors) - own
    # The frozen allocator accounts for the original primary coordinator as a
    # fixed baseline; every auxiliary coordinator is an explicit active lease.
    used_cpu = 4 + sum(item["reserved_cpu"] for item in active)
    used_memory = 16 * policy.GIB + sum(item["reserved_memory_bytes"] for item in active)
    spool = sum(item.get("reserved_spool_bytes", 0) for item in active)
    pair_memory = policy.CONSTRAINTS["generation_pair_reserved_memory_bytes"]
    pair_cpu = policy.CONSTRAINTS["generation_pair_reserved_cpu"]
    pair_spool = policy.CONSTRAINTS["generation_pair_payload_spool_bytes"]
    lanes = policy.CONSTRAINTS["active_actor_limit"]
    if type(qwen_reserved_lanes) is not int or not 0 <= qwen_reserved_lanes <= lanes:
        raise ValueError("Qwen lane reservation is outside the existing environment pool")
    extra_qwen_lanes = max(0, qwen_reserved_lanes - other)
    limits = {
        "environment_lanes": max(0, lanes - own - max(other, qwen_reserved_lanes)),
        "reserved_cpu": max(0, (policy.CONSTRAINTS["maximum_combined_reserved_cpu"] - used_cpu) // pair_cpu),
        "reserved_memory": max(0, (policy.CONSTRAINTS["maximum_combined_reserved_memory_bytes"] - used_memory) // pair_memory),
        "physical_memory": max(0, (physical["memory_available_bytes"] - policy.CONSTRAINTS["memory_minimum_free_bytes"]) // pair_memory),
        "physical_disk": max(0, (physical["disk_free_bytes"] - policy.CONSTRAINTS["disk_minimum_free_bytes"] - spool) // pair_spool),
    }
    free = min(limits.values())
    gate = physical.get("admit") is True
    additional = max(0, free) if gate else 0
    return {"resource_generation_limit": min(lanes, own + additional),
        "environment_lane_limit": lanes, "ledger_remote_request_cap": API_REQUEST_CAP,
        "qwen_lane_reservation": qwen_reserved_lanes,
        "qwen_additional_reserved_lanes": extra_qwen_lanes,
        "additional_slots_by_constraint": limits,
        "capacity_limiting_constraints": [name for name, value in limits.items() if value == free]
            + (["primary_qwen_lane_reservation"] if extra_qwen_lanes and limits["environment_lanes"] == free else [])
            + ([] if gate else ["frozen_episode_physical_admission"]),
        "cpu_reservation_generation_ceiling": own + limits["reserved_cpu"],
        "memory_reservation_generation_ceiling": own + limits["reserved_memory"],
        "generation_pair_reserved_cpu": pair_cpu, "generation_pair_reserved_memory_bytes": pair_memory,
        "additional_resource_slots": additional, "actual_active_api_actors": own,
        "actual_active_qwen_actors": other,
        "actual_active_model_reservations": sum(item.get("spec", {}).get("role") == "model" for item in active),
        "actual_active_grader_reservations": sum(item.get("spec", {}).get("role") in {"score", "delivery_score", "control"} for item in active),
        "actual_active_auxiliary_reservations": sum(item.get("spec", {}).get("role") == "auxiliary_coordinator" for item in active),
        "combined_reserved_cpu": used_cpu, "combined_reserved_memory_bytes": used_memory,
        "physical_admission": gate, "physical_observation": physical,
        "capacity_observed_unix": snapshot.get("observed_unix")}


class DynamicAdmission:
    """Refresh 1..64 desired concurrency; admit only prepared physical capacity."""

    def __init__(self, rows, initial_state, qualifications, stop, api_runtime,
                 event_sink, progress_sink, *, control_file=CONTROL_FILE,
                 capacity_probe=shared_capacity_snapshot, poll_seconds=3):
        self.rows = {row["slot_id"]: row for row in rows}
        self.pending = set(self.rows) - initial_state["generation"].keys() | initial_state["retry_zero_generation"].keys()
        self.active = set()
        self.qualifications, self.stop, self.api_runtime = qualifications, stop, api_runtime
        self.event_sink, self.progress_sink = event_sink, progress_sink
        self.control_file, self.capacity_probe = Path(control_file), capacity_probe
        self.poll_seconds, self.last_capacity = poll_seconds, float("-inf")
        self.observation, self.last_progress = {}, {}
        self.previous_cpu_sample = None
        self.wait_reason = None

    def event(self, kind, **values):
        slot = values.get("slot_id")
        if kind == "generation_scheduled":
            self.pending.discard(slot)
            self.active.add(slot)
        elif kind == "generation_not_started":
            self.pending.discard(slot)
        elif kind == "generation_finished":
            self.active.discard(slot)
            if values.get("status") == "not_entered":
                self.pending.add(slot)
        self.event_sink(kind, **values)

    def refresh_capacity(self):
        now = time.monotonic()
        if now - self.last_capacity < self.poll_seconds:
            return
        error, desired = None, DEFAULT_DESIRED_CONCURRENCY
        try:
            if self.control_file.exists():
                control = json.loads(self.control_file.read_bytes())
                desired = control["desired"]
                if type(desired) is not int or not 1 <= desired <= API_REQUEST_CAP:
                    raise ValueError("desired must be an integer from 1 through 64")
        except (OSError, ValueError, KeyError, TypeError) as failure:
            desired, error = None, str(failure)
        snapshot = self.capacity_probe()
        self.qualifications.refresh()
        primary_state = self.qualifications.snapshot
        reserve_qwen = 2 if (primary_state.get("failure") is None
            and (primary_state.get("pending_generation") or primary_state.get("active_generation"))) else 0
        resources = resource_limit(snapshot, set(self.rows), qwen_reserved_lanes=reserve_qwen)
        cpu = cpu_utilization(self.previous_cpu_sample, snapshot.get("host_cpu_sample"))
        self.previous_cpu_sample = snapshot.get("host_cpu_sample")
        configured = desired if error is None else 0
        # Lowering desired only drains existing work; it never cancels actors.
        self.observation = {**resources, **cpu, "configured_generation_limit": desired,
            "effective_generation_limit": min(configured, resources["resource_generation_limit"]),
            "concurrency_control_file": str(self.control_file), "concurrency_control_error": error}
        self.last_capacity = now

    def report(self, value):
        self.last_progress = dict(value)
        self.refresh_capacity()
        status = value.get("api_status") or self.api_runtime.budget_status()
        self.progress_sink({**value, **self.observation,
            "actual_generation_futures": len(self.active),
            "api_inflight_requests": status.get("inflight_count"),
            "capacity_wait_reason": self.wait_reason})

    def limit(self):
        while not self.stop.is_set():
            self.refresh_capacity()
            self.qualifications.refresh()
            primary = self.qualifications.snapshot
            if primary.get("failure") is not None:
                self.wait_reason = "primary_shared_safety_stop"
                self.event_sink("primary_shared_safety_stop", failure=primary["failure"])
                self.stop.set()
                break
            ceiling = self.observation["effective_generation_limit"]
            if not self.pending or self.active:
                self.wait_reason = None
                return ceiling
            statuses = [self.qualifications.values[self.rows[slot]["instance_id"]].get("status")
                        for slot in self.pending]
            if all(value == "not_qualified" for value in statuses):
                self.wait_reason = None
                return ceiling
            if "qualified" in statuses and ceiling > 0:
                self.wait_reason = None
                return ceiling
            if (primary.get("phase") in {"closed", "stopped", "stopping"}
                    and any(value not in {"qualified", "not_qualified"} for value in statuses)):
                self.wait_reason = "primary_stopped_with_pending_environment_qualifications"
                self.event_sink("qualification_wait_stopped", reason=self.wait_reason)
                self.stop.set()
                break
            self.wait_reason = ("invalid_concurrency_control" if self.observation["concurrency_control_error"]
                else "shared_resource_capacity" if ceiling == 0 else "primary_environment_qualification")
            self.report({**self.last_progress, "phase": "waiting", "planned_generation": len(self.rows),
                "pending_generation": len(self.pending), "active_generation": len(self.active)})
            self.stop.wait(self.poll_seconds)
        if self.wait_reason not in {"primary_shared_safety_stop", "primary_stopped_with_pending_environment_qualifications"}:
            self.wait_reason = "api_coordinator_cancelled_during_admission_wait"
        return 0


def _event(kind, **values):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    with (RUN_ROOT / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"unix": time.time(), "kind": kind, **values}, ensure_ascii=False) + "\n")


def _snapshot(filename, value):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write(RUN_ROOT / filename, json_bytes({"version": VERSION, "unix": time.time(), **value}))


class APIUsageRecorder(base.UsageRecorder):
    """Reuse receipt extraction, with every writable output owned by this sidecar."""

    def import_records(self, record_files, *, eligible_records, exclude=()):
        rows = {row["slot_id"]: row for row in self.matrix["rows"] if row["model_key"] == "DEEPSEEK"}
        for slot, ref in record_files.items():
            if slot not in rows or slot in exclude or slot not in eligible_records:
                continue
            value = base.load(ref)
            if value.get("slot_id") != slot:
                raise ValueError("A predecessor API receipt changed identity")
            self.remember_record(rows[slot], value, ref)

    def save_record(self, row, record):
        path = RUN_ROOT / "usage-records" / f"{row['slot_index']}.json"
        atomic_write(path, json_bytes(record))
        self.remember_record(row, record, reference(path))

    def flush(self, *, final=False):
        if not final and time.monotonic() - self.last_write < 60:
            return
        groups = {key: value for key, value in self.matrix["groups"].items() if value["model_key"] == "DEEPSEEK"}
        if final:
            from proworksim.software_benchmark_usage_metrics_v064 import episode_record, summarize, usage_summary
            preparation = self.api_runtime.preparation_usage()
            receipts = {key: base.load(value["record"]) for key, value in self.records.items()}
            report = summarize(self.matrix, receipts.values(), preparation_calls=preparation.get("calls", []),
                preparation_unresolved_calls=preparation.get("unresolved_calls", []))
            report["groups"] = {key: value for key, value in report["groups"].items() if key in groups}
            report["planned_episodes"] = 3000
            report["aggregate_actual_usage"] = usage_summary([episode_record(row, receipts.get(row["slot_id"]))
                for row in self.matrix["rows"] if row["model_key"] == "DEEPSEEK"])
            atomic_write(RUN_ROOT / "actual-usage-records.json", json_bytes({
                "record_files": {key: value["record"] for key, value in self.records.items()}, **preparation}))
        else:
            selected_groups = {}
            for group_id in groups:
                selected = [value for value in self.records.values() if value["group_id"] == group_id]
                complete = [value for value in selected if value["entered"]
                    and value["generation_state"] in {"closed", "technical_unknown"}
                    and value["usage_capture_complete"] and not value["uncertain_reserved_tokens"]]
                total = sum(value["prompt_tokens_known"] + value["completion_tokens_known"] for value in complete)
                selected_groups[group_id] = {"planned": 500, "entered": sum(value["entered"] for value in selected),
                    "known_actual_tokens_lower_bound": sum(value["prompt_tokens_known"] + value["completion_tokens_known"] for value in selected),
                    "usage_final_episodes": len(complete), "actual_mean_complete_usage_subset": total / len(complete) if complete else None,
                    "actual_mean_full_500": total / 500 if len(complete) == 500 else None}
            report = {"groups": selected_groups, "planned_episodes": 3000, "live_compact_counters_only": True}
        report.update(version_runtime=VERSION, unix=time.time(), final=final,
            matrix=reference(policy.MATRIX_FILE), scope="original_API_six_groups_only",
            non_model_preparation_is_separate=True, api_budget_authority=self.api_runtime.budget_status(),
            usage_report_is_not_budget_admission_authority=True)
        atomic_write(RUN_ROOT / "actual-usage-summary.json", json_bytes(report))
        self.last_write = time.monotonic()


def execute_api_queue(rows, *, initial_state, qualifications, grading, run_episode, api_runtime,
                      stop_event, progress_sink, event_sink, cursor_sink, result_sink=None,
                      disk_check=None, entered_probe=base._slot_entered,
                      control_file=CONTROL_FILE, capacity_probe=shared_capacity_snapshot,
                      poll_seconds=3):
    if any(row["model_key"] != "DEEPSEEK" for row in rows):
        raise ValueError("API sidecar cannot admit any local-model row")
    admission = DynamicAdmission(rows, initial_state, qualifications, stop_event, api_runtime,
        event_sink, progress_sink, control_file=control_file,
        capacity_probe=capacity_probe, poll_seconds=poll_seconds)
    cursor_sink({"phase": "starting", "pending_generation": sorted(admission.pending),
        "active_generation": [], "active_grading": [], "pending_controls": [], "pending_scores": [],
        "generation": initial_state["generation"], "scores": initial_state.get("scores", {}),
        "deliveries": initial_state.get("deliveries", {}), "qualifications": qualifications.materialize(),
        "provider_failures": initial_state.get("provider_failures", {}), "failure": None,
        "resume_inventory": initial_state.get("inventory"), "automatic_model_retry": False})
    result = base.execute_queue(rows, controls=[], qualifications=qualifications.values,
        grading=grading, runtime=NoQwenRuntime(), run_episode=run_episode, api_runtime=api_runtime,
        stop_event=stop_event, progress_sink=admission.report, event_sink=admission.event,
        cursor_sink=cursor_sink, result_sink=result_sink, disk_check=disk_check,
        entered_probe=entered_probe, model_exhausted=lambda _: False, generation_limit=admission.limit,
        initial_state=initial_state)
    result.update(version=VERSION, qualifications=qualifications.materialize(),
        primary_qualification_wait_failure=admission.wait_reason,
        local_model_lifecycle_operations=0, controls_repeated=0,
        last_concurrency_observation={**admission.observation,
            "actual_generation_futures": len(admission.active),
            "api_inflight_requests": (result.get("last_api_status") or {}).get("inflight_count")})
    if admission.wait_reason in {"primary_shared_safety_stop", "primary_stopped_with_pending_environment_qualifications",
                                "api_coordinator_cancelled_during_admission_wait"} and result["failure"] is None:
        result["failure"] = {"kind": admission.wait_reason}
    return result


def run():
    from proworksim import software_benchmark_recovery_scope_v068 as scope
    authorization = scope.require_allowed("v068.api.run")
    host_limits = scope.verify_api_host_limits()
    if (RUN_ROOT / "execution-started.json").exists():
        raise ValueError("An entered API continuation is never automatically replayed")
    if Path(scope.API_ROOT) != RUN_ROOT or Path(scope.PRIMARY_CURSOR) != PRIMARY_CURSOR:
        raise ValueError("API coordinator paths differ from the recovery scope")
    inventory_ref = reference(scope.INVENTORY_FILE)
    inventory = base.load(inventory_ref)
    rows, initial_state = original_api_state(base.load(reference(policy.PLAN_FILE))["rows"], inventory, inventory_ref)
    if len(rows) != 3000:
        raise ValueError("API continuation must retain all six original 500-task groups")
    primary = verify_primary_api_idle(rows, initial_state, cursor_path=scope.PRIMARY_CURSOR)
    plan = base.load(reference(policy.COORDINATOR_RUN_ROOT / "coordinator-plan.json"))
    qualifications = PrimaryQualifications({row["instance_id"] for row in rows},
        cursor_path=scope.PRIMARY_CURSOR, initial=inventory["qualifications"])
    qualifications.refresh()
    reservation = scope.reserve_api_coordinator()
    stopped = threading.Event()
    handlers = base._handle_termination(stopped)
    try:
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        from proworksim.software_benchmark_deepseek_runtime_v068 import DeepSeekRuntime
        from proworksim.software_benchmark_episode_v066 import run_episode
        from proworksim import software_benchmark_grading_recovery_v068 as grading
        api_runtime = DeepSeekRuntime(scope_guard=scope.require_allowed, inventory_ref=inventory_ref)
        identity = None
        try:
            identity = api_runtime.initialize_for_run()
        except Exception as error:
            initial_state["provider_failures"] = {"DEEPSEEK": {"scope": "provider",
                "reason": "api_initialization_unavailable", "error": str(error)}}
        recorder = APIUsageRecorder(base.load(reference(policy.MATRIX_FILE)), api_runtime)
        recorder.import_records(inventory["usage_record_files"], eligible_records=initial_state["generation"],
            exclude=initial_state["retry_zero_generation"])
        write_new(RUN_ROOT / "execution-started.json", {"version": VERSION, "unix": time.time(),
            "authorization": authorization, "actual_host_limits": host_limits,
            "reservation": reservation, "primary_API_exclusivity": primary,
            "continuation_inventory": inventory_ref, "API_identity": identity,
            "planned_API_slots": 3000, "maximum_generation_futures": 12,
            "dynamic_concurrency_control": str(CONTROL_FILE),
            "default_desired_generation_limit": DEFAULT_DESIRED_CONCURRENCY,
            "ledger_remote_request_cap": API_REQUEST_CAP,
            "environment_lane_limit": policy.CONSTRAINTS["active_actor_limit"],
            "local_model_lifecycle_operations": 0, "controls_repeated": 0})
        result = execute_api_queue(rows, initial_state=initial_state, qualifications=qualifications,
            grading=grading, run_episode=run_episode, api_runtime=api_runtime,
            stop_event=stopped, progress_sink=lambda value: _snapshot("progress.json", value),
            event_sink=_event, cursor_sink=lambda value: _snapshot("cursor.json", value), result_sink=recorder,
            disk_check=lambda: base.check_disk_boundary(plan["disk_boundary"]))
        try:
            recorder.flush(final=True)
        except Exception as error:
            result["exceptions"].append({"scope": "measurement", "kind": "final_usage_report_failed",
                "error": str(error), "episode_receipts_preserved": True})
        result.update(finished_unix=time.time(), planned_API_slots=3000,
            actual_usage_summary=reference(RUN_ROOT / "actual-usage-summary.json") if (RUN_ROOT / "actual-usage-summary.json").exists() else None,
            actual_usage_records=reference(RUN_ROOT / "actual-usage-records.json") if (RUN_ROOT / "actual-usage-records.json").exists() else None)
        write_new(RUN_ROOT / "run-summary.json", result)
        _snapshot("progress.json", {"phase": "closed" if result["failure"] is None else "stopped",
            **result["last_concurrency_observation"],
            "planned_generation": 3000, "finished_generation": sum(value.get("entered") is True for value in result["generation"].values()),
            "failure": result["failure"], "provider_failures": result["provider_failures"],
            "summary": reference(RUN_ROOT / "run-summary.json")})
        return result
    finally:
        base._restore_termination(handlers)
        scope.release_api_coordinator(reservation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
