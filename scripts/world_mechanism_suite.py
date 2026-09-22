"""Deterministic world-semantic witnesses; no model sampling or parameter training.

Usage: .venv/bin/python scripts/world_mechanism_suite.py --output runs/new-suite
Every case retains its own world, checks, checkpoints and errors. An expected
block or rejected specification can pass a mechanism check without task success.
"""

import argparse
import copy
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.audience import audience_content_defects
from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.contracts import CONTRACT_VERSION, EVALUATOR_VERSION
from proworksim.designer import design
from proworksim.formula import ENGINE_VERSION
from proworksim.kernel import World
from proworksim.lifecycle import current_work_items
from proworksim.schema import SCHEMA_VERSION
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.validation import evaluate

SEED = 701


class Paused(Exception):
    pass


class BoundarySession:
    def __init__(self, session, *, before_submit=False, active_work=None):
        self.session = session
        self.before_submit = before_submit
        self.active_work = active_work

    def observe(self):
        observation = self.session.observe()
        if self.active_work and any(
            work["work_item_id"] == self.active_work for work in observation["work_items"]
        ):
            raise Paused
        return observation

    def call(self, action, **arguments):
        if action == "submit" and self.before_submit:
            raise Paused
        return self.session.call(action, **arguments)


def until(world, *, before_submit=False, active_work=None):
    try:
        run_baseline(
            BoundarySession(world.session(), before_submit=before_submit, active_work=active_work)
        )
    except Paused:
        return
    raise AssertionError("Baseline finished without reaching the requested public boundary")


def call(world, action, actor="analyst", **arguments):
    response = world.session(actor).call(action, **arguments)
    if not response["ok"]:
        raise AssertionError(f"Unexpected {action} failure: {response['error']}")
    return response["result"]


class Case:
    def __init__(self, path, expected):
        self.path = path
        path.mkdir()
        self.world = None
        self.result = {
            "case": path.name,
            "seed": SEED,
            "provider": "rule_based",
            "expected": expected,
            "checks": [],
            "checkpoints": {},
            "world_path": None,
            "business_complete": False,
            "artifact_valid": None,
        }

    def create(self, **options):
        self.world = World(compile_world(design(SEED, **options), self.path / "world"))
        self.result["world_path"] = str(self.world.store.root)
        self.checkpoint("initial")
        return self.world

    def check(self, name, condition, observed=None):
        row = {"name": name, "passed": bool(condition)}
        if observed is not None:
            row["observed"] = observed
        self.result["checks"].append(row)
        if not condition:
            raise AssertionError(name)

    def checkpoint(self, name):
        state = self.world.store.load()
        artifacts = {}
        for aid, artifact in state["artifacts"].items():
            artifacts[aid] = {
                "current_version": artifact["current_version"],
                "sha256": digest(self.world.store.content(artifact)),
                "versions": {
                    version: digest(self.world.store.content(artifact, version))
                    for version in artifact["versions"]
                },
                "freshness": artifact.get("freshness"),
                "data_freshness": artifact.get("data_freshness"),
                "basis_applicability": artifact.get("basis_applicability"),
            }
        checkpoint = {
            "clock": state["clock"],
            "state_sha256": digest(json_bytes(state)),
            "artifacts": artifacts,
            "work_items": {
                wid: {
                    "status": item["status"],
                    "requirement_version": item["requirement_version"],
                    "required_basis": item.get("required_basis"),
                    "submissions": copy.deepcopy(item["submissions"]),
                    "blocker_ids": list(item.get("blocker_ids", [])),
                }
                for wid, item in state["work_items"].items()
            },
            "blockers": copy.deepcopy(state.get("blockers", {})),
            "requests": copy.deepcopy(state.get("requests", {})),
        }
        self.result["checkpoints"][name] = checkpoint
        atomic_write(self.path / f"checkpoint-{name}.json", json_bytes(checkpoint))
        return checkpoint

    def complete(self):
        result = run_baseline(self.world.session())
        self.result.setdefault("baseline_runs", []).append(result)
        self.check("rule_witness_completes", result["complete"], result)
        self.grade()

    def grade(self):
        records = evaluate(self.world.store.root)
        state = self.world.store.load()
        latest = {(record["work_item_id"], record["submission_id"]): record for record in records}
        active = current_work_items(state)
        selected = [
            latest.get((work["work_item_id"], work["submissions"][-1]["submission_id"]))
            if work["submissions"]
            else None
            for work in active
        ]
        valid = bool(selected) and all(record and record["passed"] for record in selected)
        self.result["artifact_valid"] = valid
        self.result["evaluation_summary"] = {
            "all_records": len(records),
            "historical_failed_records": sum(not record["passed"] for record in records),
            "current_records": len(selected),
            "current_failed_checks": [
                {
                    "work_item_id": record["work_item_id"],
                    "checks": [check["name"] for check in record["checks"] if not check["passed"]],
                }
                for record in selected
                if record and not record["passed"]
            ],
        }
        atomic_write(self.path / "evaluations.json", json_bytes(records))
        self.check("current_submissions_pass_independent_evaluation", valid)


