"""Read-only admission for the twelve unstarted slots of the original v044 plan.

This binds saved qualification receipts; it never replays capacity controls,
renders a prompt, tokenizes, loads a model or executes business acceptance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

from proworksim.storage import digest, json_bytes
from scripts.software_organization_admission_v044 import EvidenceReader, reference

VERSION = "software-organization-resume-admission-v0.44"
SOURCE = Path(__file__).resolve().parents[1]
ORIGINAL_COMMIT = "e8aa60bd1a427944d8503fb02b30f6379ebd5889"
ORIGINAL_PUBLICATION_COMMIT = "6f37d0c23820e08a3ed2ce7ae40df0b6bba4b761"
ORIGINAL_TREE = "47eb019ff4cc6170111cec16ab4c538c57719ad23d8774a5fd0c82dbc3caba30"
ORIGINAL_PLAN_DIGEST = "ffa2d8946f24a7a7526c9874479dea29281e9f41fc71337e9337cf4c9f72e02e"
FIRST_BLOCK = "block-r1-s0"
REMAINING_BLOCKS = ("block-r0-s0", "block-r0-s1", "block-r1-s1")
BLOCK_LAYOUT = {
    "block-r0-s0": ("views", 202610100441, ("ST", "PB", "PT", "SB"), "member_002", "member_002"),
    "block-r0-s1": ("views", 202610100442, ("PB", "PT", "SB", "ST"), "member_001", "member_002"),
    FIRST_BLOCK: ("catalog", 202610100441, ("PT", "SB", "ST", "PB"), "member_001", "member_001"),
    "block-r1-s1": ("catalog", 202610100442, ("SB", "ST", "PB", "PT"), "member_002", "member_001"),
}
TEAM_LIMITS = {"max_decisions": 128, "max_attempts": 128,
               "max_total_tokens": 500000, "max_test_runs": 32}
ALLOWED_NEW_CODE = frozenset({
    "scripts/measure_organization_feedback_v044r1.py",
    "scripts/software_organization_resume_admission_v044.py",
    "scripts/software_organization_resume_v044.py",
    "tests/test_organization_feedback_v044r1.py",
    "tests/test_software_organization_resume_admission_v044.py",
    "tests/test_software_organization_resume_v044.py",
})
CODE_ROOTS = ("src", "scripts", "tests", "examples")


def require(value, reason):
    if not value:
        raise ValueError("v044 resume admission rejected: " + reason)


def checked_json(reader, path):
    ref = reference(path)
    return reader.read(ref), ref


def validate_inventory(plan):
    """Check the original slots, ordering and budgets, independently of rewards."""
    require(set(plan["assignments"]) == set(BLOCK_LAYOUT), "original four-block inventory changed")
    seen = []
    for block, (root, seed, conditions, first, owner) in BLOCK_LAYOUT.items():
        units = plan["assignments"][block]
        cases = plan["cases"][block]
        require(len(units) == len(cases) == 4, "each original block requires four cases")
        require(tuple(unit["condition"] for unit in units) == conditions, "original condition order changed")
        for unit, case, condition in zip(units, cases, conditions):
            slot = "org44-" + block.removeprefix("block-") + "-" + condition
            expected = {"slot_id": slot, "case_id": f"sc-record-{root}-handoff-v040",
                "sampling_seed": seed, "condition": condition, "first_member": first,
                "diagnostic_a_owner": owner, "root_family": "handoff_development",
                "information_condition": "shared" if condition[0] == "S" else "split",
                "framing_condition": "base" if condition[1] == "B" else "team"}
            require(all(unit.get(key) == value for key, value in expected.items()),
                    "original slot, seed, first member or diagnostic allocation changed: " + slot)
            require(all(case.get(key) == value for key, value in expected.items()
                        if key not in {"slot_id", "sampling_seed", "root_family"}),
                    "case differs from its original assignment: " + slot)
            require(case.get("team_limits") == TEAM_LIMITS, "original per-slot budget changed")
            require(case.get("active_roles") == ["member_001", "member_002"], "initial members changed")
            seen.append(slot)
    require(len(seen) == len(set(seen)) == 16, "duplicate or missing original slots")
    return {block: plan["assignments"][block] for block in REMAINING_BLOCKS}


def validate_never_started(root, supervisor, report, progress, assignments):
    """Absence of a result alone is insufficient; reject any original launch trace."""
    root = Path(root)
    require(supervisor.get("status") == "stopped_by_first_block_gate", "original stop state changed")
    require(set(supervisor.get("states", {})) == set(BLOCK_LAYOUT), "original worker states incomplete")
    old = supervisor["states"][FIRST_BLOCK]
    require(old.get("status") == "complete" and old.get("attempted") is True
            and old.get("exit_code") == 0 and old.get("stop_reason") is None,
            "original first block did not complete normally")
    require(report.get("status") == "complete" and report.get("rows") == progress,
            "original worker report and progress disagree")
    expected = [unit["slot_id"] for unit in assignments[FIRST_BLOCK]]
    require([row.get("slot_id") for row in progress] == expected, "original output inventory changed")
    episodes = root / FIRST_BLOCK / "actual/episodes"
    require(sorted(p.name for p in episodes.iterdir()) == sorted(expected),
            "unexpected or duplicate original episode output")
    require(sorted(p.name for p in root.glob("block-*")) == [FIRST_BLOCK],
            "an unstarted original worker has a directory or launch artifact")
    rows = []
    for block in REMAINING_BLOCKS:
        state = supervisor["states"][block]
        require(state.get("worker") == block and state.get("status") == "stopped"
                and state.get("attempted") is False
                and state.get("stop_reason") == "first_block_mechanism_gate"
                and state.get("elapsed_gpu_seconds") == 0, "remaining block has an attempted or unexplained state")
        require(not any(key in state for key in ("pid", "command", "started_at", "gpu", "gpu_uuid",
                                                "process_identity", "exit_code", "ended_at")),
                "remaining block retains a launch identity")
        require(not (root / block).exists() and not (root / block).is_symlink(),
                "remaining block already has original artifacts")
        rows.append({"block": block, "original_state": state, "original_worker_path_absent": True,
            "slot_ids": [unit["slot_id"] for unit in assignments[block]],
            "absent_from_original_progress_and_report": True})
    return rows


def source_audit(source_root):
    """All original execution bytes stay fixed; additions are explicitly scoped."""
    source_root = Path(source_root).resolve()
    archive = subprocess.check_output(["git", "archive", ORIGINAL_COMMIT, *CODE_ROOTS,
                                       "pyproject.toml"], cwd=source_root)
    old = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for member in stream.getmembers():
            if member.isfile():
                old[member.name] = stream.extractfile(member).read()
    files = {}
    src_hash = hashlib.sha256()
    for name, before in sorted(old.items()):
        current = source_root / name
        require(current.is_file() and current.read_bytes() == before, "original execution/control bytes changed: " + name)
        files[name] = {"sha256": digest(before), "bytes": len(before)}
        if name.startswith("src/") and name.endswith(".py"):
            src_hash.update(name.encode())
            src_hash.update(before)
    require(src_hash.hexdigest() == ORIGINAL_TREE, "original execution source tree differs")
    additions = {}
    for base in CODE_ROOTS:
        for path in sorted((source_root / base).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            name = str(path.relative_to(source_root))
            if name in old:
                continue
            require(name in ALLOWED_NEW_CODE, "undeclared added execution dependency: " + name)
            additions[name] = {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
    require("scripts/software_organization_resume_admission_v044.py" in additions,
            "resume admission source missing")
    return {"original_execution_commit": ORIGINAL_COMMIT, "original_src_tree_sha256": ORIGINAL_TREE,
        "all_original_bytes_unchanged": True, "original_files": files, "new_files": additions,
        "scope": "All original src/scripts/tests/examples and pyproject bytes compared with the execution commit. No new src or unspecified helper can enter the frozen source tree."}


def bind_qualification(plan, reader, source_root):
    """Reuse recorded exact-source receipts, never the current driver's glob."""
    value = reader.read(plan["qualification"])
    require(value.get("passed") is True and value.get("version") == "software-organization-execution-v0.44"
            and value.get("new_model_calls") == value.get("new_backward_calls") == 0,
            "original qualification identity or result changed")
    require(bool(value.get("checks")) and all(row["exit_code"] == 0 for row in value["checks"]),
            "original CPU qualification checks failed")
    for row in value["checks"]:
        reader.path(row["log"])
    layered = reader.read(value["layered_admission"])
    require(layered.get("passed") is True and layered.get("version") == "software-organization-admission-v0.44"
            and layered.get("admission_sha256") == digest(json_bytes({k: v for k, v in layered.items()
                                                                       if k != "admission_sha256"})),
            "original layered qualification identity changed")
    for receipt in (value, layered):
        require(bool(receipt.get("source_files")), "missing original qualification source binding")
        for name, sha in receipt["source_files"].items():
            require(digest((Path(source_root) / name).read_bytes()) == sha,
                    "qualified source bytes changed: " + name)
    refs = layered["evidence_refs"]
    for ref in refs.values():
        reader.path(ref)
    history = reader.read(refs["historical_112"])
    routes = reader.read(refs["finite_lifecycle_routes"])
    require(history.get("passed") is True and history.get("expected_requests") == 112
            and routes.get("passed") is True and len(routes.get("route_results", [])) == 8,
            "original capacity receipts do not establish the admitted candidate")
    return {"qualification": plan["qualification"], "layered_admission": value["layered_admission"],
        "capacity_and_permission_receipts": refs, "source_files_checked": len(set(value["source_files"]) | set(layered["source_files"])),
        "reused_exactly": True, "new_capacity_encodings": 0, "new_route_executions": 0,
        "scope": "Reuse the originally passed qualification by its saved receipt hashes and explicit source sets; no regeneration and no repeated full raw-capacity artifact scan."}


