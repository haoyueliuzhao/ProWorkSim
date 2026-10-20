"""Synthetic real-World controls for the explicitly expanded managed interface."""
import copy
import json

from proworksim import software_benchmark_world_v054 as module
from proworksim.repository_sources_v054 import RepositorySources, capture_repository, tree_manifest

TASK_ID = "fixture__managed-1"
IDENTITY = {"instance_id": TASK_ID, "repo": "fixture/managed", "base_commit": "a" * 40,
            "dataset_revision": "b" * 40}


def prepare(tmp_path, *, extra_files=0, large_file=False):
    source = tmp_path / "public"
    source.mkdir()
    (source / "main.py").write_text("value = 0\n")
    (source / "entry.sh").write_text("#!/bin/sh\nexit 0\n")
    (source / "entry.sh").chmod(0o755)
    (source / "asset.bin").write_bytes(b"\xff\x00data")
    (source / "alias").symlink_to("main.py")
    (source / "protected").mkdir()
    (source / "protected/test_public.py").write_text("# readonly public fixture\n")
    for index in range(extra_files):
        (source / f"module_{index:04}.py").write_text(f"value = {index}\n")
    if large_file:
        (source / "long.py").write_text("needle" + "x" * 400_000 + "\nlast\n")
    manifest = capture_repository(
        source, tmp_path / "source", task_id=TASK_ID, problem_statement="Original public fixture.",
        source_identity=IDENTITY, file_policy={"readonly_prefixes": ["protected"]})
    calls = []

    def runner(*, files, entry_metadata, task, run_root):
        calls.append(copy.deepcopy(files))
        execution = {"executed": True, "input_tree_sha256": tree_manifest(files, entry_metadata)["tree_sha256"],
                     "scope": "Synthetic programmed public callback; no actual repository tests or model"}
        return {"execution": execution, "passed": False, "groups": {
            "public_fixture": {"status": "failed", "executed": True, "passed": False,
                               "tests": [{"test_id": "synthetic_public", "passed": False}]}}}

    provider = RepositorySources(manifest, runner=runner)
    prepared = module.build_software_collaboration_case(TASK_ID, tmp_path / "prepared", provider=provider)
    port = module.SoftwareCollaborationPort(prepared.world.session(module.MEMBERS[0], module.PROJECT),
                                            module.MEMBERS[0])
    return prepared, port, calls


def call(port, name, **arguments):
    result = port.call(name, **arguments)
    assert result["ok"], result
    return result["result"]


def bundle(prepared):
    world = prepared.world
    world.state = world.store.load()
    return world._bundle(module.MEMBERS[0])


def test_real_registered_operations_version_tests_and_fixed_delivery(tmp_path):
    prepared, port, calls = prepare(tmp_path)
    names = {tool["name"] for tool in port.tools()}
    assert {"create_file", "delete_file", "rename_file", "read_task"} <= names
    assert not {"terminal", "bash", "run_command", "spawn_member"} & names
    first_version = bundle(prepared)[1]
    call(port, "create_file", path="new/package/helper.py", text="answer = 1\r\n")
    created_version = bundle(prepared)[1]
    assert created_version != first_version
    call(port, "run_tests")
    fixed = call(port, "fix_patch", task_ids=[], message="explicit current version")
    old_bundle = copy.deepcopy(bundle(prepared)[2])
    delivery = call(port, "submit_integration", message="failed public tests still permit a fixed delivery")
    assert delivery["source_reference"] == fixed["source_reference"] and len(calls) == 1
    call(port, "rename_file", path="entry.sh", new_path="scripts/entry.sh")
    renamed_version = bundle(prepared)[1]
    assert renamed_version != created_version
    assert not port.call("submit_integration", message="old test/fix must not cover a new version")["ok"]
    call(port, "run_tests")
    assert not port.call("submit_integration", message="new test without a current fix")["ok"]
    call(port, "delete_file", path="asset.bin")
    assert bundle(prepared)[1] != renamed_version
    assert not port.call("submit_integration", message="test became stale after delete")["ok"]
    call(port, "run_tests")
    current = call(port, "fix_patch", task_ids=[], message="full filesystem delta")
    call(port, "submit_integration", message="last legal version")
    world = prepared.world
    patch = world._software()["patches"][current["patch_id"]]
    assert patch["added_paths"] == ["new/package/helper.py", "scripts/entry.sh"]
    assert patch["deleted_paths"] == ["asset.bin", "entry.sh"]
    assert patch["modified_paths"] == []
    assert set(patch["changed_paths"]) == set(patch["added_paths"] + patch["deleted_paths"])
    assert bundle(prepared)[2]["entry_metadata"]["scripts/entry.sh"]["mode"] == "100755"
    assert world._bundle(module.MEMBERS[0], reference=delivery["source_reference"])[2] == old_bundle
    assert len(calls) == 3 and world.test_budget.snapshot()["used"] == 3


