"""G0: reproject byte-identical copies of original E2 checkpoints; test measurement.

This is read-only replay, not fresh adapter execution or a new kernel experiment.
Original 31/31 checks remain historical outputs with the audited limitation.
"""

import argparse
import copy
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from adapter_conformance_experiment import (
    MARKERS,
    expected_confirmation_check,
    formal_confirmation_fact,
    semantic_projection,
)
from state_projection_experiment import TEMPLATES, write_json

from proworksim.audit import code_identity
from proworksim.core.references import ApplicabilityContext, VersionRef
from proworksim.core.rules import confirm_credential, registered_applicability
from proworksim.core.types import Credential
from proworksim.storage import digest


def confirmation_fixture():
    reference = {"artifact_id": "policy", "version_id": "v1"}
    state = {
        "clock": 2,
        "roles": [{"role_id": "signatory"}],
        "organization": {
            "positions": {},
            "grants": [{"actor_id": "signatory", "power": "confirm", "subject": "policy",
                        "work_nodes": ["work"]}],
        },
        "artifacts": {
            "policy": {"artifact_id": "policy", "current_version": "v1", "versions": {
                "v1": {"artifact_id": "policy", "version_id": "v1", "logical_time": 1},
                "v2": {"artifact_id": "policy", "version_id": "v2", "logical_time": 2},
            }},
        },
        "attestations": {},
    }
    confirm_credential(state, "signatory", reference, Credential(
        reference, "project", "policy", 1, ("work",), None,
        "analysis", 1, "signatory", "signed-v1",
    ))
    context = ApplicabilityContext("project", "work", "policy", 1, "work", None, "analysis", 2)
    return state, reference, context.to_dict()


def measurement_cases():
    original, reference, context = confirmation_fixture()
    cases = []

    def add(name, mutation=None, expected_formal=False, expected_applicability="UNASSESSED"):
        state, query = copy.deepcopy(original), copy.deepcopy(context)
        if mutation:
            mutation(state, query)
        cases.append({"name": name, "state": state, "reference": reference, "context": query,
                      "expected_formal": expected_formal,
                      "expected_applicability": expected_applicability})

    def attestation_change(key, value):
        return lambda state, context: state["attestations"]["signed-v1"].update({key: value})

    add("legal_mixed_reference_spellings", expected_formal=True, expected_applicability="PASS")
    add("missing_attestation", lambda state, query: state["attestations"].clear())
    add("wrong_exact_version", attestation_change("reference", {
        "object_id": "policy", "version_id": "v2"}))
    add("wrong_attestation_id", attestation_change("attestation_id", "other-signature"))
    add("wrong_signer", attestation_change("actor_id", "another-actor"))
    add("wrong_requirement_link", attestation_change("requirement_version", 2))
    add("wrong_work_scope", attestation_change("work_nodes", ["another-work"]))
    add("wrong_credential_reference", lambda state, query:
        state["artifacts"]["policy"]["versions"]["v1"]["credential"].update({
            "reference": {"artifact_id": "policy", "version_id": "v2"}}))
    add("historical_issuance_new_requirement", lambda state, query:
        query.update(requirement_version=2), expected_formal=True, expected_applicability="FAIL")
    return cases


def run_measurement_controls(measurement=formal_confirmation_fact):
    results = []
    for case in measurement_cases():
        state = copy.deepcopy(case["state"])
        observed_formal = measurement(state, case["reference"])
        applicability = registered_applicability(state, case["reference"], case["context"])
        results.append({
            **case,
            "observed_formal": observed_formal,
            "observed_applicability": applicability.to_dict(),
            "measurement_preserved_input": state == case["state"],
            "passed": observed_formal == case["expected_formal"]
            and applicability.status.value == case["expected_applicability"]
            and state == case["state"],
        })
    return results


