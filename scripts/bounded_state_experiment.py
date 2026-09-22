"""E3: bounded, deduplicated component-state exploration against a tiny ledger.

The reference uses numbered editions, document counters and decision tuples. It
never imports the system under test to calculate expected permission or effects.
This is not a filesystem/adapter test or an enumeration of every action path.
"""

import argparse
import copy
import hashlib
import json
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core import conditions, work
from proworksim.storage import atomic_write, json_bytes

BOUNDARY = {
    "roles": ["owner", "reviewer"],
    "work_nodes": ["A", "B"],
    "dependency_edges": [["A", "B"]],
    "artifacts": ["doc-A", "doc-B"],
    "maximum_work_editions": 3,
    "maximum_artifact_versions": 3,
    "maximum_sequence_length": 4,
    "initial_checkpoints": ["clear", "waiting_for_evidence"],
    "actions": ["submit", "withdraw", "approve", "revise", "reply", "edit"],
    "scope": "in-memory core.work/core.conditions; edit is explicit external metadata input",
    "excluded": ["filesystem", "tool adapters", "new request creation", "arbitrary roles/graphs"],
    "coverage": "unique reachable state representatives plus all generated outgoing attempts below depth 4; not all paths",
}


@dataclass
class Ledger:
    # editions[node] is a list of submission lists; each submission is
    # (pinned_document_number, decision, answer). Decisions are P/W/A/X.
    editions: dict = field(default_factory=lambda: {"A": [[]], "B": [[]]})
    documents: dict = field(default_factory=lambda: {"A": 1, "B": 1})
    # The only preregistered conditions attach to edition 1: O/R/S.
    requests: dict = field(default_factory=dict)
    responses: set = field(default_factory=set)

    def current(self, node):
        return len(self.editions[node])

    def accepted(self, node):
        entries = self.editions[node][-1]
        return bool(entries) and entries[-1][1] == "A"

    def ready(self, node):
        return node == "A" or self.accepted("A")

    def apply(self, action):
        """Independent specification; no UUT queries and no cached status strings."""
        kind, node, edition, actor, version, variant = action
        if kind == "reply":
            key = f"reply:{node}:{variant}"
            if key in self.responses:
                return "allowed"
            if node not in self.requests or self.requests[node] != "O" or self.current(node) != 1:
                return "no_satisfaction"
            if variant != "valid":
                return "no_satisfaction"
            self.requests[node] = "R"
            self.responses.add(key)
            return "allowed"
        if kind == "revise":
            if actor != "reviewer":
                return "authority"
            # Revision explicitly accepts aliases, matching the published contract.
            previous = self.editions[node][-1]
            if previous and previous[-1][1] == "P":
                pin, _, answer = previous[-1]
                previous[-1] = (pin, "X", answer)
            self.editions[node].append([])
            if self.requests.get(node) == "O":
                self.requests[node] = "S"
            return "allowed"
        if kind == "edit":
            self.documents[node] += 1
            return "allowed"
        if edition != self.current(node):
            return "old_work"
        if actor != ("reviewer" if kind == "approve" else "owner"):
            return "authority"
        entries = self.editions[node][-1]
        last = entries[-1][1] if entries else None
        if kind == "submit":
            if last in {"P", "A"} or (edition == 1 and self.requests.get(node) == "O"):
                return "not_enabled"
            if not self.ready(node):
                return "dependencies"
            if version > self.documents[node]:
                return "unknown_version"
            entries.append((version, "P", f"answer-{node}-{edition}"))
            return "allowed"
        if kind == "approve" and not self.ready(node):
            return "dependencies"
        if last != "P" or variant == "wrong_submission":
            return "not_pending"
        pin, _, answer = entries[-1]
        if kind == "approve":
            if pin != self.documents[node]:
                return "obsolete_artifact"
            entries[-1] = (pin, "A", answer)
        else:
            entries[-1] = (pin, "W", answer)
        return "allowed"

    def projection(self):
        return {
            "editions": self.editions,
            "documents": self.documents,
            "requests": self.requests,
            "responses": sorted(self.responses),
        }