def fingerprint(checkpoint, artifact_id):
    artifact = checkpoint["artifacts"][artifact_id]
    return artifact["current_version"], artifact["sha256"]


def block(world, work_id, kind="scope", role="manager"):
    item = world.store.load()["work_items"][work_id]
    return call(
        world,
        "block_work",
        work_item_id=work_id,
        kind=kind,
        requested_role=role,
        required_scope_version=item["basis_requirement_version"] if kind == "scope" else None,
        reason=f"机制验收：等待 {role} 对 {kind} 的适用确认",
    )["blocker_id"]


def ask(world, work_id, blocker_id, topic="scope", role="manager"):
    return call(
        world,
        "mail_send",
        to=role,
        topic=topic,
        work_item_id=work_id,
        blocker_id=blocker_id,
        body="请提供适用于这项工作和需求版本的确认凭据。",
    )["message_id"]


def deadlock(case):
    spec = design(SEED, delivery="file")
    workflow = copy.deepcopy(spec.workflow)
    workflow["nodes"][0]["release"] = "self-release"
    workflow["event_rules"] = [
        {
            "rule_id": "self-gate",
            "after_accepted": ["work-1"],
            "effects": [],
            "release": "self-release",
            "delay": 2,
        }
    ]
    spec = replace(spec, workflow=workflow)
    atomic_write(case.path / "rejected-spec.json", json_bytes(spec.to_dict()))
    try:
        compile_world(spec, case.path / "rejected-world")
    except ValueError as exc:
        case.result["admission_error"] = str(exc)
        case.check("release_work_deadlock_rejected", True, str(exc))
    else:
        case.check("release_work_deadlock_rejected", False)
    case.check(
        "no_executable_world_admitted",
        not (case.path / "rejected-world/control/state.json").exists(),
    )
    case.result["world_outcome"] = "specification_rejected"


def scoped_replies(case):
    world = case.create(topology="fork")
    until(world, before_submit=True)
    call(world, "submit", work_item_id="model-1")
    call(world, "wait", ticks=2)
    memo = block(world, "memo-1")
    note = block(world, "note-1", "audience", "client")
    before = case.checkpoint("both_blocked")
    ask(world, "memo-1", memo)
    call(world, "wait", ticks=2)
    state = world.store.load()
    case.check("scope_releases_only_memo", state["work_items"]["memo-1"]["status"] == "open")
    case.check("unrelated_note_stays_blocked", state["work_items"]["note-1"]["status"] == "blocked")
    case.check(
        "unrelated_blocker_history_unchanged", state["blockers"][note] == before["blockers"][note]
    )
    case.checkpoint("scope_replied")
    ask(world, "note-1", note, "audience", "client")
    call(world, "wait", ticks=2)
    case.check(
        "client_reply_releases_note", world.store.load()["work_items"]["note-1"]["status"] == "open"
    )
    case.complete()


