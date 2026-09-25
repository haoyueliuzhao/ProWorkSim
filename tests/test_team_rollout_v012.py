"""Synthetic representation/materialization controls, not collected model support."""

import copy

import pytest

from proworksim.information_mapper import information_graph, map_joint_method
from proworksim.member_views import member_view
from proworksim.storage import digest, json_bytes
from proworksim.support_weights import build_support, materialize_weights, weighted_actor_sum
from proworksim.team_rollout import work_validity

WINDOW = {
    "window_id": "w1",
    "xi_id": "case-A",
    "xi_fingerprint": "facts-and-private-layout-A",
    "gamma_fingerprint": "fixed-tools-prompt-budget",
    "team_policy_fingerprint": "fixed-current-team",
}


def validity(value=True, record=True):
    return work_validity(
        [
            {
                "dimension": dim,
                "value": record if dim == "record" else value,
                "evidence": {"kind": "explicit arithmetic fixture"},
            }
            for dim in ("record", "permission", "basis", "delivery")
        ],
        spec_id="fixture-validity",
    )


def slot(index, category="one", v=True, origin="target_model", tokens=True, actions=1, reward=True):
    rid = "synthetic-rollout-" + str(index)
    rollout = {
        "rollout_id": rid,
        "window": copy.deepcopy(WINDOW),
        "members": {"A": {"actor_id": "actor-a", "origin": origin}},
        "work_validity": validity(v),
        "reward_eligibility": {"eligible": reward, "reward": 0},
    }
    view = {
        "version": "member-view-v0.12",
        "rollout_id": rid,
        "window": copy.deepcopy(WINDOW),
        "member_id": "A",
        "own_action_count": actions,
        "complete_actor_trajectory": tokens and actions > 0,
        "complete_semantic_trajectory": actions > 0,
    }
    return {
        "slot_id": str(index),
        "window": copy.deepcopy(WINDOW),
        "rollout": rollout,
        "member_views": {"A": view},
        "mapping": {
            "rollout_id": rid,
            "spec_id": "fixture-mapper",
            "status": "mapped",
            "class_id": category,
        },
    }


def test_reward_validity_and_reconfiguration_are_three_separate_gates():
    slots = [
        slot(0, v=False),
        slot(1, v=None),
        slot(2, tokens=False),
        slot(3, origin="teacher"),
        slot(4, actions=0),
    ]
    support = build_support(slots, window=WINDOW, member_ids=["A"])
    block = support["blocks"]["A"]
    assert block["M"] == 5 and block["n_positive"] == 0 and block["v"] == 0
    assert block["base_actor_mask"] == {"0": True, "1": True, "2": False, "3": False, "4": False}
    assert block["semantic_work_support"] == {"one": 1}
    assert slots[1]["rollout"]["work_validity"]["value"] is None


def test_q_equals_b_keeps_every_slot_and_failure_weight_one():
    slots = [slot(i, "a" if i < 3 else "b" if i < 5 else "c", v=i < 6) for i in range(10)]
    support = build_support(slots, window=WINDOW, member_ids=["A"])
    block = support["blocks"]["A"]
    assert block["M"] == 10 and block["v"] == 0.6
    assert block["b"] == {"a": 0.5, "b": 2 / 6, "c": 1 / 6}
    material = materialize_weights(support, {"A": block["b"]})
    assert material["members"]["A"]["weights"] == dict.fromkeys(map(str, range(10)), 1.0)
    losses = {str(i): float(i + 1) for i in range(10)}
    assert weighted_actor_sum(losses, material, "A") == sum(losses.values())
    assert material["members"]["A"]["actor_mask"] == dict.fromkeys(map(str, range(10)), True)


def test_composition_redistributes_only_eligible_branch_mass():
    slots = [slot(i, "a" if i < 3 else "b" if i < 5 else "c", v=i < 6) for i in range(10)]
    support = build_support(slots, window=WINDOW, member_ids=["A"])
    result = materialize_weights(support, {"A": {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}})["members"][
        "A"
    ]
    assert [result["weights"][str(i)] for i in range(6)] == [2 / 3] * 3 + [1.0] * 2 + [2.0]
    assert all(result["weights"][str(i)] == 1 for i in range(6, 10))
    assert result["eligible_branch_weight"] == 6 and result["total_slot_weight"] == 10


def test_no_own_action_never_manufactures_gradient():
    support = build_support([slot(0, actions=0)], window=WINDOW, member_ids=["A"])
    result = materialize_weights(support, {"A": {}})
    assert result["members"]["A"]["weights"] == {"0": 1.0}
    assert weighted_actor_sum({"0": 999}, result, "A") == 0


