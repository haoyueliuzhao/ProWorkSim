"""N2/N3: explicit publication, exact adoption and actual downstream content.

Each group uses a single-writer world with two projects. Policy alternatives are
byte-identical checkpoint copies, not additional projects in the world. Source
interface consistency and independent upstream correctness are separate results.
"""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.core.adoption import binding_key
from proworksim.audit import code_identity
from proworksim.core.world import WorldSpec
from proworksim.storage import digest
from proworksim.world_core import WorldCore
from work_capability_experiment import (
    all_file_hashes,
    immutable_bytes,
    submission,
    workbook_cell,
    write_json,
)

ACTORS = ("alice", "bob", "manager")
INITIAL_VALUE = 6
CURRENT_VALUE = 8
WRONG_APPROVED_VALUE = 16
N3_CASES = {
    "correct_current": {
        "policy": "current_published",
        "use": "new",
        "number": 8,
        "a_pass": True,
        "b_pass": True,
    },
    "old_fixed": {"policy": "fixed", "use": "old", "number": 6, "a_pass": True, "b_pass": True},
    "old_current": {
        "policy": "current_published",
        "use": "old",
        "number": 6,
        "a_pass": True,
        "b_pass": False,
    },
    "relabel_only": {
        "policy": "current_published",
        "use": "new",
        "number": 6,
        "a_pass": True,
        "b_pass": False,
    },
    "wrong_approved": {
        "policy": "current_published",
        "use": "wrong",
        "number": 16,
        "a_pass": False,
        "b_pass": True,
    },
    "split_current": {
        "policy": "current_published",
        "use": "new",
        "number": 8,
        "a_pass": True,
        "b_pass": True,
    },
}
CHECKS = {
    "N2": (
        "initial_adoptions_current_and_fixed_v1",
        "draft_creates_real_new_version",
        "draft_preserves_publications_shares_messages_and_targets",
        "draft_remains_unreadable_downstream",
        "unauthorized_publication_rejected",
        "unauthorized_publication_preserves_formal_effects",
        "release_binds_exact_version_actor_time_and_scope",
        "publication_grants_new_version_only_to_subscribed_A",
        "following_target_advances_while_fixed_target_stays",
        "publication_notifies_A_not_fixed_B",
        "publication_preserves_both_downstream_files",
        "fixed_B_historical_delivery_passes",
        "A_conditions_copy_identical_published_checkpoint",
        "adoption_update_alone_preserves_file_bytes",
        "relabelled_stale_number_is_rejected",
        "actual_content_and_exact_input_binding_pass",
        "historical_source_bytes_and_B_submission_preserved",
    ),
    "N3": (
        "checkpoint_has_two_projects_private_source_and_scalar_contract",
        "six_conditions_start_from_identical_checkpoint",
        "upstream_correctness_and_interface_consistency_match_declared_matrix",
        "actual_persisted_numbers_match_condition_values",
        "adoption_snapshots_preserve_policy_and_exact_targets",
        "formal_approval_survives_independent_content_rejection",
        "upstream_private_material_remains_unreadable_to_B",
        "publication_does_not_rewrite_B_deliverable",
        "published_versions_remain_readable_after_A_completion",
        "evaluations_leave_decisions_state_and_file_bytes_unchanged",
        "one_and_two_file_layouts_are_both_valid_and_equivalent",
    ),
}
PROTOCOL = {
    "suite": "publication-consumption-N2-N3-v0.7",
    "declared_checks": CHECKS,
    "N2": {
        "source": "World JSON rate v1=6 and v2=8; A follows published versions, B fixes v1",
        "branches": ["relabel_only", "actual_update"],
        "shared_prefix": "Install packages, publish/share/adopt v1, create both reports=6, write v2 draft, reject unauthorized publish, publish v2 for A/B, submit B fixed-v1 report",
        "comparison": "Both A branches restore the identical published checkpoint; adopt v2 alone cannot edit report bytes. Relabel source_ref but retain number6 fails; write number8 and dependencyv2 passes.",
        "grant_scope": "Only A subscribes to updates; B receives explicit v1 access and retains fixed v1 after v2 release targets A and B",
    },
    "N3": {
        "source": "A private JSON input supports actual workbook; published historical intermediate v1 has6, final draftedv2 has8. Only final8 is claimed to satisfy A's current scalar contract.",
        "cases": N3_CASES,
        "checkpoint": "Same two-project state before B adoption and before v2 publication; B already owns a v1/6 draft so absence of automatic rewriting is observable",
        "consumer_interface": "B may consume exact published Report!A3 without reading A private input; fixed source_ref plus submission adoption_snapshot and persisted source bytes define consistency",
        "upstream_wrongness": "Wrong A formula=SUM(A1,A2) persists16 and is explicitly approved by Bob. A independent expected8 rejects; B faithfully reporting16 can pass its narrower interface contract.",
        "layouts": "One combined JSON or two nonconflicting JSON files; both bind the same exact source and combine to the same delivered fields",
    },
    "independent_expected_scalars": {
        "historical_intermediate": 6,
        "current_A_delivery": 8,
        "deliberate_wrong_sum": 16,
    },
    "comparison_scope": "Exact immutable and materialized byte hashes, actual call returns, fixed submission snapshots, readable source references, publication/share/message facts; command timing and diagnostic rejection records are not formal effect equality",
    "limitations": [
        "One world with two projects per isolated group and checkpoint branch; no concurrent writers",
        "Controlled formulas/JSON and finite content contracts; no general professional-quality claim",
        "Scripts are informed mechanism drivers; public-only worker discovery is a separate N4 group",
        "No model/API/GPU/training or new crash-recovery cuts in N2/N3",
    ],
}