def bind_closed_block(root, plan, reader):
    actual = Path(root) / FIRST_BLOCK / "actual"
    report, report_ref = checked_json(reader, actual / "report.json")
    progress, progress_ref = checked_json(reader, actual / "progress.json")
    require(report.get("source_before") == report.get("source_after") == plan["source"]
            and report.get("actor_identity_unchanged") is True
            and report.get("common_restored_exactly") is True
            and report.get("final_actor_identity") == plan["expected_actor_identity"],
            "original worker execution or actor guard failed")
    require(all(report.get(k) == 0 for k in ("new_actor_steps", "new_critic_steps", "new_backward_calls"))
            and report.get("actor_steps") == report.get("critic_steps") == 3, "original worker is not frozen 3/3")
    reader.path(report["plan"])
    require(Path(report["plan"]["path"]).resolve() == (Path(root) / "plan.json").resolve(),
            "original worker cites a different inventory")
    rows = []
    for unit, saved in zip(plan["assignments"][FIRST_BLOCK], progress):
        folder = actual / "episodes" / unit["slot_id"]
        result, result_ref = checked_json(reader, folder / "slot-result.json")
        guard, guard_ref = checked_json(reader, folder / "evaluation-guard.json")
        _, feedback_ref = checked_json(reader, folder / "feedback-loop.json")
        require(saved == {**unit, **result}, "original result differs from worker output: " + unit["slot_id"])
        require(result.get("status") == "closed" and type(result.get("R")) is int
                and result["R"] in (0, 1), "original slot is not closed with a known original R")
        require(result.get("actor_identity") == plan["expected_actor_identity"]
                and all(result.get(k) == 0 for k in ("actor_updates", "critic_updates", "new_backward_calls")),
                "original slot actor identity or update count changed")
        require(all(guard.get(key) is True for key in ("learning_unchanged", "rng_restored_exactly",
                    "software_binding_unchanged", "actor_identity_unchanged"))
                and guard.get("learning_before_sha256") == guard.get("learning_after_sha256")
                and guard.get("rng_before_sha256") == guard.get("rng_after_restore_sha256"),
                "original slot state guard failed")
        rows.append({"slot_id": unit["slot_id"], "R": result["R"], "submitted": result["submitted"],
            "slot_result": result_ref, "evaluation_guard": guard_ref, "original_feedback": feedback_ref})
    require(len(rows) == len(progress) == 4, "original closed block must contain exactly four outputs")
    return rows, report, progress, {"worker_report": report_ref, "worker_progress": progress_ref}


