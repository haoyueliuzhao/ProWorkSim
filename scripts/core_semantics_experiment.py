"""Finite work-world rule compositions over actual operating-world artifacts.

Run: .venv/bin/python scripts/core_semantics_experiment.py --output runs/new-core-suite
These are transparent program policies, not model trajectories or training data.
A controlled harness replays an already delivered reply and delays one scheduled
reply in the composition cases. Both interventions are separately recorded.
"""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.baseline import run_baseline
from proworksim.basis import basis_context
from proworksim.compiler import compile_world
from proworksim.contracts import CONTRACT_VERSION, EVALUATOR_VERSION
from proworksim.core.rules import confirm_credential, registered_applicability
from proworksim.core.types import CheckStatus
from proworksim.core.visibility import visible_version
from proworksim.core.work import approve_submission
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.schema import SCHEMA_VERSION
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.validation import evaluate

SEED = 809


class Paused(Exception):
    pass


class BeforeSubmission:
    """Stop the existing transparent policy at a public tool-call boundary."""

    def __init__(self, world):
        self.session = world.session()

    def observe(self):
        return self.session.observe()

    def call(self, action, **arguments):
        if action == "submit":
            raise Paused
        return self.session.call(action, **arguments)


def prepare(world):
    try:
        run_baseline(BeforeSubmission(world))
    except Paused:
        return
    raise AssertionError("Rule policy did not reach its first submission boundary")


def call(world, action, actor="analyst", expect_ok=True, **arguments):
    output = world.session(actor).call(action, **arguments)
    if output["ok"] != expect_ok:
        raise AssertionError(f"{action}: expected ok={expect_ok}, observed {output}")
    return output["result"] if expect_ok else output


def block(world, work_id, topic="scope", provider="manager"):
    item = world.store.load()["work_items"][work_id]
    return call(
        world,
        "block_work",
        work_item_id=work_id,
        kind=topic,
        requested_role=provider,
        required_scope_version=item["basis_requirement_version"] if topic == "scope" else None,
        reason=f"Program property witness: await {topic} for this work requirement",
    )["blocker_id"]


def request(world, work_id, blocker_id=None, topic="scope", provider="manager"):
    return call(
        world,
        "mail_send",
        to=provider,
        topic=topic,
        work_item_id=work_id,
        blocker_id=blocker_id,
        body="Please supply the explicitly scoped supporting version.",
    )["message_id"]


def version_hashes(world, state=None):
    state = state or world.store.load()
    return {
        aid: {
            vid: digest(world.store.version_path(artifact, vid).read_bytes())
            for vid in artifact["versions"]
        }
        for aid, artifact in state["artifacts"].items()
    }


def file_facts(state):
    return {
        aid: {
            "current_version": artifact["current_version"],
            "versions": {
                vid: {key: version.get(key) for key in ("sha256", "derived_from", "credential")}
                for vid, version in artifact["versions"].items()
            },
        }
        for aid, artifact in state["artifacts"].items()
    }