def measurement_mutations():
    def linked_record(state, reference):
        ref = VersionRef.from_mapping(reference)
        record = state["artifacts"][ref.object_id]["versions"][ref.version_id]["credential"]
        return state["attestations"].get(record["attestation_ref"], {})

    mutants = (
        ("raw_dictionary_equality", "legal_mixed_reference_spellings",
         lambda state, ref: bool(linked_record(state, ref))
         and linked_record(state, ref).get("reference") == ref),
        ("object_only_reference", "wrong_exact_version",
         lambda state, ref: bool(linked_record(state, ref))
         and VersionRef.from_mapping(linked_record(state, ref)["reference"]).object_id
         == VersionRef.from_mapping(ref).object_id),
        ("attestation_existence_only", "wrong_attestation_id",
         lambda state, ref: bool(linked_record(state, ref))),
    )
    result = []
    for name, named_assertion, mutant in mutants:
        control = next(c for c in run_measurement_controls() if c["name"] == named_assertion)
        injected = next(c for c in run_measurement_controls(mutant)
                        if c["name"] == named_assertion)
        result.append({
            "mutant": name,
            "named_assertion": named_assertion,
            "control_passed": control["passed"],
            "injected_observed_formal": injected["observed_formal"],
            "expected_formal": injected["expected_formal"],
            "injection_activated": control["observed_formal"] != injected["observed_formal"],
            "named_assertion_failed": not injected["passed"],
            "detected": control["passed"] and not injected["passed"],
        })
    return result


def tree_hashes(root):
    return {str(path.relative_to(root)): digest(path.read_bytes())
            for path in sorted(root.rglob("*")) if path.is_file()}


