"""Finite v048 representation admission, reusing frozen native capacity proof."""
from __future__ import annotations

import argparse
from pathlib import Path

from proworksim.storage import digest, json_bytes, read_json
from scripts.run_ne_v021 import reference, write
from scripts.software_organization_admission_v044 import EvidenceReader
from scripts.software_organization_admission_v045 import source_files
from scripts.software_organization_admission_v046 import validate_model_qualification

VERSION = "software-organization-representation-admission-v0.48"
SOURCE = Path(__file__).resolve().parents[1]
AUDIT_SHA = "a3df7a307f8b7525448c38997933654cb1c43a9c10cc0abedd18528505fb9941"
CANDIDATE_SHA = "dec0b1cdbd0197be473f093341cb075c9f15cb3c8dc211980623aa113f631e29"
REPLAY_VERSION = "software-context-replay-v0.48"
CPU_VERSION = "software-organization-controls-v0.48"
# The already-completed 21-request encoding remains evidence for unchanged
# representation/runtime/numerical code. This one pre-model host repair fixes
# comparison of path+sha references with readers that additionally report bytes.
# It must not permit a new encoding candidate or any replay/world change.
REPLAY_HOST_ONLY_REPAIRS = frozenset({
    "scripts/software_organization_stop_policy_v048.py",
    "tests/test_software_organization_stop_policy_v048.py",
    "scripts/software_organization_admission_v048.py",
    "tests/test_software_organization_admission_v048.py",
})
REQUIRED_CONTROLS = frozenset({
    "same_input_reference_integrity", "historical_source_and_token_replay",
    "eight_slot_host_inventory_and_no_load_gate", "representation_measurement_and_stop_binding",
})
REQUIRED_REPLAY_CHECKS = frozenset({
    "finite_inventory_exact", "original_all_bindings_reproduced",
    "all_reference_integrity_passed", "targeted_eight_hard_fit",
    "final_submit_eleven_hard_fit", "mechanical_controls_passed",
    "candidate_predeclared_exact", "input_source_hashes_unchanged",
    "source_files_unchanged", "cpu_only",
})
EXPECTED_INVENTORY = {
    "unique_requests": 21, "hard_context_rejected": 10, "final_fixed_submit": 11,
    "targeted_LA_LB_P4": 8, "other_rejections": 2,
}


def require(condition, reason):
    if not condition:
        raise ValueError("v048 admission rejected: " + reason)


def source_reuse(previous, current):
    changed = sorted(name for name, sha in previous.items() if current.get(name) != sha)
    additions = sorted(set(current) - set(previous))
    require(not changed, "historical source changed: " + repr(changed))
    require(bool(additions) and all(Path(name).stem.endswith("_v048") for name in additions),
            "only isolated v048 source/test additions are authorized")
    return {"historical_files_unchanged": True, "historical_source_files": len(previous),
            "added_files": additions}


def validate_replay_source_reuse(recorded, current):
    """Retain original token evidence across only the four declared host files."""
    require(isinstance(recorded, dict) and isinstance(current, dict)
            and set(recorded) == set(current), "replay source inventory changed")
    changed = sorted(name for name in current if recorded[name] != current[name])
    require(set(changed) <= REPLAY_HOST_ONLY_REPAIRS,
            "replay representation/runtime/numerical source changed: " + repr(changed))
    return {
        "version": "v048-reference-shape-host-only-replay-reuse-v1",
        "exact_source_match": not changed,
        "source_file_count": len(recorded),
        "unchanged_source_file_count": len(recorded) - len(changed),
        "allowed_host_only_files": sorted(REPLAY_HOST_ONLY_REPAIRS),
        "changed_host_only_files": [
            {"path": name, "old_sha256": recorded[name], "new_sha256": current[name]}
            for name in changed
        ],
        "representation_runtime_world_tokenizer_unchanged": True,
        "original_replay_source_snapshot_preserved": True,
        "new_tokenizer_calls": 0,
        "reason": "Pre-model host reference-shape repair: compare the existing path+sha binding without requiring an optional bytes field; current full-source CPU controls remain required.",
    }


