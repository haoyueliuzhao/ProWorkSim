"""Condense saved work diagnostics by predeclared run/window/task, without scoring."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from proworksim.storage import digest, json_bytes


def summarize(diagnostics_path, study_path):
    diagnostics_path, study_path = Path(diagnostics_path), Path(study_path)
    raw = json.loads(diagnostics_path.read_bytes())
    study = json.loads(study_path.read_bytes())
    planned = {}
    protocols = []
    for job in study["jobs"]:
        path = Path(job["protocol"])
        protocol = json.loads(path.read_bytes())
        protocols.append({"path": str(path), "sha256": digest(path.read_bytes())})
        ordinal = 0
        for index, window in enumerate(protocol["windows"]):
            for slot_index, slot in enumerate(window["slots"]):
                episode = Path(job["run"]) / f"online/window-{index}/collection/slot-{slot_index}/episode"
                planned[str(episode.resolve())] = {
                    "run": job["name"], "condition": protocol["condition"], "seed_index": protocol["replicate_index"],
                    "mode": window["mode"], "window_id": window["window_id"],
                    "training_window_ordinal": ordinal if window["mode"] == "online" else None,
                    "case_id": slot["case_id"], "task": slot["case_id"].rsplit("-", 1)[-1],
                }
            if window["mode"] == "online":
                ordinal += 1
    if set(planned) != {row["episode_path"] for row in raw["episodes"]}:
        raise ValueError("Diagnostics must account for every exact predeclared study slot once")
    details, compact, by_mode, totals, samples = {}, {}, {}, Counter(), defaultdict(list)

    def collect(table, key, row, meta):
        block = table.setdefault(key, {**meta, "planned": 0, "closed_verified": 0, "unknown": 0,
                                       "original_reward_histogram": Counter(), "facts": {}})
        block["planned"] += 1
        block[row["status"]] += 1
        if row["status"] != "closed_verified":
            return
        reward = row.get("original_reward")
        block["original_reward_histogram"][str(reward["reward"]) if reward else "unknown"] += 1
        for fact, value in row["work"]["summary"].items():
            counts = block["facts"].setdefault(fact, {"true": 0, "false": 0, "unknown": 0, "integer_sum": 0})
            if type(value) is bool:
                counts[str(value).lower()] += 1
            elif type(value) is int:
                counts["integer_sum"] += value
            else:
                counts["unknown"] += 1

    def sample(category, row, evidence):
        if len(samples[category]) < 2:
            samples[category].append({"episode_path": row["episode_path"], "episode_id": row["episode_id"],
                                      "manifest_sha256": row["manifest_sha256"], "case_id": row["case_id"],
                                      "original_terminal_reward": row["original_reward"]["reward"] if row["original_reward"] else None,
                                      "evidence": evidence})

    for row in raw["episodes"]:
        meta = planned[row["episode_path"]]
        totals[meta["mode"] + ":planned"] += 1
        totals[meta["mode"] + ":" + row["status"]] += 1
        collect(details, (meta["run"], meta["window_id"], meta["task"]), row, meta)
        collect(compact, (meta["condition"], meta["mode"], meta["task"]), row,
                {key: meta[key] for key in ("condition", "mode", "task")})
        collect(by_mode, (meta["mode"], meta["task"]), row, {key: meta[key] for key in ("mode", "task")})
        if row["status"] != "closed_verified":
            continue
        work = row["work"]
        for write in work["writes"]:
            if write["alias"] == "code" and write["sql_program_changed"]:
                sample("actual_sql_text_change", row, write)
            if write["alias"] == "result":
                sample("manual_result_write", row, write)
        for read in work["reads"]:
            if read.get("matches_world_fixed_version_at_read") is False:
                sample("actual_fixed_version_mismatch", row, read)
        for judgment in work["review_judgments"]:
            if not judgment["evidence_complete_before_action"]:
                sample("actual_judgment_without_complete_consumed_evidence", row, judgment)
        for repair in work["feedback_obligation_repairs"]:
            if repair["repairs"]:
                sample("actual_specific_obligation_recovery", row, repair)
    return {
        "version": "study-work-summary-v0.14", "counts": dict(totals),
        "raw_diagnostics": {"path": str(diagnostics_path), "sha256": digest(diagnostics_path.read_bytes()),
                            "diagnostic_script_sha256": raw["analysis_script_sha256"]},
        "study": {"path": str(study_path), "sha256": digest(study_path.read_bytes())}, "protocols": protocols,
        "summary_script_sha256": digest(Path(__file__).read_bytes()),
        "by_mode_task": list(by_mode.values()), "by_condition_mode_task": list(compact.values()),
        "by_run_window_task": list(details.values()), "illustrative_original_events": dict(samples),
        "sample_selection": "First two observed event records per category in the declared run/slot/event order; full factual counts retain every closed episode. These examples were not used for training selection.",
        "scope": "264 closed episodes are descriptive work evidence from a prematurely stopped study, not a complete learning curve or an MC-vs-RTG benefit comparison. Unequal surviving training windows must not be treated as matched final checkpoints. No final locked evaluation exists in this run.",
        "outcome_rule": "Original terminal R/components are copied. SQL text changes, current-code execution, fixed-version reads and specific prerequisite recovery do not by themselves establish business correctness. Missing slots/rewards remain unknown, never scored zero.",
        "causal_limit": "Feedback membership proves that the actual request included the exact earlier tool message. Subsequent exact adoption/version execution establishes a factual prerequisite repair; it does not establish the internal reason the model chose it.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics", required=True, type=Path)
    parser.add_argument("--study", default=Path("examples/learning-v14/study.json"), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = summarize(args.diagnostics, args.study)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as file:
        file.write(json_bytes(result))
    print(json.dumps(result["counts"]))


if __name__ == "__main__":
    main()