def exact(value):
    return {
        "object_id": value.get("object_id", value.get("artifact_id")),
        "version_id": value["version_id"],
    }


def bootstrap(root):
    return WorldCore.create(
        root,
        WorldSpec(
            world_id="publication-consumption",
            actors={actor: {} for actor in ACTORS},
            applications=["files", "spreadsheets"],
            publication_policy="explicit",
            bootstrap_grants=[
                {"actor_id": "manager", "scope": "world", "power": power}
                for power in ("install_project", "create_object", "share", "publish")
            ],
        ),
    )


def consumer_contract(source_kind):
    check = {
        "kind": "json_matches_source_" + source_kind,
        "path": ["margin"],
        "reference_path": ["source_ref"],
        "adoption_alias": "input",
    }
    check.update(
        {"source_path": ["rate"]} if source_kind == "field" else {"sheet": "Report", "cell": "A3"}
    )
    return {
        "min_files": 1,
        "max_files": 2,
        "allowed_roles": ["report"],
        "allowed_kinds": ["json"],
        "required_fields": ["margin", "source_ref"],
        "content_checks": [check],
    }


def package(pid, *, producer=False, source_kind="field"):
    owner = "alice" if pid == "A" else "bob"
    contract = consumer_contract(source_kind)
    if producer:
        contract = {
            "min_files": 1,
            "max_files": 1,
            "allowed_roles": ["report"],
            "allowed_kinds": ["xlsx"],
            "required_fields": [],
            "content_checks": [
                {
                    "kind": "xlsx_cell_equals",
                    "sheet": "Report",
                    "cell": "A3",
                    "expected": CURRENT_VALUE,
                },
                {"kind": "xlsx_no_formula_errors"},
            ],
        }
    grants = [
        {"actor_id": owner, "power": power, "subject": "artifact"}
        for power in ("create_object", "share", "publish", "adopt")
    ]
    grants.append({"actor_id": "manager", "power": "close_project"})
    if producer:
        grants.append(
            {
                "actor_id": "bob",
                "power": "approve",
                "subject": "deliverable",
                "work_nodes": ["work-1"],
            }
        )
    objects = []
    if producer:
        objects.append(
            {
                "alias": "private-input",
                "filename": "private.json",
                "owner": "alice",
                "readers": ["alice"],
                "writers": ["alice"],
                "kind": "json",
                "data": {"draft_revenue": 10, "final_revenue": 12, "cost": 4},
            }
        )
    return {
        "project_id": pid,
        "goal": "Finite publication and interface consumption fixture",
        "participants": list(ACTORS),
        "objects": objects,
        "works": [
            {
                "work_id": "work-1",
                "owner": owner,
                "goal": "Deliver declared exact-version interface content",
                "approval_policy": "review" if producer else "delivery_only",
                "purpose": "delivery",
                "requirement_dimension": "requirements",
                "deliverable_contract": contract,
            }
        ],
        "grants": grants,
        "provenance": {
            "kind": "synthetic",
            "source_evidence_refs": [],
            "note": "Mechanism fixture with literal scalar expectations; not a real financial trace",
        },
        "close_policy": {"pending_obligations": "retain"},
    }


