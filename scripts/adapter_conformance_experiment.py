"""E2: two genuine adapter trajectories plus a separately labelled scope fixture.

No business state is patched by this harness. Confirm/Grant at compilation is an
explicit bootstrap fact. Operating late replies are scheduled events; publication
replies are editor tools, so Revise+LateReply is one declared comparison boundary.
"""

import argparse
import copy
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from state_projection_experiment import AdapterTrace, SEED, TEMPLATES, file_hashes, write_json

from proworksim.audit import code_identity
from proworksim.core.projections import derive_condition_view, derive_current_work_view
from proworksim.core.references import VersionRef
from proworksim.core.rules import confirm_credential
from proworksim.core.types import Credential
from proworksim.storage import digest

MARKERS = {
    "withdraw_resubmit": ("ConfirmGrant", "Submit1", "Withdraw", "Submit2", "Approve"),
    "revision_late_reply": (
        "ConfirmGrant",
        "OldRequest",
        "ReviseLateReply",
        "NewReply",
        "Submit",
        "Approve",
    ),
}
PINNED_FIELDS = (
    "submission_id",
    "artifact_versions",
    "required_credentials",
    "requirement_snapshot",
)
LOCAL_CHECKS = (
    "all_actions_from_real_adapter",
    "pinned_submission_history_preserved",
    "no_model_calls",
    "current_work_accepted",
)


# Constants follow the declared trace, never either adapter's measured output.
EXPECTED_CREDENTIAL_COUNTS = {
    "withdraw_resubmit": dict.fromkeys(MARKERS["withdraw_resubmit"], 1),
    "revision_late_reply": {
        marker: 1 if marker in ("ConfirmGrant", "OldRequest") else 2
        for marker in MARKERS["revision_late_reply"]
    },
}


