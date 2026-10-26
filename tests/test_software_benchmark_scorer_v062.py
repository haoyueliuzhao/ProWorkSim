import ast
import importlib.util
from pathlib import Path

import pytest

from proworksim import software_benchmark_grading_environment_v062 as environment
from proworksim import software_benchmark_scorer_v062 as scorer
from proworksim.software_benchmark_candidates_v054 import write_new


def test_provider_permissions_are_task_exact():
    assert environment.capabilities("psf__requests-1766") == ["NET_ADMIN", "NET_BIND_SERVICE"]
    assert environment.capabilities("psf__requests-1921") == ["NET_ADMIN", "NET_BIND_SERVICE"]
    assert environment.capabilities("psf__requests-2931") == ["NET_ADMIN"]
    assert environment.capabilities("psf__requests-5414") == ["NET_ADMIN"]
    assert environment.capabilities("django__django-13807") == []
    assert environment.provider("psf__requests-1766") is environment.tls
    assert environment.provider("psf__requests-2931") is environment.offline
    assert environment.provider("django__django-13807") is None


def test_grader_cannot_accept_host_resources():
    scorer.validate_options({"image": "sha256:fixed", "cap_add": ["SYS_ADMIN"]}, "sha256:fixed")
    for field, value in (("privileged", True), ("network_mode", "host"),
                         ("volumes", {"/host": {"bind": "/testbed"}}),
                         ("cap_add", ["NET_ADMIN"]), ("extra_hosts", {"httpbin.org": "1.2.3.4"})):
        with pytest.raises(ValueError):
            scorer.validate_options({"image": "sha256:fixed", field: value}, "sha256:fixed")


def test_candidate_is_bound_to_new_plan_slot_not_source_slot(tmp_path, monkeypatch):
    config = write_new(tmp_path / "config.json", {"instance_id": "task"})
    row = {"slot_id": "v062:task:BASE5M:1", "source_slot_id": "v056:task:REF_B5000K:0",
           "configuration": config, "measurement_kind": "capability_probe"}
    path = tmp_path / "plan.json"
    plan = write_new(path, {"resources": {"score-0": {"role": "score", "instance_id": "task",
                               "slot_id": row["slot_id"]}}, "rows": [row]})
    monkeypatch.setattr(scorer.policy, "PLAN_FILE", path)
    request = {**row, "resource_key": "score-0", "plan": plan}
    assert scorer._planned(request)[2]["instance_id"] == "task"
    request["slot_id"] = row["source_slot_id"]
    with pytest.raises(ValueError, match="slot mapping"):
        scorer._planned(request)


def test_new_providers_do_not_call_completed_version_grants():
    for name in ("software_benchmark_requests_offline_v062.py", "software_benchmark_requests_tls_v062.py",
                 "software_benchmark_tcp_transport_v062.py"):
        source = (Path(scorer.__file__).parent / name).read_text()
        tree = ast.parse(source)
        calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
        assert not any(isinstance(node, ast.Name) and node.id in {
            "require_v058_dispatch_allowed", "require_v060_rescore_allowed"} for node in calls)
        assert not any(isinstance(node, ast.Attribute) and node.attr in {
            "require_v058_dispatch_allowed", "require_v060_rescore_allowed"} for node in calls)


def test_r2_control_preparation_preserves_prior_directory(tmp_path, monkeypatch):
    path = Path(scorer.__file__).parents[2] / "tools/run_capability_grading_v062.py"
    spec = importlib.util.spec_from_file_location("grading_r2_directory_contract", path)
    grading = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grading)
    old_folder = tmp_path / "grading/control-task-gold"
    old_folder.mkdir(parents=True)
    old_request = old_folder / "request.json"
    old_request.write_text('{"original":true}')
    old_plan = tmp_path / "control-plan.json"
    old_plan.write_text('{"original":true}')
    run_root, grading_root = tmp_path / "coordinator-r2", tmp_path / "grading-r2"
    monkeypatch.setattr(grading, "RUN_ROOT", run_root)
    monkeypatch.setattr(grading.policy, "GRADING_ROOT", grading_root)
    plan_path = tmp_path / "plan.json"
    write_new(plan_path, {"unchanged": True})
    monkeypatch.setattr(grading.policy, "PLAN_FILE", plan_path)
    config = write_new(tmp_path / "config.json", {"instance_id": "task"})
    manifest = write_new(tmp_path / "manifest.json", {"manifest": True})
    monkeypatch.setattr(grading.policy, "create_plan", lambda: {"environments": {"task": {"configuration": config}}})
    monkeypatch.setattr(grading, "prepare_manifest", lambda: manifest)
    monkeypatch.setattr(grading, "prepare_reused_qualifications", dict)
    monkeypatch.setattr(grading, "selected_cpus", lambda lane: "0,1,2,3")
    monkeypatch.setattr(grading.environment, "request_fields", lambda task: {})
    refs = grading.prepare_controls()
    assert {Path(ref["path"]).parent for ref in refs} == {
        grading_root / "control-task-gold", grading_root / "control-task-empty"}
    assert (run_root / "control-plan.json").is_file()
    assert old_request.read_text() == old_plan.read_text() == '{"original":true}'


def test_r2_request_directory_and_environment_bindings(tmp_path, monkeypatch):
    grading_root = tmp_path / "grading-r2"
    monkeypatch.setattr(scorer.policy, "GRADING_ROOT", grading_root)
    folder = grading_root / "environments"
    folder.mkdir(parents=True)
    offline_ref = write_new(folder / "offline.json", {"marker": "r2"})
    write_new(folder / "bindings.json", {"offline": offline_ref})
    assert environment.request_fields("psf__requests-2931")["environment_revision"] == offline_ref
    resource, config = {"role": "control", "instance_id": "task"}, {"instance_id": "task"}
    monkeypatch.setattr(scorer, "_planned", lambda request: ({}, resource, config))
    monkeypatch.setattr(scorer.policy, "require_v062_allowed", lambda *args, **kwargs: {})
    monkeypatch.setattr(scorer.policy, "cpu_set", lambda *args: "0,1,2,3")
    monkeypatch.setattr(scorer, "validate_base", lambda config: {})
    monkeypatch.setattr(scorer.environment, "validate_request", lambda *args: None)
    manifest = write_new(tmp_path / "manifest.json", {})
    monkeypatch.setattr(scorer, "installation_manifest", dict)
    request = {"version": scorer.VERSION, "limits": scorer.LIMITS, "resource_key": "control-task-gold",
        "scorer_manifest": manifest, "cpuset_cpus": "0,1,2,3",
        "directory": str(grading_root / "control-task-gold")}
    assert scorer.validate_request(request)[1] == resource
    request["directory"] = str(tmp_path / "grading/control-task-gold")
    with pytest.raises(ValueError, match="output or four-CPU"):
        scorer.validate_request(request)