class Case:
    def __init__(self, path, expected):
        self.path = path
        path.mkdir()
        self.worlds = {}
        self.report = {
            "case": path.name,
            "seed": SEED,
            "expected": expected,
            "provider": "transparent_program",
            "checks": [],
            "harness_actions": [],
            "checkpoints": {},
            "worlds": {},
        }

    def create(self, name="world", **options):
        world = World(compile_world(design(SEED, **options), self.path / name))
        self.worlds[name] = world
        self.checkpoint(name, "initial")
        return world

    def check(self, name, passed, evidence=None):
        row = {"name": name, "status": "PASS" if passed else "FAIL"}
        if evidence is not None:
            row["evidence"] = evidence
        self.report["checks"].append(row)
        if not passed:
            raise AssertionError(name)

    def checkpoint(self, world_name, name):
        world = self.worlds[world_name]
        state = world.store.load()
        filename = f"{world_name}-{name}.json"
        payload = {"state": state, "immutable_version_sha256": version_hashes(world, state)}
        atomic_write(self.path / filename, json_bytes(payload))
        self.report["checkpoints"][f"{world_name}/{name}"] = {
            "file": filename,
            "state_sha256": digest(json_bytes(state)),
            "file_sha256": digest(json_bytes(payload)),
            "logical_time": state["clock"],
        }
        return state

    def harness(self, world_name, action, callback, inputs, expected_error=False):
        """Explicit controlled intervention, never recorded as a worker tool action."""
        world = self.worlds[world_name]
        with world.store.lock():
            world.state = world.store.load()
            before = copy.deepcopy(world.state)
            record = {
                "controller": "experiment_harness",
                "world": world_name,
                "action": action,
                "inputs": inputs,
                "logical_time": before["clock"],
                "before_state_sha256": digest(json_bytes(before)),
            }
            try:
                result = callback(world)
                record["output"] = {"ok": True, "result": result}
            except (ValueError, KeyError) as error:
                record["output"] = {
                    "ok": False,
                    "error": {"type": type(error).__name__, "message": str(error)},
                }
            record["after_state_sha256"] = digest(json_bytes(world.state))
            record["state_unchanged"] = before == world.state
            world.store.save(world.state)
            self.report["harness_actions"].append(record)
            atomic_write(
                self.path / "harness-actions.json", json_bytes(self.report["harness_actions"])
            )
        self.check(
            f"{world_name}:{action}:expected_execution_status",
            record["output"]["ok"] != expected_error,
            record["output"],
        )
        return record

    def evaluations(self, world_name="world"):
        records = evaluate(self.worlds[world_name].store.root)
        filename = f"{world_name}-evaluations.json"
        atomic_write(self.path / filename, json_bytes(records))
        self.report.setdefault("evaluations", {})[world_name] = {
            "file": filename,
            "records": len(records),
            "passed": sum(r["passed"] for r in records),
            "failed_checks": {
                f"{r['work_item_id']}/{r['submission_id']}": [
                    check["name"] for check in r["checks"] if not check["passed"]
                ]
                for r in records
                if not r["passed"]
            },
        }
        return records


def reply_locality(case):
    world = case.create(topology="fork")
    prepare(world)
    call(world, "submit", work_item_id="model-1")
    call(world, "wait", ticks=2)
    scope_block = block(world, "memo-1")
    audience_block = block(world, "note-1", "audience", "client")
    before = case.checkpoint("world", "both-blocked")
    request_id = request(world, "memo-1", scope_block)
    call(world, "wait", ticks=2)
    replied = case.checkpoint("world", "first-reply")
    case.check(
        "intended_condition_satisfied", replied["blockers"][scope_block]["status"] == "resolved"
    )
    case.check(
        "unrelated_blocker_unchanged",
        before["blockers"][audience_block] == replied["blockers"][audience_block],
    )
    case.check(
        "unrelated_work_stays_blocked", replied["work_items"]["note-1"]["status"] == "blocked"
    )
    case.check("reply_does_not_rewrite_files", file_facts(before) == file_facts(replied))
    replay = case.harness(
        "world",
        "redeliver_completed_reply",
        lambda w: w._deliver_reply({"request_id": request_id}),
        {"request_id": request_id, "intervention": "Replay the same already completed event"},
    )
    case.check("duplicate_reply_is_exact_state_noop", replay["state_unchanged"])
    case.check("duplicate_not_a_new_response", replay["output"]["result"].get("duplicate") is True)


def observation_and_adoption(case):
    world = case.create(delivery="file", information="clarification")
    initial = world.store.load()
    reference = initial["work_items"]["work-1"]["required_basis"]
    case.check(
        "required_version_initially_inaccessible",
        visible_version(
            initial["artifacts"]["basis"], "analyst", initial["clock"], reference["version_id"]
        )
        is None,
    )
    bid = block(world, "work-1")
    request(world, "work-1", bid)
    call(world, "wait", ticks=2)
    granted = case.checkpoint("world", "access-granted")
    case.check(
        "reply_grants_exact_version",
        visible_version(
            granted["artifacts"]["basis"], "analyst", granted["clock"], reference["version_id"]
        )
        == reference["version_id"],
    )
    case.check(
        "access_is_not_direct_file_observation",
        reference not in granted["knowledge"]["analyst"]["read_artifacts"],
    )
    context = basis_context(
        granted["work_items"]["work-1"], granted["project"]["project_id"], granted["clock"]
    )
    prior_support = registered_applicability(granted, reference, context).to_dict()
    call(world, "read_file", artifact_id="basis", version_id=reference["version_id"])
    read = case.checkpoint("world", "read")
    case.check(
        "read_records_observation", reference in read["knowledge"]["analyst"]["read_artifacts"]
    )
    case.check("read_does_not_declare_adoption", file_facts(granted) == file_facts(read))
    case.check(
        "read_does_not_create_formal_support", granted["attestations"] == read["attestations"]
    )
    case.check(
        "support_is_independent_of_reading",
        prior_support["status"] == CheckStatus.PASS
        and registered_applicability(read, reference, context).status == CheckStatus.PASS,
    )
    source_version = read["artifacts"]["financials"]["current_version"]
    # Intentionally preserve an obsolete value while declaring the new inputs.
    cell = call(world, "sheet_read")["sheets"]["Inputs"]["B4"]["value"]
    updated = call(
        world,
        "sheet_update",
        cells={"Inputs!B4": cell},
        dependencies=[
            {"artifact_id": "financials", "version_id": source_version},
            reference,
        ],
    )
    adopted = case.checkpoint("world", "declared-adoption")
    case.check("adoption_is_explicit_version_edge", reference in updated["derived_from"])
    case.check(
        "adoption_does_not_create_confirmation", adopted["attestations"] == read["attestations"]
    )
    submission = call(world, "submit", work_item_id="work-1")
    records = case.evaluations()
    evaluated = next(r for r in records if r["submission_id"] == submission["submission_id"])
    case.check(
        "declared_current_inputs_do_not_guarantee_numeric_support",
        not evaluated["passed"]
        and any(
            not check["passed"] and check["category"] in {"inputs", "calculation"}
            for check in evaluated["checks"]
        ),
    )