def validate_cpu(value, current, reader):
    require(value.get("version") == CPU_VERSION and value.get("passed") is True,
            "finite affected CPU controls incomplete")
    require(value.get("source_files") == current and value.get("source_unchanged_during_controls") is True,
            "CPU-tested source changed")
    require(value.get("new_model_calls") == value.get("new_backward_calls") == 0
            and value.get("model_weights_loaded") is False, "CPU gate includes model or learning work")
    controls = value.get("controls", {})
    require(set(controls) == REQUIRED_CONTROLS and
            all(v.get("passed") is True for v in controls.values()), "affected controls missing or failed")
    require(value.get("ruff", {}).get("returncode") == 0, "static check failed")
    require(bool(value.get("artifact_refs")), "CPU control receipts absent")
    for ref in value["artifact_refs"]:
        reader.path(ref)
    return {"passed": True, "controls": sorted(controls),
            "test_count": value.get("pytest", {}).get("tests"), "new_model_calls": 0}


def _all_true(value):
    return isinstance(value, dict) and bool(value) and all(v is True for v in value.values())


def validate_replay(value, current, reader):
    require(value.get("version") == REPLAY_VERSION and value.get("passed") is True,
            "the single representation candidate did not pass; model work is forbidden")
    replay_source_reuse = validate_replay_source_reuse(value.get("source_files"), current)
    require(value.get("candidate", {}).get("sha256") == CANDIDATE_SHA,
            "replay is not the frozen single candidate")
    reader.path(value["candidate"])
    inventory = reader.read(value["source_inventory"])
    require(inventory.get("version") == "v048-finite-source-inventory-v1",
            "wrong original source inventory")
    reader.path(value["mechanical_controls"])
    require(value.get("inventory") == EXPECTED_INVENTORY, "offline inventory is not exactly the authorized 21")
    checks = value.get("checks", {})
    require(REQUIRED_REPLAY_CHECKS <= set(checks) and _all_true(checks),
            "original replay, reference integrity or required hard fit failed")
    require(all(value.get(k) == 0 for k in (
        "new_model_calls", "new_world_actions", "new_tests_or_acceptance_calls", "new_gpu_operations"))
        and value.get("model_weights_loaded") is False, "offline work was not CPU-only")
    rows = value.get("rows", [])
    require(len(rows) == 21 and len({(r.get("slot_id"), r.get("call_id")) for r in rows}) == 21,
            "duplicate or missing original request")
    originals = {(r.get("slot_id"), r.get("call_id")): r for r in inventory.get("requests", [])}
    require(len(originals) == len(inventory.get("requests", [])) == 21
            and set(originals) == {(r["slot_id"], r["call_id"]) for r in rows},
            "replay identities differ from the original 21-source inventory")
    hard = [r for r in rows if r.get("kind") == "hard_context_rejected"]
    submits = [r for r in rows if r.get("kind") == "final_fixed_submit"]
    targets = [r for r in rows if r.get("targeted_LA_LB_P4") is True]
    require(len(hard) == 10 and len(submits) == 11 and len(targets) == 8
            and all(r in hard for r in targets), "wrong source-kind or target inventory")
    expected_targets = {"org47-A-r0-P4-B250000", "org47-A-r2-P4-B250000",
                        "org47-B-r0-P4-B500000", "org47-B-r2-P4-B500000"}
    require({r.get("slot_id") for r in targets} == expected_targets,
            "target roots or architectures differ from the prelocked eight")
    require(len({r.get("slot_id") for r in submits}) == 11, "one final submit request per original submitted slot required")
    for row in rows:
        original = originals[(row["slot_id"], row["call_id"])]
        require(row.get("historical_source") == original and all(
            row.get(k) == original.get(k) for k in
            ("kind", "member", "stage_id", "targeted_LA_LB_P4")),
            "original source identity or provenance snapshot changed")
        require(row.get("passed") is True
                and _all_true(row.get("original_reproduction_checks"))
                and _all_true(row.get("reference_integrity_checks")),
                "a request lacks exact original reproduction or reference integrity")
        require(all(isinstance(row.get(k), str) and row[k] for k in ("slot_id", "call_id", "member")),
                "request identity is incomplete")
        for arm in ("gamma0", "gamma1"):
            for package in ("selected", "protected"):
                encoded = row.get(arm, {}).get(package, {})
                require(type(encoded.get("prompt_tokens")) is int and encoded["prompt_tokens"] > 0
                        and encoded.get("reserved_output_tokens") == 2048
                        and encoded.get("context_limit") == 18432
                        and isinstance(encoded.get("input_ids_sha256"), str)
                        and isinstance(encoded.get("rendered_prompt_sha256"), str)
                        and encoded.get("fits") is (encoded["prompt_tokens"] + 2048 <= 18432),
                        "native encoding or hard-capacity accounting is incomplete")
        prep = original.get("historical_preparation", {})
        require(all(row["gamma0"]["selected"].get(k) == prep.get(k) for k in
                    ("prompt_tokens", "reserved_output_tokens", "context_limit", "fits",
                     "input_ids_sha256", "rendered_prompt_sha256")),
                "Gamma0 selected encoding differs from the original native preparation")
        if row in targets or row in submits:
            require(row["gamma1"]["selected"]["fits"] is True,
                    "one required old target remains over capacity")
    return {"passed": True, "requests": 21, "primary_targets": 8,
            "candidate_sha256": CANDIDATE_SHA, "new_model_calls": 0,
            "replay_source_reuse": replay_source_reuse}


