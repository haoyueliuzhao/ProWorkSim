"""Narrow controls for repository search, S1 visibility and honest delivery evidence."""
import copy

from proworksim import software_benchmark_managed_v056 as managed
from proworksim import software_benchmark_world_v054 as legacy
from proworksim import software_benchmark_world_v056 as module
from proworksim.repository_sources_v054 import RepositorySources, capture_repository, tree_manifest
from proworksim.storage import json_bytes


def prepare(tmp_path):
    source = tmp_path / "public"
    source.mkdir()
    (source / "a.py").write_text("needle\n" + "x" * 60 + "needle\nneedle\n")
    (source / "pkg").mkdir()
    (source / "pkg/b.py").write_text("start\nneedle elsewhere\n")
    (source / "protected").mkdir()
    (source / "protected/public_test.py").write_text("needle public fixture\n")
    (source / "asset.bin").write_bytes(b"\xffneedle")
    (source / "alias").symlink_to("a.py")
    (tmp_path / "hidden-verifier.txt").write_text("SECRET_ANSWER_NEEDLE")
    identity = {"instance_id": "fixture__managed-056", "repo": "fixture/managed",
                "base_commit": "a" * 40, "dataset_revision": "b" * 40}
    manifest = capture_repository(
        source, tmp_path / "snapshot", task_id=identity["instance_id"],
        problem_statement="Synthetic public issue.", source_identity=identity,
        file_policy={"readonly_prefixes": ["protected"]})
    calls = []

    def runner(*, files, entry_metadata, task, run_root):
        calls.append(copy.deepcopy(files))
        return {"execution": {"executed": True, "scope": "Synthetic callback; no real tests/model",
                "input_tree_sha256": tree_manifest(files, entry_metadata)["tree_sha256"]},
            "passed": False, "groups": {"public_fixture": {
                "status": "failed", "executed": True, "passed": False,
                "tests": [{"test_id": "fixture", "passed": False}]}}}

    provider = RepositorySources(manifest, runner=runner)
    prepared = module.build_software_collaboration_case(
        identity["instance_id"], tmp_path / "prepared", provider=provider)
    port = module.SoftwareCollaborationPort(
        prepared.world.session(module.MEMBERS[0], module.PROJECT), module.MEMBERS[0])
    return prepared, port, calls


def call(port, tool, **arguments):
    value = port.call(tool, **arguments)
    assert value["ok"], value
    return value["result"]