def applicability_relations(case):
    world = case.create(scenario="basis_only")
    result = run_baseline(world.session())
    case.check("transparent_policy_completes_both_requirements", result["complete"])
    state = case.checkpoint("world", "both-accepted")
    first, second = state["work_items"]["work-1"], state["work_items"]["work-2"]
    current_ref, historical_ref = second["required_basis"], first["required_basis"]
    contexts = {
        item["work_item_id"]: basis_context(item, state["project"]["project_id"], state["clock"])
        for item in (first, second)
    }
    queries = {
        "same_new_ref_old_work": registered_applicability(
            state, current_ref, contexts["work-1"]
        ).to_dict(),
        "same_new_ref_new_work": registered_applicability(
            state, current_ref, contexts["work-2"]
        ).to_dict(),
        "historical_ref_old_work": registered_applicability(
            state, historical_ref, contexts["work-1"]
        ).to_dict(),
    }
    case.report["relation_queries"] = queries
    case.check(
        "same_reference_has_different_contextual_applicability",
        queries["same_new_ref_old_work"]["status"] == "FAIL"
        and queries["same_new_ref_new_work"]["status"] == "PASS",
    )
    case.check(
        "older_credential_still_applies_to_older_work",
        queries["historical_ref_old_work"]["status"] == "PASS" and historical_ref != current_ref,
    )
    model = state["artifacts"]["model"]
    case.check(
        "global_summary_does_not_hide_disagreement",
        model["basis_applicability"] == "unknown"
        and model["basis_applicability_by_work"] == {"work-1": "stale", "work-2": "current"},
        model["basis_applicability_by_work"],
    )
    records = case.evaluations()
    case.check(
        "historical_pinned_submission_remains_independently_valid",
        any(r["work_item_id"] == "work-1" and r["passed"] for r in records),
    )
    case.check(
        "both_pinned_submissions_valid", len(records) == 2 and all(r["passed"] for r in records)
    )


BUSINESS_FIELDS = (
    "project",
    "roles",
    "organization",
    "artifact_contracts",
    "artifacts",
    "work_items",
    "work_replacements",
    "attestations",
    "basis_approvals",
    "basis_by_scenario",
    "messages",
    "requests",
    "blockers",
    "conditions",
    "condition_specs",
    "access_grants",
    "communication_grants",
    "released_groups",
    "fired_rules",
    "events",
)


def normalized_business(state):
    """Drop only file creation tick from the selected business records.

    Both branches start from one byte-identical snapshot. Their only new facts
    are two independent versions, so no broader temporal or ID erasure is needed.
    In particular, confirmation times and all object/approval/event refs remain.
    """
    result = {field: copy.deepcopy(state[field]) for field in BUSINESS_FIELDS if field in state}
    for artifact in result.get("artifacts", {}).values():
        for version in artifact["versions"].values():
            version.pop("logical_time", None)
    return result


