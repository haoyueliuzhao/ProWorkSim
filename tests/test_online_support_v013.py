"""Synthetic bindings test window isolation; these fixtures are not model data."""

import copy

import pytest

from proworksim.online_support import bind_rollout, declare_window, diagnose_window, expected_window
from proworksim.storage import digest, json_bytes
from proworksim.team_rollout import work_validity


def actor(version="0"):
    return {
        "version": "shared-actor-identity-v0.13",
        "policy_version": "actor-" + version,
        "adapter_sha256": digest(version.encode()),
        "base_manifest_sha256": digest(b"base"),
        "inference_profile_sha256": digest(b"profile"),
    }


def declaration(version="0", active=("provider",), slots=2, xi="A"):
    identity = actor(version)
    policies = {
        member: {
            "implementation": "proworksim.model_policy.ModelPolicy",
            "config": {
                "weight_identity": identity,
                "model_revision": identity["policy_version"],
                "task": "public role " + member,
            },
        }
        for member in active
    }
    specs = [
        {
            "slot_id": str(i),
            "xi_id": xi,
            "xi_fingerprint": digest(xi.encode()),
            "active_members": list(active),
            "policies": policies,
            "mapping_spec_id": "fixed-observed-methods",
        }
        for i in range(slots)
    ]
    return declare_window(
        "window-" + version,
        actor_identity=identity,
        gamma_identity={"protocol": "frozen-short-work"},
        slot_specs=specs,
        min_class_count=2,
    )


def rollout(decl, sid, valid=False, reward=True, tokens=True, no_actions=False):
    spec = next(row for row in decl["slots"] if row["slot_id"] == sid)
    events = []

    def event(member, kind, payload):
        events.append(
            {"sequence": len(events), "worker_id": member, "kind": kind, "payload": payload}
        )

    for member in spec["active_members"]:
        if no_actions:
            continue
        request = {
            "messages": [{"role": "user", "content": "Synthetic public input"}],
            "model": "fixture",
        }
        call = sid + "-" + member
        response = {
            "id": call,
            "actor_identity": decl["actor_identity"],
            "system_fingerprint": decl["actor_identity"]["policy_version"],
            "online_window_id": decl["window_id"],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        }
        if tokens:
            response["token_trace"] = {
                "input_ids": [1, 2],
                "output_ids": [3],
                "input_mask": [0, 0],
                "output_mask": [1],
                "behavior_logprobs": [-0.5],
                "source": "actual generation token IDs and sampling logits, not retokenized text",
            }
        event(
            member,
            "model_call",
            {"stage": "started", "call_id": call, "request_sha256": digest(json_bytes(request))},
        )
        event(
            member,
            "model_attempt",
            {
                "stage": "finished",
                "status": "success",
                "call_id": call,
                "request": request,
                "response": {"body": response},
            },
        )
        event(member, "model_response", {"call_id": call, "response": response})
    return {
        "rollout_id": "rollout-" + sid,
        "window": expected_window(decl, sid),
        "manifest": {"policies": copy.deepcopy(spec["policies"])},
        "members": {
            member: {"actor_id": member, "origin": "target_model"}
            for member in spec["active_members"]
        },
        "events": events,
        "reward_eligibility": {"eligible": reward, "reward": 0 if reward else None},
        "work_validity": work_validity(
            [
                {
                    "dimension": dim,
                    "value": True if dim == "record" else valid,
                    "evidence": {"fixture": "synthetic gate values"},
                }
                for dim in ["record", "permission", "basis", "delivery"]
            ],
            spec_id="synthetic-short-validity",
        ),
    }


def test_trusted_failures_remain_base_without_methods_or_success():
    decl = declaration()
    rows = [
        {"slot_id": sid, "status": "closed", "rollout": rollout(decl, sid)} for sid in ["0", "1"]
    ]
    result = diagnose_window(decl, rows)
    group = result["groups"][0]
    assert result["complete"] and group["base_RL_requires_method_support"] is False
    block = group["support"]["blocks"]["provider"]
    assert block["M"] == 2 and block["n_positive"] == 0 and block["b"] == {}
    assert block["base_actor_mask"] == {"0": True, "1": True}
    assert group["Q_equals_B"]["members"]["provider"]["weights"] == {"0": 1, "1": 1}
    assert set(group["support"]["blocks"]) == {"provider"}


@pytest.mark.parametrize("where", ["window", "policy", "adapter", "profile", "response_window"])
def test_cross_policy_window_or_actual_response_identity_is_rejected(where):
    decl = declaration(slots=1)
    row = rollout(decl, "0")
    if where == "window":
        row["window"]["window_id"] = "old-window"
    elif where == "policy":
        row["manifest"]["policies"]["provider"]["config"]["model_revision"] = "stale"
    else:
        for event in row["events"]:
            if event["kind"] != "model_response":
                continue
            response = copy.deepcopy(event["payload"]["response"])
            if where == "response_window":
                response["online_window_id"] = "old-window"
            else:
                response["actor_identity"][
                    "adapter_sha256" if where == "adapter" else "inference_profile_sha256"
                ] = digest(b"different")
            event["payload"]["response"] = response
    with pytest.raises(ValueError):
        bind_rollout(decl, "0", row)


def test_current_windows_do_not_pool_previous_successes():
    old, new = declaration("0", slots=1), declaration("1", slots=1)
    with pytest.raises(ValueError):
        diagnose_window(
            new, [{"slot_id": "0", "status": "closed", "rollout": rollout(old, "0", valid=True)}]
        )


def test_unstarted_and_interrupted_are_not_fabricated_sample_denominators():
    decl = declaration(slots=3)
    result = diagnose_window(
        decl,
        [
            {"slot_id": "0", "status": "closed", "rollout": rollout(decl, "0")},
            {"slot_id": "1", "status": "interrupted"},
        ],
    )
    group = result["groups"][0]
    assert (group["planned"], group["closed"], group["interrupted"], group["not_started"]) == (
        3,
        1,
        1,
        1,
    )
    assert not result["complete"] and group["support"] is None and group["Q_equals_B"] is None


def test_zero_actions_and_unknown_rewards_have_zero_base_mask():
    decl = declaration()
    rows = [
        {"slot_id": "0", "status": "closed", "rollout": rollout(decl, "0", no_actions=True)},
        {"slot_id": "1", "status": "closed", "rollout": rollout(decl, "1", reward=False)},
    ]
    assert diagnose_window(decl, rows)["groups"][0]["support"]["blocks"]["provider"][
        "base_actor_mask"
    ] == {"0": False, "1": False}


def test_same_actor_different_role_maps_stay_in_distinct_situations():
    first, second = (
        declaration(slots=1),
        declaration(active=("provider", "implementer", "reviewer"), slots=1, xi="B"),
    )
    specs = [
        {k: v for k, v in first["slots"][0].items() if k != "window"},
        {k: v for k, v in second["slots"][0].items() if k != "window"},
    ]
    specs[1]["slot_id"] = "1"
    decl = declare_window(
        "one-actor-window",
        actor_identity=actor(),
        gamma_identity={"contract": "joint-short-work"},
        slot_specs=specs,
    )
    assert (
        expected_window(decl, "0")["team_policy_fingerprint"]
        != expected_window(decl, "1")["team_policy_fingerprint"]
    )
    result = diagnose_window(
        decl,
        [{"slot_id": sid, "status": "closed", "rollout": rollout(decl, sid)} for sid in ["0", "1"]],
    )
    assert len(result["groups"]) == 2
    assert [len(group["support"]["blocks"]) for group in result["groups"]] == [1, 3]
