"""Per-task admission checks use synthetic immutable files and no runtime resources."""
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_grading_qualification_v058 as qualification
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
    task = "psf__requests-2931"
    source = tmp_path / "check_ref_grading_environment_v058.py"
    source.write_text("# Synthetic provenance fixture; never executed.\n")
    monkeypatch.setattr(qualification, "ADMISSION_SOURCE", source)
    environment = {"version": qualification.environment.VERSION, "network_mode": "none",
        "profiles": {name: {"standalone_httpbin": name in {"psf__requests-1766", "psf__requests-1921"},
                            "admission_enabled": name in {"psf__requests-2931", "psf__requests-5414"},
                            "blockers": [] if name in {"psf__requests-2931", "psf__requests-5414"}
                            else ["legacy_session_send_uses_repository_ca"]}
                     for name in tasks}}
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
            "candidate_kind": kind, "plan": plan_ref, "source": reference(source),
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
            "local_httpbin": True, "standalone_httpbin": environment["profiles"][task]["standalone_httpbin"],
            "httpbin_service_scope": "container_loopback", "task_files_changed": False,
            "timeout_route": {"real_connect_timeout": True}}
        quiet = {"quiescent": True, "cleanup_errors": [], "owned_container_ids": [cid],
                 "create_result_unknown": False}
        completion = {"version": qualification.ADMISSION_VERSION, "instance_id": task,
                      "status": "process_exited", "returncode": 0}
        receipt = {"version": qualification.ADMISSION_VERSION, "instance_id": task,
            "patch_kind": kind, "status": "official_report", "model_calls": 0,
            "preparation_only": True, "actor_feedback": False, "official_candidate_scores_changed": False,
            "identity": identity_ref,
            "run_id": "v058-env-admission-" + kind + "-" + digest(canonical(identity))[:40],
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


def test_single_task_qualifies_with_other_six_control_results_absent(tmp_path, monkeypatch):
    ref, originals, value = evidence(tmp_path, monkeypatch)
    assert qualification.validate_qualification(ref, originals[value["instance_id"]]) == value
    other = next(name for name in originals if name != value["instance_id"])
    with pytest.raises(ValueError, match="single-task"):
        qualification.validate_qualification(ref, originals[other])
    changed = {**originals[value["instance_id"]], "image": {"image_id": "another-image"}}
    with pytest.raises(ValueError, match="qualified task environment"):
        qualification.validate_qualification(ref, changed)


@pytest.mark.parametrize("kind", ["gold", "empty"])
def test_failed_gold_or_successful_empty_blocks_only_that_task(tmp_path, monkeypatch, kind):
    def change(stage, record_kind, value):
        if stage == "receipt" and record_kind == kind:
            value["resolved"] = kind != "gold"
            value["official_result"][1][value["instance_id"]]["resolved"] = kind != "gold"
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError, match="reference repair|Unchanged baseline"):
        qualification.validate_qualification(ref, originals[value["instance_id"]])


@pytest.mark.parametrize("stage,field,new_value", [
    ("identity", "version", "v057-offline-requests-fixture-admission-r1"),
    ("identity", "nat_lane", {"registry": "old-nat"}),
    ("receipt", "run_id", "historical-cached-report"),
    ("completion", "returncode", 1),
    ("quiescence", "owned_container_ids", ["another-container"]),
    ("initial_container", "task_files_changed", True),
    ("initial_container", "effective_network_mode", "host"),
])
def test_old_or_misbound_execution_evidence_cannot_qualify(tmp_path, monkeypatch, stage, field, new_value):
    def change(record_stage, kind, value):
        if record_stage == stage and kind == "gold":
            value[field] = new_value
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError):
        qualification.validate_qualification(ref, originals[value["instance_id"]])


def test_namespace_boolean_cannot_hide_shared_host_namespace(tmp_path, monkeypatch):
    def change(stage, kind, value):
        if stage == "initial_container" and kind == "gold":
            proof = value["namespace_evidence"]
            proof["grader"]["mnt"] = proof["host"]["mnt"]
            assert proof["all_distinct"] is True
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError, match="namespace"):
        qualification.validate_qualification(ref, originals[value["instance_id"]])


def test_claimed_success_cannot_unlock_a_disabled_profile(tmp_path, monkeypatch):
    def change(stage, kind, value):
        if stage == "environment":
            value["profiles"]["psf__requests-2931"]["admission_enabled"] = False
            value["profiles"]["psf__requests-2931"]["blockers"] = ["unresolved"]
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError, match="remains disabled"):
        qualification.validate_qualification(ref, originals[value["instance_id"]])


def test_successful_completion_from_other_endpoint_is_not_reused(tmp_path, monkeypatch):
    def change(stage, kind, value):
        if stage == "qualification":
            value["controls"][0]["completion"] = value["controls"][1]["completion"]
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError, match="evidence path"):
        qualification.validate_qualification(ref, originals[value["instance_id"]])


@pytest.mark.parametrize("duplicate_in", ["plan", "qualification"])
def test_duplicate_controls_cannot_replace_missing_endpoints(tmp_path, monkeypatch, duplicate_in):
    def change(stage, kind, value):
        if stage == duplicate_in:
            rows = value["rows"] if stage == "plan" else value["controls"]
            rows[-1] = rows[0]
    ref, originals, value = evidence(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError, match="Duplicated|unique"):
        qualification.validate_qualification(ref, originals[value["instance_id"]])


def test_immutable_receipt_tampering_is_detected(tmp_path, monkeypatch):
    ref, originals, value = evidence(tmp_path, monkeypatch)
    receipt = Path(value["controls"][0]["receipt"]["path"])
    receipt.write_text(receipt.read_text() + " ")
    with pytest.raises(ValueError, match="Immutable"):
        qualification.validate_qualification(ref, originals[value["instance_id"]])