def test_support_threshold_and_singleton_keep_baseline_failures():
    support = build_support(
        [slot(0, "common"), slot(1, "common"), slot(2, "rare")],
        window=WINDOW,
        member_ids=["A"],
        min_class_count=2,
    )
    block = support["blocks"]["A"]
    assert block["v"] == 2 / 3 and block["b"] == {"common": 1.0}
    assert block["composition_degrees_of_freedom"] == 0
    assert materialize_weights(support, {"A": {"common": 1.0}})["members"]["A"]["weights"]["2"] == 1


@pytest.mark.parametrize("field", list(WINDOW))
def test_no_cross_layout_protocol_policy_or_window_support(field):
    slots = [slot(0), slot(1)]
    slots[1]["window"][field] = "different"
    with pytest.raises(ValueError, match="merge"):
        build_support(slots, window=WINDOW, member_ids=["A"])


def test_copied_joint_rollout_cannot_count_as_new_member_sample():
    slots = [slot(0), slot(1)]
    slots[1]["rollout"]["rollout_id"] = slots[0]["rollout"]["rollout_id"]
    with pytest.raises(ValueError, match="new joint"):
        build_support(slots, window=WINDOW, member_ids=["A"])


@pytest.mark.parametrize("target", [{"new": 1.0}, {"one": 0.5}, {"one": -1}, {"one": float("nan")}])
def test_unsupported_unnormalized_or_nonfinite_q_is_rejected(target):
    support = build_support([slot(0)], window=WINDOW, member_ids=["A"])
    with pytest.raises(ValueError):
        materialize_weights(support, {"A": target})


def graph_fixture(requested=False, origin="member_action", outcome="applied", rename="original"):
    ref = {"object_id": rename + "-object", "version_id": "v1"}
    events = []

    def call(member, action, args, result):
        events.append(
            {
                "sequence": len(events),
                "worker_id": member,
                "kind": "tool_call",
                "payload": {
                    "action": action,
                    "arguments": args,
                    "response": {"ok": True, "result": result},
                },
            }
        )

    if requested:
        call(
            "B",
            "request_information",
            {"route_id": "basis", "work_id": "TEAM::build"},
            {"request_id": rename + "-request"},
        )
    args = {
        "route_id": "basis",
        "work_id": "TEAM::build",
        "reference": ref,
        "body": "Surface wording is not a method",
    }
    if requested:
        args["request_id"] = rename + "-request"
    call("A", "handoff_information", args, {"handoff_id": rename + "-handoff", "created": True})
    events.append(
        {
            "sequence": len(events),
            "kind": "environment_event",
            "payload": {
                "event_id": rename + "-event",
                "outcome": outcome,
                "payload": {
                    "handoff_id": rename + "-handoff",
                    "origin": origin,
                    "sender": "a",
                    "recipients": ["b"],
                    "reference": ref,
                },
            },
        }
    )
    call(
        "B",
        "read_object",
        {"object_id": ref["object_id"], "version_id": "v1"},
        {"reference": ref, "data": {"value": 7}},
    )
    return {
        "rollout_id": "graph-fixture",
        "members": {
            "A": {"actor_id": "a", "origin": "rule"},
            "B": {"actor_id": "b", "origin": "rule"},
        },
        "events": events,
    }


def test_actual_handoff_method_preserves_direction_and_ignores_surface_ids():
    def mapped(row):
        return map_joint_method(
            information_graph(row), route_id="basis", spec_id="frozen-two-methods"
        )

    proactive = mapped(graph_fixture())
    renamed = mapped(graph_fixture(rename="renamed"))
    requested = mapped(graph_fixture(requested=True))
    assert proactive["class_id"] == renamed["class_id"] == "proactive_handoff"
    assert requested["class_id"] == "requested_handoff"
    graph = information_graph(graph_fixture())
    assert any(edge["kind"] == "delivery_before_matching_access" for edge in graph["edges"])


@pytest.mark.parametrize(
    "change", [{"origin": "automatic_service"}, {"outcome": "historical_only"}]
)
def test_automatic_or_late_reply_is_not_a_current_member_handoff(change):
    result = map_joint_method(
        information_graph(graph_fixture(**change)), route_id="basis", spec_id="frozen-two-methods"
    )
    assert result["status"] == "unmapped" and result["class_id"] is None


