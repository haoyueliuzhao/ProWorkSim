"""Read existing compact evidence; no provider, grader, or runtime operations."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/software-benchmark-v139/coordination-cost-r1"
GROUPS = ("CHIEF", "PIPELINE", "REVIEW", "SPRINT", "MATRIX")
SOURCES = {
    "selection": "artifacts/software-benchmark-v136/cash-excluded-usage-r1/per-task.json",
    "compact_actions": "artifacts/software-benchmark-v133/collaboration-cost-evidence-r1/per-task.json",
    "token_decomposition": "artifacts/software-benchmark-v137/token-causes-r1/summary.json",
}
SETS = {
    "direct_message": {"send_message"},
    "patch_handoff_integration": {"handoff_patch", "integrate_patch", "merge_patch"},
    "task_and_responsibility": {
        "create_task", "claim_task", "return_task", "revise_task", "read_task",
        "declare_dependency", "remove_dependency", "clear_dependency",
        "offer_transfer", "accept_transfer", "decline_transfer", "delegate_task",
    },
    "private_history_workbench": {
        "work_note", "work_todo", "work_search", "work_read",
        "work_history_search", "work_history_read",
    },
    "world_event_readback": {"read_work_event"},
    "publication_delivery": {"fix_patch", "submit_integration", "delivery_status"},
    "public_tests": {"run_tests", "read_test_result"},
    "file_navigation": {
        "read_file", "list_files", "search_file", "search_repository", "diff_workspace",
    },
    "file_edits": {
        "write_file", "replace_file", "create_file", "delete_file", "rename_file",
    },
    "lifecycle": {"staff_done", "staff_wait"},
}
COORDINATION = {
    "direct_message", "patch_handoff_integration", "task_and_responsibility",
    "organization_observation", "organization_governance",
}
HISTORY = {"private_history_workbench", "world_event_readback"}
FIELDS = (
    "dispatched", "explicit_rejections", "successful_responses",
    "request_tokens", "attributed_requests",
)


def read(path: Path):
    return json.loads(path.read_text())


def ref(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def category(tool: str) -> str:
    if tool == "org_status":
        return "organization_observation"
    if tool.startswith("org_"):
        return "organization_governance"
    return next((key for key, values in SETS.items() if tool in values), "other")


def save(name: str, value) -> None:
    path = OUT / name
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def aggregate(operations: dict, labels: set[str], n: int, actions: int, tokens: int) -> dict:
    total = Counter({key: 0 for key in FIELDS})
    for label in labels:
        total.update(operations.get(label, {}))
    return {
        **total, "actions_per_task": total["dispatched"] / n,
        "action_share": total["dispatched"] / actions,
        "whole_request_token_share": total["request_tokens"] / tokens,
    }


def bounded_case() -> dict:
    path = ROOT / (
        "runs/software-benchmark-v131/fixed-organization-50-r1/episodes/9214/"
        "controller-output/controller-result.json"
    )
    assert path.stat().st_size <= 2 * 1024 * 1024
    source = ref(path)
    assert source["sha256"] == "214fae03dcffca59a24a01d20c4247b9329f5af145fb02f0e367eda7ae44a693"
    data = read(path)
    boundary = data["managed_boundary"]
    indices = (7, 8, 9, 10, 70, 72, 79)
    examples = []
    for index in indices:
        outcome = boundary["outcomes"][index]
        decision = outcome["decision"]
        result = outcome["response"]["result"]
        charge = boundary["team_budget"]["model"]["records"][decision["model_call_id"]]
        assert decision["action"] == "read_file" and outcome["response"]["ok"]
        examples.append({
            "outcome_index": index, "member": outcome["worker_id"],
            "arguments": decision["arguments"], "source_reference": result["source_reference"],
            "path": result["path"], "text_sha256": result["text_sha256"],
            "start_character": result["start_character"],
            "end_character": result["end_character"],
            "total_characters": result["total_characters"],
            "whole_request_charged_tokens": charge["charge"]["charged_tokens"],
        })
    initial = examples[:4]
    published = examples[4:]
    assert len({x["text_sha256"] for x in initial}) == 1
    assert len({x["member"] for x in initial}) == 4
    assert len({json.dumps(x["source_reference"], sort_keys=True) for x in published}) == 1
    assert len({x["text_sha256"] for x in published}) == 1
    overlap = min(x["end_character"] for x in published) - max(x["start_character"] for x in published)
    assert overlap == 1948
    return {
        "slot_index": 9214, "instance_id": "pydata__xarray-4966", "source": source,
        "observed": [
            "All four members read xarray/coding/variables.py from their initial private v1; file text hashes are identical, although object identities differ.",
            "Later members 004, 002, and 001 read patch-1's identical source object/version v5. Their returned ranges share 1,948 Unicode characters.",
        ],
        "read_events": examples, "shared_published_range_characters": overlap,
        "inference_boundary": [
            "This is source-bound repeated information acquisition across private contexts, not proof every repeated read is unnecessary.",
            "Independent review can legitimately need the same code. Character overlap is not a tokenizer measurement or a net token-saving estimate.",
            "Request charges include all preceding context and the model's action output; the returned file page enters later requests, not this action's output charge.",
        ],
    }


def main() -> None:
    selection = read(ROOT / SOURCES["selection"])
    selected = {r["slot_id"]: r for r in selection if r["included"]}
    rows = [r for r in read(ROOT / SOURCES["compact_actions"]) if r["slot_id"] in selected]
    decomposition = read(ROOT / SOURCES["token_decomposition"])
    assert len(rows) == len(selected) == 68
    groups = {}
    per_task = []
    for group in GROUPS:
        matching = [r for r in rows if r["group"] == group]
        n = len(matching)
        total_tokens = sum(r["actual_tokens"] for r in matching)
        actions = sum(r["performed_actions"] for r in matching)
        operations = {}
        tool_totals = {}
        call_purposes = Counter()
        rejection_examples = []
        for row in matching:
            assert row["actual_tokens"] == selected[row["slot_id"]]["usage"]["known_tokens"]["total_tokens"]
            assert sum(m["known_actual_tokens"] for m in row["members"].values()) == row["actual_tokens"]
            call_purposes.update(row["calls_by_purpose"])
            task_ops = {}
            for tool, count in row["tool_operations"].items():
                label = category(tool)
                values = {key: count[key] for key in FIELDS}
                operations.setdefault(label, Counter()).update(values)
                task_ops.setdefault(label, Counter()).update(values)
                tool_totals.setdefault(tool, Counter()).update(values)
            for example in row["rejection_examples"]:
                if category(example["tool"]) in COORDINATION:
                    rejection_examples.append(example)
            per_task.append({
                "slot_id": row["slot_id"], "instance_id": row["instance_id"],
                "group": group, "controller_result": row["controller_result"],
                "actual_calls": row["actual_calls"], "actual_tokens": row["actual_tokens"],
                "performed_actions": row["performed_actions"], "categories": task_ops,
                "condenser_tokens": row["condenser_tokens"],
                "S1_same_task_calls": row["S1_PROJECT_calls_same_task"],
                "S1_same_task_tokens": row["S1_PROJECT_tokens_same_task"],
            })
        assert sum(x["dispatched"] for x in operations.values()) == actions
        attributed_tokens = sum(x["request_tokens"] for x in operations.values())
        attributed_calls = sum(x["attributed_requests"] for x in operations.values())
        calls = sum(r["actual_calls"] for r in matching)
        condenser_tokens = sum(r["condenser_tokens"] for r in matching)
        assert attributed_calls <= calls and attributed_tokens + condenser_tokens <= total_tokens
        cached = sum(selected[r["slot_id"]]["usage"]["known_tokens"]["cache_hit_tokens"] for r in matching)
        comparison = decomposition["groups"][group]
        assert comparison["n"] == n
        assert math.isclose(comparison["team_mean_tokens"]["total_tokens"], total_tokens / n, rel_tol=1e-15)
        old_actions = sum(r["collaboration_operations"] for r in matching)
        old_tokens = sum(r["collaboration_request_tokens"] for r in matching)
        new_coordination = aggregate(operations, COORDINATION, n, actions, total_tokens)
        read_task = tool_totals.get("read_task", Counter())
        assert new_coordination["dispatched"] - old_actions == read_task["dispatched"]
        assert new_coordination["request_tokens"] - old_tokens == read_task["request_tokens"]
        groups[group] = {
            "n": n, "members_count": matching[0]["member_count"],
            "actual_calls": calls, "actual_tokens": total_tokens,
            "performed_actions": actions, "calls_by_purpose": call_purposes,
            "cached_input_tokens": cached, "roles_and_member_usage": comparison["members"],
            "direct_messages": aggregate(operations, {"direct_message"}, n, actions, total_tokens),
            "coordination": new_coordination,
            "original_v133_collaboration_definition": {
                "dispatched": old_actions, "action_share": old_actions / actions,
                "request_tokens": old_tokens, "whole_request_token_share": old_tokens / total_tokens,
            },
            "coordination_definition_delta": {
                "added_tools": ["read_task"], "removed_tools": [],
                "dispatched_delta": read_task["dispatched"],
                "request_tokens_delta": read_task["request_tokens"],
                "history_only_reclassification_not_in_coordination": {
                    key: tool_totals.get(key, {}) for key in ("work_history_search", "work_history_read")
                },
            },
            "history": aggregate(operations, HISTORY, n, actions, total_tokens),
            "coordination_plus_history": aggregate(operations, COORDINATION | HISTORY, n, actions, total_tokens),
            "categories": {key: aggregate(operations, {key}, n, actions, total_tokens) for key in operations},
            "tool_totals": tool_totals,
            "whole_request_attribution_reconciliation": {
                "action_attributed_calls": attributed_calls,
                "action_attributed_tokens": attributed_tokens,
                "condenser_calls": call_purposes["condenser"],
                "condenser_tokens": condenser_tokens,
                "non_action_agent_calls": calls - attributed_calls - call_purposes["condenser"],
                "non_action_agent_tokens": total_tokens - attributed_tokens - condenser_tokens,
            },
            "S1_same_task_comparison": {
                key: comparison[key] for key in (
                    "team_mean_tokens", "S1_mean_tokens", "team_mean_calls", "S1_mean_calls",
                    "call_count_factor", "mean_team_input_per_call", "mean_S1_input_per_call",
                    "mean_total_tokens_per_call_factor", "total_token_factor", "input_fraction",
                    "output_fraction", "condenser_fraction", "code_passed", "S1_code_passed_same_tasks",
                )
            },
            "coordination_rejection_examples_from_compact_summary": rejection_examples,
            "rejection_examples_are_not_an_exhaustive_reason_census": True,
        }
    OUT.mkdir(parents=True, exist_ok=True)
    case = bounded_case()
    save("bounded-shared-read-case.json", case)
    save("per-task.json", per_task)
    save("summary.json", {
        "version": "v139-explicit-coordination-whole-request-attribution-r1",
        "created_UTC": datetime.now(timezone.utc).isoformat(),
        "sources": {key: ref(ROOT / path) for key, path in SOURCES.items()},
        "script": ref(Path(__file__)), "selected_tasks": len(rows), "groups": groups,
        "classification": {
            "explicit_sets": {key: sorted(value) for key, value in SETS.items()},
            "organization_observation": "org_status",
            "organization_governance": "remaining org_* tools",
            "coordination_categories": sorted(COORDINATION), "history_categories": sorted(HISTORY),
            "change_from_v133": "read_task is task/coordination; work_history_search/read are history, previously falling under other; old artifacts remain unchanged.",
        },
        "interpretation": [
            "Retain exactly the v136 68 officially scored non-cash-cutoff tasks. Groups have different selected task subsets; each S1 comparison uses its identical tasks.",
            "Dispatched counts are managed action_performed events, including business rejections. Successful send_message responses are separate from attempted message actions.",
            "Whole-request attributed tokens are the full settled prompt plus output of the request selecting that action, not message text tokens, not net communication cost, and not a causal share of the increase.",
            "The action's returned feedback/page enters later requests. Received messages, repeated repository state, tool descriptions and prior dialogue can be carried by subsequent non-coordination requests. No exact marginal/context-segment token measurement is claimed.",
            "Coordination plus history is a descriptive broader category; private notes and history readback are not necessarily inter-member communication.",
            "Observed private-context reacquisition, version handoff and organization procedures are mechanisms that consume the same 5M team pool. The additional calls are an accounting result, not a complete causal explanation.",
            "No matched member-count-only or no-communication ablation exists. Role configurations, task subsets and implementation versions differ; two versus four members is not a causal estimate.",
            "Cache hits remain actual input tokens under the token budget while price differs. Request-token attribution is not monetary attribution; no history costs are removed.",
        ],
        "bounded_case": ref(OUT / "bounded-shared-read-case.json"),
        "new_provider_calls": 0, "new_tests_or_grading": 0, "Docker_operations": 0,
    })
    print(json.dumps({"output": str(OUT), "summary": ref(OUT / "summary.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
