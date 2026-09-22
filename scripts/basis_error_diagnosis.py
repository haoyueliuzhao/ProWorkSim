"""Diagnose stale approval use and metadata-only relabeling through actual tools.

These are fresh program_error_strategy worlds, not historical API trajectory
replays. No model is called, no training runs, and no historical data is edited.
"""

import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.validation import evaluate

CONDITIONS = ("old_basis", "relabel_only")


class PreparationBoundary(Exception):
    pass


class BeforeFirstSubmission:
    """Forward actual worker tools, stopping before the first submit executes."""

    def __init__(self, session):
        self.session = session
        self.work_item_id = None

    def observe(self):
        return self.session.observe()

    def call(self, action, **arguments):
        if action == "submit":
            self.work_item_id = arguments["work_item_id"]
            raise PreparationBoundary
        return self.session.call(action, **arguments)


def call(session, action, **arguments):
    response = session.call(action, **arguments)
    if not response["ok"]:
        raise RuntimeError(f"{action}: {response['error']}")
    return response["result"]


def artifact_record(state, artifact_id):
    artifact = state["artifacts"][artifact_id]
    version = artifact["current_version"]
    return {
        "version_id": version,
        "sha256": artifact["versions"][version]["sha256"],
        "derived_from": artifact["versions"][version]["derived_from"],
        "freshness": artifact.get("freshness"),
        "data_freshness": artifact.get("data_freshness"),
        "basis_applicability": artifact.get("basis_applicability"),
    }


