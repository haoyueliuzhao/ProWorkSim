"""Necessary host controls for seven retained outcomes plus nine untouched slots."""
import copy
import hashlib
import io
import tarfile

import pytest

from scripts import software_organization_completion_admission_v044 as admission


def plans():
    original = {"assignments": {}, "cases": {}}
    for block, (root, seed, conditions, first, owner) in admission.previous.BLOCK_LAYOUT.items():
        units, cases = [], []
        for condition in conditions:
            unit = {"slot_id": "org44-" + block.removeprefix("block-") + "-" + condition,
                "case_id": f"sc-record-{root}-handoff-v040", "root_family": "handoff_development",
                "sampling_seed": seed, "condition": condition, "first_member": first,
                "diagnostic_a_owner": owner, "information_condition": "shared" if condition[0] == "S" else "split",
                "framing_condition": "base" if condition[1] == "B" else "team"}
            units.append(unit)
            cases.append({**unit, "active_roles": ["member_001", "member_002"],
                          "team_limits": dict(admission.previous.TEAM_LIMITS)})
        original["assignments"][block], original["cases"][block] = units, cases
    resume = {key: {block: copy.deepcopy(original[key][block]) for block in admission.BLOCKS}
              for key in ("assignments", "cases")}
    return original, resume


def test_completion_contains_only_the_nine_original_suffix_slots():
    original, resume = plans()
    result = admission.remaining_inventory(original, resume)
    assert {block: [row["condition"] for row in rows] for block, rows in result.items()} == {
        "block-r0-s0": ["PB", "PT", "SB"], "block-r0-s1": ["PT", "SB", "ST"],
        "block-r1-s1": ["ST", "PB", "PT"]}
    assert sum(map(len, result.values())) == 9
    retained = {row["slot_id"] for row in original["assignments"][admission.FIRST_BLOCK]}
    retained.update(admission.EXPECTED_FIRST.values())
    assert len(retained) == 7
    assert not retained & {row["slot_id"] for rows in result.values() for row in rows}


@pytest.mark.parametrize("change", ["seed", "allocation", "order", "budget", "prior_twelve_suffix_only"])
def test_original_coordinates_and_prior_inventory_cannot_be_redefined(change):
    original, resume = plans()
    if change == "seed":
        original["assignments"]["block-r0-s0"][1]["sampling_seed"] += 1
    elif change == "allocation":
        resume["assignments"]["block-r0-s0"][1]["diagnostic_a_owner"] = "member_001"
    elif change == "order":
        resume["assignments"]["block-r0-s0"].reverse()
    elif change == "budget":
        resume["cases"]["block-r0-s1"][2]["team_limits"]["max_total_tokens"] += 130862
    else:
        resume["assignments"]["block-r0-s0"] = resume["assignments"]["block-r0-s0"][1:]
    with pytest.raises(ValueError):
        admission.remaining_inventory(original, resume)


def old_outputs(tmp_path):
    original, _ = plans()
    old_root, resume_root = tmp_path / "original", tmp_path / "resume"
    (old_root / admission.FIRST_BLOCK).mkdir(parents=True)
    reports, progress, states = {}, {}, {}
    for block, first in admission.EXPECTED_FIRST.items():
        (resume_root / block / "actual/episodes" / first).mkdir(parents=True)
        progress[block] = [{"slot_id": first, "status": "closed", "R": 0}]
        reports[block] = {"status": "mechanism_fault" if block == "block-r0-s0" else "paused_before_next_slot",
                          "rows": progress[block]}
        states[block] = {"status": "stopped", "attempted": True, "exit_code": 0,
                         "stop_reason": None, "ended_at": 20}
    state = {"status": "closed_with_unknowns", "ended_at": 21, "states": states}
    return old_root, resume_root, original, reports, progress, state


def test_existing_workers_are_not_mistaken_for_nine_started_episodes(tmp_path):
    rows = admission.validate_unstarted(*old_outputs(tmp_path))
    assert len(rows) == 9
    assert all(row["prior_worker_was_closed"] and not row["whole_worker_replay_permitted"] for row in rows)


@pytest.mark.parametrize("trace", ["empty_suffix", "partial_preparation", "extra_progress", "old_root_suffix",
                                   "running_worker", "changed_stop"])
def test_no_result_is_not_enough_to_release_a_suffix(tmp_path, trace):
    args = old_outputs(tmp_path)
    old_root, resumed, _, reports, progress, state = args
    suffix = resumed / "block-r0-s0/actual/episodes/org44-r0-s0-PB"
    if trace == "empty_suffix":
        suffix.mkdir()
    elif trace == "partial_preparation":
        (suffix / "prepared").mkdir(parents=True)
    elif trace == "extra_progress":
        progress["block-r0-s0"].append({"slot_id": "org44-r0-s0-PB", "status": "running"})
    elif trace == "old_root_suffix":
        (old_root / "block-r0-s0/actual/episodes/org44-r0-s0-PB").mkdir(parents=True)
    elif trace == "running_worker":
        state["states"]["block-r0-s0"]["status"] = "running"
    else:
        reports["block-r0-s0"]["status"] = "complete"
    with pytest.raises(ValueError):
        admission.validate_unstarted(*args)