def formal_publication_facts(state):
    return {
        key: copy.deepcopy(state.get(key))
        for key in (
            "artifacts",
            "releases",
            "shares",
            "messages",
            "adoptions",
            "adoption_view",
            "events",
            "event_history",
        )
    }


def producer_review(world, sid):
    return copy.deepcopy(submission(world, "A", "work-1", sid)["review"])


class Evidence:
    def __init__(self, group, output):
        self.group, self.output = group, output
        self.world, self.context = None, "setup"
        self.checks, self.calls, self.snapshots, self.evaluations = [], [], [], []

    def check(self, name, observed, expected):
        if name not in CHECKS[self.group] or any(c["name"] == name for c in self.checks):
            raise AssertionError("Undeclared or duplicate check: " + name)
        self.checks.append(
            {
                "name": name,
                "observed": observed,
                "expected": expected,
                "passed": observed == expected,
                "not_executed": False,
            }
        )

    def call(self, session, action, must_succeed=True, **arguments):
        result = session.call(action, **arguments)
        self.calls.append(
            {
                "context": self.context,
                "actor": session.actor_id,
                "project": session.project_id,
                "action": action,
                "arguments": copy.deepcopy(arguments),
                "return": copy.deepcopy(result),
            }
        )
        if must_succeed and not result.get("ok"):
            raise AssertionError(f"{self.context}/{session.actor_id}/{action}: {result}")
        return result["result"] if must_succeed else result

    def snapshot(self, name):
        record = {
            "name": name,
            "world_root": str(self.world.store.root),
            "state": write_json(self.output / f"{name}-state.json", self.world.store.load()),
            "files": all_file_hashes(self.world),
        }
        self.snapshots.append(record)
        return record

    def evaluate(self, project, sid):
        result = self.world.evaluate_submission(project, "work-1", sid)
        self.evaluations.append({"context": self.context, "project": project, "result": result})
        return result

    def restore(self, snapshot, name):
        self.world = WorldCore.restore(snapshot, self.output / name, branch=False)
        self.context = name
        return self.world


def adopt(ev, session, reference, policy):
    return ev.call(
        session, "adopt", alias="input", **exact(reference), policy=policy, work_ids=["work-1"]
    )


def create_json_report(ev, session, ref, margin=INITIAL_VALUE, alias="report", data=None):
    return ev.call(
        session,
        "create_object",
        alias=alias,
        filename=alias + ".json",
        kind="json",
        data={"margin": margin, "source_ref": exact(ref)} if data is None else data,
        dependencies=[exact(ref)],
        deliverable_role="report",
    )


def release(ev, session, ref, projects):
    return ev.call(session, "publish", **exact(ref), target_projects=projects)


def share(ev, session, ref, project, actor, follow):
    return ev.call(
        session,
        "share",
        **exact(ref),
        target_project=project,
        actor_ids=[actor],
        follow_updates=follow,
    )


