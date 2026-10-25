"""Per-task admission checks use synthetic immutable files and no runtime resources."""
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_grading_qualification_v060 as qualification
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_scorer_v054 import canonical
from proworksim.storage import digest


def evidence(tmp_path, monkeypatch, change=lambda stage, kind, value: None):
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return reference(path)

    tasks = sorted(qualification.TASKS)
    task = "psf__requests-1766"
    source = tmp_path / "check_legacy_requests_environment_v060.py"
    source.write_text("# Synthetic provenance fixture; never executed.\n")
    monkeypatch.setattr(qualification, "ADMISSION_SOURCE", source)
    environment = {"version": qualification.environment.VERSION, "network_mode": "none",
        "profiles": {name: {"admission_enabled": True, "blockers": [], "standalone_httpbin": True}
                     for name in tasks}}
    resolution = write("resolution", {"hostname": "httpbin.org", "ports": [80, 443],
        "ipv4": ["8.8.8.8"], "selected_ip": "8.8.8.8", "automatic_retry": False})
    change("environment", None, environment)
    environment_ref = write("environment", environment)
    monkeypatch.setattr(qualification.environment, "validate_environment", qualification.load)
    originals, original_refs, mappings = {}, {}, {}
    for name in tasks:
        mappings[name] = {"official_head": name + "-head", "official_tree": name + "-tree"}
        originals[name] = {"instance_id": name,
            "image": {"instance_id": name, "image_id": "sha256:" + digest(name.encode())},
            "dataset": {"revision": "fixed-dataset"}, "scorer_manifest": {"revision": "fixed-harness"},
            "baseline_mapping": write(name + "-mapping", mappings[name]),
            "limits": {"network_mode": "none", "memory_bytes": 16 * 1024**3}}
        original_refs[name] = write(name + "-original", originals[name])
    plan = {"version": qualification.ADMISSION_VERSION, "tasks": tasks,
        "source": reference(source), "environment_revision": environment_ref,
        "preparation_only": True, "actor_feedback": False, "model_calls": 0,
        "official_candidate_scores_changed": False,
        "rows": [{"instance_id": name, "patch_kind": kind,
                  "original_request": original_refs[name], "scoring_cpuset_cpus": "0,1,2,3",
                  "directory": str(tmp_path / (name + "-" + kind))}
                 for name in tasks for kind in ("gold", "empty")]}
    change("plan", None, plan)
    plan_ref = write("plan", plan)
    controls = []
    for kind in ("gold", "empty"):
        original = originals[task]
        identity = {**original, "version": qualification.ADMISSION_VERSION,
            "candidate_kind": kind, "plan": plan_ref, "source": reference(source), "network_resolution": resolution,
            "environment_revision": environment_ref, "original_request": original_refs[task],
            "scoring_cpuset_cpus": "0,1,2,3", "model_calls": 0, "preparation_only": True,
            "actor_feedback": False, "official_candidate_scores_changed": False,
            "candidate_tree_identity_claimed": False,
            "gold_patch_sha256": digest(b"synthetic gold patch" if kind == "gold" else b""),
            "gold_patch_bytes": len(b"synthetic gold patch") if kind == "gold" else 0}
        change("identity", kind, identity)
        identity_ref = write(task + "-" + kind + "/official-output/identity", identity)
        cid = digest((task + kind).encode())
        observed = {"environment_revision": environment_ref, "container_id": cid,
            "image_id": original["image"]["image_id"], "head": mappings[task]["official_head"],
            "head_git_tree": mappings[task]["official_tree"], "working_tree_clean": True,
            "git_returncode": 0, "host_config": {"NetworkMode": "none"},
            "effective_network_mode": "none", "host_network_namespace_shared": False,
            "namespace_evidence": {"host": dict(zip(qualification.NAMESPACES, range(101, 105))),
                                   "grader": dict(zip(qualification.NAMESPACES, range(201, 205))),
                                   "all_distinct": True},
            "local_httpbin": False, "standalone_httpbin": False,
            "original_ca": {"path": "/testbed/requests/cacert.pem", "sha256": "a" * 64},
            "original_ca_changed": False, "tls_verification_changed": False, "resolution": resolution,
            "httpbin_service_scope": "public_httpbin_over_bounded_exec_transport", "task_files_changed": False,
            "timeout_route": {"real_connect_timeout": True}}
        transport = {"ok": True, "status": "completed", "ready": True,
            "network_errors": [], "cleanup_errors": [], "error": None,
            "thread_finished": True, "exec_finished": True, "exec_exit_code": 0,
            "original_ca_unchanged": True, "original_ca_before": observed["original_ca"],
            "original_ca_after": observed["original_ca"], "target_hostname": "httpbin.org",
            "target_ip": "8.8.8.8", "listen_ports": [80, 443], "connection_attempts": 8,
            "max_active_observed": 2, "application_payload_bytes": 12000}
        change("transport", kind, transport)
        transport_ref = write(task + "-" + kind + "/official-output/transport", transport)
        quiet = {"transport_result": transport_ref, "deadline_reached": False,"quiescent": True, "cleanup_errors": [], "owned_container_ids": [cid],
                 "create_result_unknown": False}
        completion = {"version": qualification.ADMISSION_VERSION, "instance_id": task,
                      "status": "process_exited", "returncode": 0}
        receipt = {"transport_result": transport_ref,"version": qualification.ADMISSION_VERSION, "instance_id": task,
            "patch_kind": kind, "status": "official_report", "model_calls": 0,
            "preparation_only": True, "actor_feedback": False, "official_candidate_scores_changed": False,
            "identity": identity_ref,
            "run_id": "v060-env-admission-" + kind + "-" + digest(canonical(identity))[:40],
            "resolved": kind == "gold", "official_result": [task, {task: {
                "patch_successfully_applied": True, "resolved": kind == "gold", "infra_failure": False,
                "tests_status": {"FAIL_TO_PASS": {"failure": ["target"] if kind == "empty" else []}}}}]}
        item = {"instance_id": task, "patch_kind": kind, "identity": identity_ref,
                "original_request": original_refs[task]}
        for field, record in (("initial_container", observed), ("quiescence", quiet),
                              ("completion", completion), ("receipt", receipt)):
            change(field, kind, record)
            name = "official-output/initial-container" if field == "initial_container" else field
            item[field] = write(task + "-" + kind + "/" + name, record)
        controls.append(item)
    value = {"version": qualification.VERSION, "instance_id": task, "tasks": tasks,
             "controls": controls, "passed": True, "model_calls": 0, "official_scores_changed": False,
             "environment_revision": environment_ref, "plan": plan_ref}
    change("qualification", None, value)
    return write("qualification", value), originals, value



