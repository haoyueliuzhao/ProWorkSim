"""Protected length is measured separately; actual v041 selection stays exact."""
import copy

import pytest

from proworksim.software_context_v041 import project_software_request as old_project
from proworksim.software_context_v042 import project_software_request, protected_software_request
from proworksim.storage import digest, json_bytes
from test_software_context_v034 import render, tokenizer
from test_software_context_v041 import request


def test_actual_selection_is_identical_and_protected_drops_all_old_rounds_only():
    original = request()
    original["messages"][2:2] = [
        {"role": "assistant", "content": "earlier actual action", "tool_calls": [{"id": "old", "function": {"name": "read"}}]},
        {"role": "tool", "tool_call_id": "old", "content": "Previously requested report page. " * 20}]
    old, _ = old_project(original, render=render, tokenizer=tokenizer, context_limit=50000)
    selected, audit = project_software_request(original, render=render, tokenizer=tokenizer, context_limit=50000)
    protected, evidence = protected_software_request(original)
    assert selected == old
    assert evidence["removed_indices"] == [2, 3]
    assert protected["messages"][2:5] == original["messages"][4:7]
    actual_ids = tokenizer(render(protected)[0])["input_ids"]
    assert audit["protected_prompt_tokens"] == len(actual_ids) < audit["selected_prompt_tokens"]
    assert audit["protected_input_ids_sha256"] == digest(json_bytes(actual_ids))
    assert audit["protected_request_sha256"] == digest(json_bytes(protected))
    assert audit["protected_rendered_prompt_sha256"] == digest(render(protected)[0].encode())
    assert audit["protected_headroom_after_margin"] == 50000 - original["max_tokens"] - len(actual_ids) - 1024
    assert audit["protected_selected_indices"] == evidence["selected_indices"]
    assert audit["deduplication"]["declared_static_fields"] == evidence["deduplication"]["declared_static_fields"]


def test_latest_complete_page_and_real_format_feedback_remain_when_capacity_fails():
    original = request()
    original["messages"][3]["content"] = "Exact latest requested page remains complete. " * 100
    before = copy.deepcopy(original)
    selected, audit = project_software_request(original, render=render, tokenizer=tokenizer, context_limit=200)
    assert not audit["fits"] and audit["protected_headroom_after_margin"] < 0
    assert selected["messages"][2:5] == original["messages"][2:5] and original == before
    invalid = copy.deepcopy(original)
    invalid["messages"][3]["tool_call_id"] = "wrong-associated-call"
    with pytest.raises(ValueError, match="match"):
        protected_software_request(invalid)