def group_n2(ev):
    world = ev.world = bootstrap(ev.output / "world")
    admin = world.session("manager")
    for pid in ("A", "B"):
        ev.call(admin, "install_project", package=package(pid))
    material = ev.call(
        admin,
        "create_object",
        alias="rates",
        filename="rates.json",
        kind="json",
        data={"rate": INITIAL_VALUE},
    )
    for pid, actor, policy in (("A", "alice", "current_published"), ("B", "bob", "fixed")):
        share(ev, admin, material, pid, actor, pid == "A")
    release(ev, admin, material, ["A", "B"])
    reports = {}
    for pid, actor, policy in (("A", "alice", "current_published"), ("B", "bob", "fixed")):
        session = world.session(actor, pid)
        adopt(ev, session, material, policy)
        reports[pid] = create_json_report(ev, session, material)
    initial = world.store.load()
    initial_source = immutable_bytes(world, material)
    ev.check(
        "initial_adoptions_current_and_fixed_v1",
        {
            pid: [
                initial["adoption_view"][binding_key(pid + "::work-1", "input")]["target_version"],
                initial["adoption_view"][binding_key(pid + "::work-1", "input")]["status"],
            ]
            for pid in ("A", "B")
        },
        {pid: [material["version_id"], "current"] for pid in ("A", "B")},
    )
    before_draft = world.store.load()
    new = ev.call(admin, "write_object", alias="rates", data={"rate": CURRENT_VALUE})
    drafted = world.store.load()
    ev.check(
        "draft_creates_real_new_version",
        [new["version_id"] != material["version_id"], json.loads(immutable_bytes(world, new))],
        [True, {"rate": CURRENT_VALUE}],
    )
    ev.check(
        "draft_preserves_publications_shares_messages_and_targets",
        {key: drafted.get(key) for key in ("releases", "shares", "messages", "adoption_view")},
        {key: before_draft.get(key) for key in ("releases", "shares", "messages", "adoption_view")},
    )
    ev.check(
        "draft_remains_unreadable_downstream",
        [
            ev.call(world.session(actor, pid), "read_object", must_succeed=False, **exact(new))[
                "ok"
            ]
            for pid, actor in (("A", "alice"), ("B", "bob"))
        ],
        [False, False],
    )
    before_reject, before_files = world.store.load(), all_file_hashes(world)
    unauthorized = ev.call(
        world.session("alice", "A"),
        "publish",
        must_succeed=False,
        **exact(new),
        target_projects=["A", "B"],
    )
    ev.check("unauthorized_publication_rejected", unauthorized["ok"], False)
    ev.check(
        "unauthorized_publication_preserves_formal_effects",
        [
            formal_publication_facts(world.store.load()) == formal_publication_facts(before_reject),
            all_file_hashes(world) == before_files,
        ],
        [True, True],
    )
    before_publish = world.store.load()
    before_report_bytes = {pid: immutable_bytes(world, ref) for pid, ref in reports.items()}
    publication = release(ev, admin, new, ["A", "B"])["release"]
    published = world.store.load()
    ev.check(
        "release_binds_exact_version_actor_time_and_scope",
        {
            key: publication.get(key)
            for key in (
                "object_id",
                "version_id",
                "actor_id",
                "at",
                "policy",
                "source_project",
                "scope",
            )
        },
        {
            **exact(new),
            "actor_id": "manager",
            "at": before_publish["clock"],
            "policy": "explicit",
            "source_project": None,
            "scope": {"target_projects": ["A", "B"], "work_ids": []},
        },
    )
    ev.check(
        "publication_grants_new_version_only_to_subscribed_A",
        [
            ev.call(world.session(actor, pid), "read_object", must_succeed=False, **exact(new))[
                "ok"
            ]
            for pid, actor in (("A", "alice"), ("B", "bob"))
        ],
        [True, False],
    )
    ev.check(
        "following_target_advances_while_fixed_target_stays",
        {
            pid: [
                published["adoption_view"][binding_key(pid + "::work-1", "input")]["target_version"],
                published["adoption_view"][binding_key(pid + "::work-1", "input")]["status"],
            ]
            for pid in ("A", "B")
        },
        {"A": [new["version_id"], "update_required"], "B": [material["version_id"], "current"]},
    )
    notices = published["messages"][len(before_publish["messages"]) :]
    ev.check(
        "publication_notifies_A_not_fixed_B", sorted({msg["project_id"] for msg in notices}), ["A"]
    )
    ev.check(
        "publication_preserves_both_downstream_files",
        {
            pid: immutable_bytes(world, ref) == before_report_bytes[pid]
            and published["artifacts"][ref["object_id"]]["current_version"] == ref["version_id"]
            for pid, ref in reports.items()
        },
        {"A": True, "B": True},
    )
    bsub = ev.call(world.session("bob", "B"), "submit", work_id="work-1", artifacts=["report"])
    b_eval = ev.evaluate("B", bsub["submission_id"])
    ev.check("fixed_B_historical_delivery_passes", b_eval["passed"], True)
    fixed_b = copy.deepcopy(submission(world, "B", "work-1", bsub["submission_id"]))
    ev.snapshot("published-prefix")
    checkpoint = world.snapshot(ev.output / "checkpoint")
    checkpoint_state = digest((checkpoint / "control/state.json").read_bytes())
    branch_results = {}
    starts = {}
    for name in ("relabel_only", "actual_update"):
        branch = ev.restore(checkpoint, name)
        starts[name] = digest((branch.store.control / "state.json").read_bytes())
        a = branch.session("alice", "A")
        files_before = all_file_hashes(branch)
        ev.call(a, "adopt_version", work_id="work-1", alias="input", version_id=new["version_id"])
        adopt_preserves_files = files_before == all_file_hashes(branch)
        number = INITIAL_VALUE if name == "relabel_only" else CURRENT_VALUE
        report = ev.call(
            a,
            "write_object",
            alias="report",
            data={"margin": number, "source_ref": exact(new)},
            dependencies=[exact(new)],
        )
        asub = ev.call(a, "submit", work_id="work-1", artifacts=["report"])
        evaluation = ev.evaluate("A", asub["submission_id"])
        state = branch.store.load()
        branch_results[name] = {
            "passed": evaluation["passed"],
            "adopt_preserves_files": adopt_preserves_files,
            "data": json.loads(immutable_bytes(branch, report)),
            "dependencies": state["artifacts"][report["object_id"]]["versions"][
                report["version_id"]
            ]["derived_from"],
            "old_source_unchanged": immutable_bytes(branch, material) == initial_source,
            "B_submission_unchanged": submission(branch, "B", "work-1", bsub["submission_id"])
            == fixed_b,
        }
        ev.snapshot(name + "-final")
    ev.check(
        "A_conditions_copy_identical_published_checkpoint",
        starts,
        {name: checkpoint_state for name in starts},
    )
    ev.check(
        "adoption_update_alone_preserves_file_bytes",
        {name: result["adopt_preserves_files"] for name, result in branch_results.items()},
        {name: True for name in starts},
    )
    ev.check(
        "relabelled_stale_number_is_rejected",
        [
            branch_results["relabel_only"]["passed"],
            branch_results["relabel_only"]["data"]["margin"],
        ],
        [False, INITIAL_VALUE],
    )
    ev.check(
        "actual_content_and_exact_input_binding_pass",
        {key: branch_results["actual_update"][key] for key in ("passed", "data", "dependencies")},
        {
            "passed": True,
            "data": {"margin": CURRENT_VALUE, "source_ref": exact(new)},
            "dependencies": [{"artifact_id": new["object_id"], "version_id": new["version_id"]}],
        },
    )
    ev.check(
        "historical_source_bytes_and_B_submission_preserved",
        {
            name: [result["old_source_unchanged"], result["B_submission_unchanged"]]
            for name, result in branch_results.items()
        },
        {name: [True, True] for name in starts},
    )