def diagnose(base, seed, condition):
    path = base / f"{seed}-{condition}"
    identity = code_identity()
    result = {
        "seed": seed,
        "condition": condition,
        "world_path": str(path),
        "strategy_kind": "program_error_strategy",
        "historical_api_replay": False,
        "code_identity": identity,
    }
    try:
        compile_world(design(seed, delivery="continuous", information="mail"), path)
        world = World(path)
        analyst = world.session()
        preparation = BeforeFirstSubmission(analyst)
        try:
            run_baseline(preparation)
        except PreparationBoundary:
            pass
        if preparation.work_item_id != "work-1":
            raise RuntimeError("Expected a prepared work-1 before its first submission")

        guide = json.loads(call(analyst, "read_file", artifact_id="guide")["content"])
        source = call(analyst, "read_file", artifact_id="financials")
        memo = json.loads(call(analyst, "read_file", artifact_id="memo")["content"])
        old_metrics = dict(memo["metrics"])
        before_model = call(analyst, "sheet_read")
        input_sheet = guide["layout"]["input_sheet"]
        output_sheet = guide["layout"]["output_sheet"]
        growth_cell = guide["input_cells"]["growth"]
        old_growth = before_model["sheets"][input_sheet][growth_cell]["value"]
        before = world.store.load()
        prepared_artifacts = {
            name: artifact_record(before, name) for name in ("financials", "basis", "model", "memo")
        }
        if any(item["submissions"] for item in before["work_items"].values()):
            raise RuntimeError("Preparation unexpectedly included a submission")

        revision = call(
            world.session("manager"),
            "revise_requirements",
            work_item_ids=["work-1"],
            growth_delta=0.02,
            reason=f"program_error_strategy seed={seed}: financials unchanged, approved growth +0.02",
        )
        new_id = revision["replacements"]["work-1"]
        work = next(item for item in call(analyst, "work_list") if item["work_item_id"] == new_id)
        basis = json.loads(
            call(
                analyst,
                "read_file",
                artifact_id="basis",
                version_id=work["required_basis"]["version_id"],
            )["content"]
        )
        revised_artifacts = {
            name: artifact_record(world.store.load(), name)
            for name in ("financials", "basis", "model", "memo")
        }

        if condition == "relabel_only":
            call(
                analyst,
                "sheet_update",
                cells={f"{input_sheet}!{growth_cell}": old_growth},
                dependencies=[
                    {"artifact_id": "financials", "version_id": source["version_id"]},
                    work["required_basis"],
                ],
            )
            # sheet_update recalculates the actual workbook. Read its outputs to
            # confirm that unchanged growth leaves the original memo metrics intact.
            actual_model = call(analyst, "sheet_read")
            observed_metrics = {
                name: actual_model["sheets"][output_sheet][address]["value"]
                for name, address in guide["output_cells"].items()
            }
            if not all(
                math.isclose(observed_metrics[name], value, rel_tol=1e-12, abs_tol=1e-12)
                for name, value in old_metrics.items()
            ):
                raise RuntimeError("Relabel-only unexpectedly changed model outputs")
            memo["source_versions"]["model"] = actual_model["version_id"]
            for citation in memo["citations"]:
                if citation["artifact_id"] == "model":
                    citation["version_id"] = actual_model["version_id"]
            call(
                analyst,
                "write_file",
                artifact_id="memo",
                content=json.dumps(memo, ensure_ascii=False),
                dependencies=[
                    {"artifact_id": name, "version_id": version}
                    for name, version in memo["source_versions"].items()
                ],
            )
        else:
            actual_model = call(analyst, "sheet_read")

        submitted = call(analyst, "submit", work_item_id=new_id)
        call(analyst, "wait", ticks=2)
        # Do not advance further tools: business acceptance can queue the next
        # disclosure event. This diagnostic ends at the current review boundary.
        evaluations = evaluate(path, new_id)
        evaluation = next(
            row for row in evaluations if row["submission_id"] == submitted["submission_id"]
        )
        state = world.store.load()
        submission = next(
            row
            for row in state["work_items"][new_id]["submissions"]
            if row["submission_id"] == submitted["submission_id"]
        )
        final_artifacts = {
            name: artifact_record(state, name) for name in ("financials", "basis", "model", "memo")
        }
        final_memo = json.loads(
            world.store.version_path(
                state["artifacts"]["memo"], submitted["artifact_versions"]["memo"]
            ).read_bytes()
        )
        unchanged_financials = (
            prepared_artifacts["financials"]["version_id"]
            == final_artifacts["financials"]["version_id"]
            and digest(source["content"].encode()) == final_artifacts["financials"]["sha256"]
        )
        requirement_only_changed = all(
            prepared_artifacts[name]["version_id"] == revised_artifacts[name]["version_id"]
            and prepared_artifacts[name]["sha256"] == revised_artifacts[name]["sha256"]
            for name in ("financials", "model", "memo")
        )
        failed_checks = [check for check in evaluation["checks"] if not check["passed"]]
        result.update(
            {
                "lineage_id": state["project"]["lineage_id"],
                "prepared_work_item_id": "work-1",
                "evaluated_work_item_id": new_id,
                "submission_id": submitted["submission_id"],
                "actual_growth": actual_model["sheets"][input_sheet][growth_cell]["value"],
                "expected_basis_growth": basis["assumptions"]["growth"],
                "approved_basis_ref": work["required_basis"],
                "approved_basis_period": basis["period"],
                "financials_unchanged": unchanged_financials,
                "revision_did_not_modify_worker_artifacts": requirement_only_changed,
                "memo_metrics_unchanged": final_memo["metrics"] == old_metrics,
                "model_data_freshness": final_artifacts["model"]["data_freshness"],
                "model_basis_applicability": final_artifacts["model"]["basis_applicability"],
                "model_freshness": final_artifacts["model"]["freshness"],
                "business_review": submission["review"],
                "business_accepted": evaluation["business_accepted"],
                "independent_passed": evaluation["passed"],
                "failed_checks": failed_checks,
                "root_causes": evaluation["root_causes"],
                "propagated_failures": evaluation["propagated_failures"],
                "diagnostic_interpretation": evaluation["diagnostic_interpretation"],
                "evaluation": evaluation,
                "prepared_artifacts": prepared_artifacts,
                "artifacts_after_revision": revised_artifacts,
                "artifacts_after_review": final_artifacts,
                "logical_model_calls": len(state["calls"]),
                "tool_and_staff_actions": len(state["interactions"]),
                "pending_events_at_boundary": state["events"],
                "experiment_boundary": "new requirement's first business review; no continuation",
            }
        )
        expected = {
            "financials_unchanged": unchanged_financials,
            "revision_did_not_modify_worker_artifacts": requirement_only_changed,
            "memo_metrics_unchanged": result["memo_metrics_unchanged"],
            "old_growth_retained": result["actual_growth"] == old_growth,
            "approved_growth_changed": math.isclose(
                result["expected_basis_growth"], old_growth + 0.02, abs_tol=1e-12
            ),
            "independent_rejection": not evaluation["passed"],
            "business_result": evaluation["business_accepted"] == (condition == "relabel_only"),
            "data_current": result["model_data_freshness"] == "current",
            "basis_status": result["model_basis_applicability"]
            == ("stale" if condition == "old_basis" else "current"),
            "root_cause_grouping": len(evaluation["root_causes"]) == 1
            and len(evaluation["propagated_failures"]) > 1,
            "no_model_calls": not state["calls"],
        }
        result["acceptance_observations"] = expected
        result["observations_as_expected"] = all(expected.values())
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["observations_as_expected"] = False
    result["ending_code_identity"] = code_identity()
    result["source_changed_during_trial"] = (
        identity["source_tree_sha256"] != result["ending_code_identity"]["source_tree_sha256"]
    )
    atomic_write(path / "diagnosis.json", json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--seeds", type=int, nargs="+", default=[317, 331])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    base = Path(args.output)
    if base.exists():
        parser.error("Output directory must not exist; historical worlds are never overwritten")
    if args.workers < 1 or len(set(args.seeds)) != len(args.seeds):
        parser.error("workers must be positive and seeds must be unique")
    base.mkdir(parents=True)
    identity = code_identity()
    configurations = [(seed, condition) for seed in args.seeds for condition in CONDITIONS]
    with ThreadPoolExecutor(max_workers=min(args.workers, len(configurations))) as executor:
        rows = list(executor.map(lambda cfg: diagnose(base, *cfg), configurations))
    ending_identity = code_identity()
    summary = {
        "experiment": "basis_error_diagnosis",
        "strategy_kind": "program_error_strategy",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "code_identity": identity,
        "ending_code_identity": ending_identity,
        "source_changed_during_run": identity["source_tree_sha256"]
        != ending_identity["source_tree_sha256"],
        "historical_api_replay": False,
        "historical_worlds_modified": False,
        "uses_api": False,
        "uses_gpu": False,
        "independent_worlds": len(rows),
        "seeds": args.seeds,
        "conditions": list(CONDITIONS),
        "interpretation": (
            "Fresh, controlled tool-strategy counterexamples. Current provenance does not prove "
            "correct adoption of approved assumptions. Grouped downstream checks are dependency "
            "propagation, not independent capability deficits or inferred model mental causes."
        ),
        "observations_as_expected": all(row["observations_as_expected"] for row in rows),
        "results": rows,
    }
    atomic_write(base / "summary.json", json_bytes(summary))
    print(
        json.dumps(
            {
                "summary": str(base / "summary.json"),
                "observations_as_expected": summary["observations_as_expected"],
                "results": [
                    {
                        key: row.get(key)
                        for key in (
                            "seed",
                            "condition",
                            "actual_growth",
                            "expected_basis_growth",
                            "model_data_freshness",
                            "model_basis_applicability",
                            "business_accepted",
                            "independent_passed",
                            "observations_as_expected",
                            "error",
                        )
                    }
                    for row in rows
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not summary["observations_as_expected"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
