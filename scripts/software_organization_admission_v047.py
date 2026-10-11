"""Bind the new architecture pilot to finite CPU controls and existing C18432 proof."""
from __future__ import annotations

import argparse
from pathlib import Path

from proworksim.storage import digest, json_bytes, read_json
from scripts.run_ne_v021 import reference, write
from scripts.software_organization_admission_v044 import EvidenceReader
from scripts.software_organization_admission_v046 import validate_model_qualification
from scripts.software_organization_admission_v045 import source_files

VERSION = "software-organization-architecture-admission-v0.47"
SOURCE = Path(__file__).resolve().parents[1]
AUDIT_SHA = "79a0cd1605f3071c8c33f26ea90bda30f001a40b8f6d0d7c8062f411baa7ef6d"
REQUIRED_CONTROLS = frozenset({
    "new_membership_and_permissions", "stage_accounting_and_forward_transfer",
    "exact_candidate_adoption_and_native_submission", "staged_native_sdk_and_terminal_guard",
    "deadline_dispatch_cancellation_and_inflight_close", "measurement_and_joint_token_censoring",
    "phase_inventory_and_frozen_qualification_reuse", "initial_new_interface_tokenizer_hard_capacity",
})
CPU_ONLY_SOURCE_CHANGES = frozenset({
    "scripts/software_organization_qualification_v047.py",
    "scripts/software_organization_admission_v047.py",
    "tests/test_software_organization_materials_v047.py",
    "tests/test_software_organization_admission_v047.py",
})


def require(condition, reason):
    if not condition:
        raise ValueError("v047 admission rejected: " + reason)


def source_reuse(previous, current):
    """Old evidence/source is immutable; new Γ resides in explicit v047 files."""
    changed = [name for name, sha in previous.items() if current.get(name) != sha]
    additions = sorted(set(current) - set(previous))
    require(not changed, "historical source changed: " + repr(changed))
    require(bool(additions) and all(Path(name).stem.endswith("_v047") for name in additions),
            "all new implementation and tests must be isolated v047 files")
    return {"historical_source_files": len(previous), "historical_files_unchanged": True,
            "added_files": additions, "new_source_files": len(additions)}


def validate_material_source_reuse(recorded, current):
    """A CPU itinerary repair cannot change the model's world or execution code."""
    require(set(recorded) == set(current), "material reuse source inventory changed")
    changed = sorted(name for name in current if recorded[name] != current[name])
    require(set(changed) <= CPU_ONLY_SOURCE_CHANGES,
            "material reuse changed production/numerical source: " + repr(changed))
    return {"production_sources_unchanged": True, "cpu_only_changed_files": changed,
            "allowed_cpu_only_files": sorted(CPU_ONLY_SOURCE_CHANGES)}


def validate_cpu(value, current, reader):
    require(value.get("version") == "software-organization-qualification-v0.47" and value.get("passed") is True,
            "finite affected CPU controls incomplete")
    require(value.get("source_files") == current, "CPU-tested source changed")
    require(value.get("new_model_calls") == value.get("new_backward_calls") == 0
            and value.get("model_weights_loaded") is False, "CPU gate includes new model/learning work")
    require(value.get("source_unchanged_during_controls") is True, "CPU sources changed during controls")
    controls = value.get("controls", {})
    require(set(controls) == REQUIRED_CONTROLS and all(v.get("passed") is True for v in controls.values()),
            "declared new interface/accounting/closure routes did not all pass")
    require(value.get("ruff", {}).get("returncode") == 0, "static check failed")
    artifacts = value.get("artifact_refs", [])
    require(bool(artifacts), "CPU control receipts absent")
    for item in artifacts:
        reader.path(item)
    tokenizer = reader.read(value["initial_tokenizer_control"])
    require(tokenizer.get("passed") is True and tokenizer.get("model_weights_loaded") is False
            and tokenizer.get("new_model_calls") == 0
            and tokenizer.get("context_limit") == 18432
            and tokenizer.get("reserved_output_tokens") == 2048
            and tokenizer.get("source_files") == current
            and tokenizer.get("source_unchanged_during_routes") is True,
            "new initial interface hard-capacity proof absent")
    from scripts.software_organization_v047 import assignments
    route_ids = {u["slot_id"] for seq in assignments().values() for u in seq}
    routes = tokenizer.get("routes", [])
    require(tokenizer.get("required_routes") == 44 and len(routes) == 44
            and {r.get("route_id") for r in routes} == route_ids
            and all(r.get("passed") is True and type(r.get("min_selected_headroom")) is int
                    and r["min_selected_headroom"] >= 0
                    and r.get("prepared_requests", 0) >= r.get("programmed_responses", 0) > 0 for r in routes),
            "new material inventory or exact hard-capacity bound incomplete")
    if tokenizer.get("evidence_kind") == "exact_reuse_plus_cpu_fixture_route_revision":
        previous = reader.read(tokenizer["reused_routes_source"])
        revised = reader.read(tokenizer["revised_routes_source"])
        reuse = validate_material_source_reuse(previous["source_files"], current)
        require(tokenizer.get("production_source_reuse") == reuse,
                "material reuse lacks exact unchanged production-source proof")
        require(revised.get("source_files") == current and revised.get("passed") is True
                and revised.get("source_unchanged_during_routes") is True,
                "new bounded fixture paths did not pass with current source")
        revised_ids = set(tokenizer.get("revised_route_ids", []))
        expected_revised = {"org47-A-r1-P4-B250000", "org47-B-r1-P4-B500000"}
        require(revised_ids == expected_revised
                and {r["route_id"] for r in revised["routes"]} == revised_ids
                and revised.get("required_routes") == len(revised_ids)
                and all(r["passed"] for r in revised["routes"]),
                "only the two explicitly revised CPU positive paths may replace their old failed controls")
        old_rows = {r["route_id"]: r for r in previous["routes"]}
        new_rows = {r["route_id"]: r for r in revised["routes"]}
        require(set(old_rows) == route_ids and previous.get("passed") is False,
                "original failed whole-run control must remain preserved")
        for row in routes:
            expected = new_rows[row["route_id"]] if row["route_id"] in revised_ids else old_rows[row["route_id"]]
            require(row == expected and expected["passed"] is True,
                    "retained CPU input evidence was modified or a failed path imputed as passed")
            reader.path(row["receipt"])
        require(tokenizer.get("new_model_calls") == revised.get("new_model_calls") == previous.get("new_model_calls") == 0,
                "CPU material reuse may not hide a new model qualification")
    return {"passed": True, "controls": sorted(controls), "test_count": value.get("pytest", {}).get("tests"),
            "new_model_calls": 0, "initial_tokenizer_control": value["initial_tokenizer_control"]}


