"""M3F: a real approved basis replacement, separate from M3's reference edits.

Eight declared checks exercise public WorldCore tools and preserve raw snapshots.
The cross-project applicability probe runs in a copy after the main comparison,
so its explicit sharing/adoption does not alter the B-preservation baseline.
"""

import argparse
import json
import shutil
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.world_core import WorldCore
from world_core_experiment import bootstrap, exact_ref, file_hashes, mustcall, package

CHECKS = (
    "basis_v1_really_confirmed_and_applicable_to_A_r2",
    "A_and_B_really_reviewed_and_accepted",
    "basis_v2_really_confirmed_and_applicable_to_A_r3",
    "old_confirmation_and_review_retained_old_basis_not_applicable_to_new_A",
    "new_A_requires_a_new_delivery",
    "B_project_facts_remain_equal",
    "reports_common_model_and_existing_bytes_unchanged",
    "explicitly_shared_v2_still_not_applicable_to_B",
)


def write(path, value):
    atomic_write(path, json_bytes(value))
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def snapshot(world, path):
    result = {"state": world.store.load(), "files": file_hashes(world)}
    return result, write(path, result)


def project_facts(state, pid):
    """All declared B-local business records, excluding shared clock and actor log."""
    works = {k: v for k, v in state["work_items"].items() if v["project_id"] == pid}
    return {
        "project": state["projects"][pid],
        "workspace": state["workspaces"][pid],
        "artifacts": {k: v for k, v in state["artifacts"].items() if v.get("project_id") == pid},
        "works": works,
        "replacements": {k: v for k, v in state["work_replacements"].items() if k in works},
        "conditions": {
            k: v for k, v in state["condition_specs"].items() if v["work_item_id"] in works
        },
        "requests": {k: v for k, v in state["requests"].items() if v.get("project_id") == pid},
        "grants": [v for v in state["organization"]["grants"] if v.get("project_id") == pid],
        "adoptions": {k: v for k, v in state["adoptions"].items() if v["project_id"] == pid},
        "shares": [v for v in state["shares"] if v["project_id"] == pid],
        "messages": [v for v in state["messages"] if v.get("project_id") == pid],
        "project_history": [v for v in state["project_history"] if v["project_id"] == pid],
    }


def applicability(world, project, work, reference):
    return world.applicability(project, work, reference, "requirements", "delivery")


def confirmation(state, ref):
    """Read exact registered facts; never treat a latest-version pointer as approval."""
    credential = state["artifacts"][ref["object_id"]]["versions"][ref["version_id"]]["credential"]
    attestation = state["attestations"][credential["attestation_ref"]]
    return {
        "reference": credential["reference"],
        "attestation_reference": attestation["reference"],
        "issuer_matches": credential["confirmed_by"] == attestation["actor_id"] == "manager",
        "registration_matches": credential["attestation_ref"] == attestation["attestation_id"],
        "requirement_version": credential["requirement_version"],
    }


