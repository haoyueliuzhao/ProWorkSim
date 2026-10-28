"""Resume unused original 5M API slots with fully retained uncertain cash bounds."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import threading
import time

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.storage import atomic_write, json_bytes

ROOT = policy.ROOT
BATCH_ROOT = ROOT / "runs/software-benchmark-v072/api-5m-bounded-uncertain-r1"
RUN_ROOT = BATCH_ROOT / "api-coordinator"
CONTROL_FILE = RUN_ROOT / "concurrency-control.json"
VERSION = "v072-unused-5M-bounded-uncertainty-coordinator-r1"
_spec = importlib.util.spec_from_file_location("v072_frozen_expansion_queue", ROOT / "tools/run_api_expansion_v069.py")
frozen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frozen)


class UsageRecorder(frozen.APIUsageRecorder):
    save_record = private_function(frozen.APIUsageRecorder.save_record, RUN_ROOT=RUN_ROOT)
    flush = private_function(frozen.APIUsageRecorder.flush, RUN_ROOT=RUN_ROOT, VERSION=VERSION)


def event(kind, **values):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    with (RUN_ROOT / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"unix": time.time(), "kind": kind, **values}, ensure_ascii=False) + "\n")


def snapshot(name, value):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write(RUN_ROOT / name, json_bytes({"version": VERSION, "unix": time.time(), **value}))


def run():
    from proworksim import software_benchmark_api_recovery_scope_v072 as scope
    from proworksim.software_benchmark_deepseek_runtime_v072 import DeepSeekRuntime
    from proworksim.software_benchmark_expansion_episode_v069 import run_episode as existing_episode
    from proworksim import software_benchmark_grading_recovery_v068 as grading
    authorization = scope.require_allowed("v072.api.run")
    host_limits = scope.verify_api_host_limits()
    if Path(scope.API_ROOT) != RUN_ROOT or (RUN_ROOT / "execution-started.json").exists():
        raise ValueError("Only the unentered exact bounded API recovery unit may execute")
    inventory_ref = reference(scope.INVENTORY_FILE)
    inventory = frozen.base.load(inventory_ref)
    targets, rows, initial = frozen.selected_inventory(
        frozen.base.load(reference(policy.PLAN_FILE))["rows"], inventory, inventory_ref)
    predecessor = scope.require_predecessor_closed()
    qualifications = frozen.PrimaryQualifications({row["instance_id"] for row in rows},
        cursor_path=scope.PRIMARY_CURSOR, initial=inventory["qualifications"])
    qualifications.refresh()
    reservation = scope.reserve_api_coordinator()
    stopped = threading.Event()
    handlers = frozen.base._handle_termination(stopped)
    try:
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        runtime = DeepSeekRuntime(scope_guard=scope.require_allowed, inventory_ref=inventory_ref)
        identity = None
        try:
            identity = runtime.initialize_for_run()
        except Exception as error:
            initial["provider_failures"] = {"DEEPSEEK": {"scope": "provider",
                "reason": "api_initialization_unavailable", "error": str(error)}}
        recorder = UsageRecorder(frozen.base.load(reference(policy.MATRIX_FILE)), runtime)
        recorder.import_records(inventory["usage_record_files"], eligible_records={row["slot_id"] for row in targets})
        write_new(RUN_ROOT / "execution-started.json", {"version": VERSION, "unix": time.time(),
            "authorization": authorization, "actual_host_limits": host_limits, "reservation": reservation,
            "continuation_inventory": inventory_ref, "predecessor": predecessor, "API_identity": identity,
            "bounded_uncertainty": inventory["bounded_uncertainty"], "cash_status": runtime.budget_status(),
            "planned_API_slots": 1000, "new_eligible_API_slots": len(rows),
            "input_plus_output_tokens": 5_000_000, "maximum_generation_futures": 18,
            "same_original_cash_cap_CNY": "1500.00", "unknown_reservations_released": False,
            "local_model_lifecycle_operations": 0, "controls_repeated": 0})

        def episode(row, resident, **kwargs):
            scope.require_allowed("v072.run", slot_id=row["slot_id"], instance_id=row["instance_id"])
            return existing_episode(row, resident, **kwargs)

        def progress(value):
            snapshot("progress.json", {**value, "planned_5M_panel_slots": 1000,
                "new_eligible_API_slots": len(rows), "same_original_cash_cap_CNY": "1500.00",
                "unknown_reservations_released": False})

        old_plan = frozen.base.load(reference(policy.COORDINATOR_RUN_ROOT / "coordinator-plan.json"))
        result = frozen.execute_api_queue(rows, initial_state=initial, qualifications=qualifications,
            grading=grading, run_episode=episode, api_runtime=runtime, stop_event=stopped,
            progress_sink=progress, event_sink=event, cursor_sink=lambda value: snapshot("cursor.json", value),
            result_sink=recorder, control_file=CONTROL_FILE,
            disk_check=lambda: frozen.base.check_disk_boundary(old_plan["disk_boundary"]))
        try:
            recorder.flush(final=True)
        except Exception as error:
            result["exceptions"].append({"scope": "measurement", "kind": "final_usage_report_failed",
                "error": str(error), "episode_receipts_preserved": True})
        result.update(version=VERSION, finished_unix=time.time(), planned_API_slots=1000,
            new_eligible_API_slots=len(rows), historical_inventory=inventory_ref,
            same_original_cash_cap_CNY="1500.00", unknown_reservations_released=False,
            actual_usage_summary=reference(RUN_ROOT / "actual-usage-summary.json") if (RUN_ROOT / "actual-usage-summary.json").exists() else None,
            actual_usage_records=reference(RUN_ROOT / "actual-usage-records.json") if (RUN_ROOT / "actual-usage-records.json").exists() else None)
        write_new(RUN_ROOT / "run-summary.json", result)
        progress({"phase": "closed" if result["failure"] is None else "stopped",
            **result["last_concurrency_observation"], "planned_generation": len(rows),
            "finished_generation": sum(entry.get("entered") is True for entry in result["generation"].values()),
            "failure": result["failure"], "provider_failures": result["provider_failures"],
            "summary": reference(RUN_ROOT / "run-summary.json")})
        return result
    finally:
        frozen.base._restore_termination(handlers)
        scope.release_api_coordinator(reservation)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
