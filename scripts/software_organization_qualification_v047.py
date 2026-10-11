"""Finite new-interface native-tokenizer CPU routes; no model weights or samples."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
import time
from types import SimpleNamespace

from scripts.run_ne_v021 import reference, write

VERSION = "software-organization-native-materials-v0.47"
SOURCE = Path(__file__).resolve().parents[1]


def material_action(prepared, member, stage, ordinal):
    """The frozen CPU itinerary uses a short exact comment replacement only."""
    world, condition = prepared.world, prepared.case["condition"]
    read_action = {
        "name": "read_file",
        "arguments": {"path": "test_member.py", "start_line": 1, "max_lines": 30},
    }
    finish = {
        "name": "finish_stage",
        "arguments": {"reason": "CPU material shape complete; no business test or acceptance"},
    }
    if ordinal == 0:
        return read_action
    if (
        condition.startswith("D")
        and member == "member_001"
        and len(world._software()["registry"]) < int(condition[1])
    ):
        return {
            "name": "spawn_member",
            "arguments": {
                "briefing": "CPU fixture: inspect the same public contract; no model output."
            },
        }
    if condition[0] in "SD":
        return {
            "name": "staff_done",
            "arguments": {"reason": "CPU fixture ends this private session"},
        }
    patches = world.visible_patches(member)
    if not isinstance(patches, list):
        raise TypeError("The v047 world exposes a list of legal fixed patch metadata")
    mutable = stage in {"generate", "implement", "revise_integrate"}
    # The revision member obtains the actual prior fixed tree by its own tool.
    adopt_first = stage == "revise_integrate" and bool(patches)
    if ordinal == 1 and patches and (not mutable or adopt_first):
        return {"name": "adopt_candidate", "arguments": {"patch_id": patches[-1]["patch_id"]}}
    edit_ordinal = 2 if adopt_first else 1
    if mutable and ordinal == edit_ordinal:
        original = "# Optional member-authored exploratory checks; no automatic discovery."
        return {
            "name": "replace_file",
            "arguments": {
                "path": "test_member.py",
                "old": original,
                "new": original + "\n# v047 CPU material fixture: " + member + ":" + stage,
            },
        }
    if mutable and ordinal == edit_ordinal + 1:
        return {
            "name": "fix_patch",
            "arguments": {
                "task_ids": [],
                "message": "CPU fixture: exact non-executable member-test comment version",
            },
        }
    return finish


def validate_programmed_request_accounting(measurements, responses, ledger):
    """Every prepared input binds either one CPU reply or a retained stage rejection."""
    by_response = {row["response_id"]: row for row in responses}
    if len(by_response) != len(responses):
        raise ValueError("CPU response identity reused")
    seen_calls, seen_responses, outcomes = set(), set(), []
    for measurement in measurements:
        call_id = measurement["association"]["call_id"]
        if call_id in seen_calls:
            raise ValueError("One CPU preparation call identity measured twice")
        seen_calls.add(call_id)
        row = ledger["records"].get(call_id)
        if (
            row is None
            or row["member"] != measurement["member"]
            or row.get("stage_id") != measurement["stage_id"]
        ):
            raise ValueError("CPU material preparation lacks its exact stage/member ledger row")
        reservation = (
            row.get("rejected_reservation")
            if row["status"] == "admission_rejected"
            else row.get("reservation")
        )
        preparation = (reservation or {}).get("preparation", {})
        if (
            preparation.get("preparation_sha256") != measurement["preparation_sha256"]
            or preparation.get("input_ids_sha256") != measurement["input_ids_sha256"]
        ):
            raise ValueError("CPU material preparation differs from its original ledger identity")
        response_id = row.get("charge", {}).get("response_id")
        if row["status"] == "settled" and row.get("attempt_started") is True:
            response = by_response.get(response_id)
            if (
                response is None
                or response_id in seen_responses
                or row["charge"].get("usage_status") != "reported_actual_trace"
                or row["charge"].get("reported_usage") != response["usage"]
            ):
                raise ValueError(
                    "CPU material completed response is missing, reused or incorrectly charged"
                )
            seen_responses.add(response_id)
            status = "completed_programmed_response"
        elif (
            row["status"] == "admission_rejected"
            and row.get("budget_kind") == "stage_budget"
            and row.get("attempt_started") is False
            and "charge" not in row
            and row.get("admission_limits")
            and set(row["admission_limits"]) <= {"stage_max_total_tokens", "stage_max_attempts"}
        ):
            status = "prepared_only_stage_rejection"
        else:
            raise ValueError(
                "Unresolved material request cannot be relabeled as a stage preparation"
            )
        outcomes.append(
            {
                "call_id": call_id,
                "member": row["member"],
                "stage_id": row["stage_id"],
                "status": status,
                "response_id": response_id,
                "preparation_sha256": preparation["preparation_sha256"],
            }
        )
    if seen_responses != set(by_response):
        raise ValueError("CPU response has no uniquely measured preparation")
    return {
        "passed": True,
        "requests": outcomes,
        "prepared_only_stage_rejections": sum(
            row["status"] == "prepared_only_stage_rejection" for row in outcomes
        ),
        "completed_programmed_responses": len(seen_responses),
        "scope": "Prepared stage rejections retain exact inputs and zero attempts/charges; CPU scripted token usage is not model usage",
    }


def material_coverage(prepared, measurements, programmed_actions):
    """Expose missing declared finite shapes separately from selected-input capacity."""
    case, world = prepared.case, prepared.world
    missing = []
    measured = {(row["member"], row["stage_id"]) for row in measurements}
    for stage in case["stage_plan"]:
        for member in stage["members"]:
            if (member, stage["stage_id"]) not in measured:
                missing.append("unmeasured member/stage: " + member + ":" + stage["stage_id"])
    if case["condition"].startswith("D") and len(world._software()["registry"]) != int(
        case["condition"][1]
    ):
        missing.append("declared dynamic birth and child-read shapes not all reached")
    if case["condition"][0] in "IP":
        expected = (
            {"select"}
            if case["condition"].startswith("I")
            else {row["stage_id"] for row in case["stage_plan"][1:]}
        )
        actual = {
            row["stage_id"]
            for row in world.state.get("software_events", [])
            if row["kind"] == "candidate_adopted"
        }
        if case["condition"].startswith("I"):
            fixed_authors = {
                row["author"]
                for row in world._software()["patches"].values()
                if row.get("stage_id") == "generate"
            }
            for member in case["active_roles"]:
                if member not in fixed_authors:
                    missing.append("fixed generation candidate absent: " + member)
        for stage in sorted(expected - actual):
            missing.append("native adopted-candidate shape absent: " + stage)
        request_positions = {
            row["association"]["call_id"]: index for index, row in enumerate(measurements)
        }
        for action in programmed_actions:
            if action["programmed_action"]["name"] != "adopt_candidate":
                continue
            position = request_positions[action["association"]["call_id"]]
            if not any(
                row["member"] == action["member"] and row["stage_id"] == action["stage_id"]
                for row in measurements[position + 1 :]
            ):
                missing.append(
                    "adoption feedback follow-up not measured: "
                    + action["member"]
                    + ":"
                    + action["stage_id"]
                )
    return {
        "complete": not missing,
        "missing_shapes": missing,
        "measured_member_stages": [
            {"member": member, "stage_id": stage} for member, stage in sorted(measured)
        ],
        "business_success_required": False,
        "stage_rejection_can_cover_a_prepared_followup": True,
    }


def select_route_units(inventory, route_ids=None):
    """A subset changes only CPU fixture coverage, never formal pilot inventory."""
    units = [unit for sequence in inventory.values() for unit in sequence]
    available = [unit["slot_id"] for unit in units]
    if len(available) != len(set(available)):
        raise ValueError("The frozen material inventory contains duplicate route identities")
    if route_ids is None:
        return units
    if (
        not isinstance(route_ids, (list, tuple))
        or not route_ids
        or any(not isinstance(route, str) or not route for route in route_ids)
    ):
        raise ValueError("Declare a nonempty explicit list of frozen CPU route IDs")
    if len(route_ids) != len(set(route_ids)) or set(route_ids) - set(available):
        raise ValueError("CPU route subsets cannot repeat identities or introduce unknown routes")
    selected = set(route_ids)
    return [unit for unit in units if unit["slot_id"] in selected]


def native_routes(destination, plan_path, *, route_ids=None):
    from proworksim.software_context_replay_v041 import encode_request
    from proworksim.software_context_v044 import (
        SoftwareContextTransport,
        protected_software_request,
    )
    from proworksim.software_organization_runtime_v038 import _CollectionOwner, close_runtime
    from proworksim.software_organization_runtime_v047 import (
        DispatchDeadline,
        build_runtime,
        context_transport,
        run_fragment,
    )
    from proworksim.software_organization_v047 import build_software_collaboration_case, case_spec
    from scripts.software_context_replay_v044 import load_cpu_measurement
    from scripts.software_feedback_qualification_v044 import (
        ProgrammedOutput,
        feedback_preservation_checks,
    )
    from scripts.software_organization_v047 import assignments, source_files

    units = select_route_units(assignments(), route_ids)
    required_route_ids = [unit["slot_id"] for unit in units]
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    before = source_files()
    started = time.time()
    measurement = load_cpu_measurement(plan_path)
    original_recipe = copy.deepcopy(measurement.recipe)
    measurement.recipe["max_length"] = 18432
    rows, failures = [], []

    class RecordingContext(SoftwareContextTransport):
        def __init__(self, owner, directory):
            super().__init__(owner, directory, evidence_kind="cpu_programmed_fixture")
            self.rows = []

        def prepare_for_budget(self, request):
            result = super().prepare_for_budget(request)
            pending = self._prepared
            selected, projection = pending["selected"], pending["projection"]
            protected, _ = protected_software_request(
                request, ledger=self.feedback_ledger, member_id=self._turn["member_id"]
            )
            encoding = encode_request(selected, measurement)
            protected_encoding = encode_request(protected, measurement)
            checks, _ = feedback_preservation_checks(
                request,
                selected,
                projection,
                ledger=self.feedback_ledger.snapshot(),
                member_id=self._turn["member_id"],
            )
            folder = self.directory.parent / "cpu-inputs" / f"request-{len(self.rows) + 1:05d}"
            folder.mkdir(parents=True, exist_ok=False)
            for name, value in (
                ("original", request),
                ("selected", selected),
                ("encoding", encoding),
                ("projection", projection),
                ("preparation", result),
            ):
                write(folder / (name + ".json"), value)
            self.rows.append(
                {
                    "member": self._turn["member_id"],
                    "association": copy.deepcopy(self._turn["association"]),
                    "selected_prompt_tokens": encoding["prompt_tokens"],
                    "protected_prompt_tokens": protected_encoding["prompt_tokens"],
                    "context_limit": 18432,
                    "reserved_output_tokens": 2048,
                    "selected_hard_capacity_passed": encoding["fits"],
                    "headroom_tokens": encoding["headroom_tokens"],
                    "protected_margin_after1024": protected_encoding["headroom_tokens"] - 1024,
                    "protected_margin_diagnostic_only": True,
                    "preservation_checks": checks,
                    "input_ids_hash_matches": encoding["input_ids_sha256"]
                    == result["input_ids_sha256"],
                    "artifacts": [
                        reference(folder / (name + ".json"))
                        for name in (
                            "original",
                            "selected",
                            "encoding",
                            "projection",
                            "preparation",
                        )
                    ],
                    "evidence_kind": "cpu_programmed_fixture",
                    "model_generated": False,
                    "stage_id": prepared.world.stage_state()["stage_id"],
                    "preparation_sha256": result["preparation_sha256"],
                    "input_ids_sha256": result["input_ids_sha256"],
                }
            )
            return result

    class MaterialProgram(ProgrammedOutput):
        """One fixed finite native material program, never a business solver."""

        def __init__(self, owner, measurement, prepared):
            super().__init__(owner, measurement)
            self.prepared, self.visits, self.context = prepared, {}, None
            self.actions = []

        def complete(self, request, **kwargs):
            world = self.prepared.world
            state = world.stage_state()
            member = self.context._turn["member_id"]
            stage = state["stage_id"]
            key = (member, stage)
            ordinal = self.visits.get(key, 0)
            self.visits[key] = ordinal + 1
            self.action = material_action(self.prepared, member, stage, ordinal)
            self.actions.append(
                {
                    "member": member,
                    "stage_id": stage,
                    "ordinal": ordinal,
                    "association": copy.deepcopy(self.context._turn["association"]),
                    "programmed_action": copy.deepcopy(self.action),
                    "model_generated": False,
                }
            )
            return super().complete(request, **kwargs)

    for unit in units:
        route_id = unit["slot_id"]
        folder = destination / route_id
        folder.mkdir(exist_ok=False)
        identity = {"policy_version": "cpu-v047-not-model", "adapter_sha256": "no-weights"}
        owner = SimpleNamespace(
            window_id="organization-v047:cpu-" + route_id,
            recipe=copy.deepcopy(measurement.recipe),
            prepare_request=measurement.render,
            tokenizer=measurement.tokenizer,
            freeze_identity=lambda: copy.deepcopy(identity),
        )
        case = case_spec(
            unit["case_id"],
            condition=unit["condition"],
            team_token_budget=unit["team_token_budget"],
            first_member=unit["first_member"],
        )
        prepared = build_software_collaboration_case(case, folder / "prepared")
        program = MaterialProgram(owner, measurement, prepared)
        owner.transport = program
        deadline = DispatchDeadline()
        context = context_transport(
            owner, folder / "raw-transport", deadline, transport_factory=RecordingContext
        )
        program.context = context
        runtime, _, _ = build_runtime(
            _CollectionOwner(owner, context), prepared, folder / "runtime", deadline=deadline
        )
        failure, boundary, accounting, coverage = None, None, None, None
        try:
            boundary = run_fragment(prepared, runtime)
            if boundary["execution_integrity_failure"]:
                raise ValueError("CPU native SDK material route integrity failure")
            if not context.rows or not all(
                r["selected_hard_capacity_passed"]
                and r["input_ids_hash_matches"]
                and all(r["preservation_checks"].values())
                for r in context.rows
            ):
                raise ValueError("New material request does not fit or preserve required input")
            accounting = validate_programmed_request_accounting(
                context.rows, program.responses, runtime.team_budget.snapshot()
            )
            coverage = material_coverage(prepared, context.rows, program.actions)
            if not coverage["complete"]:
                raise ValueError(
                    "Finite material coverage is incomplete: "
                    + "; ".join(coverage["missing_shapes"])
                )
            if any(
                e["kind"] in {"test", "submit"}
                for e in prepared.world.state.get("software_events", [])
            ):
                raise ValueError(
                    "Initial-material CPU routes must not execute business test or acceptance"
                )
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            failures.append({"route_id": route_id, **failure})
        finally:
            snapshot = runtime.snapshot()
            close_runtime(runtime)
            result = {
                "route_id": route_id,
                "unit": unit,
                "passed": failure is None,
                "failure": failure,
                "boundary": boundary,
                "measurements": context.rows,
                "programmed_responses": program.responses,
                "runtime_snapshot": snapshot,
                "request_accounting": accounting,
                "material_coverage": coverage,
                "programmed_actions": program.actions,
                "programmed_fixture_usage": {
                    key: sum(row["usage"][key] for row in program.responses)
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                },
                "visited_member_stages": [
                    {"member": key[0], "stage": key[1], "calls": n}
                    for key, n in program.visits.items()
                ],
                "environment_preparation_cost": prepared.world._software()[
                    "environment_preparation_cost"
                ],
                "new_model_calls": 0,
                "model_weights_loaded": False,
                "new_business_tests_or_acceptance": 0,
            }
            write(folder / "route.json", result)
            rows.append(
                {
                    "route_id": route_id,
                    "passed": result["passed"],
                    "receipt": reference(folder / "route.json"),
                    "prepared_requests": len(context.rows),
                    "programmed_responses": len(program.responses),
                    "prepared_only_stage_rejections": accounting["prepared_only_stage_rejections"]
                    if accounting
                    else None,
                    "material_coverage_complete": coverage["complete"] if coverage else None,
                    "missing_material_shapes": coverage["missing_shapes"] if coverage else None,
                    "min_selected_headroom": min(
                        (r["headroom_tokens"] for r in context.rows), default=None
                    ),
                    "max_selected_prompt_tokens": max(
                        (r["selected_prompt_tokens"] for r in context.rows), default=None
                    ),
                }
            )
    result = {
        "version": VERSION,
        "passed": len(rows) == len(required_route_ids)
        and not failures
        and before == source_files(),
        "required_routes": len(required_route_ids),
        "required_route_ids": required_route_ids,
        "route_selection": "all_frozen_routes" if route_ids is None else "explicit_frozen_subset",
        "cpu_fixture_initial_read": {"path": "test_member.py", "start_line": 1, "max_lines": 30},
        "fixture_scope": "Positive native mechanics use the short editable member-test file directly needed by the next nonsemantic edit. Optional full-contract reads remain separately preserved capacity-negative evidence; the contract is already present in initial observations.",
        "routes": rows,
        "failures": failures,
        "source_files": before,
        "source_unchanged_during_routes": before == source_files(),
        "context_limit": 18432,
        "reserved_output_tokens": 2048,
        "native_measurement_identity": measurement.identity,
        "original_cpu_recipe": original_recipe,
        "declared_cpu_capacity_recipe": measurement.recipe,
        "tokenizer_statistics": measurement.statistics,
        "new_model_calls": 0,
        "new_backward_calls": 0,
        "model_weights_loaded": False,
        "actual_gpu_work": 0,
        "new_business_tests_or_acceptance": 0,
        "programmed_responses": sum(r["programmed_responses"] for r in rows),
        "prepared_requests": sum(r["prepared_requests"] for r in rows),
        "prepared_only_stage_rejections": sum(
            r["prepared_only_stage_rejections"] or 0 for r in rows
        ),
        "finite_material_coverage_complete": all(
            r["material_coverage_complete"] is True for r in rows
        ),
        "elapsed_seconds": time.time() - started,
        "scope": "Finite new architecture/budget/member/stage input routes with original native renderer/tokenizer and CPU scripted outputs. No solver, model weights, old trajectory replay, candidate business validation or model success gate. Not a proof that arbitrary later histories fit.",
    }
    write(destination / "native-routes.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--route-id",
        action="append",
        dest="route_ids",
        help="Explicit frozen route ID; repeat for a nonempty unique subset. Omit to run all44.",
    )
    args = parser.parse_args()
    result = native_routes(args.output, args.plan, route_ids=args.route_ids)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
