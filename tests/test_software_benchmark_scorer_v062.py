import ast
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