def run(output):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    code_before = code_identity()
    protocol = {
        "group": "M3F",
        "expected_checks": list(CHECKS),
        "check_count": 8,
        "counting": "Supplemental denominator. Original M3 remains 10 checks, not rewritten.",
        "formal_operations": [
            "create basis v1",
            "revise A to require v1",
            "confirm v1 for A r2",
            "submit and approve A and B",
            "write basis v2",
            "revise A to require v2",
            "confirm v2 for A r3",
        ],
        "comparison": "B-local declared business facts and all old file hashes; global logical time and command logs legitimately advance",
        "negative_probe": "Separate copied post-revision checkpoint; explicitly share and adopt basis v2 in B, then query B applicability",
        "material_provenance": "Synthetic finite JSON witness; actual confirmations/reviews are executed, not reconstructed histories",
        "model_calls": 0,
        "gpu_used": False,
    }
    write(root / "protocol.json", protocol)
    checks, evidence, result_details = [], [], {}
    error = None

    def check(name, expected, observed):
        checks.append(
            {
                "name": name,
                "expected": expected,
                "observed": observed,
                "passed": expected == observed,
            }
        )

    try:
        world = bootstrap(root / "world")
        admin = world.session("manager")
        common = mustcall(
            admin,
            "create_object",
            alias="common-model",
            filename="model.json",
            data={"factor": 2, "description": "Shared fixed computation structure"},
        )
        for pid in ("A", "B"):
            mustcall(admin, "install_project", package=package(pid))
            mustcall(
                admin,
                "share",
                object_id=common["object_id"],
                version_id="v1",
                target_project=pid,
                actor_ids=["alice", "bob", "manager"],
                follow_updates=False,
            )
            mustcall(
                world.session("alice", pid),
                "adopt",
                alias="common-model",
                object_id=common["object_id"],
                version_id="v1",
                policy="fixed",
                work_ids=["work-1"],
            )
        manager = world.session("manager", "A")
        basis = mustcall(
            manager,
            "create_object",
            alias="basis",
            filename="basis.json",
            data={"growth_rate": 0.1, "audience": "internal"},
        )
        v1 = exact_ref(basis)
        changed = mustcall(
            manager,
            "revise",
            work_id="work-1",
            updates={"required_credentials": [v1]},
            reason="A requires the exact first confirmed basis",
        )
        old_work = changed["replacements"]["A::work-1"]
        att1 = mustcall(
            manager,
            "confirm",
            work_id=old_work,
            alias="basis",
            dimension="requirements",
            purpose="delivery",
        )
        first_app = applicability(world, "A", old_work, v1)
        first_state, first_meta = snapshot(world, root / "v1-confirmed.json")
        evidence.append(first_meta)
        check(
            CHECKS[0],
            {
                "reference": v1,
                "attestation_reference": v1,
                "issuer_matches": True,
                "registration_matches": True,
                "requirement_version": 2,
                "applicability": "PASS",
            },
            {**confirmation(first_state["state"], v1), "applicability": first_app["status"]},
        )
        reports = {}
        for pid, work in (("A", old_work), ("B", "work-1")):
            deps = [exact_ref(common)] + ([v1] if pid == "A" else [])
            reports[pid] = mustcall(
                world.session("alice", pid),
                "create_object",
                alias="report",
                filename="report.json",
                data={"revenue": 100, "cost": 60},
                deliverable_role="report",
                dependencies=deps,
            )
            submitted = mustcall(
                world.session("alice", pid), "submit", work_id=work, artifacts=["report"]
            )
            mustcall(
                world.session("bob", pid),
                "approve",
                work_id=work,
                submission_id=submitted["submission_id"],
            )
        baseline, baseline_meta = snapshot(world, root / "accepted-baseline.json")
        evidence.append(baseline_meta)
        actual_accepted = {}
        for pid, wid in (("A", old_work), ("B", "B::work-1")):
            item = baseline["state"]["work_items"][wid]
            actual_accepted[pid] = {
                "status": item["status"],
                "decision": item["submissions"][-1]["review"]["decision"],
                "reviewer": item["submissions"][-1]["review"]["actor_id"],
            }
        check(
            CHECKS[1],
            {
                pid: {"status": "accepted", "decision": "accepted", "reviewer": "bob"}
                for pid in ("A", "B")
            },
            actual_accepted,
        )
        written = mustcall(
            manager,
            "write_object",
            alias="basis",
            data={"growth_rate": 0.2, "audience": "internal"},
        )
        v2 = exact_ref(written)
        changed = mustcall(
            manager,
            "revise",
            work_id=old_work,
            updates={"required_credentials": [v2]},
            reason="Only A must adopt the newly published confirmed basis",
        )
        new_work = changed["replacements"][old_work]
        att2 = mustcall(
            manager,
            "confirm",
            work_id=new_work,
            alias="basis",
            dimension="requirements",
            purpose="delivery",
        )
        second_app = applicability(world, "A", new_work, v2)
        old_app = applicability(world, "A", old_work, v1)
        old_for_new = applicability(world, "A", new_work, v1)
        after, after_meta = snapshot(world, root / "v2-confirmed-A-revised.json")
        evidence.append(after_meta)
        check(
            CHECKS[2],
            {
                "reference": v2,
                "attestation_reference": v2,
                "issuer_matches": True,
                "registration_matches": True,
                "requirement_version": 3,
                "applicability": "PASS",
                "required_credentials": [v2],
            },
            {
                **confirmation(after["state"], v2),
                "applicability": second_app["status"],
                "required_credentials": after["state"]["work_items"][new_work][
                    "required_credentials"
                ],
            },
        )
        old_before = baseline["state"]["work_items"][old_work]["submissions"][-1]
        old_after = after["state"]["work_items"][old_work]["submissions"][-1]
        check(
            CHECKS[3],
            {
                "attestation_retained": True,
                "credential_retained": True,
                "review_retained": True,
                "version_pinned_submission_retained": True,
                "old_context_applicability": "PASS",
                "new_context_old_basis_applicability": "FAIL",
            },
            {
                "attestation_retained": after["state"]["attestations"][att1["attestation_id"]]
                == baseline["state"]["attestations"][att1["attestation_id"]],
                "credential_retained": after["state"]["artifacts"][v1["object_id"]]["versions"][
                    "v1"
                ]["credential"]
                == baseline["state"]["artifacts"][v1["object_id"]]["versions"]["v1"]["credential"],
                "review_retained": old_after["review"] == old_before["review"],
                "version_pinned_submission_retained": all(
                    old_after[key] == old_before[key]
                    for key in (
                        "artifact_versions",
                        "answer",
                        "required_credentials",
                        "requirement_snapshot",
                    )
                ),
                "old_context_applicability": old_app["status"],
                "new_context_old_basis_applicability": old_for_new["status"],
            },
        )
        observed = world.session("alice", "A").observe()
        evidence.append(write(root / "A-observed-after-revision.json", observed))
        item = after["state"]["work_items"][new_work]
        check(
            CHECKS[4],
            {
                "status": "open",
                "submission_count": 0,
                "is_current": True,
                "old_review_decision": "accepted",
                "old_applicability": "superseded_requirements",
            },
            {
                "status": item["status"],
                "submission_count": len(item["submissions"]),
                "is_current": observed["work_items"][new_work]["is_current"],
                "old_review_decision": old_after["review"]["decision"],
                "old_applicability": after["state"]["work_items"][old_work]["applicability"],
            },
        )
        check(
            CHECKS[5],
            True,
            project_facts(after["state"], "B") == project_facts(baseline["state"], "B"),
        )
        expected_added = "versions/" + v2["object_id"] + "/v2"
        preserved_mirrors = ["mirrors/" + reports[p]["object_id"] for p in ("A", "B")] + [
            "mirrors/" + common["object_id"]
        ]
        check(
            CHECKS[6],
            {
                "report_and_common_mirrors_equal": True,
                "prior_immutable_bytes_equal": True,
                "new_registered_versions": [expected_added],
            },
            {
                "report_and_common_mirrors_equal": all(
                    after["files"][key] == baseline["files"][key] for key in preserved_mirrors
                ),
                "prior_immutable_bytes_equal": all(
                    after["files"][key] == value
                    for key, value in baseline["files"].items()
                    if key.startswith("versions/")
                ),
                "new_registered_versions": sorted(set(after["files"]) - set(baseline["files"])),
            },
        )
        target = root / "cross-project-probe"
        shutil.copytree(world.store.root, target, ignore=shutil.ignore_patterns("world.lock"))
        probe = WorldCore(target)
        mustcall(
            probe.session("manager", "A"),
            "share",
            object_id=v2["object_id"],
            version_id="v2",
            target_project="B",
            actor_ids=["alice", "bob", "manager"],
            follow_updates=False,
        )
        mustcall(
            probe.session("alice", "B"),
            "adopt",
            alias="foreign-A-basis",
            object_id=v2["object_id"],
            version_id="v2",
            policy="fixed",
            work_ids=["work-1"],
        )
        accessible = mustcall(
            probe.session("alice", "B"), "read_object", alias="foreign-A-basis", version_id="v2"
        )
        cross_app = applicability(probe, "B", "work-1", v2)
        _, cross_meta = snapshot(probe, root / "shared-v2-B-negative-probe.json")
        evidence.append(cross_meta)
        check(
            CHECKS[7],
            {
                "explicit_shared_read": v2,
                "applicability": "FAIL",
                "project_mismatch": True,
                "main_B_preservation_checkpoint_unchanged": True,
            },
            {
                "explicit_shared_read": {
                    "object_id": accessible["reference"]["artifact_id"],
                    "version_id": accessible["reference"]["version_id"],
                },
                "applicability": cross_app["status"],
                "project_mismatch": "project_id_mismatch" in cross_app["reasons"],
                "main_B_preservation_checkpoint_unchanged": world.store.load() == after["state"],
            },
        )
        result_details = {
            "old_work": old_work,
            "new_work": new_work,
            "basis_v1": v1,
            "basis_v2": v2,
            "attestation_v1": att1,
            "attestation_v2": att2,
            "v1_applicability": first_app,
            "v2_applicability": second_app,
            "old_context_applicability": old_app,
            "old_basis_new_context": old_for_new,
            "cross_project_applicability": cross_app,
            "common_model": common,
            "reports": reports,
            "business_scope": list(project_facts(after["state"], "B")),
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    report = {
        "experiment": "world-core-approved-basis-v0.6",
        "group": "M3F",
        "protocol": protocol,
        "code_before": code_before,
        "code_after": code_identity(),
        "script_sha256": digest(Path(__file__).read_bytes()),
        "helper_script_sha256": digest(
            Path(__file__).with_name("world_core_experiment.py").read_bytes()
        ),
        "checks": checks,
        "expected_checks": len(CHECKS),
        "executed_checks": len(checks),
        "checks_passed": sum(c["passed"] for c in checks),
        "not_executed": [name for name in CHECKS if name not in {c["name"] for c in checks}],
        "error": error,
        "raw_snapshots": evidence,
        "details": result_details,
        "passed": error is None and len(checks) == len(CHECKS) and all(c["passed"] for c in checks),
    }
    write(root / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run(args.output)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("passed", "executed_checks", "checks_passed", "not_executed", "error")
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if report["passed"] else 1)