def basis_only(case):
    world = case.create(scenario="basis_only")
    until(world, active_work="work-2")
    boundary = case.checkpoint("basis_changed")
    initial = case.result["checkpoints"]["initial"]
    case.check(
        "financials_unchanged_at_basis_change",
        fingerprint(initial, "financials") == fingerprint(boundary, "financials"),
    )
    case.check(
        "approved_basis_version_changes",
        fingerprint(initial, "basis") != fingerprint(boundary, "basis"),
    )
    case.check(
        "adopted_model_and_memo_marked_stale",
        all(boundary["artifacts"][aid]["freshness"] == "stale" for aid in ("model", "memo")),
    )
    case.complete()
    final = case.checkpoint("after_second_stage")
    case.check(
        "financials_bytes_and_version_unchanged_across_two_stages",
        fingerprint(initial, "financials") == fingerprint(final, "financials"),
    )
    case.check(
        "both_stages_accepted",
        all(work["status"] == "accepted" for work in world.store.load()["work_items"].values()),
    )


def selective(case):
    world = case.create(topology="selective")
    until(world, active_work="note-2")
    boundary = case.checkpoint("audience_changed")
    case.complete()
    final = case.checkpoint("after_note_revision")
    for aid in ("model", "memo", "basis"):
        case.check(
            f"{aid}_unchanged_by_audience_revision",
            fingerprint(boundary, aid) == fingerprint(final, aid),
        )
    case.check(
        "only_one_additional_note_version",
        len(final["artifacts"]["note"]["versions"])
        == len(boundary["artifacts"]["note"]["versions"]) + 1,
    )
    state = world.store.load()
    note = read_json(
        world.store.version_path(
            state["artifacts"]["note"], state["artifacts"]["note"]["current_version"]
        )
    )
    defects = audience_content_defects(note.get("audience_content"), "external_client")
    case.check(
        "external_audience_content_satisfies_public_fields",
        note["audience"] == "external_client" and not defects,
        defects,
    )
    case.result["audience_validation_scope"] = (
        "Required fields, types and nonempty content only; not professional prose quality."
    )


def waiting_reply(case):
    world = case.create(scenario="waiting_reply")
    old_blocker = block(world, "work-1")
    old_request = ask(world, "work-1", old_blocker)
    state = world.store.load()
    replacement = state["work_replacements"]["work-1"]
    old_ref = state["work_items"]["work-1"]["required_basis"]
    new_ref = state["work_items"][replacement]["required_basis"]
    new_blocker = block(world, replacement)
    call(world, "wait", ticks=2)
    state = world.store.load()
    case.check(
        "old_reply_archived_as_outdated",
        state["requests"][old_request]["status"] == "outdated_reply",
    )
    case.check(
        "old_reply_does_not_resolve_new_blocker",
        state["blockers"][new_blocker]["status"] == "open"
        and state["work_items"][replacement]["status"] == "blocked",
    )
    old_access = world.session().call(
        "read_file", artifact_id="basis", version_id=old_ref["version_id"]
    )
    new_access = world.session().call(
        "read_file", artifact_id="basis", version_id=new_ref["version_id"]
    )
    private_access = world.session().call("read_file", artifact_id="scope")
    case.check("old_confirmation_remains_readable", old_access["ok"])
    case.check("old_reply_does_not_grant_new_basis_access", not new_access["ok"], new_access)
    case.check("manager_private_scope_stays_private", not private_access["ok"])
    case.checkpoint("outdated_reply")
    ask(world, replacement, new_blocker)
    call(world, "wait", ticks=2)
    case.check(
        "new_scoped_reply_resolves_new_blocker",
        world.store.load()["blockers"][new_blocker]["status"] == "resolved",
    )
    case.complete()


def during_review(case):
    world = case.create(scenario="during_review")
    until(world, before_submit=True)
    submission = call(world, "submit", work_item_id="work-1")
    call(world, "wait", ticks=2)
    state = world.store.load()
    replacement = state["work_replacements"]["work-1"]
    archived = state["work_items"]["work-1"]["submissions"][0]
    case.check(
        "submitted_versions_preserved_in_archive",
        archived["artifact_versions"] == submission["artifact_versions"],
    )
    case.check(
        "old_submission_not_approved_after_requirement_change",
        archived["invalidated"]
        and archived["review"] is None
        and archived["current_applicability"] == "superseded_requirements",
    )
    for work_id in ("work-1", replacement):
        response = world.session("reviewer").call(
            "approve", work_item_id=work_id, submission_id=submission["submission_id"]
        )
        case.check(f"old_submission_cannot_approve_{work_id}", not response["ok"], response)
    case.checkpoint("old_submission_archived")
    case.complete()