def bind_published_original(source_root, supervisor, report, gate):
    """Old results must still equal the immutable report published before resume."""
    object_id = ORIGINAL_PUBLICATION_COMMIT + ":docs/experiments/software-organization-v044.json"
    raw = subprocess.check_output(["git", "show", object_id], cwd=source_root)
    published = json.loads(raw)
    require(published.get("supervisor") == supervisor and published.get("first_block_gate") == gate
            and published.get("workers", {}).get(FIRST_BLOCK, {}).get("report") == report,
            "original stop, gate or worker results differ from the immutable published record")
    require(published.get("known") == 4 and published.get("scheduled") == 16,
            "published original inventory is not four closed plus twelve unstarted")
    for block in REMAINING_BLOCKS:
        require(published["workers"][block]["report"] is None,
                "published remaining worker has execution output")
    return {"git_object": object_id, "sha256": digest(raw), "bytes": len(raw),
            "old_worker_results_and_stop_exactly_preserved": True}


def installed_runtime_identity(executable, dependency_path, expected_versions):
    """Inspect metadata with the original interpreter; do not import packages."""
    code = """import importlib.metadata as m,json
rows={}
for name in ['torch','transformers','peft','tokenizers','Jinja2']:
 d=m.distribution(name)
 rows[name]={'version':d.version,'root':str(d.locate_file('')),
             'metadata':str(d._path / 'METADATA'),'record':str(d._path / 'RECORD')}
print(json.dumps(rows))
"""
    env = {**os.environ, "PYTHONPATH": dependency_path, "CUDA_VISIBLE_DEVICES": "",
           "PYTHONDONTWRITEBYTECODE": "1"}
    packages = json.loads(subprocess.check_output([str(executable), "-c", code], env=env, text=True))
    require(all(packages[name]["version"] == version for name, version in expected_versions.items()),
            "resident numerical/runtime package identity differs from original execution")
    for package in packages.values():
        for key in ("metadata", "record"):
            package[key] = reference(package[key])
    return {"executable": str(executable), "dependency_path": dependency_path,
        "packages": packages, "original_recorded_versions_matched": True,
        "scope": "Same interpreter/dependency path and original recorded torch/transformers/peft versions. Current metadata/RECORD identities freeze the resumed environment; no package import, GPU call or unrecorded historical full-package checksum claim."}