def build_admission(data_root, controls, replay, *, source_root=SOURCE):
    data_root, source_root = Path(data_root).resolve(), Path(source_root).resolve()
    reader = EvidenceReader()
    parent_ref = reference(data_root / "runs/software-organization-v047/plan.json")
    parent = reader.read(parent_ref)
    require(parent.get("version") == "software-organization-architecture-pilot-v0.47",
            "wrong sealed parent plan")
    current = source_files(source_root)
    unchanged = source_reuse(parent["source_files"], current)
    original = reader.read(parent["original_plan"])
    qualification_ref = parent["reused_model_qualification"]
    qualified = validate_model_qualification(reader.read(qualification_ref), original, reader)
    require(qualified["capacity_actor_identity"] == parent["expected_actor_identity"]
            and qualified["capacity_recipe_sha256"] == parent["expected_capacity_recipe_sha256"]
            and qualified["capacity_profile_sha256"] == parent["expected_capacity_profile_sha256"],
            "original qualified capacity/common identity changed")
    audit_ref = reference(source_root / "docs/reference/audit-v047-next-v048-representation.md")
    candidate_ref = reference(source_root / "docs/experiments/software-organization-v048-candidate.json")
    require(audit_ref["sha256"] == AUDIT_SHA and candidate_ref["sha256"] == CANDIDATE_SHA,
            "audit or predeclared single candidate changed")
    common = reader.read(parent["common"])
    require((common.get("actor_steps"), common.get("critic_steps")) == (3, 3),
            "original complete common3/3 required")
    controls_ref, replay_ref = reference(controls), reference(replay)
    cpu = validate_cpu(reader.read(controls_ref), current, reader)
    replay_summary = validate_replay(reader.read(replay_ref), current, reader)
    result = {
        "version": VERSION, "passed": True, "source_files": current, "source_reuse": unchanged,
        "parent_plan": parent_ref, "original_plan": parent["original_plan"], "common": parent["common"],
        "audit": audit_ref, "candidate": candidate_ref,
        "cpu_controls": controls_ref, "cpu_summary": cpu,
        "offline_replay": replay_ref, "offline_summary": replay_summary,
        "reused_model_qualification": qualification_ref, "capacity_qualification": qualified,
        "qualification_scope": "Original v046 native C18432/common/numerical proof reused; no new model qualification or old44 material replay.",
        "new_qualification_model_calls": 0, "new_qualification_actual_tokens": 0,
        "new_model_calls": 0, "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0,
        "verified_artifacts": list(reader.checked.values()), "automatic_successors": [],
    }
    result["admission_sha256"] = digest(json_bytes(result))
    return result


def create_admission(data_root, controls, replay, output, *, source_root=SOURCE):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Retain original admission evidence; no overwrite")
    result = build_admission(data_root, controls, replay, source_root=source_root)
    write(output, result)
    return result


def validate_admission(path, *, source_root=SOURCE):
    value = read_json(path)
    require(value.get("version") == VERSION and value.get("passed") is True,
            "admission is not a passed v048 receipt")
    require(value.get("admission_sha256") == digest(json_bytes(
        {k: v for k, v in value.items() if k != "admission_sha256"})), "admission digest mismatch")
    data_root = Path(value["parent_plan"]["path"]).parents[2]
    rebuilt = build_admission(data_root, value["cpu_controls"]["path"],
                              value["offline_replay"]["path"], source_root=source_root)
    require(rebuilt == value, "qualification, finite replay, controls or frozen source changed")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("create", "validate"))
    parser.add_argument("--data-root", type=Path, default=SOURCE)
    parser.add_argument("--controls", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "create":
        create_admission(args.data_root, args.controls, args.replay, args.output)
    else:
        validate_admission(args.output)


if __name__ == "__main__":
    main()
