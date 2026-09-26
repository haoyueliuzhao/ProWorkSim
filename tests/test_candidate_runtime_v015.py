import json

from proworksim.candidate_runtime_v015 import (
    candidate_profile, parse_candidate_generated, prepare_candidate_prompt,
    validate_generation_defaults,
)


REQUEST = {"messages": [{"role": "user", "content": "Work using public tools"}],
           "tools": [{"type": "function", "function": {"name": "edit", "parameters": {
               "type": "object", "properties": {"text": {"type": "string"},
                   "version": {"type": "integer"}, "strict": {"type": "boolean"},
                   "refs": {"type": "array"}}}}}]}


def test_official_xml_schema_types_and_literal_sql():
    raw = '<tool_call>\n<function=edit>\n<parameter=text>\nSELECT * WHERE x < 2\n</parameter>\n<parameter=version>\n2\n</parameter>\n<parameter=strict>\nTrue\n</parameter>\n<parameter=refs>\n["actual-v2"]\n</parameter>\n</function>\n</tool_call><|im_end|>'
    message, error = parse_candidate_generated(raw, REQUEST)
    assert error is None
    args = json.loads(message["tool_calls"][0]["function"]["arguments"])
    assert args == {"text": "SELECT * WHERE x < 2", "version": 2,
                    "strict": True, "refs": ["actual-v2"]}


def test_bad_or_partial_xml_never_salvages_a_call():
    for raw in [
        '<tool_call><function=edit><parameter=version>two</parameter></function></tool_call>',
        '<tool_call><function=edit><parameter=refs>[NaN]</parameter></function></tool_call>',
        '<tool_call><function=edit><parameter=text>a</parameter><parameter=text>b</parameter></function></tool_call>',
        '<tool_call><function=edit></function></tool_call><tool_call>',
    ]:
        message, error = parse_candidate_generated(raw, REQUEST)
        assert error is not None and "tool_calls" not in message


def test_unknown_or_missing_arguments_are_not_invented():
    message, error = parse_candidate_generated(
        '<tool_call><function=unknown><parameter=value>001</parameter></function></tool_call>', REQUEST)
    assert error is None
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"value": "001"}
    message, error = parse_candidate_generated('<tool_call><function=edit></function></tool_call>', REQUEST)
    assert error is None
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {}


def test_template_receives_frozen_non_thinking_and_public_tools():
    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            assert kwargs["enable_thinking"] is False
            assert kwargs["preserve_thinking"] is False
            assert kwargs["tools"] == REQUEST["tools"]
            assert messages[-1] == REQUEST["messages"][0]
            return "official template"
    profile = candidate_profile("qwen3.5-9b")
    rendered, messages, record = prepare_candidate_prompt(REQUEST, Tokenizer(), profile)
    assert rendered == "official template" and record["single_call_hint_applied"]
    assert messages[0]["role"] == "system"
    assert REQUEST["messages"][0]["role"] == "user"


def test_undeclared_generation_transforms_fail_closed():
    import pytest
    neutral = {"min_length": 0, "min_new_tokens": None, "min_p": None,
               "suppress_tokens": None, "num_beams": 1, "token_healing": False}
    for key, bad in [("min_length", 10), ("min_new_tokens", 8), ("min_p", 0.1),
                     ("suppress_tokens", [2]), ("num_beams", 2), ("token_healing", True),
                     ("unrecognized_future_processor", {"bias": 1})]:
        with pytest.raises(ValueError, match="Non-neutral"):
            validate_generation_defaults({**neutral, key: bad}, neutral)
    assert validate_generation_defaults({**neutral, "top_p": .8, "top_k": 20,
                                         "eos_token_id": [248044, 248046]}, neutral)