def model_rollout(two=True, missing_second=False, budget_end=False, tokens=True):
    events = []

    def event(kind, payload):
        events.append({"sequence": len(events), "worker_id": "A", "kind": kind, "payload": payload})

    for index in range(2 if two else 1):
        cid = "model-" + str(index)
        request = {
            "messages": [{"role": "user", "content": "actual selected public input"}],
            "model": "fixture",
        }
        event(
            "model_call",
            {
                "stage": "started",
                "call_id": cid,
                "decision_index": index + 1,
                "request_sha256": digest(json_bytes(request)),
            },
        )
        if missing_second and index == 1:
            continue
        if budget_end and index == 1:
            event("model_budget_stop", {"call_id": cid, "limits": ["max_total_tokens"]})
            continue
        response = {
            "id": "completion-" + cid,
            "model": "fixture",
            "choices": [{"message": {"role": "assistant", "content": "generated message"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        }
        if tokens:
            response["token_trace"] = {
                "input_ids": [10, 11],
                "output_ids": [12],
                "input_mask": [0, 0],
                "output_mask": [1],
                "behavior_logprobs": [-0.2],
                "source": "actual generation token IDs and sampling logits, not retokenized text",
                "sampling_temperature": 0.3,
            }
        event(
            "model_attempt",
            {
                "stage": "finished",
                "status": "success",
                "call_id": cid,
                "request": request,
                "response": {"body": response},
            },
        )
        event("model_response", {"call_id": cid, "response": response})
    return {
        "rollout_id": "synthetic-model-record",
        "window": WINDOW,
        "manifest": {"policies": {"A": {"implementation": "explicit offline fixture"}}},
        "members": {"A": {"actor_id": "a", "origin": "target_model"}},
        "events": events,
    }


def test_all_actual_member_decisions_and_input_zero_masks_are_retained():
    view = member_view(model_rollout(), "A")
    assert view["own_action_count"] == 2 and view["complete_actor_trajectory"]
    assert all(
        row["labels"] == [-100, -100, 12] and row["loss_mask"] == [0, 0, 1]
        for row in view["decisions"]
    )


def test_missing_tokens_keeps_semantic_view_without_retokenizing():
    view = member_view(model_rollout(tokens=False), "A")
    assert view["own_action_count"] == 2 and not view["complete_actor_trajectory"]
    assert view["complete_semantic_trajectory"]
    assert all(row["tokens"] is None and row["actual_input"] for row in view["decisions"])


def test_missing_round_is_not_silently_reduced_to_first_response():
    view = member_view(model_rollout(missing_second=True), "A")
    assert len(view["decisions"]) == 2 and not view["complete_actor_trajectory"]
    assert not view["complete_semantic_trajectory"]
    budget = member_view(model_rollout(budget_end=True), "A")
    assert budget["complete_actor_trajectory"]
    assert budget["decisions"][1]["generation_status"] == "not_started_budget_stop"
    assert budget["decisions"][1]["actor_required"] is False


@pytest.mark.parametrize("kind", ["duplicate", "orphan"])
def test_duplicate_or_orphan_model_records_cannot_enter_actor_support(kind):
    rollout = model_rollout(two=False)
    extra = copy.deepcopy(rollout["events"][0 if kind == "duplicate" else 1])
    extra["sequence"] = len(rollout["events"])
    if kind == "orphan":
        extra["payload"]["call_id"] = "missing-start"
    rollout["events"].append(extra)
    view = member_view(rollout, "A")
    assert not view["complete_actor_trajectory"]
    assert not view["complete_semantic_trajectory"]
    assert view["diagnostics"]


def test_graph_links_only_public_results_present_in_actual_selected_input():
    rollout = graph_fixture()
    message = {"role": "tool", "tool_call_id": "read-1", "content": "actual returned evidence"}
    rollout["events"][-1]["payload"]["model_call_id"] = "read-1"
    for kind, payload in [
        ("model_tool_result", {"call_id": "read-1", "message": message}),
        (
            "model_attempt",
            {
                "stage": "finished",
                "status": "success",
                "call_id": "use-1",
                "request": {"messages": [message]},
            },
        ),
        (
            "model_attempt",
            {
                "stage": "finished",
                "status": "success",
                "call_id": "dropped-1",
                "request": {
                    "messages": [{"role": "user", "content": "newer unrelated observation"}]
                },
            },
        ),
    ]:
        rollout["events"].append(
            {"sequence": len(rollout["events"]), "worker_id": "B", "kind": kind, "payload": payload}
        )
    graph = information_graph(rollout)
    presented = [edge for edge in graph["edges"] if edge["kind"] == "presented_in_actual_input"]
    returned = [edge for edge in graph["edges"] if edge["kind"] == "returned_to_member"]
    assert len(presented) == len(returned) == 1
    target = next(node for node in graph["nodes"] if node["node_id"] == presented[0]["target"])
    assert target["call_id"] == "use-1"


def test_incomplete_semantic_record_cannot_fill_api_semantic_support():
    row = slot(0, tokens=False)
    row["member_views"]["A"]["complete_semantic_trajectory"] = False
    block = build_support([row], window=WINDOW, member_ids=["A"])["blocks"]["A"]
    assert block["semantic_work_support"] == {}
    assert block["n_positive"] == 0
