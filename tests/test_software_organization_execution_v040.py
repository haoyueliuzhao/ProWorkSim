"""Finite v040 inventory, source delta and reporting contracts; no GPU/model."""
from collections import Counter
import hashlib
import io
import os
import tarfile

import pytest

from scripts import software_organization_v040 as runner
from scripts.run_ne_v021 import write


def plan_at(root):
    value = {"source": {"code_commit": "CPU-fixture", "code_dirty": False},
             "assignments": runner.assignments()}
    write(root / "plan.json", value)
    return value


def recorded(root, worker, unit, *, reward, status="closed", calls=3):
    row = {**unit, "status": status, "R": reward, "submitted": reward == 1,
        "usage": {"decisions": calls + 1, "attempts": calls, "prompt_tokens": calls * 10,
                  "completion_tokens": calls * 2, "total_tokens": calls * 12,
                  "output_bearing_calls": calls, "budget_charged_tokens": calls * 12,
                  "uncertain_usage_attempts": 0},
        "team_budget": {"tests": {"used": 2}},
        "member_lifecycle": {"initial_members": ["member_001", "member_002"],
                             "cumulative_births": 2, "member_requested_births": 0}}
    write(root / worker / "actual/episodes" / unit["slot_id"] / "slot-result.json", row)
    return row


def test_four_condition_blocks_preserve_information_assignment_and_first_member_balance():
    inventory = runner.assignments()
    units = [unit for group in inventory.values() for unit in group]
    assert len(inventory) == 4
    assert len(units) == len({u["slot_id"] for u in units}) == 16
    assert Counter(u["condition"] for u in units) == dict.fromkeys(("SB", "ST", "PB", "PT"), 4)
    assert {u["case_id"] for u in units} == {"sc-record-views-handoff-v040", "sc-record-catalog-handoff-v040"}
    assert {u["sampling_seed"] for u in units} == {202610090301, 202610090302}
    assert Counter(group[0]["condition"] for group in inventory.values()) == dict.fromkeys(runner.CONDITIONS, 1)
    starts, owners, first_holds_a = [], [], []
    for group in inventory.values():
        assert len(group) == 4
        assert len({u["case_id"] for u in group}) == len({u["sampling_seed"] for u in group}) == 1
        assert len({u["first_member"] for u in group}) == len({u["diagnostic_a_owner"] for u in group}) == 1
        starts.append(group[0]["first_member"])
        owners.append(group[0]["diagnostic_a_owner"])
        first_holds_a.append(group[0]["first_member"] == group[0]["diagnostic_a_owner"])
        assert {u["information_condition"] for u in group} == {"shared", "split"}
        assert {u["framing_condition"] for u in group} == {"base", "team"}
    assert Counter(starts) == Counter(owners) == {"member_001": 2, "member_002": 2}
    assert Counter(first_holds_a) == {True: 2, False: 2}
    for r in range(2):
        a, b = inventory[f"block-r{r}-s0"][0], inventory[f"block-r{r}-s1"][0]
        assert a["first_member"] != b["first_member"]
        assert (a["first_member"] == a["diagnostic_a_owner"]) != (b["first_member"] == b["diagnostic_a_owner"])
    assert runner.LIMITS["max_new_episodes"] == 16
    assert runner.LIMITS["max_new_backward_calls"] == 0


def test_factorial_contrasts_use_all_four_conditions_for_main_effect_and_interaction():
    group = {c: {"status": "closed", "R": int(c == "PT")} for c in runner.CONDITIONS}
    value = runner.block_contrasts(group)
    assert value["complete"] is True
    assert value["split_minus_shared_base"] == value["team_minus_base_shared"] == 0
    assert value["split_minus_shared_team"] == value["team_minus_base_split"] == 1
    assert value["information_main_effect"] == value["framing_main_effect"] == .5
    assert value["interaction"] == 1
    group["SB"].update(status="technical_unknown", R=None, passed=True)
    value = runner.block_contrasts(group)
    assert value["complete"] is False
    assert value["information_main_effect"] is value["framing_main_effect"] is value["interaction"] is None
    assert value["split_minus_shared_team"] == 1
    assert value["split_minus_shared_base"] is None