def bind_model_identity(root, plan, reader, supervisor):
    actual = Path(root) / FIRST_BLOCK / "actual"
    common = reader.read(plan["common"])
    checkpoint = reader.read(common["common"])
    reader.path(checkpoint["state"])
    restore, restore_ref = checked_json(reader, actual / "common-restore.json")
    for value in (common, checkpoint, restore):
        require(value.get("actor_steps") == value.get("critic_steps") == 3
                and value.get("actor_identity") == plan["expected_actor_identity"],
                "require the original complete common 3/3 actor")
    require(common["state_tensor_digest"] == checkpoint["state_tensor_digest"]
            == restore["state_sha256"] == plan["expected_state_sha256"]
            and restore.get("complete_state_exact") is True
            and restore["rng_sha256"] == common["training_rng_sha256"], "complete common state/RNG binding changed")
    require(checkpoint["state"] == plan["model_references"]["common_state"], "common state differs from original model reference")
    owner, owner_ref = checked_json(reader, actual / "resident/owner.json")
    inherited_owner = reader.read(plan["model_references"]["owner"])
    eos, eos_ref = checked_json(reader, actual / "resident-eos-contract.json")
    manifest = reader.read(plan["model_references"]["base_manifest"])
    model_path = Path(manifest["model_path"])
    assets = {}
    for name, saved in manifest["files"].items():
        path = model_path / name
        if name.endswith(".safetensors"):
            require(path.is_file() and path.stat().st_size == saved["bytes"], "pinned base shard missing or size changed")
            continue
        if name.endswith((".json", ".jinja", ".txt")):
            reader.path({"path": str(path), **saved})
            assets[name] = saved
    require(all(assets.get(name) == saved for name, saved in eos["official_source_files"].items()),
            "original tokenizer/renderer assets changed")
    require(owner["base_identity"]["manifest"]["sha256"] == plan["expected_actor_identity"]["base_manifest_sha256"],
            "base model manifest identity changed")
    profile = owner["inference_profile"]
    require(digest(json_bytes(profile)) == plan["expected_actor_identity"]["inference_profile_sha256"]
            and profile == inherited_owner["inference_profile"] and owner["recipe"] == inherited_owner["recipe"],
            "resident numerical, sampling or renderer profile differs from original actor")
    require(profile.get("max_context_tokens") == 16384 and profile.get("max_output_tokens") == 2048
            and profile.get("prefix_cache", {}).get("enabled") is False,
            "original inference capacity or cache profile changed")
    versions = {name: profile[name] for name in ("torch", "transformers", "peft")}
    runtime = installed_runtime_identity(supervisor["states"][FIRST_BLOCK]["command"][0],
                                         plan["runtime_dependency_path"], versions)
    for package in runtime["packages"].values():
        reader.path(package["metadata"])
        reader.path(package["record"])
    return {"common": plan["common"], "checkpoint": common["common"], "serialized_state": checkpoint["state"],
        "original_restore": restore_ref, "original_owner": owner_ref, "original_eos_contract": eos_ref,
        "actor_identity": plan["expected_actor_identity"], "state_tensor_sha256": plan["expected_state_sha256"],
        "model_manifest": plan["model_references"]["base_manifest"], "non_weight_assets": assets,
        "original_inference_profile_sha256": digest(json_bytes(profile)),
        "original_package_versions": versions, "resident_runtime_identity": runtime,
        "runtime_dependency_path": plan["runtime_dependency_path"],
        "scope": "Original 3/3 metadata and serialized common bytes, original guards, model manifest, shard presence/sizes and tokenizer/renderer/config bytes. No tensor loading, base-weight rehash, tokenizer call or numerical replay."}