def independent_order(case):
    base = case.create(name="base", topology="fork")
    prepare(base)
    call(base, "submit", work_item_id="model-1")
    call(base, "wait", ticks=2)
    snapshot = base.snapshot(case.path / "common-snapshot")
    state = base.store.load()
    contents = {
        aid: json.dumps(
            {**json.loads(base.store.content(state["artifacts"][aid])), "property_witness": aid},
            ensure_ascii=False,
            sort_keys=True,
        )
        for aid in ("memo", "note")
    }
    normalizations = {}
    for name, order in (("memo-then-note", ("memo", "note")), ("note-then-memo", ("note", "memo"))):
        world = World.restore(snapshot, case.path / name)
        case.worlds[name] = world
        for aid in order:
            call(world, "write_file", artifact_id=aid, content=contents[aid])
        resulting = case.checkpoint(name, "after-independent-writes")
        normalizations[name] = normalized_business(resulting)
        atomic_write(
            case.path / f"{name}-normalized-business.json", json_bytes(normalizations[name])
        )
    case.report["normalization"] = {
        "included_top_level_fields": BUSINESS_FIELDS,
        "removed_temporal_fields": ["artifacts.*.versions.*.logical_time"],
        "removed_reference_fields": [],
        "excluded": "Transport/runtime logs, observation logs, random world/branch identifiers; immutable bytes hashes, credential refs, attestations, work facts, reviews and messages are preserved.",
        "scope": "Two writes to independent JSON deliverables; no shared input, pending event or review conflict.",
    }
    case.check(
        "independent_write_orders_have_equal_business_state",
        normalizations["memo-then-note"] == normalizations["note-then-memo"],
    )
    case.check(
        "approvals_and_reference_graphs_retained_in_comparison",
        all(normalizations[name]["attestations"] for name in normalizations),
    )


def unauthorized_actions(case):
    world = case.create(delivery="file")
    prepare(world)
    state = world.store.load()
    reference = state["work_items"]["work-1"]["required_basis"]
    forged = copy.deepcopy(
        state["artifacts"]["basis"]["versions"][reference["version_id"]]["credential"]
    )
    forged.update(confirmed_by="analyst", attestation_ref="unauthorized-attempt")
    failed_confirm = case.harness(
        "world",
        "unauthorized_confirm",
        lambda w: confirm_credential(w.state, "analyst", reference, forged),
        {"actor_id": "analyst", "reference": reference, "credential": forged},
        expected_error=True,
    )
    case.check("unauthorized_confirmation_produces_no_fact", failed_confirm["state_unchanged"])
    denied_file = call(
        world, "write_file", artifact_id="basis", content="forged approval", expect_ok=False
    )
    case.check(
        "credential_file_cannot_be_overwritten_by_worker",
        denied_file["error"]["type"] == "WorldError",
    )
    submission = call(world, "submit", work_item_id="work-1")
    failed_approval = case.harness(
        "world",
        "unauthorized_approve",
        lambda w: approve_submission(w.state, "analyst", "work-1", submission["submission_id"]),
        {
            "actor_id": "analyst",
            "work_item_id": "work-1",
            "submission_id": submission["submission_id"],
        },
        expected_error=True,
    )
    case.check("unauthorized_approval_produces_no_fact", failed_approval["state_unchanged"])
    pending = case.checkpoint("world", "after-denied-actions")
    case.check(
        "submission_remains_without_review",
        pending["work_items"]["work-1"]["submissions"][-1]["review"] is None,
    )
    case.check("confirmation_registry_unchanged", pending["attestations"] == state["attestations"])


def executable_error_and_approval(case):
    world = case.create(delivery="file")
    prepare(world)
    wrong = call(world, "sheet_update", cells={"Outputs!B6": "=1+1"})
    values = call(world, "sheet_read")["sheets"]["Outputs"]["B6"]
    case.check("incorrect_formula_executes_and_is_persisted", values["value"] == 2, values)
    submission = call(world, "submit", work_item_id="work-1")
    case.check(
        "submission_pins_actual_erroneous_version",
        submission["artifact_versions"]["model"] == wrong["version_id"],
    )
    # Explicit staff action before scheduled automatic review, not a claim that
    # the default reviewer policy autonomously overlooked the defect.
    call(
        world,
        "approve",
        actor="reviewer",
        work_item_id="work-1",
        submission_id=submission["submission_id"],
    )
    state = case.checkpoint("world", "authorized-acceptance")
    review = state["work_items"]["work-1"]["submissions"][-1]["review"]
    case.check(
        "authorized_reviewer_can_accept_wrong_answer",
        review["decision"] == "accepted" and review["actor_id"] == "reviewer",
    )
    records = case.evaluations()
    row = next(r for r in records if r["submission_id"] == submission["submission_id"])
    failed = [check["name"] for check in row["checks"] if not check["passed"]]
    case.check(
        "independent_evaluator_rejects_accepted_error",
        not row["passed"] and "output:share_price" in failed,
        failed,
    )
    case.report["staff_policy_intervention"] = (
        "Harness explicitly invoked authorized reviewer approval before automatic review; this demonstrates allowed institutional error, not spontaneous model/reviewer behavior."
    )


