"""CPU fake-transport collection controls, not model-performance experiments."""

import copy
import json
from collections import Counter

from proworksim.online_collection import collect_window
from proworksim.storage import digest, read_json


class FakeOwner:
    """Explicit offline response fixture; never instantiates torch or a model."""

    def __init__(self, window_id="cpu-window", provider_done=False, argument_error_then_read=False):
        self.window_id = window_id
        self.provider_done = provider_done
        self.argument_error_then_read = argument_error_then_read
        self.context_after = None
        self.recipe = {"temperature": 0.7, "max_output_tokens": 16, "max_length": 8192}
        self.calls = Counter()
        self.requests = []
        self.seeds = []
        self.transport = self
        self.identity = {
            "version": "shared-actor-identity-v0.13",
            "policy_version": "explicit-offline-fixture",
            "adapter_sha256": digest(b"fixture-adapter"),
            "base_manifest_sha256": digest(b"fixture-base"),
            "inference_profile_sha256": digest(b"fixture-profile"),
        }

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def reseed(self, seed, *, label):
        self.seeds.append((seed, label))

    def complete(self, request, *, timeout_seconds):
        assert timeout_seconds > 0
        observed = next(
            json.loads(message["content"])["observation"]
            for message in reversed(request["messages"])
            if message["role"] == "user" and "observation" in json.loads(message["content"])
        )
        role = observed["actor_id"]
        self.calls[role] += 1
        self.requests.append(copy.deepcopy(request))
        if self.context_after is not None and self.calls[role] > self.context_after:
            body = {
                "error": {
                    "code": "context_length_exceeded",
                    "prompt_tokens": 8190,
                    "requested_output": request["max_tokens"],
                    "context_limit": 8192,
                },
                "transport_kind": "resident_direct",
                "generation_started": False,
                "actor_identity": self.freeze_identity(),
                "online_window_id": self.window_id,
            }
            return {"http_status": 400, "body": body, "raw_body": json.dumps(body)}
        control = "staff_done" if role == "provider" and self.provider_done else "staff_wait"
        arguments = {"reason": "CPU collection fixture"}
        if self.argument_error_then_read and role == "provider" and self.calls[role] <= 2:
            control, arguments = "read_alias", {"alias": "basis", "work_id": "TEAM::build"}
            if self.calls[role] == 1:
                arguments["object_id"] = "not-a-public-read-alias-parameter"
        cid = role + "-" + str(self.calls[role])
        body = {
            "id": cid,
            "model": "explicit-offline-fixture",
            "system_fingerprint": self.identity["policy_version"],
            "actor_identity": self.freeze_identity(),
            "online_window_id": self.window_id,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "control-" + cid,
                                "type": "function",
                                "function": {
                                    "name": control,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            "token_trace": {
                "input_ids": [1, 2],
                "output_ids": [3],
                "input_mask": [0, 0],
                "output_mask": [1],
                "behavior_logprobs": [-0.5],
                "sampling_temperature": 0.7,
                "sampling_top_p": 1.0,
                "sampling_top_k": 0,
                "source": "actual generation token IDs and sampling logits, not retokenized text",
            },
        }
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}


def spec(case_id):
    return {
        "window_id": "cpu-window",
        "interface": "v13",
        "external_tick_per_sweep": 1,
        "min_class_count": 2,
        "slots": [{"slot_id": "fixed-slot", "case_id": case_id, "sampling_seed": 17}],
    }


def test_done_provider_does_not_consume_other_role_decision_budgets(tmp_path):
    owner = FakeOwner(provider_done=True)
    entries = collect_window(owner, spec("train-w0-chain"), tmp_path / "collected")
    assert len(entries) == 1 and entries[0]["rollout"] is not None
    assert owner.calls == {"provider": 1, "implementer": 8, "reviewer": 6}
    assert owner.seeds == [(17, "fixed-slot")]
    rollout = entries[0]["rollout"]
    assert rollout["manifest"]["status"] == "closed"
    assert rollout["reward_eligibility"]["eligible"] is True
    assert rollout["reward_eligibility"]["reward"] == 0
    assert rollout["work_validity"]["components"]["record"]["value"] is True
    support = read_json(tmp_path / "collected/support.json")
    assert support["complete"]
    for member in owner.calls:
        assert (
            support["groups"][0]["support"]["blocks"][member]["base_actor_mask"]["fixed-slot"]
            is True
        )
        assert support["groups"][0]["support"]["blocks"][member]["n_positive"] == 0