def bind_remeasurement(path, reader, original_rows, original_gate_ref, source_root):
    from scripts.measure_organization_feedback_v044r1 import aggregate_denominators, first_block_gate

    summary, summary_ref = checked_json(reader, path)
    require(summary.get("version") == "organization-feedback-opportunities-v0.44r1"
            and summary.get("read_only") is True and summary.get("passed") is True
            and summary.get("original_artifacts_unchanged") is True
            and all(summary.get(key) == 0 for key in ("new_model_calls", "new_tokenizer_calls",
                                                      "new_test_or_acceptance_executions")),
            "revised first-block audit failed or altered original artifacts")
    require(summary.get("slot_ids") == [row["slot_id"] for row in original_rows], "revised audit does not cover the exact original four")
    require(summary.get("original_gate", {}).get("sha256") == original_gate_ref["sha256"],
            "revised audit is not bound to the original failed gate")
    reader.path(summary["original_gate"])
    gate = reader.read(summary["revised_gate"])
    require(gate.get("passed") is True and gate.get("measured_slots") == 4 and gate.get("reasons") == [],
            "revised mechanism gate did not pass")
    supplied = summary.get("original_slots", [])
    require(len(supplied) == 4, "revised audit missing original result bindings")
    for actual, saved in zip(original_rows, supplied):
        require(all(saved.get(key) == actual[key] for key in ("slot_id", "R", "submitted")),
                "revised audit changed original R or submission identity")
        for key in ("slot_result", "original_feedback"):
            require(saved[key]["sha256"] == actual[key]["sha256"], "revised audit changed original slot evidence")
            reader.path(saved[key])
    refs = summary.get("slot_measurements", [])
    require(len(refs) == 4, "revised audit missing four measurements")
    require(summary.get("measurements_by_slot") == dict(zip(summary["slot_ids"], refs)),
            "revised audit lookup differs from its verified ordered measurements")
    measurements = [reader.read(ref) for ref in refs]
    require(gate == first_block_gate(measurements), "revised gate does not follow its saved measurements")
    require([row.get("slot_id") for row in measurements] == summary["slot_ids"],
            "revised measurements have a different slot order or identity")
    old_measurements = [reader.read(row["original_feedback"]) for row in original_rows]
    observed_changes = []
    for old, new in zip(old_measurements, measurements):
        require(new.get("original_v044_remeasurement_sha256") == digest(json_bytes(old)),
                "full original feedback remeasurement was not reproduced")
        require(new.get("termination_revision", {}).get("unresolved") == [],
                "retirement attribution remains unresolved")
        allowed = {"version", "denominators", "feedback_records", "mechanism_gate_inputs"}
        require(all(new.get(key) == value for key, value in old.items() if key not in allowed),
                "revised measurement changed unrelated original fields")
        old_facts, new_facts = old["mechanism_gate_inputs"], new["mechanism_gate_inputs"]
        require(all(new_facts.get(key) == value for key, value in old_facts.items()
                    if key not in {"resolved", "unresolved_no_followup_ids"}),
                "revised measurement changed other original mechanical evidence")
        prior_rows, current_rows = old.get("feedback_records", []), new.get("feedback_records", [])
        require(len(prior_rows) == len(current_rows), "revised feedback denominator changed")
        for before, after in zip(prior_rows, current_rows):
            normalized = copy.deepcopy(after)
            normalized.pop("termination_attribution", None)
            if normalized.get("no_actual_followup"):
                previous_reason = before["no_actual_followup"]["reason"]
                revised_reason = normalized["no_actual_followup"]["reason"]
                if previous_reason != revised_reason:
                    observed_changes.append((new["slot_id"], before["feedback_id"], previous_reason, revised_reason))
                normalized["no_actual_followup"]["reason"] = before["no_actual_followup"]["reason"]
            require(normalized == before, "revised measurement altered feedback or actual presentation")
    changes = summary.get("classification_changes")
    require(isinstance(changes, list) and len(changes) == 1, "expected exactly the original direct-retirement explanation")
    change = changes[0]
    require(all(change.get(key) == value for key, value in {
        "slot_id": "org44-r1-s0-PT", "feedback_id": "feedback-610", "member": "member_002",
        "call_id": "model-83d9656bd89573202e40c8b5", "previous_reason": "unknown_no_actual_followup",
        "revised_reason": "voluntary_self_retirement", "presentation_unchanged": True,
        "feedback_denominator_retained": True}.items()), "unexpected classification correction")
    require(observed_changes == [("org44-r1-s0-PT", "feedback-610", "unknown_no_actual_followup",
                                  "voluntary_self_retirement")]
            and changes == [change for row in measurements
                            for change in row["termination_revision"]["classification_changes"]],
            "actual feedback explanation changes differ from the declared single correction")
    require(summary["original_denominators"] == aggregate_denominators(old_measurements)
            and summary["revised_denominators"] == aggregate_denominators(measurements),
            "revised audit denominator summary is inconsistent")
    before, after = summary["original_denominators"], summary["revised_denominators"]
    require({k: v for k, v in before.items() if k != "no_followup_reasons"}
            == {k: v for k, v in after.items() if k != "no_followup_reasons"}
            and after.get("all_saved_feedback_units") == 144
            and after.get("presented_in_first_actual_followup") == 136
            and after.get("without_later_actual_generation") == 8
            and after.get("no_followup_reasons") == {"team_budget": 6, "voluntary_end": 1,
                                                     "voluntary_self_retirement": 1},
            "revised audit changed original presentation opportunities")
    for ref in summary.get("protected_original_artifacts", []):
        reader.path(ref)
    bindings = summary.get("source_bindings", [])
    bound_sources = set()
    for ref in bindings:
        reader.path(ref)
        original_path = Path(ref["path"])
        prefix = next((name for name in ("src", "scripts", "tests") if name in original_path.parts), None)
        require(prefix is not None, "unrecognized revised measurement source path")
        relative = Path(*original_path.parts[original_path.parts.index(prefix):])
        bound_sources.add(str(relative))
        require(digest((Path(source_root) / relative).read_bytes()) == ref["sha256"],
                "revised measurement differs from resumed source: " + str(relative))
    require(bound_sources == {"scripts/measure_organization_feedback_v044r1.py",
        "tests/test_organization_feedback_v044r1.py",
        "scripts/measure_organization_feedback_v044.py", "scripts/software_context_replay_v044.py",
        "src/proworksim/software_feedback_v044.py", "src/proworksim/software_context_v044.py"},
        "revised measurement source binding is incomplete")
    return {"summary": summary_ref, "revised_gate": summary["revised_gate"],
        "slot_measurements": refs, "original_gate_preserved": original_gate_ref,
        "classification_changes": summary["classification_changes"],
        "original_denominators": summary["original_denominators"],
        "revised_denominators": summary["revised_denominators"]}