def build_admission(data_root, controls, *, source_root=SOURCE):
    data_root, source_root = Path(data_root).resolve(), Path(source_root).resolve()
    reader = EvidenceReader()
    parent_ref = reference(data_root / "runs/software-organization-v046/plan.json")
    parent = reader.read(parent_ref)
    require(parent.get("version") == "software-organization-capacity-diagnostic-v0.46", "wrong sealed parent plan")
    current = source_files(source_root)
    unchanged = source_reuse(parent["source_files"], current)
    original = reader.read(parent["original_plan"])
    qualification = reader.read(parent["qualification"])
    qualified = validate_model_qualification(qualification, original, reader)
    require(qualified["capacity_actor_identity"] == parent["expected_actor_identity"]
            and qualified["capacity_recipe_sha256"] == parent["expected_capacity_recipe_sha256"]
            and qualified["capacity_profile_sha256"] == parent["expected_capacity_profile_sha256"],
            "native qualification and original capacity identity disagree")
    # All old numerical/model/context/tokenizer files were checked above. New files
    # add execution Γ and its meters, not a new model or numeric implementation.
    controls_ref = reference(controls)
    cpu = validate_cpu(reader.read(controls_ref), current, reader)
    audit_ref = reference(source_root / "docs/reference/audit-v046-next-v047-architecture.md")
    require(audit_ref["sha256"] == AUDIT_SHA, "user audit archive changed")
    common = reader.read(parent["common"])
    require((common.get("actor_steps"), common.get("critic_steps")) == (3, 3), "original complete common required")
    result = {
        "version": VERSION, "passed": True, "source_files": current, "source_reuse": unchanged,
        "parent_plan": parent_ref, "original_plan": parent["original_plan"], "common": parent["common"],
        "audit": audit_ref, "cpu_controls": controls_ref, "cpu_summary": cpu,
        "reused_model_qualification": parent["qualification"], "capacity_qualification": qualified,
        "qualification_scope": "Exact prior native C18432/common/numerical qualification reused. Its one historical call is not a new pilot call or cost.",
        "new_qualification_model_calls": 0, "new_qualification_actual_tokens": 0,
        "new_model_calls": 0, "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0,
        "verified_artifacts": list(reader.checked.values()), "automatic_successors": [],
    }
    result["admission_sha256"] = digest(json_bytes(result))
    return result


def create_admission(data_root, controls, output, *, source_root=SOURCE):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Retain previous admission receipts")
    result = build_admission(data_root, controls, source_root=source_root)
    write(output, result)
    return result


def validate_admission(path, *, source_root=SOURCE):
    value = read_json(path)
    require(value.get("admission_sha256") == digest(json_bytes({k: v for k, v in value.items() if k != "admission_sha256"})),
            "admission digest mismatch")
    data_root = Path(value["parent_plan"]["path"]).parents[2]
    rebuilt = build_admission(data_root, value["cpu_controls"]["path"], source_root=source_root)
    require(rebuilt == value, "qualification, controls, source or shared common changed")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("create", "validate"))
    parser.add_argument("--data-root", type=Path, default=SOURCE)
    parser.add_argument("--controls", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "create":
        create_admission(args.data_root, args.controls, args.output)
    else:
        validate_admission(args.output)


if __name__ == "__main__":
    main()
