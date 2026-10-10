"""Bind a disclosed batch-stop revision to the nine untouched original v044 slots.

Seven completed episodes and both original stops remain immutable. This module
only verifies saved evidence and dependency bytes. It does not re-run a legacy
admission implementation, capacity qualification, model, tokenizer or acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

from proworksim.storage import digest, json_bytes
from scripts.software_organization_admission_v044 import EvidenceReader, reference
from scripts import software_organization_resume_admission_v044 as previous

VERSION = "software-organization-completion-admission-v0.44"
SOURCE = Path(__file__).resolve().parents[1]
RESUME_COMMIT = "67a4da1194cdad7de66d7621bf568261338f4f01"
RESUME_PUBLICATION = "b16d3e2a2b891daaaba14adb07dce7f50b9f7557"
FINAL_PUBLICATION = "4ef22f1ddfba862c52ba6f5021a36195d121ec79"
SRC_TREE = previous.ORIGINAL_TREE
BLOCKS = previous.REMAINING_BLOCKS
FIRST_BLOCK = previous.FIRST_BLOCK
EXPECTED_FIRST = {"block-r0-s0": "org44-r0-s0-ST", "block-r0-s1": "org44-r0-s1-PB",
                  "block-r1-s1": "org44-r1-s1-SB"}
ALLOWED_NEW_CODE = frozenset({
    "scripts/software_organization_stop_policy_v044.py",
    "scripts/software_organization_completion_admission_v044.py",
    "scripts/software_organization_complete_v044.py",
    "tests/test_organization_stop_policy_v044.py",
    "tests/test_software_organization_completion_admission_v044.py",
    "tests/test_software_organization_complete_v044.py",
})
OLD_ACTUAL = {"decisions": 267, "attempts": 256, "total_tokens": 3369138, "test_runs": 26}
NEW_CAPS = {"decisions": 1152, "attempts": 1152, "total_tokens": 4500000, "test_runs": 288}
COMBINED_CAPS = {"decisions": 1419, "attempts": 1408, "total_tokens": 7869138, "test_runs": 314}


def require(value, reason):
    if not value:
        raise ValueError("v044 completion admission rejected: " + reason)


def read_path(reader, path):
    ref = reference(path)
    return reader.read(ref), ref


def git_publication(source_root, commit, path):
    object_id = commit + ":" + path
    content = subprocess.check_output(["git", "show", object_id], cwd=source_root)
    return json.loads(content), {"git_object": object_id, "sha256": digest(content), "bytes": len(content)}


def source_audit(source_root):
    """The entire prior 67a execution tree stays unchanged; only six additions."""
    source_root = Path(source_root).resolve()
    archive = subprocess.check_output(["git", "archive", RESUME_COMMIT, *previous.CODE_ROOTS,
                                       "pyproject.toml"], cwd=source_root)
    old, source_hash = {}, hashlib.sha256()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for member in stream.getmembers():
            if member.isfile():
                old[member.name] = stream.extractfile(member).read()
    original = {}
    for name, content in sorted(old.items()):
        path = source_root / name
        require(path.is_file() and path.read_bytes() == content, "prior execution bytes changed: " + name)
        original[name] = {"sha256": digest(content), "bytes": len(content)}
        if name.startswith("src/") and name.endswith(".py"):
            source_hash.update(name.encode())
            source_hash.update(content)
    require(source_hash.hexdigest() == SRC_TREE, "original e8/67 model-visible source tree changed")
    additions = {}
    for base in previous.CODE_ROOTS:
        for path in sorted((source_root / base).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            name = str(path.relative_to(source_root))
            if name in old:
                continue
            require(name in ALLOWED_NEW_CODE, "undeclared new dependency: " + name)
            additions[name] = {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
    require(set(additions) == ALLOWED_NEW_CODE, "require exactly the declared policy/admission/driver and three tests")
    return {"baseline_execution_commit": RESUME_COMMIT, "original_model_visible_src_tree_sha256": SRC_TREE,
        "all_prior_bytes_unchanged": True, "original_files": original, "new_files": additions,
        "scope": "All files in prior src/scripts/tests/examples and pyproject are byte-identical to 67a. No old policy, measurement, collector, renderer, numerical implementation or input asset is changed."}


def remaining_inventory(original_plan, resume_plan):
    original_twelve = previous.validate_inventory(original_plan)
    require(resume_plan.get("assignments") == original_twelve, "prior twelve-slot assignment identity changed")
    require(resume_plan.get("cases") == {block: original_plan["cases"][block] for block in BLOCKS},
            "prior twelve-slot model-visible cases changed")
    result = {}
    for block in BLOCKS:
        units = original_twelve[block]
        require(units[0]["slot_id"] == EXPECTED_FIRST[block], "prior executed block prefix changed")
        result[block] = units[1:]
    ids = [unit["slot_id"] for units in result.values() for unit in units]
    require(len(ids) == len(set(ids)) == 9 and not set(ids) & set(EXPECTED_FIRST.values()),
            "completion inventory duplicates or replays a prior slot")
    return result


def validate_unstarted(original_root, resume_root, original_plan, reports, progresses, supervisor):
    """Existing workers ran one slot, so only exact untouched suffixes may open."""
    original_root, resume_root = Path(original_root), Path(resume_root)
    require(sorted(path.name for path in original_root.glob("block-*")) == [FIRST_BLOCK],
            "original root contains another attempted worker")
    require(sorted(path.name for path in resume_root.glob("block-*")) == sorted(BLOCKS),
            "prior resume has an unexpected worker output namespace")
    require(supervisor.get("status") == "closed_with_unknowns" and "ended_at" in supervisor
            and set(supervisor.get("states", {})) == set(BLOCKS), "prior supervisor is not the frozen terminal run")
    rows = []
    for block in BLOCKS:
        state, report, progress = supervisor["states"][block], reports[block], progresses[block]
        expected_status = "mechanism_fault" if block == "block-r0-s0" else "paused_before_next_slot"
        require(state.get("status") == "stopped" and state.get("attempted") is True
                and state.get("exit_code") == 0 and state.get("stop_reason") is None and "ended_at" in state,
                "existing worker did not close normally before completion")
        require(report.get("status") == expected_status and report.get("rows") == progress
                and [row.get("slot_id") for row in progress] == [EXPECTED_FIRST[block]],
                "existing worker is not the exact one-slot prefix; never restart a whole block")
        episodes = resume_root / block / "actual/episodes"
        require(sorted(path.name for path in episodes.iterdir()) == [EXPECTED_FIRST[block]],
                "prior worker contains a started suffix, even without a result")
        for unit in original_plan["assignments"][block][1:]:
            paths = [root / block / "actual/episodes" / unit["slot_id"] for root in (original_root, resume_root)]
            require(all(not path.exists() and not path.is_symlink() for path in paths),
                    "remaining slot has an original directory or partial launch")
            rows.append({"slot_id": unit["slot_id"], "block": block,
                "checked_absent_episode_paths": [str(path.resolve()) for path in paths],
                "absent_from_both_saved_worker_outputs": True, "prior_worker_was_closed": True,
                "whole_worker_replay_permitted": False})
    require(len(rows) == 9, "exactly nine prior unstarted slots are required")
    return rows


def saved_refs(value, reader):
    """Verify a saved reference tree without rebuilding a legacy qualification."""
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            reader.path(value)
        else:
            for item in value.values():
                saved_refs(item, reader)
    elif isinstance(value, list):
        for item in value:
            saved_refs(item, reader)


def bind_prior_qualification(original_plan, resume_plan, reader, sources, source_root):
    admission = reader.read(resume_plan["resume_admission"])
    require(admission.get("passed") is True and admission.get("version") == previous.VERSION
            and admission.get("admission_sha256") == digest(json_bytes({k: v for k, v in admission.items()
                                                                        if k != "admission_sha256"})),
            "saved prior admission identity changed")
    require(admission["original_execution_source"] == original_plan["source"]
            and admission["remaining_assignments"] == resume_plan["assignments"], "prior admission cites another inventory")
    saved_refs(admission["original_refs"], reader)
    require(admission["revised_first_block"]["summary"]["sha256"] == resume_plan["correction_summary"]["sha256"],
            "prior corrected first-block receipt lineage changed")
    for group in ("original_files", "new_files"):
        for name, entry in admission["source_audit"][group].items():
            require(sources["original_files"].get(name) == entry, "67a source differs from prior admitted dependency: " + name)
    for ref in (original_plan["qualification"], resume_plan["qualification"]):
        receipt = reader.read(ref)
        require(receipt.get("passed") is True and receipt.get("new_model_calls") == 0,
                "prior qualification failed or has model work")
        require(bool(receipt.get("checks")) and all(row["exit_code"] == 0 for row in receipt["checks"]),
                "prior CPU qualification did not pass")
        for check in receipt["checks"]:
            reader.path(check["log"])
        for name, expected in receipt["source_files"].items():
            require(sources["original_files"].get(name, {}).get("sha256") == expected,
                    "saved qualified source changed: " + name)
    saved_refs(admission["qualification_reuse"], reader)
    model = admission["model_identity"]
    require(model["actor_identity"] == original_plan["expected_actor_identity"] == resume_plan["expected_actor_identity"]
            and model["state_tensor_sha256"] == original_plan["expected_state_sha256"] == resume_plan["expected_state_sha256"]
            and model["runtime_dependency_path"] == original_plan["runtime_dependency_path"] == resume_plan["runtime_dependency_path"],
            "common, inference or dependency identity changed")
    saved_refs(model, reader)
    manifest = reader.read(model["model_manifest"])
    for name, expected in model["non_weight_assets"].items():
        require(manifest["files"].get(name) == expected, "saved tokenizer/renderer manifest identity changed")
        reader.path({"path": str(Path(manifest["model_path"]) / name), **expected})
    for ref in admission["revised_first_block"]["slot_measurements"]:
        reader.path(ref)
    correction = reader.read(resume_plan["correction_summary"])
    require(correction.get("passed") is True and correction.get("original_artifacts_unchanged") is True,
            "original first-block correction is not preserved")
    corrected_gate = reader.read(correction["revised_gate"])
    require(corrected_gate.get("passed") is True and corrected_gate.get("measured_slots") == 4,
            "original corrected first-block gate changed")
    return {"prior_resume_admission": resume_plan["resume_admission"],
        "original_qualification": original_plan["qualification"], "resume_qualification": resume_plan["qualification"],
        "original_capacity_and_permission_reuse": admission["qualification_reuse"],
        "original_model_identity": model,
        "legacy_validate_admission_invoked": False, "legacy_qualification_reexecuted": False,
        "source_whitelist_handling": "Consume explicit saved source maps against the immutable 67a tree; never regenerate the older glob or additions whitelist on the new tree.",
        "new_model_calls": 0, "new_tokenizer_calls": 0, "new_capacity_encodings": 0,
        "new_test_or_acceptance_executions": 0}, {
            "summary": resume_plan["correction_summary"], "gate": correction["revised_gate"],
            "original_gate": correction["original_gate"]}


def bind_seven(cost, original_plan, reports, reader):
    units = {unit["slot_id"]: unit for block in original_plan["assignments"].values() for unit in block}
    expected = [unit["slot_id"] for unit in original_plan["assignments"][FIRST_BLOCK]] + list(EXPECTED_FIRST.values())
    require([row["slot_id"] for row in cost["slots"]] == expected, "saved cost inventory is not the unique retained seven")
    require({worker["worker"] for worker in cost["workers"]} == {FIRST_BLOCK, *BLOCKS},
            "saved worker provenance is incomplete")
    for worker in cost["workers"]:
        require(worker.get("common_3_3_exact") is True and worker.get("source_identity_unchanged") is True
                and worker.get("actor_steps") == worker.get("critic_steps") == 3,
                "saved worker common/source guard failed")
        for name in ("report.json", "common-restore.json"):
            reader.path(worker["sources"][name])
    rows, total, tests = [], Counter(), 0
    for saved in cost["slots"]:
        slot = saved["slot_id"]
        refs = saved["sources"]
        result = reader.read(refs["slot-result.json"])
        guard = reader.read(refs["evaluation-guard.json"])
        reader.path(refs["team-budget.json"])
        require(result.get("status") == "closed" and type(result.get("R")) is int
                and result["R"] == saved["R"] and result.get("submitted") == saved["submitted"],
                "original formal outcome was changed or is not closed")
        require(result.get("actor_identity") == original_plan["expected_actor_identity"]
                and all(result.get(key) == 0 for key in ("actor_updates", "critic_updates", "new_backward_calls")),
                "retained slot did not preserve the frozen common actor")
        require(all(guard.get(key) is True for key in ("learning_unchanged", "rng_restored_exactly",
                    "software_binding_unchanged", "actor_identity_unchanged"))
                and guard.get("learning_before_sha256") == guard.get("learning_after_sha256")
                and guard.get("rng_before_sha256") == guard.get("rng_after_restore_sha256"),
                "retained slot guard failed")
        block = "block-" + "-".join(slot.split("-")[1:3])
        exact = next((row for row in reports[block]["rows"] if row.get("slot_id") == slot), None)
        require(exact == {**units[slot], **result}, "original result differs from immutable published worker output")
        require(result["usage"] == saved["usage"], "retained usage differs from immutable cost audit")
        total.update(result["usage"])
        tests += result["team_budget"]["tests"]["used"]
        rows.append({**units[slot], "status": "closed", "R": result["R"], "submitted": result["submitted"],
            "execution_phase": saved["execution_phase"], "slot_result": refs["slot-result.json"],
            "evaluation_guard": refs["evaluation-guard.json"], "team_budget": refs["team-budget.json"],
            "usage": result["usage"], "run_tests": result["team_budget"]["tests"]["used"],
            "recollection_permitted": False})
    require({**{key: total[key] for key in ("decisions", "attempts", "total_tokens")}, "test_runs": tests} == OLD_ACTUAL,
            "old seven cost baseline differs")
    return rows


def budget_caps():
    require({key: OLD_ACTUAL[key] + NEW_CAPS[key] for key in OLD_ACTUAL} == COMBINED_CAPS,
            "completion cost upper bound arithmetic changed")
    return {"old_actual": dict(OLD_ACTUAL), "new": dict(NEW_CAPS), "combined": dict(COMBINED_CAPS),
        "unused_old_tokens": 7 * 500000 - OLD_ACTUAL["total_tokens"], "transfer_old_unused": False,
        "scope": "Only nine original slots with their original per-slot limits. Old seven costs count once; their unused 130862 tokens are never transferred."}


def validate_policy_value(value):
    require(value.get("version") == "v044-batch-stop-scope-revision-r2"
            and value.get("slot_id") == "org44-r0-s0-ST" and value.get("decision") == "continue"
            and value.get("classification") == "safe_local_resource_stop" and value.get("read_only") is True,
            "new policy did not bind the original local resource stop")
    require(value.get("global_violations") == value.get("unresolved") == [], "new policy still has global or unresolved evidence")
    require(all(value.get(key) is False for key in ("R_used_for_scope", "restart_current_member",
                "feedback_visibility_changed", "model_visible_Gamma_changed")),
            "batch policy changes rewards, member treatment or model-visible information")
    require(all(value.get(key) == 0 for key in ("new_model_calls", "new_tokenizer_calls",
                "new_test_or_acceptance_executions", "new_world_actions")), "policy receipt includes execution work")
    events = value.get("local_context_events", [])
    require(value.get("context_blocked_feedback_ids") == ["feedback-361"] and len(events) == 1,
            "original blocked feedback was removed or local-stop identity changed")
    event = events[0]
    expected = {"classification": "safe_local_resource_stop", "call_id": "model-b51be34942fd42c33bc3be7d",
        "member": "member_001", "prompt_tokens": 14565, "reserved_output_tokens": 2048,
        "context_limit": 16384, "excess_tokens": 229, "team_available_tokens_at_rejection": 231277,
        "attempt_started": False, "new_native_output": False, "charged_tokens": 0,
        "execution_side_effect": False, "context_blocked_feedback_ids": ["feedback-361"],
        "concurrent_team_reservation_shortage": False,
        "member_remains_stopped": True, "R_used_for_classification": False,
        "submission_timing_used_for_classification": False}
    require(all(event.get(key) == expected_value for key, expected_value in expected.items()),
            "original hard-context evidence or new scope semantics changed")


def bind_policy(path, reader, retained, old_stop, source_root):
    value, policy_ref = read_path(reader, path)
    validate_policy_value(value)
    st = next(row for row in retained if row["slot_id"] == "org44-r0-s0-ST")
    result = reader.read(st["slot_result"])
    require(value.get("formal_result") == {key: result.get(key) for key in ("status", "R", "submitted", "complete_delivery")},
            "new policy changed the original formal result")
    sources = value.get("sources", {})
    for key, expected in (("result", st["slot_result"]), ("guard", st["evaluation_guard"]),
                          ("budget", st["team_budget"]), ("feedback", old_stop["feedback"])):
        require(sources.get(key, {}).get("sha256") == expected["sha256"], "policy receipt uses another original " + key)
    require(sources.get("old_stop_record", {}).get("sha256") == old_stop["source"]["sha256"],
            "policy receipt did not preserve the old global stop")
    saved_refs(sources, reader)
    saved_refs(value.get("supersedes", {}), reader)
    bindings = value.get("source_bindings", [])
    required = {"scripts/software_organization_stop_policy_v044.py", "tests/test_organization_stop_policy_v044.py"}
    found = set()
    for ref in bindings:
        reader.path(ref)
        path = Path(ref["path"])
        prefix = next((name for name in ("src", "scripts", "tests") if name in path.parts), None)
        require(prefix is not None, "unknown policy source path")
        relative = str(Path(*path.parts[path.parts.index(prefix):]))
        require(digest((Path(source_root) / relative).read_bytes()) == ref["sha256"], "policy source changed after receipt")
        found.add(relative)
    require(required <= found, "policy implementation and boundary-test source bindings missing")
    return policy_ref, {"decision": value["decision"], "classification": value["classification"],
        "local_context_events": value["local_context_events"], "context_blocked_feedback_ids": value["context_blocked_feedback_ids"],
        "old_global_stop_retained": old_stop["source"], "only_future_independent_slots_released": True}


def build_admission(original_root, resume_root, policy_receipt, *, source_root=SOURCE):
    original_root, resume_root, source_root = (Path(path).resolve() for path in (original_root, resume_root, source_root))
    require(original_root != resume_root, "original and prior resume roots must remain separate")
    reader = EvidenceReader()
    original_plan, original_plan_ref = read_path(reader, original_root / "plan.json")
    resume_plan, resume_plan_ref = read_path(reader, resume_root / "plan.json")
    require(original_plan["source"] == {"code_commit": previous.ORIGINAL_COMMIT, "code_dirty": False, "source_tree_sha256": SRC_TREE}
            and resume_plan["source"] == {"code_commit": RESUME_COMMIT, "code_dirty": False, "source_tree_sha256": SRC_TREE},
            "original execution identity changed")
    for plan in (original_plan, resume_plan):
        require(plan["plan_sha256"] == digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"})), "frozen plan digest changed")
    require(original_plan["plan_sha256"] == previous.ORIGINAL_PLAN_DIGEST
            and resume_plan["original_plan"]["sha256"] == original_plan_ref["sha256"]
            and Path(resume_plan["original_run_root"]).resolve() == original_root, "two prior inventories do not share original lineage")
    remaining = remaining_inventory(original_plan, resume_plan)
    original_state, original_state_ref = read_path(reader, original_root / "supervisor.json")
    resume_state, resume_state_ref = read_path(reader, resume_root / "supervisor.json")
    old_gate, old_gate_ref = read_path(reader, original_root / "first-block-gate.json")
    old_finish, old_finish_ref = read_path(reader, original_root / "finish.json")
    new_finish, new_finish_ref = read_path(reader, resume_root / "finish.json")
    require(old_finish.get("status") == "stopped_by_first_block_gate"
            and old_finish.get("publication", {}).get("commit") == previous.ORIGINAL_PUBLICATION_COMMIT
            and old_finish.get("publication", {}).get("status") == "pushed"
            and new_finish.get("status") == "closed_with_unknowns"
            and new_finish.get("publication", {}).get("commit") == RESUME_PUBLICATION,
            "either original finisher or stop record changed")
    require(new_finish.get("publication", {}).get("status") == "pushed", "prior continuation publication not complete")
    original_report, original_report_ref = read_path(reader, original_root / FIRST_BLOCK / "actual/report.json")
    original_progress, original_progress_ref = read_path(reader, original_root / FIRST_BLOCK / "actual/progress.json")
    original_publication = previous.bind_published_original(source_root, original_state, original_report, old_gate)
    previous.validate_never_started(original_root, original_state, original_report, original_progress, original_plan["assignments"])
    publication, publication_ref = git_publication(source_root, RESUME_PUBLICATION, "docs/experiments/software-organization-v044-resume.json")
    final, final_ref = git_publication(source_root, FINAL_PUBLICATION, "docs/experiments/software-organization-v044-resume-final.json")
    require(final["sources"]["finish"]["sha256"] == new_finish_ref["sha256"]
            and final["sources"]["original_gate"]["sha256"] == old_gate_ref["sha256"],
            "original finisher or failed-gate bytes differ from the immutable final audit")
    require(publication["plan"]["sha256"] == resume_plan_ref["sha256"]
            and publication["supervisor"] == resume_state
            and publication["workers"][FIRST_BLOCK]["report"] == original_report,
            "prior completion records differ from immutable b16 publication")
    reports, progresses, report_refs, progress_refs, task_refs = {FIRST_BLOCK: original_report}, {}, {}, {}, {}
    for block in BLOCKS:
        actual = resume_root / block / "actual"
        report, report_ref = read_path(reader, actual / "report.json")
        progress, progress_ref = read_path(reader, actual / "progress.json")
        task, task_ref = read_path(reader, actual / "task.json")
        require(report == publication["workers"][block]["report"] and report["source_before"] == report["source_after"] == resume_plan["source"],
                "prior worker output or source differs from immutable publication")
        require(task.get("task") == "final-frozen-state-boundary" and task.get("kind") == "boundary",
                "prior worker did not reach its terminal boundary")
        reports[block], progresses[block] = report, progress
        report_refs[block], progress_refs[block], task_refs[block] = report_ref, progress_ref, task_ref
    never_started = validate_unstarted(original_root, resume_root, original_plan, reports, progresses, resume_state)
    stops = {}
    for ref in resume_state["mechanism_pauses"]:
        stops[Path(ref["path"]).name] = {**reader.read(ref), "source": ref}
    require(set(stops) == {"org44-r0-s0-ST.json", *[block + "-supervisor.json" for block in BLOCKS]},
            "prior stop-marker inventory changed")
    require(sorted(stops) == sorted(path.name for path in (resume_root / "mechanism-stops").glob("*.json")),
            "unexpected prior pause marker")
    old_stop = stops["org44-r0-s0-ST.json"]
    require(old_stop.get("kind") == "mechanism_fault" and old_stop.get("details") == {"context_blocked_feedback_ids": ["feedback-361"]},
            "original hard-context global stop was erased or changed")
    cost = reader.read(final["sources"]["cost-review"])
    require(cost["cost_partitions"] == final["cost_partitions"] and cost["inventory"] == final["inventory"],
            "prior cost record differs from immutable 4ef publication")
    retained = bind_seven(cost, original_plan, reports, reader)
    sources = source_audit(source_root)
    reuse, revised = bind_prior_qualification(original_plan, resume_plan, reader, sources, source_root)
    policy_ref, policy_scope = bind_policy(policy_receipt, reader, retained, old_stop, source_root)
    value = {"version": VERSION, "passed": True, "read_only": True,
        "original_run_root": str(original_root), "resume_run_root": str(resume_root),
        "original_refs": {"plan": original_plan_ref, "supervisor": original_state_ref, "gate": old_gate_ref,
            "finish": old_finish_ref, "worker_report": original_report_ref, "worker_progress": original_progress_ref},
        "resume_refs": {"plan": resume_plan_ref, "supervisor": resume_state_ref, "finish": new_finish_ref,
            "worker_reports": report_refs, "worker_progress": progress_refs, "terminal_tasks": task_refs,
            "original_pause_markers": [stops[key]["source"] for key in sorted(stops)]},
        "immutable_publications": {"original_first_block": original_publication,
            "resume_automatic": publication_ref, "resume_final": final_ref},
        "retained_slots": retained, "never_started_checks": never_started, "remaining_assignments": remaining,
        "remaining_cases_sha256": {block: [digest(json_bytes(case)) for case in original_plan["cases"][block][1:]] for block in BLOCKS},
        "revised_first_block": revised, "policy_receipt": policy_ref, "batch_stop_scope": policy_scope,
        "source_audit": sources, "prior_qualification_and_model_reuse": reuse,
        "old_cost_baseline": {"source": final["sources"]["cost-review"], "actual": OLD_ACTUAL}, "budget_caps": budget_caps(),
        "completion_scope": {"logical_inventory": 16, "retained_closed": 7, "max_new_episodes": 9,
            "max_new_resident_workers": 3, "allowed_physical_gpus": [3, 4, 5, 7], "replay_old_workers": False,
            "restart_old_members": False, "transfer_old_unused_budget": False,
            "model_visible_Gamma_changed": False, "member_or_episode_runtime_changed": False,
            "batch_stop_policy_explicitly_changed": True, "old_false_gates_and_stops_preserved": True},
        "verified_refs": list(reader.checked.values()), "new_model_calls": 0, "new_tokenizer_calls": 0,
        "new_capacity_encodings": 0, "new_test_or_acceptance_executions": 0, "new_backward_calls": 0,
        "scope": "Nine original independent slots only, under a disclosed new batch-stop policy. Safe local capacity stops remain real member/episode outcomes and unseen feedback stays unseen. The seven prior results, original false gate, corrected gate, hard-context stop and pauses are not rewritten."}
    value["admission_sha256"] = digest(json_bytes(value))
    return value


def create_admission(original_root, resume_root, policy_receipt, output, *, source_root=SOURCE):
    output = Path(output).resolve()
    require(not output.exists(), "refuse to overwrite a completion admission")
    value = build_admission(original_root, resume_root, policy_receipt, source_root=source_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(json_bytes(value))
    return value


def validate_admission(path_or_ref, *, source_root=SOURCE):
    reader = EvidenceReader()
    value = reader.read(path_or_ref if isinstance(path_or_ref, dict) else reference(path_or_ref))
    require(value.get("version") == VERSION and value.get("passed") is True
            and value.get("admission_sha256") == digest(json_bytes({k: v for k, v in value.items() if k != "admission_sha256"})),
            "completion admission identity changed")
    rebuilt = build_admission(value["original_run_root"], value["resume_run_root"], value["policy_receipt"]["path"], source_root=source_root)
    require(rebuilt == value, "completion admission no longer matches immutable inventory and dependencies")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-run-root", type=Path, required=True)
    parser.add_argument("--resume-run-root", type=Path, required=True)
    parser.add_argument("--policy-receipt", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = create_admission(args.original_run_root, args.resume_run_root, args.policy_receipt, args.output, source_root=args.source_root)
    print(json.dumps({"passed": value["passed"], "new_slots": 9, "output": str(args.output)}))


if __name__ == "__main__":
    main()