def policy_receipt(reward):
    return {"version": "v044-batch-stop-scope-revision-r2", "slot_id": "org44-r0-s0-ST", "decision": "continue",
        "classification": "safe_local_resource_stop", "read_only": True, "global_violations": [], "unresolved": [],
        "R_used_for_scope": False, "restart_current_member": False, "feedback_visibility_changed": False,
        "model_visible_Gamma_changed": False, "new_model_calls": 0, "new_tokenizer_calls": 0,
        "new_test_or_acceptance_executions": 0, "new_world_actions": 0,
        "formal_result": {"status": "closed", "R": reward, "submitted": bool(reward)},
        "context_blocked_feedback_ids": ["feedback-361"],
        "local_context_events": [{"classification": "safe_local_resource_stop",
            "call_id": "model-b51be34942fd42c33bc3be7d", "member": "member_001", "prompt_tokens": 14565,
            "reserved_output_tokens": 2048, "context_limit": 16384, "excess_tokens": 229,
            "team_available_tokens_at_rejection": 231277, "attempt_started": False, "new_native_output": False,
            "charged_tokens": 0, "execution_side_effect": False, "context_blocked_feedback_ids": ["feedback-361"],
            "concurrent_team_reservation_shortage": False,
            "member_remains_stopped": True, "R_used_for_classification": False,
            "submission_timing_used_for_classification": False}]}


@pytest.mark.parametrize("reward", [0, 1])
def test_receipt_scope_rule_is_not_conditioned_on_reward(reward):
    admission.validate_policy_value(policy_receipt(reward))


@pytest.mark.parametrize("change", ["erase_feedback", "restart", "score_selection", "global_fault", "pending", "fake_pool"])
def test_new_policy_cannot_erase_a_stop_or_release_untrusted_evidence(change):
    receipt = policy_receipt(1)
    if change == "erase_feedback":
        receipt["context_blocked_feedback_ids"] = []
    elif change == "restart":
        receipt["restart_current_member"] = True
    elif change == "score_selection":
        receipt["R_used_for_scope"] = True
    elif change == "global_fault":
        receipt["global_violations"] = ["identity_mismatch"]
    elif change == "pending":
        receipt["decision"] = "measurement_pending"
    else:
        receipt["local_context_events"][0]["team_available_tokens_at_rejection"] = 5016
    with pytest.raises(ValueError):
        admission.validate_policy_value(receipt)


def test_nine_slot_caps_count_old_cost_once_without_balance_transfer():
    caps = admission.budget_caps()
    assert caps["old_actual"] == {"decisions": 267, "attempts": 256, "total_tokens": 3369138, "test_runs": 26}
    assert caps["new"] == {"decisions": 1152, "attempts": 1152, "total_tokens": 4500000, "test_runs": 288}
    assert caps["combined"] == {"decisions": 1419, "attempts": 1408, "total_tokens": 7869138, "test_runs": 314}
    assert caps["unused_old_tokens"] == 130862 and caps["transfer_old_unused"] is False


@pytest.mark.parametrize("change", ["prior_source", "new_src", "missing_control"])
def test_completion_source_whitelist_does_not_relax_the_model_protocol(monkeypatch, tmp_path, change):
    name, content = "src/proworksim/frozen.py", b"PROMPT = 'old'\n"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as stream:
        entry = tarfile.TarInfo(name)
        entry.size = len(content)
        stream.addfile(entry, io.BytesIO(content))
    monkeypatch.setattr(admission.subprocess, "check_output", lambda *a, **k: archive.getvalue())
    monkeypatch.setattr(admission, "SRC_TREE", hashlib.sha256(name.encode() + content).hexdigest())
    for base in admission.previous.CODE_ROOTS:
        (tmp_path / base).mkdir()
    (tmp_path / name).parent.mkdir()
    (tmp_path / name).write_bytes(content)
    for path in admission.ALLOWED_NEW_CODE:
        (tmp_path / path).write_text("# host control only\n")
    if change == "prior_source":
        (tmp_path / name).write_text("PROMPT = 'changed'\n")
    elif change == "new_src":
        (tmp_path / "src/proworksim/extra.py").write_text("PROMPT = 'new advice'\n")
    else:
        (tmp_path / "tests/test_organization_stop_policy_v044.py").unlink()
    with pytest.raises(ValueError):
        admission.source_audit(tmp_path)
