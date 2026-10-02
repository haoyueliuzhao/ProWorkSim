"""Native qualification output must preserve exact editable source bytes."""

from proworksim.candidate_runtime_v017 import parse_candidate_generated
from scripts.qualify_software_v028 import native_xml


def test_program_xml_preserves_first_and_last_newlines_and_nonstring_values():
    import json

    arguments = {"old": "\n    return value\n", "new": "\n\n    return value.strip()\n\n", "count": 3}
    request = {"tools": [{"type": "function", "function": {"name": "test_edit", "parameters": {
        "type": "object", "properties": {"old": {"type": "string"}, "new": {"type": "string"},
                                          "count": {"type": "integer"}}}}}]}
    message, error = parse_candidate_generated(native_xml("test_edit", arguments), request)
    assert error is None
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == arguments