def group_n3(ev):
    world = ev.world = bootstrap(ev.output / "world")
    admin = world.session("manager")
    ev.call(admin, "install_project", package=package("A", producer=True))
    ev.call(admin, "install_project", package=package("B", source_kind="cell"))
    a, b = world.session("alice", "A"), world.session("bob", "B")
    private_read = ev.call(a, "read_object", alias="private-input")
    private = exact(private_read["reference"])
    old = ev.call(
        a,
        "create_object",
        alias="result",
        filename="result.xlsx",
        kind="xlsx",
        data={"Report!A1": 10, "Report!A2": 4, "Report!A3": "=A1-A2"},
        dependencies=[private],
        deliverable_role="report",
    )
    share(ev, a, old, "B", "bob", True)
    release(ev, a, old, ["B"])
    create_json_report(ev, b, old)
    new = ev.call(a, "sheet_update", alias="result", cells={"Report!A1": 12})
    state = world.store.load()
    scalar = state["work_items"]["A::work-1"]["deliverable_contract"]["content_checks"][0][
        "expected"
    ]
    ev.check(
        "checkpoint_has_two_projects_private_source_and_scalar_contract",
        [
            sorted(state["projects"]),
            state["artifacts"][private["object_id"]]["readers"],
            scalar,
            workbook_cell(immutable_bytes(world, old))["cached"],
            workbook_cell(immutable_bytes(world, new))["cached"],
        ],
        [["A", "B"], ["alice"], CURRENT_VALUE, INITIAL_VALUE, CURRENT_VALUE],
    )
    ev.snapshot("checkpoint-prefix")
    checkpoint = world.snapshot(ev.output / "checkpoint")
    checkpoint_hash = digest((checkpoint / "control/state.json").read_bytes())
    starts, results = {}, {}
    for name, condition in N3_CASES.items():
        branch = ev.restore(checkpoint, name)
        starts[name] = digest((branch.store.control / "state.json").read_bytes())
        a, b = branch.session("alice", "A"), branch.session("bob", "B")
        adopt(ev, b, old, condition["policy"])
        current = new
        if name == "wrong_approved":
            current = ev.call(a, "sheet_update", alias="result", cells={"Report!A3": "=SUM(A1,A2)"})
        b_artifact = branch.store.load()["workspaces"]["B"]["report"]
        b_before = copy.deepcopy(branch.store.load()["artifacts"][b_artifact])
        b_before_bytes = branch.store.current_path(b_before).read_bytes()
        release(ev, a, current, ["B"])
        b_after_publish = branch.store.load()["artifacts"][b_artifact]
        no_auto_edit = (
            b_after_publish == b_before
            and branch.store.current_path(b_after_publish).read_bytes() == b_before_bytes
        )
        used = old if condition["use"] == "old" else current
        if condition["use"] != "old":
            ev.call(b, "adopt_version", work_id="work-1", alias="input", version_id=used["version_id"])
        asub = ev.call(a, "submit", work_id="work-1", artifacts=["result"])
        ev.call(
            branch.session("bob", "A"),
            "approve",
            work_id="work-1",
            submission_id=asub["submission_id"],
        )
        approved = producer_review(branch, asub["submission_id"])
        published_bytes = immutable_bytes(branch, used)
        ev.call(
            branch.session("manager", "A"),
            "close_project",
            mode="completed",
            reason="Institutional approval recorded; independent quality remains separate",
        )
        source_read = ev.call(b, "sheet_read", **exact(used))
        private_attempt = ev.call(b, "read_object", must_succeed=False, **private)
        private_same_project = ev.call(
            branch.session("bob", "A"), "read_object", must_succeed=False, **private
        )
        aliases = ["report"]
        if name == "split_current":
            ev.call(
                b,
                "write_object",
                alias="report",
                data={"margin": condition["number"]},
                dependencies=[exact(used)],
            )
            create_json_report(ev, b, used, alias="provenance", data={"source_ref": exact(used)})
            aliases.append("provenance")
        elif condition["use"] != "old":
            ev.call(
                b,
                "write_object",
                alias="report",
                data={"margin": condition["number"], "source_ref": exact(used)},
                dependencies=[exact(used)],
            )
        bsub = ev.call(b, "submit", work_id="work-1", artifacts=aliases)
        before_eval, before_files = branch.store.load(), all_file_hashes(branch)
        ae, be = ev.evaluate("A", asub["submission_id"]), ev.evaluate("B", bsub["submission_id"])
        final = branch.store.load()
        bfixed = submission(branch, "B", "work-1", bsub["submission_id"])
        combined = {}
        for aid, vid in bfixed["artifact_versions"].items():
            combined.update(
                json.loads(immutable_bytes(branch, {"object_id": aid, "version_id": vid}))
            )
        adopted = bfixed["adoption_snapshot"][binding_key("B::work-1", "input")]
        results[name] = {
            "A_pass": ae["passed"],
            "B_pass": be["passed"],
            "persisted_B_number": combined["margin"],
            "persisted_A_number": workbook_cell(immutable_bytes(branch, current))["cached"],
            "adoption": {key: adopted[key] for key in ("policy", "version_id", "target_version")},
            "expected_used": used["version_id"],
            "expected_target": old["version_id"]
            if condition["policy"] == "fixed"
            else current["version_id"],
            "formal_review_before": approved,
            "formal_review_after": producer_review(branch, asub["submission_id"]),
            "private_read_ok": [private_attempt["ok"], private_same_project["ok"]],
            "evaluation_avoids_private_source": all(
                ref["object_id"] != private["object_id"] for ref in be["read_set"]
            ),
            "no_auto_edit": no_auto_edit,
            "A_completed": final["projects"]["A"]["status"] == "completed",
            "source_read_reference": exact(source_read["reference"]),
            "expected_source_reference": exact(used),
            "source_bytes_survive": immutable_bytes(branch, used) == published_bytes,
            "evaluation_readonly": final == before_eval and all_file_hashes(branch) == before_files,
            "combined": combined,
            "file_count": len(bfixed["artifact_versions"]),
        }
        ev.snapshot(name + "-final")
    ev.check(
        "six_conditions_start_from_identical_checkpoint",
        starts,
        {name: checkpoint_hash for name in N3_CASES},
    )
    ev.check(
        "upstream_correctness_and_interface_consistency_match_declared_matrix",
        {name: [value["A_pass"], value["B_pass"]] for name, value in results.items()},
        {name: [case["a_pass"], case["b_pass"]] for name, case in N3_CASES.items()},
    )
    ev.check(
        "actual_persisted_numbers_match_condition_values",
        {
            name: [value["persisted_A_number"], value["persisted_B_number"]]
            for name, value in results.items()
        },
        {
            name: [
                WRONG_APPROVED_VALUE if name == "wrong_approved" else CURRENT_VALUE,
                case["number"],
            ]
            for name, case in N3_CASES.items()
        },
    )
    ev.check(
        "adoption_snapshots_preserve_policy_and_exact_targets",
        {name: value["adoption"] for name, value in results.items()},
        {
            name: {
                "policy": N3_CASES[name]["policy"],
                "version_id": value["expected_used"],
                "target_version": value["expected_target"],
            }
            for name, value in results.items()
        },
    )
    wrong = results["wrong_approved"]
    ev.check(
        "formal_approval_survives_independent_content_rejection",
        [
            wrong["A_pass"],
            wrong["B_pass"],
            wrong["formal_review_before"] == wrong["formal_review_after"],
            wrong["formal_review_after"]["decision"],
        ],
        [False, True, True, "accepted"],
    )
    ev.check(
        "upstream_private_material_remains_unreadable_to_B",
        {
            name: value["private_read_ok"] + [value["evaluation_avoids_private_source"]]
            for name, value in results.items()
        },
        {name: [False, False, True] for name in N3_CASES},
    )
    ev.check(
        "publication_does_not_rewrite_B_deliverable",
        {name: value["no_auto_edit"] for name, value in results.items()},
        {name: True for name in N3_CASES},
    )
    ev.check(
        "published_versions_remain_readable_after_A_completion",
        {
            name: [
                value["A_completed"],
                value["source_read_reference"] == value["expected_source_reference"],
                value["source_bytes_survive"],
            ]
            for name, value in results.items()
        },
        {name: [True, True, True] for name in N3_CASES},
    )
    ev.check(
        "evaluations_leave_decisions_state_and_file_bytes_unchanged",
        {name: value["evaluation_readonly"] for name, value in results.items()},
        {name: True for name in N3_CASES},
    )
    ev.check(
        "one_and_two_file_layouts_are_both_valid_and_equivalent",
        [
            results["correct_current"]["B_pass"],
            results["split_current"]["B_pass"],
            results["correct_current"]["file_count"],
            results["split_current"]["file_count"],
            results["correct_current"]["combined"] == results["split_current"]["combined"],
        ],
        [True, True, 1, 2, True],
    )
    write_json(ev.output / "condition-results.json", results)