def work_id(node, edition):
    return node if edition == 1 else f"{node}@r{edition}"


def initial(waiting=False):
    state = {
        "schema_version": "0.5",
        "clock": 10,
        "roles": [{"role_id": x} for x in BOUNDARY["roles"]],
        "organization": {
            "grants": [
                {"actor_id": "reviewer", "power": "approve", "subject": "deliverable"},
                {"actor_id": "reviewer", "power": "revise_requirement", "subject": "*"},
            ]
        },
        "artifacts": {},
        "work_items": {},
        "work_replacements": {},
        "condition_specs": {},
        "condition_responses": {},
        "requests": {},
        "messages": [],
        "blockers": {},
        "events": [],
    }
    ref = Ledger(requests={x: "O" for x in ("A", "B")} if waiting else {})
    for node in ("A", "B"):
        aid = f"doc-{node}"
        state["artifacts"][aid] = {
            "current_version": "v1",
            "versions": {
                "v1": {
                    "logical_time": 0,
                    "sha256": f"{aid}-1",
                    "status": "draft",
                    "review_status": "unreviewed",
                }
            },
        }
        state["work_items"][node] = {
            "work_item_id": node,
            "node_id": node,
            "owner_role": "owner",
            "requirement_version": 1,
            "requirements": {"edition": 1},
            "status": "blocked" if waiting else "open",
            "dependencies": ["A"] if node == "B" else [],
            "deliverables": [aid, "answer"],
            "required_credentials": [],
            "submissions": [],
            "blocker_ids": [],
        }
        if waiting:
            cid, rid = f"condition-{node}", f"request-{node}"
            state["condition_specs"][cid] = {
                "condition_id": cid,
                "work_item_id": node,
                "requirement_version": 1,
                "request_id": rid,
                "providers": ["reviewer"],
                "status": "open",
                "purpose": "support",
                "evidence_spec": {
                    "kind": "version",
                    "reference": {"artifact_id": aid, "version_id": "v1"},
                },
                "history": [{"at": 10, "status": "open", "event": "created"}],
            }
            state["messages"].append(
                {
                    "message_id": rid,
                    "sender": "owner",
                    "recipients": ["reviewer"],
                    "work_item_id": node,
                }
            )
            state["requests"][rid] = {
                "work_item_id": node,
                "requirement_version": 1,
                "requested_role": "reviewer",
                "evidence_reference": {"artifact_id": aid, "version_id": "v1"},
            }
    return state, ref


def actions(ref):
    """Same predeclared alphabet, pruned only at object/version bounds."""
    for node in ("A", "B"):
        edition = ref.current(node)
        for kind in ("submit", "withdraw", "approve"):
            role = "reviewer" if kind == "approve" else "owner"
            yield kind, node, edition, role, ref.documents[node], "valid"
            yield (
                kind,
                node,
                edition,
                "owner" if role == "reviewer" else "reviewer",
                ref.documents[node],
                "wrong_role",
            )
            if edition > 1:
                yield kind, node, 1, role, ref.documents[node], "old_work"
            if kind == "submit":
                yield kind, node, edition, role, 99, "unknown_version"
                if ref.documents[node] > 1:
                    yield kind, node, edition, role, 1, "old_version"
            else:
                yield kind, node, edition, role, 0, "wrong_submission"
        if edition < 3:
            yield "revise", node, edition, "reviewer", 0, "valid"
            yield "revise", node, edition, "owner", 0, "wrong_role"
        if ref.documents[node] < 3:
            yield "edit", node, edition, "owner", 0, "valid"
        if node in ref.requests:
            for variant in (
                "valid",
                "wrong_role",
                "wrong_reference",
                "wrong_work",
                "wrong_request",
            ):
                yield "reply", node, 1, "reviewer", 1, variant