def formal_confirmation_fact(state, reference):
    """Read exact historical issuance, independently of current applicability.

    Normalize accepted reference spellings, then check the registered version,
    credential and attestation agree on the exact reference and issuance links.
    Historical issuance may exist while a newer requirement is not satisfied.
    """
    try:
        ref = VersionRef.from_mapping(reference)
        version = state["artifacts"][ref.object_id]["versions"][ref.version_id]
        credential = version["credential"]
        attestation = state["attestations"][credential["attestation_ref"]]
        return bool(
            credential.get("kind") == "credential"
            and VersionRef.from_mapping(credential["reference"]) == ref
            and VersionRef.from_mapping(attestation["reference"]) == ref
            and attestation["attestation_id"] == credential["attestation_ref"]
            and attestation["actor_id"] == credential["confirmed_by"]
            and attestation["requirement_dimension"] == credential["requirement_dimension"]
            and attestation["requirement_version"] == credential["requirement_version"]
            and set(attestation["work_nodes"]) == set(credential["work_nodes"])
            and attestation["power"] == "confirm"
            and attestation["subject"] == credential["requirement_dimension"]
            and version["logical_time"] <= attestation["at"] <= state["clock"]
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def expected_confirmation_check(trajectory, marker, projection):
    """One independently specified truth assertion per adapter checkpoint."""
    count = EXPECTED_CREDENTIAL_COUNTS[trajectory][marker]
    expected = [
        {"credential": f"C{index + 1}", "formal_confirmation": True, "coordinator_signed": True}
        for index in range(count)
    ]
    actual = [
        {key: value.get(key) for key in expected[0]}
        for value in (projection or {}).get("credentials", [])
    ]
    return {
        "name": "declared_credentials_have_exact_formal_issuance",
        "trajectory": trajectory,
        "marker": marker,
        "expected": expected,
        "observed": actual,
        "passed": actual == expected,
        "not_executed": projection is None,
    }


def semantic_projection(trace, state):
    """Frozen relational comparison, excluding all domain content and time fields.

    Work, credential, request and condition identities get aliases in creation
    order. The selected records and omitted fields are declared in protocol.json;
    raw states, exact artifact pins and tool returns remain separately archived.
    """
    work_views = derive_current_work_view(state)
    condition_views = derive_condition_view(state)
    work_alias = {
        wid: f"W{item['requirement_version']}" for wid, item in state["work_items"].items()
    }
    credential_refs = [trace.initial_reference]
    for item in state["work_items"].values():
        for ref in item["required_credentials"]:
            if ref not in credential_refs:
                credential_refs.append(ref)

    def credential_alias(ref):
        return f"C{credential_refs.index(ref) + 1}"

    condition_alias = {cid: f"K{index + 1}" for index, cid in enumerate(state["condition_specs"])}
    request_alias = {rid: f"R{index + 1}" for index, rid in enumerate(state["requests"])}
    credentials = []
    for ref in credential_refs:
        artifact = state["artifacts"][ref["artifact_id"]]
        version = artifact["versions"][ref["version_id"]]
        credential = version.get("credential", {})
        attestation = state["attestations"].get(credential.get("attestation_ref"), {})
        exact_readers = artifact.get("version_readers", {}).get(ref["version_id"], [])
        credentials.append(
            {
                "credential": credential_alias(ref),
                "formal_confirmation": formal_confirmation_fact(state, ref),
                "coordinator_signed": attestation.get("actor_id") == trace.coordinator,
                "worker_has_exact_version": trace.worker in artifact.get("readers", [])
                or trace.worker in exact_readers,
            }
        )
    work = []
    for wid, item in state["work_items"].items():
        view = work_views[wid]
        work.append(
            {
                "work": work_alias[wid],
                "requirement_version": item["requirement_version"],
                "is_current": view["is_current"],
                "status": view["status"],
                "applicability": view["applicability"],
                "dependencies_ready": view["dependencies_ready"],
                "enabled_actions": view["enabled_actions"],
                "required_credentials": [
                    credential_alias(ref) for ref in item["required_credentials"]
                ],
                "outstanding_conditions": [
                    condition_alias[cid] for cid in view["outstanding_condition_ids"]
                ],
                "submissions": [
                    {
                        "submission": f"S{index + 1}",
                        "invalidated": bool(sub["invalidated"]),
                        "applicability": sub["current_applicability"],
                        "requirement_version": sub["requirement_version"],
                        "required_credentials": [
                            credential_alias(ref) for ref in sub["required_credentials"]
                        ],
                        "pins_all_deliverables": set(sub["artifact_versions"])
                        == set(item["deliverables"]) - {"answer"}
                        and all(
                            version in state["artifacts"][aid]["versions"]
                            for aid, version in sub["artifact_versions"].items()
                        ),
                        "review_decision": (sub.get("review") or {}).get("decision"),
                        "review_actor_institutional_role": "reviewer"
                        if (sub.get("review") or {}).get("actor_id") == trace.reviewer
                        else "worker"
                        if (sub.get("review") or {}).get("actor_id") == trace.worker
                        else None,
                    }
                    for index, sub in enumerate(item["submissions"])
                ],
            }
        )
    conditions = [
        {
            "condition": condition_alias[cid],
            "work": work_alias[view["work_item_id"]],
            "request": request_alias.get(view["request_id"]),
            "status": view["status"],
            "resolved_by_matching_response": view["status"] == "resolved"
            and bool(view["resolution_ref"]),
            "coordinator_unavailable": trace.coordinator in view["unavailable_providers"],
        }
        for cid, view in condition_views.items()
    ]
    requests = [
        {
            "request": request_alias[rid],
            "work": work_alias[request["work_item_id"]],
            "response_recorded": bool(request.get("reply_message_id")),
            "request_targets_current_work": work_views[request["work_item_id"]]["is_current"],
            "provider_is_coordinator": request["requested_role"] == trace.coordinator,
        }
        for rid, request in state["requests"].items()
    ]
    return {
        "credentials": credentials,
        "work": work,
        "conditions": conditions,
        "requests": requests,
    }


def pinned_history(states):
    previous = {}
    for state in states:
        present = {}
        for item in state["work_items"].values():
            for submission in item["submissions"]:
                present[submission["submission_id"]] = {
                    key: submission[key] for key in PINNED_FIELDS
                }
        if any(present.get(key) != value for key, value in previous.items()):
            return False
        previous = copy.deepcopy(present)
    return True


def run_trace(entry):
    output, template, name = entry
    root = output / f"{name}-{template}"
    root.mkdir()
    result = {
        "template": template, "trajectory": name, "markers": {},
        "checks": [], "independent_expectations": [],
    }
    states = []
    trace = None
    try:
        trace = AdapterTrace(
            template,
            root / "world",
            information="clarification" if name == "revision_late_reply" else "mail",
        )

        def mark(marker):
            state = trace.world.store.load()
            states.append(copy.deepcopy(state))
            result["markers"][marker] = {
                "semantic_projection": semantic_projection(trace, state),
                "raw_state": write_json(root / f"{marker}-state.json", state),
                "files": file_hashes(trace.world),
                "action_count": len(trace.actions),
            }
            result["independent_expectations"].append(
                expected_confirmation_check(
                    name, marker, result["markers"][marker]["semantic_projection"]
                )
            )

        if name == "withdraw_resubmit":
            mark("ConfirmGrant")
            trace.prepare()
            first = trace.submit()
            mark("Submit1")
            trace.withdraw(first)
            mark("Withdraw")
            second = trace.submit()
            mark("Submit2")
            trace.approve(second)
            mark("Approve")
        else:
            initial_request = trace.request()
            trace.reply(initial_request)
            mark("ConfirmGrant")
            old_request = trace.request()
            mark("OldRequest")
            trace.revise()
            trace.reply(old_request)
            mark("ReviseLateReply")
            new_request = trace.request()
            trace.reply(new_request)
            mark("NewReply")
            trace.prepare()
            submitted = trace.submit()
            mark("Submit")
            trace.approve(submitted)
            mark("Approve")
        state = trace.world.store.load()
        action_ids = {record["action_id"] for record in state["interactions"]}
        values = (
            all(action["output"].get("action_id") in action_ids for action in trace.actions),
            pinned_history(states),
            not state.get("calls"),
            derive_current_work_view(state)[trace.work_id]["status"] == "accepted",
        )
        result["checks"] = [
            {"name": name, "passed": bool(value)} for name, value in zip(LOCAL_CHECKS, values)
        ]
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()
        result["checks"] = [
            {"name": name, "passed": False, "not_completed": True} for name in LOCAL_CHECKS
        ]
    if trace is not None:
        result["actions"] = write_json(root / "adapter-actions.json", trace.actions)
        result["final_state"] = write_json(root / "final-state.json", trace.world.store.load())
    result["passed"] = (
        all(c["passed"] for c in result["checks"])
        and len(result["independent_expectations"]) == len(MARKERS[name])
        and all(c["passed"] for c in result["independent_expectations"])
    )
    write_json(root / "result.json", result)
    return result


def scope_fixture(output):
    """Independent state-only shared-core experiment, explicitly not adapter E2."""
    state = {
        "clock": 0,
        "roles": [{"role_id": "signatory"}],
        "organization": {
            "positions": {},
            "grants": [
                {
                    "actor_id": "signatory",
                    "power": "confirm",
                    "subject": "policy",
                    "work_nodes": ["A"],
                }
            ],
        },
        "work_items": {node: {"work_item_id": node, "node_id": node} for node in ("A", "B")},
        "artifacts": {
            node: {
                "artifact_id": node,
                "current_version": "v1",
                "versions": {"v1": {"artifact_id": node, "version_id": "v1", "logical_time": 0}},
            }
            for node in ("A", "B")
        },
        "attestations": {},
    }
    initial = copy.deepcopy(state)

    def confirm(node):
        ref = {"artifact_id": node, "version_id": "v1"}
        return confirm_credential(
            state,
            "signatory",
            ref,
            Credential(
                ref,
                "scope-component",
                "policy",
                1,
                (node,),
                None,
                "scope_test",
                0,
                "signatory",
                f"confirm-{node}",
            ),
        )

    allowed = confirm("A")
    after_a = copy.deepcopy(state)
    denied = None
    try:
        confirm("B")
    except ValueError as error:
        denied = str(error)
    checks = [
        {
            "name": "scope_A_formally_confirmed",
            "passed": allowed["work_nodes"] == ["A"]
            and "credential" in state["artifacts"]["A"]["versions"]["v1"],
        },
        {
            "name": "scope_B_explicitly_denied",
            "passed": denied is not None and "institutional power" in denied,
        },
        {"name": "scope_B_attempt_has_no_fact_effect", "passed": state == after_a},
        {
            "name": "scope_A_fact_preserved",
            "passed": state["attestations"].get("confirm-A") == allowed
            and len(state["attestations"]) == 1,
        },
    ]
    return {
        "kind": "state_only_shared_core_fixture_not_adapter_trajectory",
        "initial": write_json(output / "scope-initial.json", initial),
        "after_A": write_json(output / "scope-after-A.json", after_a),
        "after_B": write_json(output / "scope-after-B.json", state),
        "denial": denied,
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or args.workers < 1:
        parser.error("Use a new output directory and positive worker count")
    args.output.mkdir(parents=True)
    before = code_identity()
    scripts_before = {
        name: digest((Path(__file__).parent / name).read_bytes())
        for name in ("adapter_conformance_experiment.py", "state_projection_experiment.py")
    }
    started = datetime.now(timezone.utc).isoformat()
    protocol = {
        "version": "adapter-conformance-e2-v2",
        "templates": TEMPLATES,
        "markers": MARKERS,
        "world_count": 4,
        "cross_template_comparisons": 11,
        "world_local_checks": 16,
        "separate_shared_core_scope_checks": 4,
        "legacy_relation_check_count": 31,
        "independent_expected_confirmation_checks": 22,
        "expected_credential_counts": EXPECTED_CREDENTIAL_COUNTS,
        "expected_check_count": 53,
        "normalization": {
            "aliases": "Participating work by requirement revision; credentials/requests/conditions/submissions by creation order; actor by action-specific institutional role.",
            "selected_relations": "Exact credential confirmation and grant, current work/status/readiness/actions, bound condition status, recorded response and current request target, submission invalidation/applicability/decision and presence of every pinned deliverable.",
            "excluded": "Domain content, extra nonparticipating bootstrap credentials, artifact count/format, message text, numeric logical time, staff transport details (including differing outdated_reply/delivered labels). Full raw states and exact pins remain archived.",
            "history_fields_preserved_exactly_within_each_template": PINNED_FIELDS,
            "formal_confirmation": "Normalize target, credential and attestation with VersionRef; require exact object/version and matching issuance links. Historical issuance is separate from current-work applicability.",
        },
        "timing": "Operating scheduled replies run when a tool advances the clock; publication replies use editor actions. ReviseLateReply is an explicit macro boundary, not equality at every lower-level event.",
        "bootstrap": "Compilation confirms and grants the initial credentials. The revision trajectory requests and replies once before ConfirmGrant to establish equivalent public scope.",
        "scope_fixture": "A/B static scope is an independent shared-core component fixture; not an adapter trajectory or a new business template.",
        "forbidden_harness_operations": "No hidden core calls or state patches in the four adapter trajectories; no event timestamp edits.",
    }
    write_json(args.output / "protocol.json", protocol)
    entries = [(args.output, template, name) for name in MARKERS for template in TEMPLATES]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(run_trace, entries))
    comparisons = []
    lookup = {(result["trajectory"], result["template"]): result for result in results}
    for name, markers in MARKERS.items():
        for marker in markers:
            values = [
                lookup[name, template]["markers"].get(marker, {}).get("semantic_projection")
                for template in TEMPLATES
            ]
            comparisons.append(
                {
                    "trajectory": name,
                    "marker": marker,
                    "passed": values[0] is not None and values[0] == values[1],
                    "not_executed": any(value is None for value in values),
                    "operating": values[0],
                    "publication": values[1],
                }
            )
    scope = scope_fixture(args.output)
    legacy_checks = [
        *comparisons, *(c for result in results for c in result["checks"]), *scope["checks"]
    ]
    expectations = [
        {
            "template": template,
            **expected_confirmation_check(
                name,
                marker,
                lookup[name, template]["markers"].get(marker, {}).get("semantic_projection"),
            ),
        }
        for name, markers in MARKERS.items()
        for template in TEMPLATES
        for marker in markers
    ]
    checks = [*legacy_checks, *expectations]
    after = code_identity()
    report = {
        "suite": "adapter-conformance-e2-g0-corrected",
        "protocol": protocol,
        "seed": SEED,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "code_identity_before": before,
        "code_identity_after": after,
        "source_tree_unchanged_during_run": before["source_tree_sha256"]
        == after["source_tree_sha256"],
        "script_sha256_before": scripts_before,
        "script_sha256_after": {
            name: digest((Path(__file__).parent / name).read_bytes()) for name in scripts_before
        },
        "workers": args.workers,
        "adapter_world_count": len(results),
        "adapter_world_pass_count": sum(r["passed"] for r in results),
        "cross_template_comparison_count": len(comparisons),
        "cross_template_not_executed_count": sum(c["not_executed"] for c in comparisons),
        "cross_template_pass_count": sum(c["passed"] for c in comparisons),
        "check_count": len(checks),
        "check_pass_count": sum(c["passed"] for c in checks),
        "legacy_relation_check_count": len(legacy_checks),
        "legacy_relation_check_pass_count": sum(c["passed"] for c in legacy_checks),
        "independent_expectation_count": len(expectations),
        "independent_expectation_pass_count": sum(c["passed"] for c in expectations),
        "api_calls": 0,
        "gpu_used": False,
        "training_performed": False,
        "interpretation": "Finite agreement of specified institutional relations, not domain equivalence, quality agreement, arbitrary adapter conformance or model performance. Static A/B scope is separate state-only evidence.",
        "comparisons": comparisons,
        "independent_expectations": expectations,
        "adapter_results": results,
        "scope_fixture": scope,
    }
    write_json(args.output / "report.json", report)
    print(
        f"E2: {report['cross_template_pass_count']}/11 marker comparisons; {report['check_pass_count']}/{report['check_count']} total checks",
        flush=True,
    )
    return 0 if all(c["passed"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