def test_complete_inventory_counts_unsuccessful_costs_and_returns_four_block_effects(tmp_path):
    plan = plan_at(tmp_path)
    for worker, units in plan["assignments"].items():
        for u in units:
            recorded(tmp_path, worker, u, reward=int(u["condition"] == "PT"), calls=2 if u["condition"] == "PT" else 7)
    write(tmp_path / "supervisor.json", {"status": "complete", "states": {}})
    report = runner.results(tmp_path)
    assert report["scheduled"] == report["known"] == len(report["rows"]) == 16
    assert all(r["known"] == 4 and r["unknown_or_pending"] == 0 for r in report["by_condition"].values())
    assert report["by_condition"]["PT"]["mean_R"] == 1
    assert report["by_condition"]["SB"]["mean_R"] == 0
    assert report["full_inventory_mean_contrasts"]["interaction"] == 1
    assert report["cost"]["recorded_usage"]["attempts"] == 4 * 2 + 12 * 7
    assert report["cost"]["recorded_usage"]["total_tokens"] == (4 * 2 + 12 * 7) * 12
    assert report["cost"]["run_tests"] == 32
    assert all(r["work_use"] is None for r in report["rows"])


def test_technical_unknown_and_unstarted_remain_in_original_inventory(tmp_path):
    plan = plan_at(tmp_path)
    first, units = next(iter(plan["assignments"].items()))
    recorded(tmp_path, first, units[0], reward=1)
    recorded(tmp_path, first, units[1], reward=None, status="technical_unknown", calls=7)
    write(tmp_path / "supervisor.json", {"status": "closed_with_unknowns", "states": {first: {"status": "stopped"}}})
    value = runner.results(tmp_path)
    assert value["known"] == 1 and len(value["rows"]) == 16
    unknown = next(r for r in value["rows"] if r["slot_id"] == units[1]["slot_id"])
    untouched = next(r for r in value["rows"] if r["slot_id"] == units[2]["slot_id"])
    assert unknown["status"] == "technical_unknown" and unknown["R"] is None
    assert untouched["status"] == "not_started" and untouched["R"] is None
    assert all(v is None for v in value["full_inventory_mean_contrasts"].values())
    assert value["cost"]["recorded_usage"]["attempts"] == 10


def test_result_known_requires_formal_binary_R_not_raw_passed_or_boolean():
    for reward in (None, True, False, 1.0, 2, -1):
        assert runner.known({"status": "closed", "R": reward, "passed": True}) is False
    assert runner.known({"status": "technical_unknown", "R": 1}) is False
    assert runner.known({"status": "closed", "R": 0}) is True
    assert runner.known({"status": "closed", "R": 1}) is True


def test_gpu_selection_is_explicit_physical_allowlist(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "target_resources", lambda selector, **kwargs: calls.append(selector) or {})
    runner.allowed_resources()
    assert calls == ["3,4,5,7"]
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1,2,6")
    monkeypatch.setenv("PROWORKSIM_REPLICA_GPUS", "0,1")
    for card in (3, 4, 5, 7):
        env = runner.worker_env({"runtime_dependency_path": "/cpu/runtime"}, card)
        assert env["CUDA_VISIBLE_DEVICES"] == str(card)
        assert "PROWORKSIM_REPLICA_GPUS" not in env
        assert env["PYTHONPATH"].split(os.pathsep)[1:] == [str(runner.SOURCE / "src"), str(runner.SOURCE)]
    for card in (0, 1, 2, 6, "3", "3,4", None):
        with pytest.raises(ValueError):
            runner.worker_env({"runtime_dependency_path": "/cpu/runtime"}, card)


def test_only_declared_sdk_hook_can_differ_from_inherited_numerical_source(tmp_path, monkeypatch):
    original = {runner.SDK_POLICY_HOOK: b"original SDK", "src/proworksim/actor.py": b"fixed actor arithmetic"}
    archive = io.BytesIO()
    digest = hashlib.sha256()
    with tarfile.open(fileobj=archive, mode="w") as stream:
        for name, raw in sorted(original.items()):
            digest.update(name.encode())
            digest.update(raw)
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            stream.addfile(info, io.BytesIO(raw))
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
    (tmp_path / runner.SDK_POLICY_HOOK).write_bytes(b"SDK with explicit error hook")
    monkeypatch.setattr(runner, "SOURCE", tmp_path)
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *a, **k: archive.getvalue())
    parent = {"code_dirty": False, "code_commit": "cpu-fixture", "source_tree_sha256": digest.hexdigest()}
    result = runner.inherited_source_manifest(parent)
    assert result["unchanged_count"] == 1
    assert set(result["declared_changes"]) == {runner.SDK_POLICY_HOOK}
    (tmp_path / "src/proworksim/actor.py").write_bytes(b"changed arithmetic")
    with pytest.raises(ValueError, match="undeclared inherited source"):
        runner.inherited_source_manifest(parent)


