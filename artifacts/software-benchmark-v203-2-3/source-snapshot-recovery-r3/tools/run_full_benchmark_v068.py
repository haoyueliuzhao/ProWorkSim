"""Resume unused original Qwen/environment identities without rewriting history."""
from __future__ import annotations

import argparse
import ast
import copy
import fcntl
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import threading
import time

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim import software_benchmark_recovery_scope_v068 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT, BATCH_ROOT, RUN_ROOT = scope.ROOT, scope.BATCH_ROOT, scope.PRIMARY_ROOT
VERSION = "v068-Qwen-primary-unused-identities-continuation-r1"
MAX_LIVE_RESIDENTS = 2
_spec = importlib.util.spec_from_file_location("v068_primary_frozen_coordinator", ROOT / "tools/run_full_benchmark_v066.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)


def recovery_function():
    """Two explicit queue seeds in a private AST; old module globals stay intact."""
    source = inspect.getsource(base.execute_queue)
    tree = ast.parse(source)
    changes = {
        "control_queue, score_queue = list(controls), []":
            "control_queue, score_queue = list(controls), list(initial_state.get('pending_score_jobs', []))",
        "controls_done, exceptions = {}, list(initial_state.get(\"exceptions\", []))":
            "controls_done, exceptions = copy.deepcopy(initial_state.get('completed_controls', {})), list(initial_state.get('exceptions', []))",
    }
    count = dict.fromkeys(changes, 0)
    for index, node in enumerate(tree.body[0].body):
        for old, new in changes.items():
            expected = ast.parse(old).body[0]
            if ast.dump(node, include_attributes=False) == ast.dump(expected, include_attributes=False):
                tree.body[0].body[index] = ast.parse(new).body[0]
                count[old] += 1
    if any(number != 1 for number in count.values()):
        raise ValueError("The frozen coordinator no longer has exactly the two reviewed queue initializations")
    namespace = {**base.execute_queue.__globals__, "copy": copy}
    exec(compile(ast.fix_missing_locations(tree), "v068-private-queue-seeds", "exec"), namespace)
    proof = {"original_source": reference(ROOT / "tools/run_full_benchmark_v066.py"),
        "original_function_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "new_AST_sha256": hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest(),
        "only_changes": changes, "old_module_globals_modified": False,
        "model_visible_generation_or_grading_rules_changed": False}
    return namespace["execute_queue"], proof


def original_qwen_state(rows, inventory, inventory_ref):
    rows = [row for row in rows if row["model_key"] == "QWEN"]
    identities = {row["slot_id"] for row in rows}
    generations = {slot: value for slot, value in inventory["generation"].items() if slot in identities}
    retries = {slot: value for slot, value in inventory["retry_zero_generation"].items() if slot in identities}
    eligible = identities - generations.keys() | retries.keys()
    if (len(identities) != len(rows) or not retries.keys() <= generations.keys()
            or eligible != identities & set(inventory["allowed_generation_slot_ids"])):
        raise ValueError("Only the exact original unused Qwen identities may continue")
    for row in rows:
        if row["slot_id"] in eligible and (policy.BATCH_ROOT / "resource-claims" / f"actor-{row['slot_index']}.json").exists():
            raise ValueError("An eligible Qwen actor identity has already been consumed")
    jobs = []
    by_id = {row["slot_id"]: row for row in rows}
    for job in inventory.get("unused_score_jobs", []):
        kind, row, item, prepared = job
        if row["slot_id"] not in identities:
            continue
        if row != by_id[row["slot_id"]] or kind not in {"code", "delivery"} or type(prepared) is not bool:
            raise ValueError("A pending score job must bind its exact original Qwen row")
        jobs.append((kind, row, item, prepared))
    return rows, {"generation": generations, "retry_zero_generation": retries, "inventory": inventory_ref,
        "scores": {slot: value for slot, value in inventory["scores"].items() if slot in identities},
        "deliveries": {slot: value for slot, value in inventory["deliveries"].items() if slot in identities},
        "exceptions": [item for item in inventory.get("exceptions", [])
                       if item.get("slot_id") is None or item["slot_id"] in identities],
        "completed_controls": copy.deepcopy(inventory.get("completed_controls", {})),
        "pending_score_jobs": jobs}


class UnusedResidentRuntime:
    """Keep the original six single-use IDs; admit at most two live residents."""
    def __init__(self, delegate=None, guard=scope.require_allowed, launch=subprocess.run):
        if delegate is None:
            from proworksim import software_benchmark_ref_resident_v066 as delegate
        self.delegate, self.guard, self.launch = delegate, guard, launch

    def active_specs(self):
        active = []
        for path in sorted(self.delegate.RUNS.glob("model-*/spec.json")):
            spec = json.loads(path.read_bytes())
            closed = path.parent / "closed.json"
            released = policy.BATCH_ROOT / "resource-claims" / (f"model-{spec['index']}.released.json")
            if (closed.exists() and json.loads(closed.read_bytes()).get("child_exited") is True
                    and released.exists()):
                continue
            active.append(spec)
        return active

    def start_residents(self):
        self.guard("v068.run")
        self.delegate.RUNS.mkdir(parents=True, exist_ok=True)
        with (self.delegate.RUNS / "allocation.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            active = self.active_specs()
            unused = [index for index in range(1, 6)
                      if not (self.delegate.RUNS / f"model-{index}").exists()]
            vacancies = max(0, MAX_LIVE_RESIDENTS - len(active))
            # A closed old UUID is available again if the original physical
            # free-memory/lease checks admit it. Only active specifications exclude.
            used = {spec["gpu_uuid"] for spec in active}
            cards = [card for card in self.delegate.gpu_capacity() if card["gpu_uuid"] not in used] if vacancies and unused else []
            count = min(vacancies, len(unused), len(cards))
            if count and self.delegate.shared_capacity_for(count):
                for index, card in zip(unused[:count], cards[:count], strict=True):
                    try:
                        spec = self.delegate.make_spec(index, card)
                    except policy.ResourceBusy:
                        break
                    command = self.delegate.unit_command(spec)
                    directory = Path(spec["root"])
                    write_new(directory / "unit-launch-intent.json", {
                        "specification": reference(directory / "spec.json"), "command": command,
                        "host_dispatch_revision": VERSION, "old_resident_identity_replayed": False})
                    result = self.launch(command, env=self.delegate.user_manager_environment(),
                                         capture_output=True, text=True, timeout=30)
                    write_new(directory / "unit-launch-result.json", {
                        "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
                    if result.returncode != 0:
                        raise RuntimeError("Owned unused model identity failed to launch: " + result.stderr[-1000:])
        return self.ready_residents()

    def ready_residents(self):
        return self.delegate.ready_residents()

    def stop_residents(self):
        return self.delegate.stop_residents()

    def exhausted(self, ready):
        if ready or self.active_specs():
            return False
        return all((self.delegate.RUNS / f"model-{index}").exists() for index in range(1, 6))


def snapshot(filename, value):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write(RUN_ROOT / filename, json_bytes({"version": VERSION, "unix": time.time(), **value}))


def event(kind, **values):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    with (RUN_ROOT / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"unix": time.time(), "kind": kind, **values}, ensure_ascii=False) + "\n")


class QwenUsageRecorder(base.UsageRecorder):
    def import_original(self, files, *, eligible_records, exclude=()):
        rows = {row["slot_id"]: row for row in self.matrix["rows"] if row["model_key"] == "QWEN"}
        for slot, ref in files.items():
            if slot not in rows or slot not in eligible_records or slot in exclude:
                continue
            record = base.load(ref)
            if record["slot_id"] != slot:
                raise ValueError("An imported usage record belongs to another original Qwen task")
            self.remember_record(rows[slot], record, ref)

    def save_record(self, row, record):
        folder = RUN_ROOT / "usage-records"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{row['slot_index']}.json"
        atomic_write(path, json_bytes(record))
        self.remember_record(row, record, reference(path))

    def flush(self, *, final=False):
        if not final and time.monotonic() - self.last_write < 60:
            return
        groups = {key for key, value in self.matrix["groups"].items() if value["model_key"] == "QWEN"}
        if final:
            from proworksim.software_benchmark_usage_metrics_v064 import episode_record, summarize, usage_summary
            records = {key: base.load(value["record"]) for key, value in self.records.items()}
            report = summarize(self.matrix, records.values())
            report["groups"] = {key: value for key, value in report["groups"].items() if key in groups}
            report.pop("api_money", None)
            report["aggregate_actual_usage"] = usage_summary([episode_record(row, records.get(row["slot_id"]))
                for row in self.matrix["rows"] if row["model_key"] == "QWEN"])
            snapshot("actual-usage-records.json", {"record_files": {key: value["record"] for key, value in self.records.items()},
                "preparation_calls": [], "preparation_unresolved_calls": []})
        else:
            report = {"groups": {}, "live_compact_counters_only": True}
            for key in groups:
                selected = [row for row in self.records.values() if row["group_id"] == key]
                complete = [row for row in selected if row["entered"]
                    and row["generation_state"] in {"closed", "technical_unknown"}
                    and row["usage_capture_complete"] and not row["uncertain_reserved_tokens"]]
                total = sum(row["prompt_tokens_known"] + row["completion_tokens_known"] for row in complete)
                report["groups"][key] = {"planned": 500, "entered": sum(row["entered"] for row in selected),
                    "known_actual_tokens_lower_bound": sum(row["prompt_tokens_known"] + row["completion_tokens_known"] for row in selected),
                    "usage_final_episodes": len(complete), "actual_mean_complete_usage_subset": total / len(complete) if complete else None,
                    "actual_mean_full_500": total / 500 if len(complete) == 500 else None}
        snapshot("actual-usage-summary.json", {**report, "planned_episodes": 3000,
            "final": final, "scope": "original_Qwen_six_groups_only", "matrix": reference(policy.MATRIX_FILE),
            "usage_report_is_not_budget_admission_authority": True, "API_accounting_owned_by_separate_coordinator": True})
        self.last_write = time.monotonic()


def starting_cursor(rows, state, controls, qualifications):
    return {"phase": "starting", "provider": "QWEN", "failure": None,
        "pending_generation": [row["slot_id"] for row in rows if row["slot_id"] not in state["generation"]
                               or row["slot_id"] in state["retry_zero_generation"]],
        "active_generation": [], "active_grading": [], "pending_controls": controls,
        "pending_scores": state["pending_score_jobs"], "generation": state["generation"],
        "scores": state["scores"], "deliveries": state["deliveries"], "qualifications": qualifications,
        "provider_failures": {}, "resume_inventory": state["inventory"], "automatic_model_retry": False}


def run():
    authorization = scope.require_allowed("v068.run")
    limits = base.coordinator_limits()
    if scope.PRIMARY_CURSOR != RUN_ROOT / "cursor.json" or (RUN_ROOT / "execution-started.json").exists():
        raise ValueError("A primary recovery run cannot be replayed or redirected")
    inventory_ref = reference(scope.INVENTORY_FILE)
    inventory = base.load(inventory_ref)
    rows, state = original_qwen_state(base.load(reference(policy.PLAN_FILE))["rows"], inventory, inventory_ref)
    if len(rows) != 3000:
        raise ValueError("Retain the complete six original Qwen groups")
    controls, qualifications = inventory["unused_control_requests"], inventory["qualifications"]
    plan = base.load(reference(policy.COORDINATOR_RUN_ROOT / "coordinator-plan.json"))
    queue, delta = recovery_function()
    diagnostics = base.diagnostic_qualifications()
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    write_new(RUN_ROOT / "execution-started.json", {"version": VERSION, "unix": time.time(),
        "authorization": authorization, "actual_host_limits": limits, "continuation_inventory": inventory_ref,
        "diagnostics": diagnostics, "private_queue_binding": delta,
        "maximum_live_Qwen_residents": MAX_LIVE_RESIDENTS, "API_generation_enabled": False})
    # The API sidecar must see existing environment decisions even while the
    # first available local model is still loading.
    snapshot("cursor.json", starting_cursor(rows, state, controls, qualifications))
    recorder = QwenUsageRecorder(base.load(reference(policy.MATRIX_FILE)), None)
    recorder.import_original(inventory["usage_record_files"], eligible_records=state["generation"],
                             exclude=state["retry_zero_generation"])
    runtime = UnusedResidentRuntime()
    stopped = threading.Event()
    handlers = base._handle_termination(stopped)
    from proworksim.software_benchmark_episode_v066 import run_episode
    from proworksim import software_benchmark_grading_recovery_v068 as grading
    def generation(row, resident, **kwargs):
        scope.require_allowed("v068.run", slot_id=row["slot_id"], instance_id=row["instance_id"])
        return run_episode(row, resident, **kwargs)
    try:
        result = queue(rows, controls=controls, qualifications=qualifications, grading=grading,
            runtime=runtime, run_episode=generation, api_runtime=None, stop_event=stopped,
            progress_sink=lambda value: snapshot("progress.json", value), event_sink=event,
            cursor_sink=lambda value: snapshot("cursor.json", value), result_sink=recorder,
            initial_state=state, model_exhausted=runtime.exhausted,
            generation_limit=lambda: min(4, base.generation_lane_limit()),
            disk_check=lambda: base.check_disk_boundary(plan["disk_boundary"]))
        try:
            recorder.flush(final=True)
        except Exception as error:
            result["exceptions"].append({"kind": "final_usage_report_failed", "error": str(error)})
    finally:
        base._restore_termination(handlers)
    result.update(version=VERSION, finished_unix=time.time(), planned_Qwen_slots=3000)
    write_new(RUN_ROOT / "run-summary.json", result)
    phase = "closed" if result["failure"] is None else "stopped"
    final_cursor = base.load(reference(RUN_ROOT / "cursor.json"))
    snapshot("cursor.json", {**final_cursor, "phase": phase, "failure": result["failure"],
        "qualifications": result["qualifications"], "summary": reference(RUN_ROOT / "run-summary.json")})
    snapshot("progress.json", {"phase": phase, "planned_generation": 3000,
        "finished_generation": sum(entry.get("entered") is True for entry in result["generation"].values()),
        "finished_code_scores": len(result["scores"]), "failure": result["failure"],
        "summary": reference(RUN_ROOT / "run-summary.json")})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    if not parser.parse_args().execute:
        parser.error("Use the separately authorized recovery launcher with --execute")
    print(json.dumps(run(), ensure_ascii=False))