def delay_reply(world, request_id, delay):
    event = next(
        event
        for event in world.state["events"]
        if event["kind"] == "staff_reply" and event["payload"]["request_id"] == request_id
    )
    before = event["at"]
    event["at"] = world.state["clock"] + delay
    return {"event_id": event["event_id"], "old_due": before, "new_due": event["at"]}


def composed_lifecycle(case):
    outcomes = {}
    for order in ("withdraw-before-revise", "revise-before-withdraw"):
        world = case.create(name=order, delivery="file", information="clarification")
        prepare(world)
        old_request = request(world, "work-1")
        case.harness(
            order,
            "defer_pending_reply",
            lambda w: delay_reply(w, old_request, 20),
            {
                "request_id": old_request,
                "delay": 20,
                "intervention": "Controlled external-event timing; preserve actual request and reply implementation",
            },
        )
        submission = call(world, "submit", work_item_id="work-1")
        before = case.checkpoint(order, "pending-submission-and-reply")
        unchanged_bytes = version_hashes(world, before)
        withdrawal_arguments = {
            "work_item_id": "work-1",
            "submission_id": submission["submission_id"],
            "reason": "Finite composition witness: retract pending delivery",
        }
        if order == "withdraw-before-revise":
            call(world, "withdraw", **withdrawal_arguments)
        replacement = call(
            world,
            "revise_requirements",
            actor="manager",
            work_item_ids=["work-1"],
            growth_delta=0.01,
            reason="Finite composition witness: newer approved requirement",
        )["replacements"]["work-1"]
        if order == "revise-before-withdraw":
            failure = call(world, "withdraw", expect_ok=False, **withdrawal_arguments)
            case.check("withdraw_of_superseded_work_is_rejected", not failure["ok"], failure)
        new_blocker = block(world, replacement)
        call(world, "wait", ticks=20)
        late = case.checkpoint(order, "old-reply-delivered")
        archived = late["work_items"]["work-1"]["submissions"][0]
        case.check(
            f"{order}:old_reply_is_outdated",
            late["requests"][old_request]["status"] == "outdated_reply",
        )
        case.check(
            f"{order}:new_condition_still_unsatisfied",
            late["blockers"][new_blocker]["status"] == "open"
            and late["work_items"][replacement]["status"] == "blocked",
        )
        case.check(
            f"{order}:historical_submission_pins_preserved",
            all(
                archived[key] == submission[key]
                for key in (
                    "submission_id",
                    "artifact_versions",
                    "required_basis",
                    "requirement_snapshot",
                )
            ),
        )
        hashes_after = version_hashes(world, late)
        case.check(
            f"{order}:all_historical_file_bytes_preserved",
            all(
                hashes_after[aid][version] == hash_value
                for aid, versions in unchanged_bytes.items()
                for version, hash_value in versions.items()
            ),
        )
        case.check(
            f"{order}:requirement_events_do_not_edit_deliverable",
            all(
                before["artifacts"][aid]["current_version"]
                == late["artifacts"][aid]["current_version"]
                for aid in ("model", "memo")
            ),
        )
        review = archived.get("review")
        case.check(
            f"{order}:historical_decision_matches_order",
            (review and review["decision"] == "withdrawn")
            if order == "withdraw-before-revise"
            else review is None,
        )
        new_ref = late["work_items"][replacement]["required_basis"]
        case.check(
            f"{order}:old_reply_does_not_grant_new_credential",
            visible_version(
                late["artifacts"]["basis"], "analyst", late["clock"], new_ref["version_id"]
            )
            is None,
        )
        request(world, replacement, new_blocker)
        call(world, "wait", ticks=2)
        result = run_baseline(world.session())
        case.check(f"{order}:replacement_can_complete", result["complete"])
        records = case.evaluations(order)
        current = [row for row in records if row["work_item_id"] == replacement]
        case.check(
            f"{order}:replacement_independently_valid",
            bool(current) and all(row["passed"] for row in current),
        )
        outcomes[order] = {
            "withdrawal_allowed": order == "withdraw-before-revise",
            "historical_review": review,
            "replacement": replacement,
            "complete": result["complete"],
        }
    case.report["composition_outcomes"] = outcomes
    case.report["composition_scope"] = (
        "Two explicit serial schedules with one delayed reply. Order-sensitive withdrawal legality is expected; this is not a proof for arbitrary interleavings."
    )