def uut_apply(state, action):
    kind, node, edition, actor, version, variant = action
    wid, aid = work_id(node, edition), f"doc-{node}"
    if kind == "edit":
        artifact = state["artifacts"][aid]
        number = len(artifact["versions"]) + 1
        artifact["versions"][f"v{number}"] = {
            "logical_time": 0,
            "sha256": f"{aid}-{number}",
            "status": "draft",
            "review_status": "unreviewed",
        }
        artifact["current_version"] = f"v{number}"
    elif kind == "revise":
        work.revise_requirement(
            state, [wid], {"requirements": {"edition": edition + 1}}, actor, "bounded revision"
        )
    elif kind == "submit":
        work.submit_work(state, actor, wid, {aid: f"v{version}"}, answer=f"answer-{node}-{edition}")
    elif kind in {"approve", "withdraw"}:
        subs = state["work_items"][wid]["submissions"]
        sid = (
            subs[-1]["submission_id"]
            if subs and variant != "wrong_submission"
            else "absent-submission"
        )
        if kind == "approve":
            work.approve_submission(state, actor, wid, sid)
        else:
            work.withdraw_submission(state, actor, wid, sid, "bounded withdrawal")
    else:
        response = {
            "response_id": f"reply:{node}:{variant}",
            "request_id": f"request-{node}",
            "work_item_id": node,
            "requirement_version": 1,
            "responder": "reviewer",
            "purpose": "support",
            "status": "delivered",
            "reference": {"artifact_id": aid, "version_id": "v1"},
        }
        if variant == "wrong_role":
            response["responder"] = "owner"
        elif variant == "wrong_reference":
            response["reference"]["version_id"] = "v99"
        elif variant == "wrong_work":
            response["work_item_id"] = "B" if node == "A" else "A"
        elif variant == "wrong_request":
            response["request_id"] = "absent-request"
        result = conditions.apply_response(state, response)
        return "allowed" if result["resolved_conditions"] else "no_satisfaction", result
    return "allowed", None