def test_interrupted_episode_recovers_evidence_cost_without_inventing_result(tmp_path):
    plan = plan_at(tmp_path)
    worker, units = next(iter(plan["assignments"].items()))
    recorded(tmp_path, worker, units[0], reward=1, calls=3)
    folder = tmp_path / worker / "actual/episodes" / units[1]["slot_id"]
    usage = {"decisions": 10, "attempts": 9, "prompt_tokens": 90, "completion_tokens": 18,
             "total_tokens": 108, "output_bearing_calls": 9, "budget_charged_tokens": 108, "uncertain_usage_attempts": 0}
    preparation = {"wall_seconds": 2.5, "executions": 2}
    write(folder / "organization-evidence.json", {"total_usage": usage, "team_budget": {"tests": {"used": 5}},
        "member_lifecycle": {"initial_members": ["member_001", "member_002"], "cumulative_births": 3,
                             "member_requested_births": 1}, "environment_preparation_cost": preparation,
        "R": 1, "status": "closed"})
    write(tmp_path / "supervisor.json", {"status": "closed_with_unknowns", "states": {worker: {"status": "stopped"}}})
    value = runner.results(tmp_path)
    recovered = next(row for row in value["rows"] if row["slot_id"] == units[1]["slot_id"])
    assert recovered["status"] == "technical_unknown" and recovered["R"] is recovered["submitted"] is None
    assert recovered["usage"] == usage and recovered["environment_preparation_cost"] == preparation
    assert recovered["member_lifecycle"]["member_requested_births"] == 1
    assert recovered["cost_evidence"]["status"] == "partial_organization_evidence"
    assert value["known"] == 1 and len(value["rows"]) == 16
    assert value["cost"]["recorded_usage"]["attempts"] == 12
    assert value["cost"]["recorded_usage"]["total_tokens"] == 144
    assert value["cost"]["run_tests"] == 7
    assert value["cost"]["partial_cost_episodes"] == 1 and value["cost"]["cost_incomplete"] is True
    assert value["cost"]["partial_episodes_without_settlement_counts"] == 1


def test_budget_only_interruption_reports_settled_cost_and_pending_unknown_consumption(tmp_path):
    plan = plan_at(tmp_path)
    worker, units = next(iter(plan["assignments"].items()))
    budget = {"model": {"records": {
        "done": {"status": "settled", "attempt_started": True, "charge": {"charged_tokens": 17,
            "usage_status": "reported_actual_trace", "reported_usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}}},
        "uncertain": {"status": "settled", "attempt_started": True, "charge": {"charged_tokens": 99,
            "usage_status": "uncertain_attempt_charged_reservation", "reported_usage": None}},
        "live": {"status": "attempting", "attempt_started": True, "reservation": {"token_reservation": 1000}},
        "held": {"status": "reserved", "attempt_started": False, "reservation": {"token_reservation": 2000}},
        "rejected": {"status": "admission_rejected", "attempt_started": False},
    }}, "tests": {"used": 3}}
    for index, filename in enumerate(("team-budget.json", "runtime-state.json")):
        folder = tmp_path / worker / "actual/episodes" / units[index]["slot_id"]
        write(folder / filename, budget if index == 0 else {"team_budget": budget})
    (tmp_path / worker / "actual/episodes" / units[2]["slot_id"]).mkdir()
    write(tmp_path / "supervisor.json", {"status": "closed_with_unknowns", "states": {worker: {"status": "stopped"}}})
    value = runner.results(tmp_path)
    assert value["known"] == 0 and len(value["rows"]) == 16
    for unit in units[:2]:
        row = next(row for row in value["rows"] if row["slot_id"] == unit["slot_id"])
        assert row["status"] == "technical_unknown" and row["R"] is None
        assert row["usage"]["decisions"] == 5 and row["usage"]["attempts"] == 3
        assert row["usage"]["total_tokens"] == 17 and row["usage"]["budget_charged_tokens"] == 116
        assert "output_bearing_calls" not in row["usage"]
        assert row["cost_evidence"]["status"] == "partial_budget_ledger"
        assert row["cost_evidence"]["unsettled_record_ids"] == ["live", "held"]
        assert row["cost_evidence"]["unsettled_attempts"] == 1
        assert row["cost_evidence"]["attempts_without_reported_token_usage"] == 2
    cost = value["cost"]
    assert cost["recorded_usage"]["total_tokens"] == 34 and cost["recorded_usage"]["budget_charged_tokens"] == 232
    assert cost["run_tests"] == 6 and cost["unsettled_attempts"] == 2
    assert cost["attempts_without_reported_token_usage"] == 4
    assert cost["partial_cost_episodes"] == 3 and cost["unreported_started_episodes"] == 1
    assert cost["metrics_with_missing_episode_records"]["output_bearing_calls"] == 3
    assert cost["metrics_with_missing_episode_records"]["total_tokens"] == 1
    assert cost["cost_incomplete"] is True
    for key in value["full_inventory_mean_contrasts"]:
        assert value["full_inventory_mean_contrasts"][key] is None