RUNNERS = {"N2": group_n2, "N3": group_n3}


def run_group(entry):
    group, output = entry
    output.mkdir(parents=True)
    ev, error = Evidence(group, output), None
    try:
        RUNNERS[group](ev)
    except Exception as caught:
        error = {"error": f"{type(caught).__name__}: {caught}", "traceback": traceback.format_exc()}
    names = {check["name"] for check in ev.checks}
    for name in CHECKS[group]:
        if name not in names:
            ev.checks.append(
                {
                    "name": name,
                    "observed": None,
                    "expected": "Declared group protocol",
                    "passed": False,
                    "not_executed": True,
                }
            )
    if ev.world:
        ev.snapshot("end-of-run")
    result = {
        "group": group,
        "checks": ev.checks,
        "error": error,
        "snapshots": ev.snapshots,
        "calls": write_json(output / "calls.json", ev.calls),
        "evaluations": write_json(output / "evaluations.json", ev.evaluations),
        "check_count": len(ev.checks),
        "check_pass_count": sum(c["passed"] for c in ev.checks),
        "not_executed_count": sum(c["not_executed"] for c in ev.checks),
        "passed": error is None and all(c["passed"] for c in ev.checks),
    }
    write_json(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--groups", nargs="+", choices=list(CHECKS), default=list(CHECKS))
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.output.exists() or args.workers < 1 or len(args.groups) != len(set(args.groups)):
        parser.error("Use a new output directory, distinct groups and positive workers")
    args.output.mkdir(parents=True)
    before, script_before = code_identity(), digest(Path(__file__).read_bytes())
    started = datetime.now(timezone.utc).isoformat()
    write_json(args.output / "protocol.json", PROTOCOL)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run_group, [(group, args.output / group) for group in args.groups]))
    after = code_identity()
    report = {
        "suite": PROTOCOL["suite"],
        "protocol": PROTOCOL,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "code_identity_before": before,
        "code_identity_after": after,
        "script_sha256_before": script_before,
        "script_sha256_after": digest(Path(__file__).read_bytes()),
        "source_tree_unchanged": before["source_tree_sha256"] == after["source_tree_sha256"],
        "workers": args.workers,
        "results": results,
        "check_count": sum(result["check_count"] for result in results),
        "check_pass_count": sum(result["check_pass_count"] for result in results),
        "not_executed_count": sum(result["not_executed_count"] for result in results),
        "api_calls": 0,
        "gpu_used": False,
        "training_performed": False,
    }
    write_json(args.output / "report.json", report)
    print(
        f"N2/N3 {report['check_pass_count']}/{report['check_count']} checks; "
        f"{report['not_executed_count']} not executed"
    )
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