def build_admission(original_root, remeasurement, *, source_root=SOURCE):
    root, source_root = Path(original_root).resolve(), Path(source_root).resolve()
    reader = EvidenceReader()
    plan, plan_ref = checked_json(reader, root / "plan.json")
    require(plan.get("source") == {"code_commit": ORIGINAL_COMMIT, "code_dirty": False,
                                  "source_tree_sha256": ORIGINAL_TREE}, "wrong original execution identity")
    require(plan.get("plan_sha256") == ORIGINAL_PLAN_DIGEST
            == digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"})),
            "original frozen plan changed")
    assignments = validate_inventory(plan)
    supervisor, supervisor_ref = checked_json(reader, root / "supervisor.json")
    old_gate, old_gate_ref = checked_json(reader, root / "first-block-gate.json")
    finish, finish_ref = checked_json(reader, root / "finish.json")
    require(supervisor.get("source") == plan["source"] and supervisor.get("first_block_gate") == old_gate,
            "original supervisor and failed gate disagree")
    require(old_gate.get("passed") is False and old_gate.get("measured_slots") == 4
            and old_gate.get("reasons") == [{"slot_id": "org44-r1-s0-PT", "reason": "gate_unresolved"}]
            and finish.get("status") == "stopped_by_first_block_gate", "original stop or gate was overwritten")
    for ref in old_gate["measurements"]:
        reader.path(ref)
    old_rows, report, progress, worker_refs = bind_closed_block(root, plan, reader)
    published = bind_published_original(source_root, supervisor, report, old_gate)
    never_started = validate_never_started(root, supervisor, report, progress, plan["assignments"])
    revised = bind_remeasurement(remeasurement, reader, old_rows, old_gate_ref, source_root)
    sources = source_audit(source_root)
    qualification = bind_qualification(plan, reader, source_root)
    model = bind_model_identity(root, plan, reader, supervisor)
    value = {"version": VERSION, "passed": True, "original_run_root": str(root),
        "original_execution_source": plan["source"],
        "original_refs": {"plan": plan_ref, "supervisor": supervisor_ref, "gate": old_gate_ref,
                          "finish": finish_ref, **worker_refs},
        "original_closed_slots": old_rows, "never_started_checks": never_started,
        "original_published_record": published,
        "remaining_assignments": assignments,
        "remaining_cases_sha256": {block: [digest(json_bytes(case)) for case in plan["cases"][block]]
                                   for block in REMAINING_BLOCKS},
        "unchanged_plan_fields": {key: plan[key] for key in ("business_bindings", "limits", "gpu_preference",
            "feedback_protocol", "sampling", "external_intervention", "automatic_retries", "automatic_successors",
            "training_eligible", "independent_confirmation_eligible", "gpu_seconds_cap", "worker_seconds_cap",
            "wall_deadline", "old_training_queues_remain_paused")},
        "revised_first_block": revised, "source_audit": sources,
        "qualification_reuse": qualification, "model_identity": model,
        "resume_scope": {"logical_inventory": 16, "old_completed": 4, "max_new_episodes": 12,
            "max_new_resident_workers": 3, "max_new_decisions": 1536, "max_new_attempts": 1536,
            "max_new_tokens": 6000000, "max_new_test_runs": 384, "old_budget_transfer": False,
            "recollect_first_block": False, "resume_old_member_sessions": False, "force_gate": False},
        "verified_refs": list(reader.checked.values()), "new_model_calls": 0, "new_tokenizer_calls": 0,
        "new_capacity_encodings": 0, "new_test_or_acceptance_executions": 0, "new_backward_calls": 0,
        "scope": "Only the three previously unstarted original blocks may be collected. Original gate=false, closed four results and stop records remain untouched. Corrected terminal interpretation is not actual feedback presentation or business acceptance."}
    value["admission_sha256"] = digest(json_bytes(value))
    return value


def create_admission(original_root, remeasurement, output, *, source_root=SOURCE):
    output = Path(output).resolve()
    require(not output.exists(), "refuse to overwrite a resume admission")
    value = build_admission(original_root, remeasurement, source_root=source_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(json_bytes(value))
    return value


def validate_admission(path_or_ref, *, source_root=SOURCE):
    reader = EvidenceReader()
    ref = path_or_ref if isinstance(path_or_ref, dict) else reference(path_or_ref)
    value = reader.read(ref)
    require(value.get("version") == VERSION and value.get("passed") is True
            and value.get("admission_sha256") == digest(json_bytes({k: v for k, v in value.items()
                                                                     if k != "admission_sha256"})),
            "resume admission identity changed")
    rebuilt = build_admission(value["original_run_root"], value["revised_first_block"]["summary"]["path"],
                              source_root=source_root)
    require(rebuilt == value, "resume admission no longer matches its original evidence and execution dependencies")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-run-root", type=Path, required=True)
    parser.add_argument("--remeasurement", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = create_admission(args.original_run_root, args.remeasurement, args.output, source_root=args.source_root)
    print(json.dumps({"passed": value["passed"], "new_slots": value["resume_scope"]["max_new_episodes"],
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
