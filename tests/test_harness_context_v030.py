"""Exact original first/latest observations and complete SDK rounds, no synthesis."""
import copy
import json

import pytest

pytest.importorskip("openhands.sdk")

from proworksim.harness_sdk import select_context  # noqa: E402
from proworksim.software_runtime_v030 import SDK_CONTEXT_SELECTION  # noqa: E402
from proworksim.storage import json_bytes  # noqa: E402


def history(rounds=6):
    messages = [{"role": "system", "content": "Original system bytes"}]
    observations = []
    for index in range(rounds + 1):
        text = json.dumps({"observation": {"number": index, "original": "首尾字节\\n"}}, ensure_ascii=False)
        observations.append(text)
        messages.append({"role": "user", "content": text})
        if index < rounds:
            messages.extend([
                {"role": "assistant", "content": None, "tool_calls": [{"id": str(index), "type": "function",
                 "function": {"name": "read_file", "arguments": '{"path":"consumer.py"}'}}]},
                {"role": "tool", "tool_call_id": str(index), "content": '{"actual": "unchanged"}'},
            ])
    return messages, observations


def test_first_latest_observations_and_four_complete_rounds_are_original_bytes():
    messages, observations = history()
    original = copy.deepcopy(messages)
    selected, audit = select_context(messages, observations, SDK_CONTEXT_SELECTION)
    assert messages == original
    assert [message["content"] for message in selected if message["role"] == "user"] == [observations[0], observations[-1]]
    assert selected[:2] == original[:2]
    assert selected[-1] == original[-1]
    assert len(selected) == 11
    assert sum(message["role"] == "assistant" for message in selected) == 4
    assert json_bytes(selected) == json_bytes([original[index] for index in audit["selected_indices"]])
    for index, message in enumerate(selected):
        if message["role"] == "assistant":
            assert selected[index + 1]["role"] == "tool"
            assert selected[index + 1]["tool_call_id"] == message["tool_calls"][0]["id"]
    assert audit["retained_observation_indices"] == [1, len(original) - 1]
    # Both existing policies retain their exact previous choices.
    old, _ = select_context(messages, observations, "latest_observation_last4_tool_rounds")
    assert len(old) == 10 and old[-1] == original[-1]
    assert [message["content"] for message in old if message["role"] == "user"] == [observations[-1]]
    full, _ = select_context(messages, observations, "full_history")
    assert full == original


def test_initial_observation_is_never_fabricated_or_duplicated():
    messages, observations = history(0)
    selected, audit = select_context(messages, observations, SDK_CONTEXT_SELECTION)
    assert selected == messages and audit["retained_observation_indices"] == [1]
    messages, observations = history(2)
    with pytest.raises(RuntimeError, match="Initial SDK observation"):
        select_context([messages[0], *messages[2:]], observations, SDK_CONTEXT_SELECTION)
    with pytest.raises(RuntimeError, match="complete|association|orphan"):
        select_context(messages[:-2] + messages[-1:], observations, SDK_CONTEXT_SELECTION)


def test_unregistered_user_feedback_remains_exact_without_becoming_an_observation():
    messages, observations = history(2)
    feedback = {"role": "user", "content": '{"actual_feedback": "Do not rewrite this\\n"}'}
    messages.insert(-1, feedback)
    selected, audit = select_context(messages, observations, SDK_CONTEXT_SELECTION)
    assert feedback in selected
    assert len(audit["retained_observation_indices"]) == 2
    assert len([message for message in selected if message["role"] == "user"]) == 3