def unavailable(case):
    world = case.create(scenario="unavailable")
    result = run_baseline(world.session())
    case.result["baseline_runs"] = [result]
    state = world.store.load()
    case.check(
        "explicit_blocked_unavailable_outcome",
        not result["complete"] and result.get("reason") == "blocked_unavailable",
        result,
    )
    case.check(
        "no_worker_or_staff_artifact_writes",
        not any(record["writes"] for record in state["interactions"]),
    )
    case.check(
        "no_submission_or_fabricated_completion",
        not any(item["submissions"] for item in state["work_items"].values()),
    )
    case.check(
        "unavailable_blocker_retained",
        bool(state["blockers"])
        and all(record["status"] == "unavailable" for record in state["blockers"].values()),
    )
    final = case.checkpoint("blocked")
    initial = case.result["checkpoints"]["initial"]
    case.check(
        "all_artifact_bytes_and_versions_unchanged",
        all(fingerprint(initial, aid) == fingerprint(final, aid) for aid in initial["artifacts"]),
    )
    case.result["world_outcome"] = "blocked_unavailable"


def existing_basis(case):
    world = case.create(delivery="file", information="mail")
    case.complete()
    state = world.store.load()
    case.check(
        "zero_redundant_scope_requests",
        not any(
            record["action"] == "mail_send" and record["inputs"].get("topic") == "scope"
            for record in state["interactions"]
        ),
    )
    case.check(
        "one_submission_without_forced_rework",
        len(state["work_items"]["work-1"]["submissions"]) == 1,
    )


def during_update(case):
    world = case.create(scenario="during_update")
    case.complete()
    state = world.store.load()
    replacement = state["work_replacements"].get("work-1")
    case.check("active_work_replaced_after_first_model_edit", replacement is not None)
    case.check(
        "replaced_work_not_submitted",
        state["work_items"]["work-1"]["status"] == "superseded"
        and not state["work_items"]["work-1"]["submissions"],
    )
    case.check(
        "replacement_work_accepted", state["work_items"][replacement]["status"] == "accepted"
    )
    revisions = [
        record for record in state["interactions"] if record["action"] == "revise_requirements"
    ]
    case.check(
        "change_recorded_as_manager_action",
        bool(revisions) and all(record["actor_id"] == "manager" for record in revisions),
    )


def withdraw(case):
    world = case.create(delivery="file")
    until(world, before_submit=True)
    submission = call(world, "submit", work_item_id="work-1")
    call(
        world,
        "withdraw",
        work_item_id="work-1",
        submission_id=submission["submission_id"],
        reason="机制验收：主动撤回后以相同有效产物重新提交",
    )
    withdrawn = case.checkpoint("withdrawn")
    state = world.store.load()
    first = state["work_items"]["work-1"]["submissions"][0]
    case.check(
        "withdrawn_submission_not_approved",
        first["invalidated"]
        and first["current_applicability"] == "withdrawn"
        and first["review"]["decision"] == "withdrawn",
    )
    new = call(world, "submit", work_item_id="work-1")
    call(world, "wait", ticks=2)
    case.check(
        "resubmission_pins_same_correct_artifact_version",
        new["artifact_versions"] == submission["artifact_versions"],
    )
    case.check("resubmission_accepted", world.session().observe()["complete"])
    case.check(
        "withdrawal_does_not_force_artifact_rewrite",
        fingerprint(withdrawn, "model") == fingerprint(case.checkpoint("resubmitted"), "model"),
    )
    case.grade()