def test_search_completes_across_scan_boundaries_without_hidden_or_binary_access(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SCAN_CHARACTERS", 64)
    monkeypatch.setattr(module, "SCAN_FILES", 2)
    monkeypatch.setattr(module, "RESULTS_PER_PAGE", 2)
    prepared, port, executions = prepare(tmp_path)
    rows, cursor, pages = [], None, 0
    while True:
        page = call(port, "search_repository", text="needle", **({"cursor": cursor} if cursor else {}))
        pages += 1
        assert pages <= 10
        assert page["scanned_characters"] <= 64
        assert page["considered_files"] <= 2
        assert len(page["matches"]) <= 2
        assert len(json_bytes(page["matches"]).decode()) <= module.RESULT_CHARACTERS
        rows.extend((row["path"], row["line"]) for row in page["matches"])
        cursor = page["next_cursor"]
        if page["complete"]:
            assert cursor is None
            break
        assert cursor is not None
    assert rows == [("a.py", 1), ("a.py", 2), ("a.py", 3),
                    ("pkg/b.py", 2), ("protected/public_test.py", 1)]
    assert pages > 1
    scoped = call(port, "search_repository", text="needle", path_prefix="pkg/")
    assert [row["path"] for row in scoped["matches"]] == ["pkg/b.py"]
    assert scoped["complete"]
    # No host walk or material outside the granted repository snapshot.
    hidden = call(port, "search_repository", text="SECRET_ANSWER_NEEDLE")
    while not hidden["complete"]:
        assert hidden["matches"] == []
        hidden = call(port, "search_repository", text="SECRET_ANSWER_NEEDLE", cursor=hidden["next_cursor"])
    assert hidden["matches"] == [] and executions == []
    events = prepared.world.store.load()["software_events"]
    assert any(event["kind"] == "repository_search" for event in events)


def test_search_rejects_stale_query_scope_and_unregistered_actor(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SCAN_CHARACTERS", 32)
    prepared, port, _ = prepare(tmp_path)
    first = call(port, "search_repository", text="needle")
    cursor = first["next_cursor"]
    assert cursor
    assert call(port, "search_repository", text="needle", cursor="")["matches"] == first["matches"]
    assert call(port, "search_repository", text="needle", cursor=None)["matches"] == first["matches"]
    assert not port.call("search_repository", text="elsewhere", cursor=cursor)["ok"]
    assert not port.call("search_repository", text="needle", path_prefix="pkg", cursor=cursor)["ok"]
    for prefix in ("../", "/tmp", ".git"):
        assert not port.call("search_repository", text="needle", path_prefix=prefix)["ok"]
    assert not prepared.world.session("operator", module.PROJECT).call("search_repository", text="needle")["ok"]
    assert not port.call("search_repository", text="needle", source_reference=first["source_reference"])["ok"]
    call(port, "write_file", path="pkg/b.py", text="changed\n")
    assert not port.call("search_repository", text="needle", cursor=cursor)["ok"]


def test_delivery_guidance_preserves_explicit_same_version_requirements(tmp_path):
    prepared, port, executions = prepare(tmp_path)
    first = port.observe()
    assert first["interface_revision"] == module.VERSION
    assert first["delivery_status"]["source_reference"] == first["workspace_reference"]
    assert first["delivery_status"]["next_explicit_tool"] == "run_tests"
    assert call(port, "delivery_status")["legal_delivery_id"] is None
    assert executions == [] and prepared.world.test_budget.snapshot()["used"] == 0
    call(port, "write_file", path="pkg/b.py", text="changed = 1\n")
    assert not port.call("submit_integration", message="premature")["ok"]
    call(port, "run_tests")
    status = call(port, "delivery_status")
    assert status["public_test_executed"] and status["public_test_passed"] is False
    assert status["next_explicit_tool"] == "fix_patch"
    fixed = call(port, "fix_patch", task_ids=[], message="current explicit patch")
    assert call(port, "delivery_status")["next_explicit_tool"] == "submit_integration"
    delivery = call(port, "submit_integration", message="explicit delivery with real failed public test")
    status = port.observe()["delivery_status"]
    assert status["legal_delivery_id"] == delivery["delivery_id"]
    assert status["fixed_patch_id"] == fixed["patch_id"]
    assert status["next_explicit_tool"] == "staff_done"
    call(port, "write_file", path="pkg/b.py", text="changed = 2\n")
    stale = call(port, "delivery_status")
    assert stale["source_reference"] != delivery["source_reference"]
    assert not stale["public_test_executed"] and stale["legal_delivery_id"] is None
    assert not port.call("submit_integration", message="must not reuse old version proof")["ok"]
    assert len(executions) == 1 and prepared.world.test_budget.snapshot()["used"] == 1


def test_s1_visibility_is_conditional_and_real_managed_gateway_uses_v056(tmp_path):
    prepared, _, _ = prepare(tmp_path)
    gateway = managed.managed_port(prepared)
    names = {tool["name"] for tool in gateway.tools()}
    assert {"search_repository", "delivery_status", "work_history_search"} <= names
    assert not module.PEER_TOOLS & names
    assert not {"bash", "terminal", "spawn_member"} & names
    assert module.PEER_TOOLS <= {tool["name"] for tool in legacy.TOOLS}
    future_multi_case = copy.deepcopy(prepared.case)
    future_multi_case["member_limits"].update(max_live_members=2, births_enabled=True)
    assert module.PEER_TOOLS <= {tool["name"] for tool in module.tool_definitions(future_multi_case)}
    result = gateway.call("delivery_status", request_key="status-1", association={})
    assert result["ok"]
    assert gateway.call("send_message", request_key="peer-1", association={}, recipient="member_002", body="hello")["ok"] is False
