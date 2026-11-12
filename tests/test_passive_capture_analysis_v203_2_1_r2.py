"""Targeted r2 controls: isolated import, pre-controller failure, zero-event tasks."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/analyze_passive_capture_v203_2_1_r2.py"


def analyzer():
    spec = importlib.util.spec_from_file_location("passive_analyzer_r2_cpu_control", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def no_artifact_controller(tmp_path):
    module = analyzer()
    controller, host = tmp_path / "controller", tmp_path / "host"
    actor, episode = "member_001", "E"
    wire = {"model": "cpu-scripted", "messages": [{"role": "user", "content": "Own visible input."}],
            "tools": [{"type": "function", "function": {"name": "staff_done"}}]}
    response = {"id": "cpu-response", "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                "choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "tool1"}]}}]}

    def save(name, value):
        path = controller / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(value, sort_keys=True) + "\n").encode()
        path.write_bytes(raw)
        return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    request_ref = save("model-ledger/member_001/request-0001.json", {"request": wire})
    response_ref = save("model-ledger/member_001/response-0001.json", response)
    save("model-ledger/ledger.json", {"slot_id": episode, "per_member": {actor: {}}, "inflight": None,
        "calls": [{"request_id": "q1", "member_id": actor, "usage_id": "agent", "usage": response["usage"],
                   "response_id": response["id"], "request": request_ref, "response": response_ref}]})
    association = {"model_call_id": "sdk-d1", "model_tool_call_id": "tool1", "decision_id": "sdk-d1"}
    decision = {"action": "staff_done", "arguments": {"reason": "complete"}, **association}
    receipt = {"ok": True, "reason": "complete", "worker_state": "done", "world_effect": False}
    outcome = {"worker_id": actor, "status": "completed", "reason": "complete", "action_performed": False}
    boundary = {"status": "bounded_work_closed", "closure_reason": "all_members_stopped", "actions": 0,
                "opportunities": 1, "initial_members": [actor], "outcomes": [outcome]}
    trace = [
        {"kind": "model_response", "worker_id": actor, "payload": {
            "response": response, "service_completion_id": response["id"], "decision_id": "sdk-d1"}},
        {"kind": "policy_decision", "worker_id": actor, "payload": {"decision": decision}},
        {"kind": "harness_tool_call", "worker_id": actor, "payload": {**decision, "response": receipt}},
        {"kind": "run_boundary", "payload": boundary},
    ]
    path = controller / "managed-runtime/experience.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps({"sequence": index, **row}) + "\n" for index, row in enumerate(trace)))
    # Exercise the actual export's embedded managed_boundary without requiring
    # a second redundant standalone boundary artifact.
    save("controller-result.json", {"status": "closed", "managed_boundary": boundary})
    save("model-ledger/passive-observer/capture-summary.json", {"observer_fault_count": 0})
    rows = [
        ("INITIAL", {"episode_id": episode, "fixed_members": [actor], "public_initial_message": "Initial public issue."}),
        ("MODEL_REQUEST", {"request_id": "q1", "member_id": actor, "wire": wire}),
        ("MODEL_RESPONSE", {"request_id": "q1", "actor": actor, "body": response}),
        ("INTENT", {"actor": actor, "tool": "staff_done", "arguments": decision["arguments"], "association": association}),
        ("RECEIPT", {"actor": actor, "tool": "staff_done", "arguments": decision["arguments"], "association": association, "response": receipt}),
        ("OPPORTUNITY", outcome),
        ("BOUNDARY", {key: boundary[key] for key in ("status", "closure_reason", "opportunities", "actions")}),
        ("CAPTURE_CLOSED", {"status": "bounded_work_closed"}),
    ]
    with module.ObserverJournal(controller / "model-ledger/passive-observer/events.sqlite") as journal:
        for index, (kind, payload) in enumerate(rows, start=1):
            journal.append(kind, "event-" + str(index), payload, {"episode_id": episode, "capture_time": index})
    context = {"physical_id": "physical1", "logical_id": "q1", "slot_id": episode, "member_id": actor,
               "condition": "CPU", "usage_id": "agent", "attempt_index": 1}
    with module.ObserverJournal(host / "physical-observer/events.sqlite") as journal:
        for kind, value, timestamp in (("HTTP_REQUEST", wire, 2.1), ("HTTP_RESPONSE", response, 2.9)):
            raw = json.dumps(value, indent=2).encode()
            journal.append(kind, kind, {"raw_base64": base64.b64encode(raw).decode(), "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "raw_bytes": len(raw), "observed_at": timestamp, "context": context, "evidence_mode": "cpu_scripted",
                "metadata": {"http_status": 200} if kind == "HTTP_RESPONSE" else {}}, {"episode_id": episode})
    return controller, host


def test_absolute_import_under_no_site_and_safe_path(tmp_path):
    code = """import importlib.util,json,sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
