import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_bridge_managed_v052 as managed
from proworksim.software_bridge_sources_v052 import ref
from proworksim.storage import digest, json_bytes
from scripts import software_bridge_v052 as host


def design():
    path = Path(__file__).resolve().parents[1] / "docs/experiments/software-bridge-v052-design.json"
    return json.loads(path.read_text())


def test_fixed_panel_and_source_input_gates():
    specification = design()
    rows = host.inventory(specification)
    assert len(rows) == 12 and len({row["seed"] for row in rows}) == 6
    changed = copy.deepcopy(specification)
    changed["rows"][0]["condition"] = "PS1"
    with pytest.raises(ValueError, match="task/seed/order/budget"):
        host.inventory(changed)
    admission = {"version": "v052-openhands-bridge-model-admission-v1", "released": True,
        "purpose": host.PURPOSE, "unresolved_blockers": [], "checks": dict.fromkeys(host.CHECKS, True),
        "design": {"sha256": "synthetic-design"},
        "source_qualification": {"sha256": "synthetic-source-qualification"},
        "test_runtime": {"sha256": "synthetic-test-runtime"},
        "reference_runtime": {"sha256": "synthetic-reference-runtime"}, "resources": {
            "allowed_gpu_indices": list(range(8)), "max_residents": 4, "idle_only_admission": False}}
    sources = {"completed": True, "passed": True, "fixture_only": False,
               "qualified_case_ids": list(host.TASKS), "runtime_manifest": admission["test_runtime"]}
    inputs = {"completed": True, "passed": True, "fixture_only": False, "actual_initial_SDK_requests": 12,
              "new_model_calls": 0, **{key: admission[key] for key in
              ("design", "source_qualification", "test_runtime", "reference_runtime")}}
    assert host.gate_records(admission, specification, sources, inputs) == rows
    for field, value in (("qualified_case_ids", list(host.TASKS[:-1])), ("passed", False)):
        with pytest.raises(ValueError, match="All six source"):
            host.gate_records(admission, specification, {**sources, field: value}, inputs)
    with pytest.raises(ValueError, match="All six source"):
        host.gate_records(admission, specification, sources, {**inputs, "new_model_calls": 1})
    for key in ("source_qualification", "test_runtime", "reference_runtime"):
        with pytest.raises(ValueError, match="All six source"):
            host.gate_records(admission, specification, sources, {**inputs, key: {"sha256": "different-valid-receipt"}})
    with pytest.raises(ValueError, match="All six source"):
        host.gate_records(admission, specification, {**sources, "runtime_manifest": {"sha256": "different-runtime"}}, inputs)
    with pytest.raises(ValueError, match="All six source"):
        host.gate_records(admission, specification, {**sources, "completed": False}, inputs)


def test_code_zero_and_NA_do_not_bypass_mechanical_closure():
    row = host.inventory(design())[0]
    accounting = {"all_started_settled": True, "integrity_errors": [], "known_actual_tokens": 123}
    guard = {"passed": True}
    episode_guard = dict.fromkeys(("learning_unchanged", "rng_restored_exactly",
        "software_binding_unchanged", "actor_identity_unchanged"), True)
    result = {"R_code": 0, "R_joint": None, "project_delivery_endpoint": "not_applicable"}

    def verdict(value=result, episode=episode_guard, measurement=None):
        return host.classify_closed(row, result=value, accounting=accounting, guard=guard,
            episode_guard=episode, measurement=measurement or {"decision": "continue"})

    assert verdict()["decision"] == "continue"
    assert verdict({**result, "R_code": None})["decision"] == "global_pause"
    assert verdict({**result, "R_joint": 0})["decision"] == "global_pause"
    assert verdict(episode={**episode_guard, "rng_restored_exactly": False})["decision"] == "global_pause"
    assert verdict(measurement={"decision": "measurement_pending"})["decision"] == "global_pause"
    row = {**row, "condition": "PS1"}
    assert verdict({"R_code": 0, "R_joint": 0, "calibration_condition": "P", "slot_id": row["slot_id"]})["decision"] == "continue"


def test_private_host_and_managed_loop_preserve_original_modules():
    original_version = host.original_host.VERSION
    original_frozen = host.original_host.frozen
    supervisor, evidence = host.supervisor_binding()
    assert evidence["changed_worker_module_literals"] == 1
    assert evidence["worker_completion_code_unchanged"] is True
    assert supervisor.__globals__["frozen"] is host.frozen
    assert host.original_host.frozen is original_frozen
    assert host.original_host.VERSION == original_version
    function, adaptation = managed.collector_binding()
    assert adaptation["changed_import_sites"] == 2
    assert function.__globals__["run_fragment"] is managed.collector.run_fragment
    assert function.__globals__["build_runtime"] is managed.collector.build_runtime
    assert function.__globals__["VERSION"] == managed.collector.VERSION


def test_managed_terminal_locked_before_fixed_score_and_cannot_change(tmp_path, monkeypatch):
    events = []
    bundle = {"files": {"module.py": "x = 1\n"}}
    source_reference = {"object_id": "synthetic-source", "version_id": "v1"}
    prepared = SimpleNamespace(source_provider=object(), case={"case_id": "synthetic"})
    monkeypatch.setattr(managed, "current_tree", lambda _: (copy.deepcopy(bundle), source_reference))

    def lock(**kwargs):
        events.append("terminal_locked")
        path = Path(kwargs["run_root"]) / "lock.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}\n")
        return ref(path)

    def fixed(*_args, **_kwargs):
        assert events == ["terminal_locked"]
        events.append("fixed_score")
        return {"submitted": False, "R": 0}

    def terminal(**_kwargs):
        assert events == ["terminal_locked", "fixed_score"]
        events.append("terminal_score")
        return {"files_sha256": digest(json_bytes(bundle["files"])),
            "reused_same_fixed_tree_assessment": False, "R_code": 0}

    monkeypatch.setattr(managed, "lock_final_candidate", lock)
    monkeypatch.setattr(managed.world_library, "assess_software_collaboration", fixed)
    monkeypatch.setattr(managed, "grade_locked_candidate", terminal)
    fixed_result = managed.assess_software_collaboration(prepared, run_root=tmp_path / "private-assessment")
    with pytest.raises(ValueError, match="only once"):
        managed.assess_software_collaboration(prepared, run_root=tmp_path / "private-assessment")
    bundle["files"]["module.py"] = "x = 2\n"
    with pytest.raises(ValueError, match="changed after"):
        managed.assess_terminal_working_tree(prepared, run_root=tmp_path / "terminal-code", fixed_assessment=fixed_result)
    assert events == ["terminal_locked", "fixed_score"]
    bundle["files"]["module.py"] = "x = 1\n"
    result = managed.assess_terminal_working_tree(prepared, run_root=tmp_path / "terminal-code", fixed_assessment=fixed_result)
    assert result["R_code"] == 0 and events[-1] == "terminal_score"