def reproject(source, output):
    source_before = tree_hashes(source)
    original_report = json.loads((source / "report.json").read_text())
    shutil.copy2(source / "report.json", output / "original-report.json")
    results = []
    lookup = {}
    for trajectory, markers in MARKERS.items():
        for template in TEMPLATES:
            origin = source / f"{trajectory}-{template}"
            copied = output / "checkpoint-copies" / f"{trajectory}-{template}"
            copied.mkdir(parents=True)
            initial = json.loads((origin / "ConfirmGrant-state.json").read_text())
            work_id = "work-1" if template == "operating" else "publish-note"
            trace = SimpleNamespace(
                initial_reference=initial["work_items"][work_id]["required_credentials"][0],
                coordinator="manager" if template == "operating" else "editor",
                worker="analyst" if template == "operating" else "author",
                reviewer="reviewer" if template == "operating" else "editor",
            )
            source_result = json.loads((origin / "result.json").read_text())
            shutil.copy2(origin / "result.json", copied / "original-result.json")
            for marker in markers:
                original = origin / f"{marker}-state.json"
                snapshot = copied / original.name
                shutil.copy2(original, snapshot)
                state = json.loads(snapshot.read_text())
                corrected = semantic_projection(trace, state)
                before = source_result["markers"][marker]["semantic_projection"]
                old_check = expected_confirmation_check(trajectory, marker, before)
                new_check = expected_confirmation_check(trajectory, marker, corrected)
                scrubbed = copy.deepcopy(corrected)
                for old, new in zip(before["credentials"], scrubbed["credentials"]):
                    new["formal_confirmation"] = old["formal_confirmation"]
                result = {
                    "template": template, "trajectory": trajectory, "marker": marker,
                    "original_snapshot": str(original), "copied_snapshot": str(snapshot),
                    "original_sha256": digest(original.read_bytes()),
                    "copy_sha256": digest(snapshot.read_bytes()),
                    "original_projection": before, "corrected_projection": corrected,
                    "old_independent_expectation": old_check,
                    "corrected_independent_expectation": new_check,
                    "only_confirmation_dimension_changed": before == scrubbed,
                    "source_state_not_mutated": state == json.loads(snapshot.read_text()),
                }
                result["passed"] = (result["original_sha256"] == result["copy_sha256"]
                                    and new_check["passed"]
                                    and result["only_confirmation_dimension_changed"]
                                    and result["source_state_not_mutated"])
                results.append(result)
                lookup[trajectory, marker, template] = corrected
    comparisons = [
        {"trajectory": trajectory, "marker": marker,
         "passed": lookup[trajectory, marker, TEMPLATES[0]]
         == lookup[trajectory, marker, TEMPLATES[1]]}
        for trajectory, markers in MARKERS.items() for marker in markers
    ]
    source_after = tree_hashes(source)
    return {
        "original_suite": original_report["suite"],
        "original_code_identity": original_report["code_identity_before"],
        "original_check_count": original_report["check_count"],
        "original_check_pass_count": original_report["check_pass_count"],
        "original_claim_limit": "31/31 is preserved as historical script output; matching false formal-confirmation values did not establish correct measurement of issuance.",
        "source_tree_hashes_before": source_before,
        "source_tree_hashes_after": source_after,
        "source_tree_unchanged": source_before == source_after,
        "checkpoint_count": len(results),
        "checkpoint_pass_count": sum(result["passed"] for result in results),
        "original_independent_expectation_pass_count": sum(
            result["old_independent_expectation"]["passed"] for result in results),
        "corrected_independent_expectation_pass_count": sum(
            result["corrected_independent_expectation"]["passed"] for result in results),
        "corrected_credential_count": sum(len(r["corrected_projection"]["credentials"])
                                          for r in results),
        "cross_template_comparisons": comparisons,
        "cross_template_pass_count": sum(c["passed"] for c in comparisons),
        "checkpoints": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("runs/adapter-conformance-v05"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output directory")
    args.output.mkdir(parents=True)
    identity = code_identity()
    controls = run_measurement_controls()
    mutants = measurement_mutations()
    replay = reproject(args.source, args.output)
    shared_false = {"credentials": [
        {"credential": "C1", "formal_confirmation": False, "coordinator_signed": True}
    ]}
    false_check = expected_confirmation_check("withdraw_resubmit", "ConfirmGrant", shared_false)
    report = {
        "suite": "e2-g0-measurement-correction",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "code_identity": identity,
        "script_sha256": {name: digest((Path(__file__).parent / name).read_bytes()) for name in (
            "conformance_measurement_experiment.py", "adapter_conformance_experiment.py")},
        "protocol": {
            "checkpoint_replay": "Copy 22 original frozen-v0.5 state JSONs byte-for-byte, recompute projections only; do not instantiate World or execute tools.",
            "independent_expectation": "Every declared credential at each trace marker has exact formal issuance; constants describe one credential before revision and two after.",
            "measurement_cases": [case["name"] for case in controls],
            "measurement_mutants": [{key: value for key, value in mutant.items()
                                      if key in ("mutant", "named_assertion")} for mutant in mutants],
            "historical_semantics": "Existing issuance and current applicability are separate dimensions; a v1 historical credential is formally present but fails a v2 requirement query.",
        },
        "reprojection": replay,
        "measurement_controls": controls,
        "measurement_control_count": len(controls),
        "measurement_control_pass_count": sum(c["passed"] for c in controls),
        "measurement_mutations": mutants,
        "measurement_mutant_count": len(mutants),
        "measurement_mutant_detected_count": sum(m["detected"] for m in mutants),
        "common_false_is_equal_but_fails_expectation": {
            "equal": shared_false == copy.deepcopy(shared_false), "independent_check": false_check,
            "passed": not false_check["passed"],
        },
        "api_calls": 0, "gpu_used": False, "training_performed": False,
        "fresh_adapter_trajectories_run": 0,
    }
    report["passed"] = (replay["source_tree_unchanged"]
                        and replay["checkpoint_pass_count"] == 22
                        and replay["cross_template_pass_count"] == 11
                        and all(c["passed"] for c in controls)
                        and all(m["detected"] for m in mutants)
                        and not false_check["passed"])
    report["code_identity_after"] = code_identity()
    report["source_tree_unchanged"] = identity["source_tree_sha256"] == report["code_identity_after"]["source_tree_sha256"]
    write_json(args.output / "report.json", report)
    print(f"G0 replay {replay['checkpoint_pass_count']}/22; controls "
          f"{report['measurement_control_pass_count']}/{len(controls)}; "
          f"measurement mutants {report['measurement_mutant_detected_count']}/{len(mutants)}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
