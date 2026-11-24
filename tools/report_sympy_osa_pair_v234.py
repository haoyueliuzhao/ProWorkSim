"""Audit the A4 request boundary and the actual independent review in both branches."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_repaired_osa_pair_v233 as prior
from run_sympy_osa_pair_v234 import PLAN, RUN, CASE
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_context_panel_v231 import ROOT
from proworksim.storage import read_json, atomic_write, json_bytes


def input_evidence(folder, source):
    (request,) = (folder / "osa-api").glob("*/request.json")
    wire = read_json(request)["payload"]["wire"]
    shown = json.loads(wire["messages"][-1]["content"])
    node = read_json(folder / "decision.json")["anomaly"]
    if shown["subject"] != node["subject"] or shown["subject"] != "independent_current_review":
        raise ValueError("Different A4 obligation")
    (evidence,) = shown["evidence"].values()
    (observed,) = [
        r["outcome"]
        for r in read_json(source / "observations.json")
        if r["ordinal"] == evidence["opportunity"]
    ]
    if (
        observed["response"]["command_id"] != evidence["command_id"]
        or observed["worker_id"] != "member_002"
    ):
        raise ValueError("Evidence not linked to reviewer")
    ready = observed["response"]["result"]
    return dict(
        subject_on_wire=shown["subject"],
        osa_evidence=evidence,
        allowed_options=shown["options"],
        public_original_receipt=dict(
            packages=ready["package_chain"]["packages"],
            gaps=ready["gaps"],
            test_passed=ready["final_test"]["passed"],
            test_version=ready["final_test"]["source_reference"],
            final_identity_at_decision={
                k: ready["final_identity"][k]
                for k in ("source_reference", "files_sha256", "entry_metadata_sha256")
            },
            current_fixed_patch_ids=ready["current_fixed_patch_ids"],
        ),
    )


def reviews(folder):
    actions = []
    with (folder / "runtime/experience.jsonl").open() as f:
        for line in f:
            event = json.loads(line)
            if event["kind"] != "tool_call":
                continue
            d = event["payload"]
            tool = d["action"]
            if tool not in (
                "fix_patch",
                "complete_work",
                "open_patch_review",
                "run_patch_review_tests",
                "org_review_patch",
                "submit_integration",
                "delivery_readiness",
            ):
                continue
            rsp = d["response"]
            res = rsp.get("result") or {}
            record = {
                "opportunity": d["opportunity_id"],
                "member": event["worker_id"],
                "tool": tool,
                "accepted": rsp["ok"],
                "patch": d["arguments"].get("patch_id")
                or res.get("review_patch_id")
                or res.get("patch_id"),
            }
            if tool == "complete_work":
                record.update(task=d["arguments"].get("task_id"), identity=res.get("identity"))
            if tool == "submit_integration":
                record.update(
                    episode_state=res.get("episode_state"),
                    identity={
                        k: res.get(k)
                        for k in ("source_reference", "files_sha256", "entry_metadata_sha256")
                    },
                )
            if tool == "org_review_patch":
                record.update(
                    decision=res.get("decision"),
                    author=res.get("author"),
                    reviewer=res.get("actor_id"),
                    evidence=res.get("test_evidence"),
                    identity=res.get("identity"),
                )
            if tool == "run_patch_review_tests":
                record.update(
                    executed=res.get("executed"),
                    passed=res.get("passed"),
                    source_reference=res.get("source_reference"),
                )
            if tool == "delivery_readiness":
                record.update(ready=res.get("ready_to_submit"), gaps=res.get("gaps"))
            if not rsp["ok"]:
                record["reason"] = ((rsp.get("error") or {}).get("rejection") or {}).get("code")
            actions.append(record)
    return actions


def delivery_review(actions):
    """Find the independent test and review on the exact submitted version of work_root."""
    for i, row in enumerate(actions):
        if not row["accepted"] or row.get("episode_state") != "DELIVERED":
            continue
        for review in actions[:i]:
            if (
                review.get("decision") != "accept"
                or not review["accepted"]
                or review.get("identity") != row["identity"]
                or review.get("reviewer") == review.get("author")
            ):
                continue
            check = review.get("evidence") or {}
            if (
                check.get("actor_id") != review["reviewer"]
                or not check.get("executed")
                or not check.get("passed")
                or any(check.get(k) != v for k, v in row["identity"].items())
            ):
                continue
            if any(
                c["accepted"]
                and c.get("task") == "work_root"
                and c["patch"] == review["patch"]
                and c.get("identity") == row["identity"]
                for c in actions[:i]
            ):
                return dict(
                    patch=review["patch"],
                    author=review["author"],
                    reviewer=review["reviewer"],
                    test_event=check["sequence"],
                    submit_opportunity=row["opportunity"],
                    identity=row["identity"],
                )
    return None


def test_durations(folder):
    rows = []
    for request in sorted((folder / "public-test-rpc").glob("*/request.json")):
        start = read_json(request)
        response = request.with_name("response.json")
        result = read_json(response) if response.exists() else {}
        execution = result.get("execution") or {}
        rows.append(
            dict(
                call_index=start["call_index"],
                member=start["actor_id"],
                selection=start["public_test_selection"],
                responded=response.exists(),
                wall_seconds=execution.get("wall_seconds"),
                timed_out=execution.get("timed_out"),
                validation_status=result.get("validation_status"),
                counts=result.get("counts"),
            )
        )
    return rows


def run():
    fn = prior.run
    clone_function(fn, {**fn.__globals__, "RUN": RUN, "PLAN": PLAN, "CASE": CASE})(
        namespace="v234", include_inventory=False
    )
    path = PLAN / "results.json"
    r = read_json(path)
    protocol = read_json(PLAN / "protocol.json")
    if r["arms"]["OSA"]["status"] == "closed":
        r["osa_input_audit"] = input_evidence(RUN / CASE / "OSA", ROOT / protocol["source_prefix"])
    for arm, row in r["arms"].items():
        if row["status"] == "closed":
            folder = RUN / CASE / arm
            episode = read_json(folder / "result.json")
            row["generation_seconds"] = episode["finished"] - episode["started"]
            row["public_test_calls"] = test_durations(folder)
            row["scored_candidates"] = {}
            for endpoint in ("code", "delivery"):
                score = read_json(folder.with_name(arm + "-" + endpoint) / "receipt.json")
                row["scored_candidates"][endpoint] = {
                    "tree": score.get("candidate_tree_sha256"),
                    "patch": (score.get("patch") or {}).get("sha256"),
                }

            row["version_review_actions"] = reviews(folder)
            row["exact_submitted_review"] = delivery_review(row["version_review_actions"])
            if (
                row["initial_budget"] != protocol["arm_limit"]
                or row["public_subject"] != protocol["subject"]
            ):
                raise ValueError("Different verification boundary")
    if r.get("osa_input_audit"):
        prefix = r["osa_input_audit"]["public_original_receipt"]["final_identity_at_decision"]
        for row in r["arms"].values():
            review = row.get("exact_submitted_review")
            row["reviewed_delivery_matches_prefix_identity"] = (
                (review["identity"] == prefix) if review else None
            )
    r["amendment_nanoyuan"] = protocol["amendment_nanoyuan"]
    r["cash_cap_nanoyuan"] = protocol["account_cap_nanoyuan"]
    r["actual_pair_cost_nanoyuan"] = sum(
        v["use"]["cost_nanoyuan"] for v in r["arms"].values() if v["status"] == "closed"
    )
    atomic_write(path, json_bytes(r))


if __name__ == "__main__":
    run()