CASES = (
    (
        "reply_locality_and_idempotence",
        "A scoped reply changes only its condition; identical replay is a state no-op.",
        reply_locality,
    ),
    (
        "access_observation_adoption",
        "Access, direct observation, adoption and independently verified support are distinct.",
        observation_and_adoption,
    ),
    (
        "contextual_applicability",
        "One credential differs across work contexts; older credential and pinned history remain valid.",
        applicability_relations,
    ),
    (
        "independent_action_order",
        "Independent object writes commute in the explicitly normalized business projection.",
        independent_order,
    ),
    (
        "unauthorized_actions",
        "Unprivileged confirmation and approval cannot create formal facts.",
        unauthorized_actions,
    ),
    (
        "executable_error_and_approval",
        "An executable wrong formula and an authorized mistaken approval remain possible; independent grading rejects.",
        executable_error_and_approval,
    ),
    (
        "change_reply_withdraw_composition",
        "Revision, delayed reply and withdrawal preserve history under two finite serial schedules.",
        composed_lifecycle,
    ),
)


def run_case(base, entry):
    name, expected, function = entry
    case = Case(base / name, expected)
    try:
        function(case)
    except Exception as error:
        case.report["error"] = f"{type(error).__name__}: {error}"
        case.report["traceback"] = traceback.format_exc()
    finally:
        for world_name, world in case.worlds.items():
            try:
                state = case.checkpoint(world_name, "final")
                case.report["worlds"][world_name] = {
                    "path": str(world.store.root),
                    "business_complete": world.session().observe()["complete"],
                    "logical_model_calls": len(state["calls"]),
                    "interactions": len(state["interactions"]),
                    "spec_sha256": digest((world.store.control / "spec.json").read_bytes()),
                    "final_state_sha256": digest(json_bytes(state)),
                }
                if state["calls"]:
                    raise AssertionError("Unexpected model call in program property suite")
            except Exception as error:
                case.report.setdefault("finalization_errors", []).append(f"{world_name}: {error}")
        case.report["property_pass"] = (
            bool(case.report["checks"])
            and all(row["status"] == "PASS" for row in case.report["checks"])
            and "error" not in case.report
            and "finalization_errors" not in case.report
        )
        atomic_write(case.path / "result.json", json_bytes(case.report))
        print(f"{name}: property_pass={case.report['property_pass']}", flush=True)
    return case.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cases", nargs="+", choices=[entry[0] for entry in CASES])
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be a new directory; historical runs are never overwritten")
    if args.workers < 1:
        parser.error("workers must be positive")
    entries = [entry for entry in CASES if not args.cases or entry[0] in args.cases]
    args.output.mkdir(parents=True)
    before = code_identity()
    script_before = digest(Path(__file__).read_bytes())
    started = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=min(args.workers, len(entries))) as executor:
        results = list(executor.map(lambda entry: run_case(args.output, entry), entries))
    after = code_identity()
    script_after = digest(Path(__file__).read_bytes())
    report = {
        "suite": "work-world-core-properties-v0.4",
        "seed": SEED,
        "code_identity_before": before,
        "code_identity_after": after,
        "source_tree_unchanged_during_run": before["source_tree_sha256"]
        == after["source_tree_sha256"],
        "script_sha256_before": script_before,
        "script_sha256_after": script_after,
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "workers": args.workers,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "property_count": len(results),
        "property_pass_count": sum(r["property_pass"] for r in results),
        "check_count": sum(len(r["checks"]) for r in results),
        "check_pass_count": sum(c["status"] == "PASS" for r in results for c in r["checks"]),
        "world_count": sum(len(r["worlds"]) for r in results),
        "business_complete_count": sum(
            w["business_complete"] for r in results for w in r["worlds"].values()
        ),
        "logical_model_calls": sum(
            w["logical_model_calls"] for r in results for w in r["worlds"].values()
        ),
        "api_calls": 0,
        "gpu_used": False,
        "training_performed": False,
        "interpretation": "Finite program property witnesses from one synthetic seed, not independent statistical samples, model success, professional realism evidence or learning gains. Partial worlds, denied actions and wrong accepted work are deliberate outcomes.",
        "results": results,
    }
    atomic_write(args.output / "report.json", json_bytes(report))
    print(
        f"report: {args.output / 'report.json'} ({report['property_pass_count']}/{len(results)} properties)"
    )
    return 0 if all(r["property_pass"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
