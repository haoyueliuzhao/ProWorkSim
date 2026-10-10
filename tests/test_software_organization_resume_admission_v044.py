"""Boundary controls for exact original-inventory continuation; no model replay."""
import copy
import hashlib
import io
import json
import tarfile
from types import SimpleNamespace

import pytest

from scripts import software_organization_resume_admission_v044 as admission


def inventory():
    plan = {"assignments": {}, "cases": {}}
    for block, (root, seed, conditions, first, owner) in admission.BLOCK_LAYOUT.items():
        units, cases = [], []
        for condition in conditions:
            unit = {"slot_id": "org44-" + block.removeprefix("block-") + "-" + condition,
                "case_id": f"sc-record-{root}-handoff-v040", "root_family": "handoff_development",
                "sampling_seed": seed, "condition": condition, "first_member": first,
                "diagnostic_a_owner": owner, "information_condition": "shared" if condition[0] == "S" else "split",
                "framing_condition": "base" if condition[1] == "B" else "team"}
            units.append(unit)
            cases.append({**unit, "team_limits": dict(admission.TEAM_LIMITS),
                          "active_roles": ["member_001", "member_002"]})
        plan["assignments"][block], plan["cases"][block] = units, cases
    return plan


def test_resume_is_exactly_original_remaining_twelve():
    result = admission.validate_inventory(inventory())
    assert tuple(result) == admission.REMAINING_BLOCKS
    assert sum(map(len, result.values())) == 12
    assert admission.FIRST_BLOCK not in result
    assert [row["condition"] for row in result["block-r0-s0"]] == ["ST", "PB", "PT", "SB"]


@pytest.mark.parametrize("field,value", [("sampling_seed", 202610100443),
    ("first_member", "member_001"), ("diagnostic_a_owner", "member_001"),
    ("slot_id", "org44-r1-s0-PT"), ("condition", "PB")])
def test_relabelled_seed_order_owner_or_slot_rejected(field, value):
    plan = inventory()
    plan["assignments"]["block-r0-s0"][0][field] = value
    with pytest.raises(ValueError, match="changed"):
        admission.validate_inventory(plan)


def test_new_budget_does_not_transfer_unused_old_tokens():
    plan = inventory()
    plan["cases"]["block-r0-s0"][0]["team_limits"]["max_total_tokens"] += 107154
    with pytest.raises(ValueError, match="per-slot budget"):
        admission.validate_inventory(plan)


def old_run(tmp_path):
    plan = inventory()
    progress = [{"slot_id": unit["slot_id"]} for unit in plan["assignments"][admission.FIRST_BLOCK]]
    for row in progress:
        (tmp_path / admission.FIRST_BLOCK / "actual/episodes" / row["slot_id"]).mkdir(parents=True)
    states = {block: {"worker": block, "status": "stopped", "attempted": False,
                     "stop_reason": "first_block_mechanism_gate", "elapsed_gpu_seconds": 0}
              for block in admission.BLOCK_LAYOUT}
    states[admission.FIRST_BLOCK] = {"status": "complete", "attempted": True, "exit_code": 0, "stop_reason": None}
    return plan, {"status": "stopped_by_first_block_gate", "states": states}, {"status": "complete", "rows": progress}, progress


def test_never_started_requires_state_and_all_original_output_boundaries(tmp_path):
    plan, supervisor, report, progress = old_run(tmp_path)
    rows = admission.validate_never_started(tmp_path, supervisor, report, progress, plan["assignments"])
    assert len(rows) == 3
    assert all(row["original_worker_path_absent"] for row in rows)


@pytest.mark.parametrize("trace", ["empty_directory", "attempted", "pid", "extra_output"])
def test_missing_result_does_not_establish_never_started(tmp_path, trace):
    plan, supervisor, report, progress = old_run(tmp_path)
    if trace == "empty_directory":
        (tmp_path / "block-r0-s0").mkdir()
    elif trace == "attempted":
        supervisor["states"]["block-r0-s0"]["attempted"] = True
    elif trace == "pid":
        supervisor["states"]["block-r0-s0"]["pid"] = 123
    else:
        (tmp_path / admission.FIRST_BLOCK / "actual/episodes/org44-r0-s0-ST").mkdir()
    with pytest.raises(ValueError):
        admission.validate_never_started(tmp_path, supervisor, report, progress, plan["assignments"])


