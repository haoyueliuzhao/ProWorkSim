"""Actual final episode AST with retained 9000/9042 data; no live operations."""
from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
from types import SimpleNamespace

import pytest

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"

from proworksim import software_benchmark_scope_v131 as frozen_scope
from proworksim.software_benchmark_alignment_contract_v131 import VERSION as CONTRACT_VERSION
from proworksim.software_benchmark_alignment_contract_v131 import condition, validate_condition
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_episode_v132 import build_episode, normalize_project_closure
from proworksim.software_benchmark_host_memory_v132 import park_snapshot


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "runs/software-benchmark-v131/fixed-organization-50-r1"


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("This retained-data control cannot perform external operations")
    for name in ("connect", "bind", "sendto"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    original_popen = subprocess.Popen
    def only_local_export(command, **kwargs):
        cwd = Path(kwargs.get("cwd", "/")).resolve()
        arguments = list(command[1:])
        while arguments[:1] == ["-c"]:
            arguments = arguments[2:]
        if (command[0] not in {"/bin/git", "/usr/bin/git"}
                or cwd.name != "git" or cwd.parent.parent != Path("/tmp")
                or not cwd.parent.name.startswith("proworksim-v061-original-export-")
                or not arguments or arguments[0] not in {
                    "init", "hash-object", "read-tree", "update-index", "write-tree", "diff", "apply"}
                or kwargs.get("env", {}).get("GIT_CONFIG_NOSYSTEM") != "1"):
            return deny(command)
        return original_popen(command, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", only_local_export)


def build():
    # This fake authority is only for constructing actual function bindings.
    # Neither run_episode nor any Docker/resource function is called here.
    return build_episode(scope=frozen_scope, guard=lambda *a, **kw: {
        "status": "approved", "execution_alignment_version": CONTRACT_VERSION,
        "source_index": {"CPU_construction_only": True}})


@pytest.mark.parametrize("index", [9000, 9042])
def test_actual_export_branch_retains_original_candidate_and_delivery(index, tmp_path):
    source = BATCH / "episodes" / str(index)
    controller = source / "controller-output"
    child = json.loads((controller / "controller-result.json").read_bytes())
    assert child["status"] == "closed"
    original_keys = set(child["project_closure"])
    assert "controller_candidate_lock" in original_keys and "project_candidate_lock" not in original_keys
    row = next(r for r in json.loads((BATCH / "execution-plan.json").read_bytes())["rows"]
               if r["slot_index"] == index)
    output = tmp_path / str(index)
    target = output / "controller-output"
    target.mkdir(parents=True)
    needed = ["controller-result.json", "initial-sync-preflight.json", "model-ledger/ledger.json"]
    for value in child["project_closure"].values():
        if isinstance(value, dict) and set(value) == {"path", "bytes", "sha256"}:
            needed.append(str(Path(value["path"]).relative_to("/pws/output")))
    for relative in needed:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(controller / relative, destination)
    binding = build()
    baseline_ref = reference(source / "baseline-snapshot.json")
    baseline = json.loads((source / "baseline-snapshot.json").read_bytes())
    parked = park_snapshot(baseline, baseline_ref)
    del baseline
    terminal_path = source / "terminal-snapshot.json"
    result = {}
    calls = []
    def compressed(*args):
        calls.append("scripted_existing_transport_receipt")
        assert threading.current_thread().name.startswith("v132-host-heavy")
        return {"archive_storage": {"scripted": True}}
    def snapshot(*args, **kwargs):
        assert kwargs["name"] == "terminal-snapshot"
        assert threading.current_thread().name.startswith("v132-host-heavy")
        calls.append("retained_terminal_snapshot")
        return json.loads(terminal_path.read_bytes()), reference(terminal_path)
    namespace = {**binding._run.__globals__, "row": row, "output": output,
        "parked_baseline": parked, "baseline_ref": baseline_ref,
        "pair": SimpleNamespace(download_compressed_archive=compressed,
            claims={"actor": {"sha256": "a" * 64}}),
        "extract_controller_output": lambda *a, **kw: {"CPU_existing_files": True},
        "snapshot": snapshot, "result": result, "controller_exit": 0,
        "lifecycle_expired": threading.Event(), "diagnostic": False,
        "limits": validate_condition(condition(row["organization_id"])),
        "bridge": SimpleNamespace(join=lambda timeout: {"threads_finished": True, "errors": []}),
        "model_thread": None, "model_result": {"status": "channel_closed"},
        "gitlinks": [], "writer_ref": reference(source / "writer-quiescence.json")}
    callbacks = [node for node in ast.walk(binding.memory_transformed_ast)
                 if isinstance(node, ast.FunctionDef) and node.name == "finish_original_episode"]
    assert len(callbacks) == 1
    wrapper = ast.parse("def retained_case():\n    terminal_ref = None\n    writer_proof = {'all_quiet': True}\n")
    wrapper.body[0].body += [copy.deepcopy(callbacks[0]), *ast.parse(
        "host_memory.run_heavy(row['slot_id'], 'retained_CPU_export', finish_original_episode)\n"
        "return result\n").body]
    try:
        exec(compile(ast.fix_missing_locations(wrapper), "<v132 retained actual export branch>", "exec"), namespace)
        actual = namespace["retained_case"]()
        assert actual["status"] == "closed" and actual["candidate_lock"]
        assert actual["project_closure"]["project_candidate_lock"]["sha256"] == (
            child["project_closure"]["controller_candidate_lock"]["sha256"])
        assert bool(actual["delivery_candidate_lock"]) == child["project_closure"]["submitted"]
        assert actual["model_calls"] == child["ledger"]["attempts"]
        assert calls == ["scripted_existing_transport_receipt", "retained_terminal_snapshot"]
        assert set(child["project_closure"]) == original_keys
        # A second, conflicting source must fail; no key is silently preferred.
        conflict = {**child["project_closure"], "project_candidate_lock": {
            **child["project_closure"]["controller_candidate_lock"], "sha256": "b" * 64}}
        with pytest.raises(ValueError, match="distinct controller"):
            normalize_project_closure(conflict)
        assert all(n == 1 for n in binding.memory_integration_points.values())
        original = binding.memory_transformed_ast.body[0]
        lifecycle = next(n for n in original.body if isinstance(n, ast.Try)
            and any(isinstance(c, ast.FunctionDef) and c.name == "finish_original_episode" for c in n.body))
        cleanup_source = ast.unparse(ast.Module(body=lifecycle.finalbody, type_ignores=[]))
        assert cleanup_source.index("model_stop.set()") < cleanup_source.index("retain_and_clean_original_episode")
        assert cleanup_source.index("writers_before_host_memory_wait") < cleanup_source.index("retain_and_clean_original_episode")
    finally:
        binding.host_memory.close()