barrier=Barrier(2)
def load(index):
    barrier.wait()
    spec=importlib.util.spec_from_file_location('loaded_analysis_'+str(index),sys.argv[1])
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.analyze_capture(None,'E',generation_result={'slot_id':'E','model_dispatch_started':False,'model_calls':0,'controller_result':None})
with ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(load,range(2)))
assert results[0]==results[1]
result=results[0]
assert 'proworksim' not in sys.modules
assert 'openpyxl' not in sys.modules
print(json.dumps({'execution_state':result['execution_state'],'integrity':result['integrity']['status']}))
"""
    result = subprocess.run([sys.executable, "-S", "-P", "-c", code, str(TOOL)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"execution_state": "NOT_STARTED", "integrity": "PARTIAL"}


def test_not_started_requires_authoritative_zero_call_and_matching_identity():
    module = analyzer()
    primary = {"slot_id": "E", "status": "technical_unknown", "controller_result": None,
               "model_calls": 0, "model_dispatch_started": False,
               "error": {"type": "ValueError", "message": "owned volume prefix rejected"}}
    report = module.analyze_capture(None, "E", generation_result=primary)
    assert report["execution_state"] == "NOT_STARTED"
    assert report["issues"][0]["original_error"] == primary["error"]
    assert report["reconciliation"]["independent_primary_call_count_known"]
    unknown = module.analyze_capture(None, "E", generation_result={**primary, "model_calls": None})
    assert unknown["execution_state"] == "CONTROLLER_NOT_OBSERVED"
    assert not unknown["reconciliation"]["independent_primary_call_count_known"]
    assert module.analyze_capture(None, "WRONG", generation_result=primary)["integrity"]["status"] == "INVALID"


def test_complete_sources_require_no_natural_artifact_or_task_events(tmp_path):
    controller, host = no_artifact_controller(tmp_path)
    report = analyzer().analyze_capture(controller, "E", host)
    assert report["integrity"]["status"] == "COMPLETE"
    assert report["execution_state"] == "CLOSED" and not report["semantic_events_required_for_complete"]
    assert report["phases"]["T0"]["observed"]
    assert all(not report["phases"][f"T{i}"]["observed"] for i in range(1, 7))
    assert all(report["phases"][f"T{i}"]["absence_proven"] for i in range(1, 7))
    assert report["stage_assessments"] == []
    assert report["member_latest_requests"] == {"member_001": "q1"}
    assert report["member_inputs"]["q1"]["request"]["messages"][0]["content"] == "Own visible input."
    assert report["phases"]["T0"]["member_view_requests"] == {"member_001": None}
    assert report["coverage_counts"]["ownership"] == {"required_sources": 1, "observed_sources": 1, "missing_sources": 0}


def test_missing_physical_capture_is_partial_without_reconstructed_bytes(tmp_path):
    controller, _ = no_artifact_controller(tmp_path)
    report = analyzer().analyze_capture(controller, "E")
    assert report["integrity"]["status"] == "PARTIAL"
    assert report["integrity"]["dimensions"]["requests"]["status"] == "PARTIAL"
    assert report["accepted_requests"] == [] and report["member_inputs"] == {}
    assert report["reconciliation"]["primary_calls"] == 1
    assert report["reconciliation"]["primary_action_receipts_match"]


def test_missing_independent_primary_inventory_cannot_be_complete(tmp_path):
    controller, host = no_artifact_controller(tmp_path)
    (controller / "model-ledger/ledger.json").unlink()
    report = analyzer().analyze_capture(controller, "E", host)
    assert report["integrity"]["status"] == "PARTIAL"
    assert report["reconciliation"]["accepted_byte_bound_requests"] == 0
    assert report["reconciliation"]["sidecar_requests_without_settled_primary"] == ["q1"]
