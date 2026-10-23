#!/usr/bin/env python3
"""Derive fixed-panel results without modifying original experimental records.

Reads only queue metadata, small candidate locks, frozen reconciliation metadata,
and provider usage/cost columns. Never opens candidate bundles or model messages.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts/software-benchmark-v055/final-result-analysis-r1"


def json_read(path, expected=None):
    path = Path(path)
    data = path.read_bytes()
    if expected and expected.get("sha256"):
        assert hashlib.sha256(data).hexdigest() == expected["sha256"], str(path)
    return json.loads(data)


def read_ref(ref):
    return json_read(ref["path"], ref)


def file_ref(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def write_csv(path, rows):
    fields = sorted({key for row in rows for key in row})
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def endpoint_scores(row):
    scores = row.get("scores", {})
    if isinstance(scores, dict):
        return scores
    output = {}
    for score in scores:
        name = Path(score["request"]["path"]).name
        endpoint = {"official-code-request.json": "code", "official-delivery-request.json": "delivery"}[name]
        assert endpoint not in output
        output[endpoint] = score
    return output


def counts(rows):
    code = Counter(row["code_outcome"] for row in rows)
    n = len(rows)
    success = code["resolved_true"]
    failure = code["resolved_false"]
    unknown = n - success - failure
    return {
        "planned": n,
        "code_success": success,
        "code_definite_failure": failure,
        "generation_unknown": code["generation_unknown"],
        "code_scoring_unknown": code["scoring_unknown"],
        "code_unknown_total": unknown,
        "success_lower_bound": success / n,
        "success_upper_bound": (success + unknown) / n,
        "bounds_type": "logical_missing_outcome_bounds_not_confidence_intervals",
    }


def project_counts(rows):
    code = Counter(row["code_outcome"] for row in rows)
    delivery = Counter(row["delivery_outcome"] for row in rows)
    relation = Counter(row["delivery_version_relation"] for row in rows)
    code_success = [row for row in rows if row["code_outcome"] == "resolved_true"]
    success_relation = Counter(row["delivery_version_relation"] for row in code_success)
    cross = Counter((row["code_outcome"], row["delivery_outcome"], row["delivery_version_relation"]) for row in rows)
    success = delivery["resolved_true"]
    unknown = delivery["generation_unknown"] + delivery["scoring_unknown"]
    return {
        "planned": len(rows),
        "code": dict(code),
        "delivery": dict(delivery),
        "legal_submission_exists": sum(row["legal_submission_exists"] is True for row in rows),
        "version_relation": dict(relation),
        "code_success_version_relation": dict(success_relation),
        "code_success_without_legal_same_final_version": sum(
            row["delivery_version_relation"] != "same_tree_same_source_version" for row in code_success
        ),
        "delivery_success_lower_bound": success / len(rows),
        "delivery_success_upper_bound": (success + unknown) / len(rows),
        "delivery_unknown_total": unknown,
        "cross_table": [
            {"code_outcome": key[0], "delivery_outcome": key[1], "version_relation": key[2], "count": value}
            for key, value in sorted(cross.items())
        ],
        "no_legal_submission_is_observed_delivery_failure_only_after_trusted_candidate_close": True,
    }


def boolean_outcome(row):
    return {"resolved_true": 1, "resolved_false": 0}.get(row["code_outcome"])


def paired(first, second):
    assert set(first) == set(second)
    cells = Counter()
    repository = defaultdict(list)
    lower = upper = 0
    for instance in sorted(first):
        a, b = boolean_outcome(first[instance]), boolean_outcome(second[instance])
        cells[f"{a if a is not None else 'unknown'}_{b if b is not None else 'unknown'}"] += 1
        row_min = (0 if b is None else b) - (1 if a is None else a)
        row_max = (1 if b is None else b) - (0 if a is None else a)
        lower += row_min
        upper += row_max
        repository[first[instance]["repo"]].append((a, b, row_min, row_max))
    both_known = sum(cells[f"{a}_{b}"] for a in (0, 1) for b in (0, 1))
    repo_rows = []
    for repo, rows in sorted(repository.items()):
        rc = Counter(f"{a if a is not None else 'unknown'}_{b if b is not None else 'unknown'}" for a, b, _, _ in rows)
        repo_rows.append({"repo": repo, "planned": len(rows), "pair_cells_A_B": dict(rc),
                          "delta_B_minus_A_lower_pp": 100 * sum(x[2] for x in rows) / len(rows),
                          "delta_B_minus_A_upper_pp": 100 * sum(x[3] for x in rows) / len(rows)})
    return {
        "planned_pairs": len(first),
        "pair_cells_A_B": dict(sorted(cells.items())),
        "both_known": both_known,
        "A_only_success_on_known_pairs": cells["1_0"],
        "B_only_success_on_known_pairs": cells["0_1"],
        "both_success": cells["1_1"],
        "both_failure": cells["0_0"],
        "conditional_known_pair_delta_B_minus_A_pp_auxiliary": (
            100 * (cells["0_1"] - cells["1_0"]) / both_known if both_known else None
        ),
        "full_panel_delta_B_minus_A_lower_pp": 100 * lower / len(first),
        "full_panel_delta_B_minus_A_upper_pp": 100 * upper / len(first),
        "bounds_type": "logical_missing_outcome_bounds_not_confidence_intervals",
        "repository_strata": repo_rows,
    }


def attach_provider_accounting(rows, database):
    by_slot = {row["slot_id"]: row for row in rows if row["model_family"] == "deepseek"}
    accumulator = defaultdict(Counter)
    unmatched = defaultdict(Counter)
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    query = """SELECT slot_id, condition, status, reserved_nanoyuan,
                      settled_nanoyuan, usage_json FROM requests"""
    for slot, condition, status, reserved, settled, usage_text in connection.execute(query):
        out = accumulator[slot] if slot in by_slot else unmatched[condition]
        out["requests"] += 1
        out[f"request_status_{status}"] += 1
        out["settled_nanoyuan"] += settled or 0
        if status != "settled":
            out["unsettled_reserved_nanoyuan"] += reserved or 0
        if usage_text:
            usage = json.loads(usage_text)
            out["requests_with_usage"] += 1
            for name in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                out[name] += usage.get(name, 0) or 0
        else:
            out["requests_without_usage"] += 1
    for slot, amount in connection.execute(
        "SELECT r.slot_id, a.amount_nanoyuan FROM budget_adjustments a JOIN requests r ON r.request_id=a.request_id"
    ):
        assert slot in by_slot
        accumulator[slot]["adjustment_hold_nanoyuan"] += amount
    connection.rollback()
    connection.close()
    for slot, row in by_slot.items():
        for name, value in accumulator[slot].items():
            row[f"provider_{name}"] = value
    group_accum = defaultdict(Counter)
    for slot, counter in accumulator.items():
        group_accum[by_slot[slot]["group"]].update(counter)
    output = {}
    for group, counter in sorted(group_accum.items()):
        output[group] = dict(counter)
        output[group]["settled_cny"] = counter["settled_nanoyuan"] / 1e9
        output[group]["committed_cny"] = (
            counter["settled_nanoyuan"] + counter["unsettled_reserved_nanoyuan"] + counter["adjustment_hold_nanoyuan"]
        ) / 1e9
    return {"groups": output, "noncanonical_preparation_requests": {k: dict(v) for k, v in sorted(unmatched.items())},
            "basis": "one read-only SQLite transaction; provider-reported usage only; missing usage remains unknown",
            "database_path": str(database), "revision_recovery_calls_share_original_slot_ids": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--controller-summary", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ("slot-results.csv", "summary.json", "paired-comparisons.json", "repository-strata.csv", "project-delivery.json", "provider-accounting.json"):
        assert not (output / name).exists(), f"immutable output already exists: {name}"
    source = ROOT / "artifacts/software-benchmark-v055/exception-reconciliation-r1/final-summary.json"
    final = json_read(source)
    primary = {family: read_ref(final["evidence"][f"{family}_primary"]) for family in ("qwen", "deepseek")}
    preentry = read_ref(final["evidence"]["preentry"])
    recovered_generation = {row["slot_id"]: row for row in preentry["generation_rows"]}
    assert len(recovered_generation) == 6
    corrections = {(row["slot_id"], row["endpoint"]): row for row in final["score_corrections"]}
    assert len(corrections) == len(final["score_corrections"]) == 25
    public_path = ROOT / "artifacts/software-benchmark-v054/source/public-tasks.json"
    public = {row["instance_id"]: row for row in json_read(public_path)}
    assert len(public) == 500
    rows = []
    used_corrections = set()
    for family, state in primary.items():
        for original in state["rows"]:
            slot = original["slot"]
            slot_id = slot["slot_id"]
            generation = original["generation"]
            effective_generation = recovered_generation.get(slot_id, generation)
            group = family + ":" + (slot["condition_id"] if family == "deepseek" else slot["arm"])
            row = {
                "slot_id": slot_id, "instance_id": slot["instance_id"], "repo": public[slot["instance_id"]]["repo"],
                "model_family": family, "group": group, "arm": slot["arm"],
                "thinking": slot.get("thinking"), "seed": slot["seed"],
                "seed_transmitted_to_provider": slot.get("provider_seed_supported") if family == "deepseek" else None,
                "original_generation_status": generation["status"], "generation_status": effective_generation["status"],
                "generation_revision": "pre-entry-recovery-r1" if slot_id in recovered_generation else "original_primary",
                "generation_result_path": effective_generation.get("result", {}).get("path"),
                "delivery_outcome": "not_applicable", "delivery_version_relation": "not_applicable",
                "legal_submission_exists": None,
            }
            scores = endpoint_scores(original)
            for endpoint in ("code", "delivery"):
                score = scores.get(endpoint, {})
                correction = corrections.get((slot_id, endpoint))
                if correction:
                    used_corrections.add((slot_id, endpoint))
                    score = {"status": "official_report", "resolved": correction["resolved"]}
                row[f"{endpoint}_score_revision"] = correction["recovery_source"] if correction else "original_primary"
                row[f"{endpoint}_score_status"] = score.get("status", "not_created")
                if endpoint == "delivery" and slot["arm"] != "PROJECT":
                    row["delivery_score_status"] = "not_applicable"
                    continue
                if score.get("status") == "official_report":
                    assert isinstance(score.get("resolved"), bool)
                    row[f"{endpoint}_outcome"] = "resolved_true" if score["resolved"] else "resolved_false"
                elif effective_generation["status"] == "technical_unknown":
                    row[f"{endpoint}_outcome"] = "generation_unknown"
                else:
                    assert effective_generation["status"] == "closed", slot_id
                    row[f"{endpoint}_outcome"] = "scoring_unknown"
            if slot["arm"] == "PROJECT":
                row["delivery_version_relation"] = "generation_unknown"
                if effective_generation["status"] == "closed":
                    result = read_ref(effective_generation["result"])
                    candidate = read_ref(result["candidate"])
                    assert candidate["task_id"] == slot["instance_id"]
                    assert candidate["locked_before_grading"] is True
                    terminal = read_ref(candidate["terminal_code"])
                    row["candidate_lock_path"] = result["candidate"]["path"]
                    row["terminal_tree_sha256"] = terminal["tree_sha256"]
                    row["terminal_source_object_id"] = terminal["source_reference"]["object_id"]
                    row["terminal_source_version_id"] = terminal["source_reference"]["version_id"]
                    legal_ref = candidate["last_legal_delivery"]
                    row["legal_submission_exists"] = legal_ref is not None
                    assert bool(candidate["submitted"]) == row["legal_submission_exists"]
                    if legal_ref:
                        legal = read_ref(legal_ref)
                        row["legal_tree_sha256"] = legal["tree_sha256"]
                        row["legal_source_object_id"] = legal["source_reference"]["object_id"]
                        row["legal_source_version_id"] = legal["source_reference"]["version_id"]
                        same_tree = terminal["tree_sha256"] == legal["tree_sha256"]
                        same_version = terminal["source_reference"] == legal["source_reference"]
                        row["same_tree"] = same_tree
                        row["same_source_version"] = same_version
                        assert same_tree == candidate["same_tree"]
                        assert not same_version or same_tree
                        row["delivery_version_relation"] = (
                            "same_tree_same_source_version" if same_tree and same_version
                            else "same_tree_different_source_version" if same_tree else "different_tree"
                        )
                    else:
                        assert row["delivery_score_status"] == "not_created"
                        row["delivery_version_relation"] = "no_legal_submission"
                        row["delivery_outcome"] = "no_legal_submission"
            rows.append(row)
    assert used_corrections == set(corrections)
    assert len(rows) == len({row["slot_id"] for row in rows}) == 4500
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["group"]].append(row)
    assert len(grouped) == 9
    summary_groups = {}
    repositories = []
    delivery_groups = {}
    for group, members in sorted(grouped.items()):
        assert len(members) == 500
        assert {row["instance_id"] for row in members} == set(public)
        result = counts(members)
        expected = final["groups"][group]["derived_reconciled"]
        assert result["code_success"] == expected["observed_resolved_code"], group
        assert result["generation_unknown"] == expected["generation"].get("technical_unknown", 0), group
        assert result["code_scoring_unknown"] == expected["code_score"].get("technical_unknown", 0), group
        assert result["code_success"] + result["code_definite_failure"] == expected["code_score"]["official_report"], group
        summary_groups[group] = result
        for repo in sorted({row["repo"] for row in members}):
            repositories.append({"group": group, "repo": repo, **counts([row for row in members if row["repo"] == repo])})
        if members[0]["arm"] == "PROJECT":
            delivery_groups[group] = project_counts(members)
            assert delivery_groups[group]["delivery"].get("resolved_true", 0) == expected["observed_resolved_delivery"]
    pairs = {}
    for family, suffix in (("qwen", ""), ("deepseek", "-nonthinking"), ("deepseek", "-thinking")):
        for arm_a, arm_b in (("REF", "MATCH"), ("MATCH", "PROJECT"), ("REF", "PROJECT")):
            group_a, group_b = family + ":" + arm_a + suffix, family + ":" + arm_b + suffix
            pairs[f"{group_b} minus {group_a}"] = {"group_A": group_a, "group_B": group_b, **paired(
                {row["instance_id"]: row for row in grouped[group_a]},
                {row["instance_id"]: row for row in grouped[group_b]})}
    for arm in ("REF", "MATCH", "PROJECT"):
        group_a, group_b = f"deepseek:{arm}-nonthinking", f"deepseek:{arm}-thinking"
        pairs[f"{group_b} minus {group_a}"] = {"group_A": group_a, "group_B": group_b, **paired(
            {row["instance_id"]: row for row in grouped[group_a]},
            {row["instance_id"]: row for row in grouped[group_b]})}
    provider = attach_provider_accounting(rows, ROOT / "runs/software-benchmark-v055/budget-r1/ledger.sqlite3")
    settled = sum(x["settled_nanoyuan"] for x in provider["groups"].values()) + sum(x["settled_nanoyuan"] for x in provider["noncanonical_preparation_requests"].values())
    assert abs(settled / 1e9 - final["ledger"]["settled_cny"]) < 1e-8
    controller_ref = None
    qwen_token_accounting = {}
    if args.controller_summary:
        controllers = json_read(args.controller_summary)
        controller_ref = file_ref(args.controller_summary)
        # Peer-produced small metadata is joined by immutable original slot ID.
        controller_rows = controllers["rows"]
        by_slot = {row["slot_id"]: row for row in rows}
        for item in controller_rows:
            target = by_slot[item["slot_id"]]
            for key in ("tokens", "complete_tokens", "known_actual_tokens", "complete_actual_tokens", "charged_tokens", "held_tokens", "uncertain_reserved_tokens", "attempts", "decisions", "integrity_failure", "all_charges_reported_actual_trace", "known_reported_actual_tokens"):
                if key in item:
                    target[f"controller_{key}"] = item[key]
        for group, members in grouped.items():
            if not group.startswith("qwen:"):
                continue
            with_metadata = [row for row in members if "controller_tokens" in row]
            qwen_token_accounting[group] = {
                "planned": len(members),
                "normal_closed_slots_with_metadata": len(with_metadata),
                "other_slots_not_included": len(members) - len(with_metadata),
                "normal_closed_ledger_tokens": sum(row["controller_tokens"] for row in with_metadata),
                "normal_closed_attempts": sum(row["controller_attempts"] for row in with_metadata),
                "normal_closed_decisions": sum(row["controller_decisions"] for row in with_metadata),
                "scope": "normal closed controller metadata only; generation technical unknown costs excluded rather than assumed zero",
            }
            if group.endswith(":PROJECT"):
                qwen_token_accounting[group]["normal_closed_known_reported_actual_tokens"] = sum(
                    row["controller_known_reported_actual_tokens"] for row in with_metadata
                )
                qwen_token_accounting[group]["zero_attempt_zero_charge_slots"] = sum(
                    row["controller_attempts"] == 0 and row["controller_charged_tokens"] == 0 for row in with_metadata
                )
                qwen_token_accounting[group]["all_nonempty_charges_have_reported_actual_trace"] = all(
                    row["controller_all_charges_reported_actual_trace"]
                    for row in with_metadata if row["controller_attempts"] > 0
                )
                qwen_token_accounting[group]["held_tokens"] = sum(row["controller_held_tokens"] for row in with_metadata)
            else:
                qwen_token_accounting[group]["normal_closed_known_actual_tokens"] = sum(row["controller_tokens"] for row in with_metadata)
    # Queue runtime strata remain descriptive; their old score counters are not
    # reused after independently reconciled scores have been applied above.
    runtime = {
        "qwen_mixed_runtime_revisions": primary["qwen"].get("mixed_runtime_revisions"),
        "qwen_cross_revision_full_panel_estimate_allowed_in_primary": primary["qwen"].get("cross_revision_full_panel_estimate_allowed"),
        "qwen_original_binding_strata": [
            {"bindings": item["bindings"], "planned_slots_in_revision": item["planned_slots_in_revision"],
             "arms": {arm: values["planned_slots_in_revision"] for arm, values in item["arms"].items()}}
            for item in primary["qwen"].get("runtime_revision_progress", {}).values()
        ],
        "interpretation": "This original binding stratification is retained; pooled counts across runtime revisions are descriptive reconciled inventory, not a homogeneous frozen-configuration score.",
    }
    total = counts(rows)
    for key in ("success_lower_bound", "success_upper_bound", "bounds_type"):
        del total[key]
    summary = {
        "version": "nine-condition-fixed-panel-analysis-v055-r1",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "source_final_summary": file_ref(source), "source_evidence": final["evidence"],
        "public_tasks": file_ref(public_path), "script": file_ref(__file__), "controller_metadata": controller_ref,
        "planned_original_slots": len(rows), "distinct_tasks": len(public), "distinct_repositories": len({row["repo"] for row in rows}),
        "groups": summary_groups, "total_counts_only_not_a_mixed_condition_rate": total,
        "project_delivery": delivery_groups, "provider_accounting": provider,
        "qwen_token_accounting": qwen_token_accounting,
        "runtime_provenance": runtime,
        "original_primary_records_modified": False, "entered_model_episodes_replayed": 0,
        "separately_identified_zero_model_preentry_recoveries": 6,
        "score_corrections_applied_exactly_once": len(corrections),
        "confidence_intervals": None,
        "interpretation": [
            "The 500 tasks form the fixed full SWE-bench Verified test panel; these are finite-panel descriptive results.",
            "Bounds allow each technical unknown to be either success or failure; they are not confidence intervals.",
            "Conditional known-pair comparisons are auxiliary and cannot replace the full 500-task estimand.",
            "One entered-model episode per original slot does not identify run-to-run variance.",
            "Repository generalization or bootstrap intervals require additional population/sampling assumptions; none are asserted here.",
            "Technical and runtime revisions remain linked to original slots; reconciled measurements do not erase original unknown records.",
            "No legal submission after trusted candidate close is an observed project delivery failure; generation unknown is not silently failed.",
            "Provider amounts are usage-ledger costs; missing actual usage and retained reservations are distinct from settled charges.",
        ],
    }
    rows.sort(key=lambda row: (row["group"], row["instance_id"]))
    write_csv(output / "slot-results.csv", rows)
    write_csv(output / "repository-strata.csv", repositories)
    write_json(output / "project-delivery.json", delivery_groups)
    write_json(output / "paired-comparisons.json", pairs)
    write_json(output / "provider-accounting.json", provider)
    write_json(output / "summary.json", summary)
    print(json.dumps({"output": str(output), "slots": len(rows), "groups": summary_groups, "project_delivery": delivery_groups}, ensure_ascii=False))


if __name__ == "__main__":
    main()