def test_actual_preparation_environment_events_stay_outside_actor_episode(tmp_path):
    owner = FakeOwner()
    output = tmp_path / "collected"
    entries = collect_window(owner, spec("train-w0-implement"), output)
    assert entries[0]["rollout"] is not None
    rollout = entries[0]["rollout"]
    start = read_json(output / "slot-0/episode/start/control/state.json")
    prepared_event_ids = {event["event_id"] for event in start["event_history"]}
    assert prepared_event_ids, "The control must have a real already-delivered preparation event"
    episode_events = rollout["events"]
    assert not any(
        event["kind"] == "environment_event" and event["payload"]["event_id"] in prepared_event_ids
        for event in episode_events
    )
    assert {event["worker_id"] for event in episode_events if event.get("worker_id")} == {
        "implementer"
    }
    assert owner.calls == {"implementer": 8}
    assert rollout["reward_eligibility"]["reward"] == 0
    assert rollout["online_scope"]["task"] == "implement"


def test_world_argument_refusal_does_not_retire_the_role(tmp_path):
    owner = FakeOwner(argument_error_then_read=True)
    output = tmp_path / "collected"
    entry = collect_window(owner, spec("train-w0-handoff"), output)[0]
    assert entry["rollout"] is not None
    assert owner.calls == {"provider": 4}
    calls = [e for e in entry["rollout"]["events"] if e["kind"] == "tool_call"]
    assert [e["payload"]["action"] for e in calls] == ["read_alias", "read_alias"]
    assert calls[0]["payload"]["response"]["ok"] is False
    assert calls[0]["payload"]["response"]["error"]["rejection"]["category"] == "policy_error"
    assert calls[1]["payload"]["response"]["ok"] is True
    assert entry["reward"]["reward"] == 0.25
    assert entry["rollout"]["work_validity"]["components"]["record"]["value"] is True


def test_postprocessing_fault_preserves_closed_unknown_sample(tmp_path, monkeypatch):
    import proworksim.online_collection as collector

    def fault(*args, **kwargs):
        raise RuntimeError("Injected read-only postprocessing fault")

    monkeypatch.setattr(collector, "export_online_rollout", fault)
    output = tmp_path / "collected"
    entry = collect_window(FakeOwner(), spec("train-w0-handoff"), output)[0]
    assert entry["rollout"] is None and entry["reward"] is None
    assert read_json(output / "slot-0/episode/manifest.json")["status"] == "closed"
    problem = read_json(output / "slot-0/interruption.json")
    assert problem["phase"] == "postprocessing" and problem["closed"] is True
    group = read_json(output / "support.json")["groups"][0]
    assert group["closed_joint_M"] == group["closed_unassessed"] == 1
    assert group["not_started"] == group["interrupted"] == 0
    assert group["support"] is None and group["Q_equals_B"] is None
    assert group["baseline_only_materialization"]["provider"] == {
        "actor_mask": {"fixed-slot": False},
        "weights": {"fixed-slot": 1.0},
    }


def test_context_stop_record_check_uses_frozen_window_and_retains_prior_actions(tmp_path):
    from proworksim.member_views import member_view
    from proworksim.online_support import assess_online_validity

    owner = FakeOwner()
    owner.context_after = 1
    output = tmp_path / "collected"
    entry = collect_window(owner, spec("train-w0-handoff"), output)[0]
    rollout = entry["rollout"]
    assert rollout is not None and entry["reward"]["eligible"] is True
    assert entry["reward"]["reward"] == 0
    view = member_view(rollout, "provider")
    assert view["own_action_count"] == 1 and view["complete_actor_trajectory"]
    assert view["decisions"][-1]["generation_status"] == "not_started_direct_context_limit"
    assert rollout["work_validity"]["components"]["record"]["value"] is True
    assert rollout["work_validity"]["spec_id"].startswith("online-scoped-validity-v0.13.1:")
    capture = read_json(output / "slot-0/public-capture.json")
    no_binding = assess_online_validity(
        output / "slot-0/episode",
        rollout["online_scope"]["reward_spec"],
        independent_capture=capture,
        members=rollout["members"],
    )
    assert no_binding["components"]["record"]["value"] is None
    wrong = copy.deepcopy(rollout["window"])
    wrong["window_id"] = "a-different-window"
    foreign = assess_online_validity(
        output / "slot-0/episode",
        rollout["online_scope"]["reward_spec"],
        independent_capture=capture,
        members=rollout["members"],
        window=wrong,
    )
    assert foreign["components"]["record"]["value"] is None
    support = read_json(output / "support.json")
    assert (
        support["groups"][0]["support"]["blocks"]["provider"]["base_actor_mask"]["fixed-slot"]
        is True
    )