def test_rejected_paths_readonly_collisions_and_types_have_no_source_effect(tmp_path):
    prepared, port, _ = prepare(tmp_path)
    original_version, original_bundle = bundle(prepared)[1:]
    trials = [
        ("create_file", {"path": "../outside.py", "text": "bad"}),
        ("create_file", {"path": ".git/config", "text": "bad"}),
        ("create_file", {"path": "main.py", "text": "overwrite"}),
        ("create_file", {"path": "main.py/child.py", "text": "ancestor conflict"}),
        ("create_file", {"path": "protected/new.py", "text": "readonly prefix"}),
        ("delete_file", {"path": "protected/test_public.py"}),
        ("rename_file", {"path": "main.py", "new_path": "protected/test_public.py"}),
        ("rename_file", {"path": "main.py", "new_path": "entry.sh"}),
        ("rename_file", {"path": "main.py", "new_path": "alias/child.py"}),
        ("write_file", {"path": "asset.bin", "text": "not a base64 rewrite"}),
        ("replace_file", {"path": "alias", "old": "main.py", "new": "entry.sh"}),
    ]
    for name, args in trials:
        assert not port.call(name, **args)["ok"], (name, args)
        assert bundle(prepared)[1:] == (original_version, original_bundle)
    call(port, "rename_file", path="asset.bin", new_path="assets/icon.bin")
    call(port, "rename_file", path="alias", new_path="alias_moved")
    assert bundle(prepared)[2]["files"]["assets/icon.bin"] == original_bundle["files"]["asset.bin"]
    assert bundle(prepared)[2]["entry_metadata"]["alias_moved"]["kind"] == "symlink"


def test_large_tree_pages_large_line_edits_and_stale_cursor(tmp_path):
    prepared, port, calls = prepare(tmp_path, extra_files=205, large_file=True)
    observation = port.observe()
    assert observation["file_count"] == 211
    assert len(json.dumps(observation)) < 20_000
    assert len(observation["editable_paths"]) <= module.PAGE_FILES
    page, paths = call(port, "list_files"), []
    stale = page["next_cursor"]
    while True:
        paths.extend(row["path"] for row in page["files"])
        assert len(page["files"]) <= module.PAGE_FILES
        if page["next_cursor"] is None:
            break
        page = call(port, "list_files", cursor=page["next_cursor"])
    assert paths == sorted(bundle(prepared)[2]["files"])
    first = call(port, "read_file", path="long.py")
    second = call(port, "read_file", path="long.py", cursor=first["next_cursor"])
    content = bundle(prepared)[2]["files"]["long.py"]
    assert first["text"] + second["text"] == content[:2 * module.PAGE_CHARACTERS]
    assert len(first["text"]) <= module.PAGE_CHARACTERS
    search = call(port, "search_file", path="long.py", text="needle")
    assert len(search["matches"][0]["text"]) <= 320
    replacement = "z" * 400_001 + "\n"
    call(port, "write_file", path="long.py", text=replacement)
    assert bundle(prepared)[2]["files"]["long.py"] == replacement
    assert not port.call("list_files", cursor=stale)["ok"]
    assert not port.call("read_file", path="long.py", cursor=first["next_cursor"])["ok"]
    assert calls == []


def test_fixed_patch_integration_preserves_structural_changes(tmp_path):
    prepared, port, _ = prepare(tmp_path)
    call(port, "create_file", path="new.py", text="new = 1\n")
    patch = call(port, "fix_patch", task_ids=[], message="new file in cumulative fixed patch")
    call(port, "delete_file", path="new.py")
    call(port, "write_file", path="main.py", text="value = 2\n")
    result = call(port, "integrate_patch", patch_id=patch["patch_id"])
    assert result["conflicts"] == []
    current = bundle(prepared)[2]
    assert current["files"]["new.py"] == "new = 1\n"
    assert current["files"]["main.py"] == "value = 2\n"
    assert patch["patch_id"] in current["included_patch_ids"]