def test_old_r_and_failed_gate_must_match_pre_resume_publication(monkeypatch, tmp_path):
    supervisor = {"status": "stopped_by_first_block_gate"}
    report = {"rows": [{"R": 1}, {"R": 0}, {"R": 0}, {"R": 0}]}
    gate = {"passed": False}
    published = {"supervisor": supervisor, "first_block_gate": gate, "known": 4, "scheduled": 16,
        "workers": {**{block: {"report": None} for block in admission.REMAINING_BLOCKS},
                    admission.FIRST_BLOCK: {"report": report}}}
    raw = json.dumps(published).encode()
    monkeypatch.setattr(admission.subprocess, "check_output", lambda *a, **k: raw)
    assert admission.bind_published_original(tmp_path, supervisor, report, gate)["old_worker_results_and_stop_exactly_preserved"]
    altered = copy.deepcopy(report)
    altered["rows"][1]["R"] = 1
    with pytest.raises(ValueError, match="immutable published"):
        admission.bind_published_original(tmp_path, supervisor, altered, gate)


def test_consumed_measurement_map_cannot_redirect_verified_slot_list(tmp_path):
    original = [{"slot_id": str(i), "R": 0, "submitted": False,
                 "slot_result": {"sha256": "result"}, "original_feedback": {"sha256": "feedback"}}
                for i in range(4)]
    refs = [{"path": f"measurement-{i}", "sha256": str(i)} for i in range(4)]
    summary = {"version": "organization-feedback-opportunities-v0.44r1", "passed": True,
        "read_only": True, "original_artifacts_unchanged": True, "new_model_calls": 0,
        "new_tokenizer_calls": 0, "new_test_or_acceptance_executions": 0,
        "slot_ids": [row["slot_id"] for row in original], "original_gate": {"sha256": "old"},
        "revised_gate": {"path": "gate"}, "original_slots": original, "slot_measurements": refs,
        "measurements_by_slot": {str(i): refs[(i + 1) % 4] for i in range(4)}}
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary))
    reader = SimpleNamespace(path=lambda ref: ref,
        read=lambda ref: {"passed": True, "measured_slots": 4, "reasons": []}
        if ref.get("path") == "gate" else summary)
    with pytest.raises(ValueError, match="lookup differs"):
        admission.bind_remeasurement(path, reader, original, {"sha256": "old"}, tmp_path)


@pytest.mark.parametrize("change", ["runtime_bytes", "new_runtime_dependency"])
def test_model_visible_source_cannot_be_changed_under_measurement_label(monkeypatch, tmp_path, change):
    before = b"PROMPT = 'original'\n"
    name = "src/proworksim/runtime.py"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as stream:
        entry = tarfile.TarInfo(name)
        entry.size = len(before)
        stream.addfile(entry, io.BytesIO(before))
    monkeypatch.setattr(admission.subprocess, "check_output", lambda *a, **k: archive.getvalue())
    tree = hashlib.sha256(name.encode() + before).hexdigest()
    monkeypatch.setattr(admission, "ORIGINAL_TREE", tree)
    for folder in admission.CODE_ROOTS:
        (tmp_path / folder).mkdir()
    (tmp_path / name).parent.mkdir()
    (tmp_path / name).write_bytes(before)
    (tmp_path / "scripts/software_organization_resume_admission_v044.py").write_text("# read-only control\n")
    if change == "runtime_bytes":
        (tmp_path / name).write_text("PROMPT = 'new advice'\n")
    else:
        (tmp_path / "src/proworksim/extra_prompt.py").write_text("PROMPT = 'new advice'\n")
    with pytest.raises(ValueError, match="bytes changed|undeclared added"):
        admission.source_audit(tmp_path)