def uut_projection(state):
    editions = {node: [] for node in ("A", "B")}
    for node in editions:
        for item in sorted(
            (x for x in state["work_items"].values() if x["node_id"] == node),
            key=lambda x: x["requirement_version"],
        ):
            entries = []
            for sub in item["submissions"]:
                decision = (sub.get("review") or {}).get("decision")
                code = {"accepted": "A", "withdrawn": "W"}.get(
                    decision, "X" if sub.get("invalidated") else "P"
                )
                entries.append(
                    (int(sub["artifact_versions"][f"doc-{node}"][1:]), code, sub["answer"])
                )
            editions[node].append(entries)
    return {
        "editions": editions,
        "documents": {
            node: int(state["artifacts"][f"doc-{node}"]["current_version"][1:]) for node in editions
        },
        "requests": {
            c["work_item_id"]: {"open": "O", "resolved": "R", "superseded": "S"}[c["status"]]
            for c in state["condition_specs"].values()
        },
        "responses": sorted(
            key
            for key, receipt in state.get("condition_responses", {}).items()
            if receipt.get("resolved_conditions")
        ),
    }


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def explore(max_depth=4):
    if max_depth not in range(1, 5):
        raise ValueError("Frozen protocol allows depth 1..4 only")
    queue, seen = deque(), set()
    for waiting in (False, True):
        state, ref = initial(waiting)
        key = canonical(ref.projection())
        seen.add(key)
        queue.append((state, ref, [], "waiting_for_evidence" if waiting else "clear"))
    layers = {i: Counter() for i in range(max_depth + 1)}
    rejects, actions_count, errors, mismatches = Counter(), Counter(), Counter(), []
    rejection_examples, depth_truncated = {}, 0
    object_bound_states = Counter()
    while queue:
        state, ref, path, checkpoint = queue.popleft()
        depth = len(path)
        layers[depth]["visited_states"] += 1
        object_bound_states["work_edition_limit_reached"] += any(
            ref.current(node) == 3 for node in ("A", "B")
        )
        object_bound_states["artifact_version_limit_reached"] += any(
            ref.documents[node] == 3 for node in ("A", "B")
        )
        if depth == max_depth:
            depth_truncated += 1
            continue
        layers[depth]["expanded_states"] += 1
        for action in actions(ref):
            layers[depth]["attempted_transitions"] += 1
            actions_count[action[0]] += 1
            next_ref, next_state = copy.deepcopy(ref), copy.deepcopy(state)
            expected = next_ref.apply(action)
            before = copy.deepcopy(next_state)
            detail = None
            try:
                observed, detail = uut_apply(next_state, action)
            except ValueError as exc:
                observed = "rejected"
                detail = str(exc)
                errors[detail] += 1
            except Exception as exc:
                observed = "unexpected_exception"
                detail = f"{type(exc).__name__}: {exc}"
            expected_accept = expected in {"allowed", "no_satisfaction"}
            ok = observed == expected if expected_accept else observed == "rejected"
            # Failed checks may append raw response facts in v0.5; those observations
            # are not condition satisfaction or formal effects in this projection.
            same = canonical(uut_projection(next_state)) == canonical(next_ref.projection())
            if not ok or not same or (observed == "rejected" and next_state != before):
                row = {
                    "initial_checkpoint": checkpoint,
                    "sequence": [list(x) for x in path + [action]],
                    "expected": expected,
                    "observed": observed,
                    "detail": detail,
                    "reference_projection": next_ref.projection(),
                    "uut_projection": uut_projection(next_state),
                    "rejected_transition_mutated_state": observed == "rejected"
                    and next_state != before,
                }
                mismatches.append(row)
                # BFS guarantees first discovered length is shortest, not uniqueness.
                return {
                    "passed": False,
                    "shortest_counterexample": row,
                    "counterexamples": mismatches,
                    "layers": layers,
                    "unique_states": len(seen),
                    "attempts": sum(actions_count.values()),
                    "actions": actions_count,
                    "rejections": rejects,
                    "uut_rejection_messages": errors,
                    "depth_boundary_states_not_expanded": depth_truncated,
                }
            if expected not in {"allowed", "no_satisfaction"}:
                rejects[expected] += 1
                rejection_examples.setdefault(
                    expected,
                    {"sequence": [list(x) for x in path + [action]], "observed_error": detail},
                )
            elif expected == "no_satisfaction":
                rejects["reply_not_satisfied"] += 1
            else:
                layers[depth]["permitted_transitions"] += 1
            key = canonical(next_ref.projection())
            if key not in seen:
                seen.add(key)
                queue.append((next_state, next_ref, path + [action], checkpoint))
    return {
        "passed": True,
        "shortest_counterexample": None,
        "layers": layers,
        "unique_states": len(seen),
        "attempts": sum(actions_count.values()),
        "actions": actions_count,
        "rejections": rejects,
        "rejection_examples": rejection_examples,
        "object_boundary_state_counts": object_bound_states,
        "uut_rejection_messages": errors,
        "depth_boundary_states_not_expanded": depth_truncated,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    protocol = {
        "boundary": {**BOUNDARY, "run_depth": args.depth},
        "source_before": before,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    atomic_write(args.output / "protocol.json", json_bytes(protocol))
    result = explore(args.depth)
    report = {
        "experiment": "E3-bounded-reference-v05",
        "boundary": {**BOUNDARY, "run_depth": args.depth},
        "source_before": before,
        "source_after": code_identity(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model_calls": 0,
        "gpu_used": False,
        **result,
    }
    atomic_write(args.output / "report.json", json_bytes(report))
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "passed",
                    "unique_states",
                    "attempts",
                    "rejections",
                    "shortest_counterexample",
                )
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