CASES = (
    (
        "release_deadlock",
        "A work/release self-deadlock is rejected at compile admission.",
        deadlock,
    ),
    (
        "scoped_replies",
        "Scope and audience replies resolve only their explicitly bound work blockers.",
        scoped_replies,
    ),
    (
        "basis_only",
        "Two accepted stages share identical financial disclosure; basis changes propagate.",
        basis_only,
    ),
    (
        "selective_audience",
        "Audience change adds one note version while model, memo and basis remain unchanged.",
        selective,
    ),
    (
        "waiting_reply",
        "A late old reply neither grants the new basis nor resolves the replacement blocker.",
        waiting_reply,
    ),
    (
        "during_review",
        "A pending old submission is archived and cannot approve current requirements.",
        during_review,
    ),
    (
        "unavailable",
        "Unavailable information yields explicit blocking without writing or submitting artifacts.",
        unavailable,
    ),
    (
        "existing_basis",
        "An applicable public confirmation permits direct valid delivery without scope requests.",
        existing_basis,
    ),
    (
        "during_update",
        "Requirement change during editing replaces work and the replacement can complete.",
        during_update,
    ),
    (
        "withdraw_resubmit",
        "Withdrawn approval cannot occur; unchanged valid artifacts can be resubmitted.",
        withdraw,
    ),
)


def run_case(base, entry):
    name, expected, function = entry
    case = Case(base / name, expected)
    try:
        function(case)
    except Exception as exc:
        case.result["error"] = f"{type(exc).__name__}: {exc}"
        case.result["traceback"] = traceback.format_exc()
    finally:
        if case.world:
            try:
                case.checkpoint("final")
                state = case.world.store.load()
                observation = case.world.session().observe()
                case.result["business_complete"] = observation["complete"]
                case.result["world_outcome"] = observation.get("terminal_reason") or (
                    "accepted" if observation["complete"] else "unfinished"
                )
                case.result["logical_model_calls"] = len(state["calls"])
                case.result["interaction_count"] = len(state["interactions"])
                case.result["spec_sha256"] = digest(
                    (case.world.store.control / "spec.json").read_bytes()
                )
            except Exception as exc:
                case.result["finalization_error"] = f"{type(exc).__name__}: {exc}"
        case.result["mechanism_pass"] = (
            bool(case.result["checks"])
            and all(check["passed"] for check in case.result["checks"])
            and "error" not in case.result
            and "finalization_error" not in case.result
        )
        atomic_write(case.path / "result.json", json_bytes(case.result))
        print(
            f"{name}: mechanism_pass={case.result['mechanism_pass']} business_complete={case.result['business_complete']}",
            flush=True,
        )
    return case.result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "Output must be a new directory; existing and historical runs are never changed"
        )
    if args.workers < 1:
        parser.error("workers must be positive")
    args.output.mkdir(parents=True)
    identity = code_identity()
    started = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=min(args.workers, len(CASES))) as executor:
        results = list(executor.map(lambda entry: run_case(args.output, entry), CASES))
    ending_identity = code_identity()
    report = {
        **identity,
        "ending_code_identity": ending_identity,
        "source_tree_unchanged_during_run": identity["source_tree_sha256"]
        == ending_identity["source_tree_sha256"],
        "script_sha256": digest(Path(__file__).read_bytes()),
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "spreadsheet_engine_version": ENGINE_VERSION,
        "suite": "world-semantics-lifecycle-v0.3",
        "seed": SEED,
        "seed_sampling": "One fixed synthetic lineage; cases are mechanism coverage, not independent samples.",
        "provider": "rule_based",
        "workers": args.workers,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(results),
        "mechanism_pass_count": sum(result["mechanism_pass"] for result in results),
        "business_complete_count": sum(result["business_complete"] for result in results),
        "logical_model_calls": sum(result.get("logical_model_calls", 0) for result in results),
        "results": results,
        "interpretation": "Programmatic world-mechanism witnesses only. Expected blocking/rejection is not model task success; no API calls, GPU training, learning-gain or professional-gold claims.",
    }
    atomic_write(args.output / "report.json", json_bytes(report))
    print(
        f"report: {args.output / 'report.json'} ({report['mechanism_pass_count']}/{len(results)} mechanism cases passed)"
    )
    return 0 if all(result["mechanism_pass"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
