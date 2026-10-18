#!/usr/bin/env python3
"""Extract existing four-member results and matched controls; no model/test runs."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
LABELS = {
    "O1": "fixed_2_free", "O2": "fixed_4_free", "O3": "start_2_expand",
    "S1": "single", "I2": "independent_2", "I4": "independent_4",
    "P2": "pipeline_2", "P4": "pipeline_4",
}
FOUR = {"fixed_4_free", "independent_4", "pipeline_4"}

def relative(path):
    if not path:
        return None
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)

def extract():
    rows = []
    sources = []
    for version in ("038", "047", "048"):
        source = ROOT / f"docs/experiments/software-organization-v{version}-final.json"
        raw = source.read_bytes()
        data = json.loads(raw)
        key = "episodes" if version == "038" else "slots"
        sources.append({"path": relative(source), "sha256": hashlib.sha256(raw).hexdigest()})
        for index, row in enumerate(data[key]):
            condition = row["condition"]
            if condition not in LABELS:
                continue
            detail = row.get("cost_detail", {})
            usage = row.get("usage", detail.get("usage", {}))
            members = row.get("usage_by_member", detail.get("usage_by_member",
                row.get("population_measurements", {}).get("per_member_actual_cost", {})))
            member_costs = {
                member: {
                    "calls": value.get("output_bearing_calls", value.get("calls")),
                    "decisions": value.get("decisions"),
                    "prompt_tokens": value.get("prompt_tokens"),
                    "completion_tokens": value.get("completion_tokens"),
                    "total_tokens": value.get("total_tokens"),
                } for member, value in members.items()
            }
            if version == "038":
                episode = Path(row["evidence"]["slot_result"]).parent
                root = row["case_id"]
                success = row["R"]
                actual_members = row["member_lifecycle"]["actual_output_participants"]
            elif version == "047":
                episode = Path(detail["sources"]["slot-result.json"]["path"]).parent
                root = row["root_id"]
                success = row["R_joint"]
                actual_members = row["actual_call_members"]
            else:
                episode = Path(row["episode_folder"])
                root = row["root_id"]
                success = row["R_joint"]
                actual_members = row["population_measurements"]["actual_call_participant_count"]
            submitted = row["submitted"]
            rows.append({
                "slot_id": row["slot_id"], "source_version": version,
                "source": {"path": relative(source), "json_pointer": f"/{key}/{index}"},
                "strategy": LABELS[condition], "condition": condition,
                "is_four_member_target": LABELS[condition] in FOUR,
                "root_id": root, "seed": row["sampling_seed"],
                "budget": row.get("team_token_budget", 500000),
                "representation": row.get("representation", "old_protocol" if version == "038" else "Gamma0"),
                "actual_output_members": actual_members, "R": success,
                "Q": row.get("Q_joint"), "submitted": submitted,
                "outcome_class": row.get("outcome_class", "success" if success == 1 else
                    ("submitted_failed" if submitted else "no_submission")),
                "complete_actual_tokens": row.get("complete_actual_tokens", usage["total_tokens"]),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "actual_calls": usage.get("output_bearing_calls", row.get("actual_calls")),
                "member_test_calls": row.get("run_tests_calls", row.get("member_tests",
                    detail.get("tests", {}).get("accepted_run_tests_calls"))),
                "member_costs": member_costs,
                "stage_accounting": row.get("stage_accounting", detail.get("stage_accounting")),
                "stop_classifications": detail.get("stop_classifications"),
                "termination": row.get("termination"),
                "rejections": row.get("rejections", detail.get("stopping_rejections")),
                "first_fixed_submit_tokens": row.get("first_fixed_submit_tokens"),
                "after_first_submit_tokens": row.get("after_first_submit_tokens"),
                "episode_path": relative(episode),
                "trajectory_path": relative(episode / "experience.jsonl"),
            })
    assert len(rows) == 64
    assert len({row["slot_id"] for row in rows}) == 64
    assert sum(row["is_four_member_target"] for row in rows) == 28
    assert all(row["R"] in (0, 1) for row in rows)
    return rows, sources

def paired(rows, label, version, target, control, budget, target_rep=None, control_rep=None):
    def select(condition, representation):
        return {
            (row["root_id"], row["seed"]): row for row in rows
            if row["source_version"] == version and row["condition"] == condition
            and row["budget"] == budget
            and (representation is None or row["representation"] == representation)
        }
    left, right = select(target, target_rep), select(control, control_rep)
    assert left.keys() == right.keys() and left
    pairs = [{
        "root_id": key[0], "seed": key[1], "target_slot": left[key]["slot_id"],
        "control_slot": right[key]["slot_id"], "target_R": left[key]["R"],
        "control_R": right[key]["R"], "target_tokens": left[key]["complete_actual_tokens"],
        "control_tokens": right[key]["complete_actual_tokens"],
    } for key in sorted(left)]
    n = len(pairs)
    return {
        "comparison": label, "source_version": version, "budget": budget, "n_pairs": n,
        "target_successes": sum(p["target_R"] for p in pairs),
        "control_successes": sum(p["control_R"] for p in pairs),
        "target_wins": sum(p["target_R"] > p["control_R"] for p in pairs),
        "target_losses": sum(p["target_R"] < p["control_R"] for p in pairs),
        "ties": sum(p["target_R"] == p["control_R"] for p in pairs),
        "target_mean_tokens": sum(p["target_tokens"] for p in pairs) / n,
        "control_mean_tokens": sum(p["control_tokens"] for p in pairs) / n,
        "pairs": pairs,
    }

def main():
    rows, sources = extract()
    comparisons = [
        paired(rows, "fixed4_vs_fixed2", "038", "O2", "O1", 500000),
        paired(rows, "I4_vs_I2_250k", "047", "I4", "I2", 250000),
        paired(rows, "I4_vs_S1_250k", "047", "I4", "S1", 250000),
        paired(rows, "P4_vs_P2_250k", "047", "P4", "P2", 250000),
        paired(rows, "P4_vs_S1_250k", "047", "P4", "S1", 250000),
        paired(rows, "I4_vs_S1_500k", "047", "I4", "S1", 500000),
        paired(rows, "P4_vs_S1_500k", "047", "P4", "S1", 500000),
        paired(rows, "P4_vs_S1_Gamma0", "048", "P4", "S1", 500000, "Gamma0", "Gamma0"),
        paired(rows, "P4_vs_S1_Gamma1", "048", "P4", "S1", 500000, "Gamma1", "Gamma1"),
        paired(rows, "P4_Gamma1_vs_Gamma0", "048", "P4", "P4", 500000, "Gamma1", "Gamma0"),
    ]
    groups = defaultdict(list)
    for row in rows:
        if row["is_four_member_target"]:
            groups[row["strategy"]].append(row)
    aggregate = [{
        "strategy": strategy, "n": len(group), "successes": sum(x["R"] for x in group),
        "submissions": sum(x["submitted"] for x in group),
        "complete_actual_tokens": sum(x["complete_actual_tokens"] for x in group),
        "actual_calls": sum(x["actual_calls"] for x in group),
        "prompt_tokens": sum(x["prompt_tokens"] for x in group),
        "completion_tokens": sum(x["completion_tokens"] for x in group),
    } for strategy, group in groups.items()]
    payload = {
        "scope": "28 four-member runs plus 36 controls from the existing three source panels; no new model, tests, private acceptance, or counterfactual replays.",
        "aggregation_warning": "Descriptive historical aggregates; tasks, budget and input representation differ. Use matched comparisons for interpretation.",
        "generated_date": "2026-10-18", "sources": sources,
        "four_member_aggregate": aggregate, "matched_comparisons": comparisons,
        "runs": rows,
    }
    (OUT / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    columns = ["slot_id","strategy","is_four_member_target","root_id","seed","budget",
               "representation","actual_output_members","R","Q","submitted","outcome_class",
               "complete_actual_tokens","prompt_tokens","completion_tokens","actual_calls",
               "member_test_calls","first_fixed_submit_tokens","after_first_submit_tokens",
               "trajectory_path"]
    with (OUT / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"runs": len(rows), "four_member_aggregate": aggregate,
        "matched_comparisons": [{k:v for k,v in item.items() if k != "pairs"} for item in comparisons]},
        ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
