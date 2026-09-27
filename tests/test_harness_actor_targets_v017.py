"""Actual SDK/world plus explicit fake tokens: private actions are actor targets."""

import json

import pytest

pytest.importorskip("openhands.sdk")
from proworksim.harness_collection import collect_window  # noqa: E402
from proworksim.online_training import prepare_window  # noqa: E402
from proworksim.storage import read_json  # noqa: E402
from test_online_collection_v013 import FakeOwner  # noqa: E402


class PrivateOwner(FakeOwner):
    def complete(self, request, **kwargs):
        response = super().complete(request, **kwargs)
        n = self.calls["implementer"]
        if n == 6:
            recent = next(m for m in reversed(request["messages"]) if m["role"] == "tool")
            ref = json.loads(recent["content"])["result"]["reference"]
            name, args = (
                "work_replace_text",
                {
                    "alias": "code",
                    "reference": ref,
                    "locator": ["config", "description"],
                    "new_text": "Explicit CPU fixture edit; no SQL answer.",
                    "dependencies": [],
                    "work_id": "TEAM::build",
                },
            )
        else:
            name, args = {
                1: ("work_note", {"key": "a", "text": "Read the public code."}),
                2: ("work_todo", {"key": "b", "text": "Inspect code", "status": "open"}),
                3: ("work_history_search", {"query": "TEAM", "limit": 1}),
                4: ("work_history_read", {"entry_id": 0}),
                5: ("read_alias", {"alias": "code", "work_id": "TEAM::build"}),
                7: ("staff_done", {"reason": "CPU fixture stop, not success"}),
            }[n]
        response["body"]["choices"][0]["message"]["tool_calls"][0]["function"] = {
            "name": name,
            "arguments": json.dumps(args),
        }
        response["raw_body"] = json.dumps(response["body"])
        return response


def test_private_memory_and_edit_are_single_original_actor_outputs(tmp_path):
    owner = PrivateOwner()
    owner.recipe.update(
        max_length=16384,
        members=["provider", "implementer", "reviewer"],
        credit_assignment="terminal_mc",
    )
    spec = {
        "window_id": owner.window_id,
        "harness": "openhands_v16",
        "stage": "H2_cpu_target_fixture",
        "mode": "online",
        "template": "retail_work",
        "slots": [
            {
                "slot_id": "private",
                "case_id": "uci-train-f0-implement",
                "pool": "train",
                "sampling_seed": 17,
            }
        ],
    }
    entries = collect_window(owner, spec, tmp_path / "work")
    training = prepare_window(entries, owner.freeze_identity(), owner.window_id, owner.recipe)
    assert len(training["decisions"]) == 7
    assert len({r["call_id"] for r in training["decisions"]}) == 7
    assert all(
        r["tokens"]["input_ids"] == [1, 2] and r["tokens"]["output_ids"] == [3]
        for r in training["decisions"]
    )
    events = entries[0]["rollout"]["events"]
    assert sum(e["kind"] == "model_response" for e in events) == 7
    world = [e for e in events if e["kind"] == "tool_call"]
    assert len(world) == 2  # read_alias and the one real write_object from edit
    assert sum(e["payload"]["action"] == "write_object" for e in world) == 1
    private = [e for e in events if e["kind"] == "harness_tool_call"]
    assert len(private) == 6  # four private tools, edit, own stop
    runtime = read_json(tmp_path / "work/slot-0/runtime.json")
    assert runtime["workbenches"]["implementer"]["notes"] == {"a": "Read the public code."}
    assert any("Read the public code." in json.dumps(r) for r in owner.requests[1:])
    # A train-mode request must not turn development/locked assets into targets.
    spec["slots"][0].update(case_id="uci-locked-f0-implement", pool="locked")
    with pytest.raises(ValueError, match="training pool"):
        collect_window(PrivateOwner(), spec, tmp_path / "forbidden")
