import json
from copy import deepcopy

import pytest

from proworksim.baseline import run_baseline
from proworksim.curriculum import propose_quotas
from proworksim.designer import design
from proworksim.learning import assert_disjoint, compile_calls, export_bundle
from proworksim.runtime import run_model
from proworksim.tools import TOOLS
from proworksim.validation import evaluate


class FixtureBackend:
    provider = "fixture"
    model = "recorded-unit-fixture"

    def __init__(self, candidates):
        self.candidates = iter(candidates)

    def payload(self, messages):
        return {"model": self.model, "messages": messages, "tools": TOOLS}

    def complete(self, request):
        assert "acceptance_spec_ref" not in json.dumps(request)
        return {
            "model": self.model,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": next(self.candidates),
                        "reasoning_content": "fixture rationale",
                    },
                    "logprobs": None,
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }


def candidate(call_id, action, args):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": action, "arguments": json.dumps(args)},
    }


def short_answer(world):
    session = world.session()
    book = session.call("sheet_read")["result"]
    source = session.call("read_file", artifact_id="financials")["result"]
    return {
        "pe": round(
            book["sheets"]["Outputs"]["B6"]["value"]
            / json.loads(source["content"])["values"]["diluted_eps"],
            2,
        ),
        "citations": [
            {"artifact_id": "model", "version_id": "v1", "location": "Outputs!B6"},
            {"artifact_id": "financials", "version_id": "v2", "location": "values.diluted_eps"},
        ],
    }


def test_runtime_preserves_actual_context_and_handles_malformed_tools(world_factory):
    world = world_factory("short")
    answer = short_answer(world)
    malformed = candidate("bad", "calculate", {})
    malformed["function"]["arguments"] = "not JSON"
    backend = FixtureBackend(
        [
            [malformed],
            [candidate("submit", "submit", {"work_item_id": "work-1", "answer": answer})],
            [candidate("wait", "wait", {"ticks": 2})],
        ]
    )
    assert run_model(world, backend, 4)["complete"]
    state = world.store.load()
    assert len(state["calls"]) == 3
    assert state["calls"][0]["tool_results"][0]["error"]["type"] == "MalformedToolCall"
    second_context = state["calls"][1]["request"]["messages"]
    assert any(m.get("reasoning_content") == "fixture rationale" for m in second_context)
    assert any(m["role"] == "tool" and "MalformedToolCall" in m["content"] for m in second_context)
    assert all(c["token_ids"] is None and c["token_logprobs"] is None for c in state["calls"])
    assert evaluate(world.store.root)[0]["passed"]
    sft, rl, _ = compile_calls(world.store.load())
    assert not sft  # unit fixtures are explicitly excluded from real training data
    assert len(rl) == 3
    assert all(r["action"]["role"] == "assistant" for r in rl)


def test_runtime_resume_does_not_duplicate_committed_tool(world_factory, monkeypatch):
    import proworksim.runtime as runtime

    world = world_factory("short")
    answer = short_answer(world)
    backend = FixtureBackend(
        [[candidate("write-once", "submit", {"work_item_id": "work-1", "answer": answer})]]
    )
    original = runtime._save_runtime
    failed = False

    def interrupt_after_action(world, actor, messages, call=None):
        nonlocal failed
        if not failed and messages[-1]["role"] == "tool":
            failed = True
            raise RuntimeError("simulated interruption")
        return original(world, actor, messages, call)

    monkeypatch.setattr(runtime, "_save_runtime", interrupt_after_action)
    with pytest.raises(RuntimeError, match="simulated"):
        run_model(world, backend, 1)
    monkeypatch.setattr(runtime, "_save_runtime", original)
    resumed = FixtureBackend([[candidate("wait", "wait", {"ticks": 2})]])
    assert run_model(world, resumed, 2)["complete"]
    actions = world.store.load()["interactions"]
    assert sum(row["action"] == "submit" for row in actions) == 1
    assert len(world.store.load()["work_items"]["work-1"]["submissions"]) == 1


def test_learning_masks_failed_prefix_and_other_roles(world_factory):
    world = world_factory()
    run_baseline(world.session(), inject_stale_memo=True)
    evaluate(world.store.root)
    state = world.store.load()
    # Artificial provider records only for checking compiler contracts, never exported.
    state["calls"] = []
    for row in state["interactions"]:
        state["calls"].append(
            {
                "call_id": row["action_id"],
                "actor_id": row["actor_id"],
                "provider": "compiler-test",
                "branch_id": state["branch_id"],
                "model_returned": "test",
                "model_requested": "test",
                "action_ids": [row["action_id"]],
                "tools_complete": True,
                "tool_results": [row["output"]],
                "usage": None,
                "request": {"messages": [{"role": "user", "content": "observed history"}]},
                "response": {
                    "choices": [{"message": {"role": "assistant", "content": row["action"]}}]
                },
            }
        )
    sft, rl, candidates = compile_calls(state)
    assert sft and rl
    first_sub = state["work_items"]["work-1"]["submissions"][0]
    first_action = next(r["action_id"] for r in state["interactions"] if r["action"] == "submit")
    assert not next(c for c in candidates if c["call_id"] == first_action)["eligible"]
    assert all(row["message_loss_mask"] == [0, 1] for row in sft)
    assert not any(row["submission_id"] == first_sub["submission_id"] for row in sft)
    staff_ids = {r["action_id"] for r in state["interactions"] if r["actor_id"] != "analyst"}
    assert all(row["call_id"] not in staff_ids for row in rl)
    child = deepcopy(state)
    child["branch_id"] = "new-branch"
    assert compile_calls(child)[0] == []
    assert compile_calls(child)[1] == []


def test_export_lineage_split_and_development_only_curriculum(world_factory, tmp_path):
    world = world_factory("short")
    run_baseline(world.session())
    manifest = export_bundle(world.store.root, tmp_path / "export")
    assert manifest["counts"]["sft"] == 0
    assert (tmp_path / "export/world/snapshot.json").is_file()
    assert design(11, "short").project.split == design(11, "continuous").project.split
    assert_disjoint([manifest, manifest])
    with pytest.raises(ValueError, match="leakage"):
        assert_disjoint([manifest, {**manifest, "split": "different"}])
    proposal = propose_quotas(
        [
            {"split": "test", "checks": [{"category": "dependency", "passed": False}]},
            {"split": "dev", "validity": "invalid", "checks": []},
            {"split": "dev", "checks": [{"category": "consistency", "passed": False}]},
        ],
        total=17,
    )
    assert proposal["development_failure_counts"] == {"consistency": 1}
    assert (
        sum(proposal["representative_quotas"].values()) + sum(proposal["stress_quotas"].values())
        == 17
    )
    assert proposal["excluded"] == {"non_development": 1, "invalid_environment_or_evaluation": 1}


def test_curriculum_allocates_failures_and_materializes_train_worlds(tmp_path):
    from proworksim.curriculum import synthesize_from_quotas

    records = [{"split": "dev", "checks": [{"category": "consistency", "passed": False}]}] * 12
    proposal = propose_quotas(records, total=6, representative_fraction=0.5)
    assert proposal["stress_quotas"]["consistency"] > proposal["stress_quotas"]["scenario"]
    manifest = synthesize_from_quotas(proposal, tmp_path / "curriculum", workers=2)
    assert len(manifest["worlds"]) == 6
    assert all(world["split"] == "train" for world in manifest["worlds"])
    assert len({world["lineage_id"] for world in manifest["worlds"]}) == 6
    assert manifest["proposal"]["applied"]
