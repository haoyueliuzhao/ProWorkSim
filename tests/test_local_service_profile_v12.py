"""Pure input/profile checks: no torch model, GPU or synthetic probability claims."""

import copy
import json

import pytest

from proworksim.local_model_service import NATIVE_SINGLE_CALL_HINT, prepare_prompt, service_parser
from proworksim.storage import digest, json_bytes


class VisibleTemplate:
    def apply_chat_template(self, messages, **kwargs):
        return json.dumps({"messages": messages, **kwargs}, ensure_ascii=False)


def test_explicit_service_profile_options_preserve_previous_defaults():
    parser = service_parser()
    mandatory = ["--model", "/read-only-base", "--revision", "base-id", "--output", "/new-output"]
    defaults = parser.parse_args(mandatory)
    assert (
        defaults.dtype,
        defaults.attention,
        defaults.max_batch,
        defaults.native_tool_prompt,
    ) == ("bfloat16", "sdpa", 3, "template_default")
    selected = parser.parse_args(
        mandatory
        + [
            "--dtype",
            "float32",
            "--attention",
            "eager",
            "--max-batch",
            "1",
            "--native-tool-prompt",
            "single_call",
        ]
    )
    assert (
        selected.dtype,
        selected.attention,
        selected.max_batch,
        selected.native_tool_prompt,
    ) == ("float32", "eager", 1, "single_call")
    with pytest.raises(SystemExit):
        parser.parse_args(mandatory + ["--dtype", "float16"])


def test_native_syntax_hint_is_an_exact_public_projection_not_an_action():
    request = {
        "messages": [
            {"role": "system", "content": "Public role only"},
            {"role": "user", "content": "Visible input"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {"name": "read_object", "parameters": {"type": "object"}},
            }
        ],
    }
    original = copy.deepcopy(request)
    rendered, messages, projection = prepare_prompt(request, VisibleTemplate(), "single_call")
    assert request == original
    assert messages[0]["content"] == "Public role only\n" + NATIVE_SINGLE_CALL_HINT
    assert messages[1:] == request["messages"][1:]
    assert projection["single_call_hint_applied"] is True
    assert projection["request_sha256"] == digest(json_bytes(request))
    assert projection["actual_prompt_messages_sha256"] == digest(json_bytes(messages))
    assert projection["rendered_prompt_sha256"] == digest(rendered.encode())


def test_json_requests_do_not_receive_native_tool_prompt():
    request = {
        "messages": [{"role": "user", "content": "JSON interface"}],
        "response_format": {"type": "json_object"},
    }
    first = prepare_prompt(request, VisibleTemplate(), "template_default")
    selected = prepare_prompt(request, VisibleTemplate(), "single_call")
    assert first[:2] == selected[:2]
    assert selected[2]["single_call_hint_applied"] is False