def test_qualified_task_keeps_other_task_independent(tmp_path, monkeypatch):
    ref, originals, value = evidence(tmp_path, monkeypatch)
    assert qualification.validate_qualification(ref, originals[value["instance_id"]]) == value
    with pytest.raises(ValueError, match="single-task"):
        qualification.validate_qualification(ref, originals["psf__requests-1921"])


@pytest.mark.parametrize("field,wrong", [
    ("ok", False), ("target_ip", "1.1.1.1"), ("original_ca_after", {}),
    ("exec_finished", False), ("connection_attempts", 513),
    ("application_payload_bytes", 67108865), ("max_active_observed", 17),
    ("network_errors", [{"error": "upstream_reset"}]),
])
def test_transport_failures_or_substitutions_cannot_qualify(tmp_path, monkeypatch, field, wrong):
    def change(stage, kind, value):
        if stage == "transport" and kind == "gold":
            value[field] = wrong
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError):
        qualification.validate_qualification(ref, originals[value["instance_id"]])


@pytest.mark.parametrize("kind", ["gold", "empty"])
def test_wrong_gold_empty_behavior_prevents_admission(tmp_path, monkeypatch, kind):
    def change(stage, which, value):
        if stage == "receipt" and which == kind:
            value["resolved"] = kind != "gold"
            value["official_result"][1][value["instance_id"]]["resolved"] = kind != "gold"
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError, match="reference repair|Unchanged baseline"):
        qualification.validate_qualification(ref, originals[value["instance_id"]])


def test_shared_namespace_and_deadline_fail_closed(tmp_path, monkeypatch):
    def change(stage, kind, value):
        if stage == "initial_container":
            value["namespace_evidence"]["grader"]["mnt"] = value["namespace_evidence"]["host"]["mnt"]
        if stage == "quiescence":
            value["deadline_reached"] = True
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError, match="namespace"):
        qualification.validate_qualification(ref, originals[value["instance_id"]])


def test_transport_receipt_cannot_be_borrowed_from_other_control(tmp_path, monkeypatch):
    ref, originals, value = evidence(tmp_path, monkeypatch)
    receipt_ref = value["controls"][0]["receipt"]
    receipt = qualification.load(receipt_ref)
    receipt["transport_result"] = qualification.load(value["controls"][1]["receipt"])["transport_result"]
    path = Path(receipt_ref["path"])
    path.write_text(json.dumps(receipt))
    value["controls"][0]["receipt"] = reference(path)
    Path(ref["path"]).write_text(json.dumps(value))
    with pytest.raises(ValueError, match="another control"):
        qualification.validate_qualification(reference(ref["path"]), originals[value["instance_id"]])


def test_zero_network_usage_can_be_a_candidate_failure_but_not_a_gold_control(tmp_path, monkeypatch):
    def change(stage, kind, value):
        if stage == "transport":
            value.update(connection_attempts=0, max_active_observed=0, application_payload_bytes=0)
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError, match="usage"):
        qualification.validate_qualification(ref, originals[value["instance_id"]])
    item = value["controls"][0]
    result = qualification.validate_transport_evidence(
        qualification.load(item["receipt"]), qualification.load(item["quiescence"]),
        qualification.load(item["initial_container"]), qualification.load(item["identity"]),
        Path(item["receipt"]["path"]).parent, require_usage=False)
    assert result["ok"] is True and result["connection_attempts"] == 0
