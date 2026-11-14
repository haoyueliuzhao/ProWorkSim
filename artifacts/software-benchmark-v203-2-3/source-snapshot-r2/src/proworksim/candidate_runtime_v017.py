"""v0.17 public native diagnostics; the chat-stop numeric loader is unchanged.

H1 explicitly selects this new runtime and profile. Historical v0.15 modules and
frozen runs retain their original parsing behavior and original result records.
"""

import copy
import json
import re
import uuid

from .candidate_runtime_v0151 import CandidateActor as ChatStopActor
from .candidate_runtime_v0151 import candidate_profile as chat_stop_profile
from .format_diagnostics import VERSION as DIAGNOSTICS_VERSION
from .format_diagnostics import exception_diagnostic, json_type

VERSION = "candidate-runtime-v0.17"
PARSER_CONTRACT = {
    "version": DIAGNOSTICS_VERSION,
    "parser": "qwen_native_xml_v017",
    "validation": "Original native parser acceptance; diagnostics use supplied public parameter types without changing later world/SDK validation",
    "failure_fields": [
        "stage",
        "field_path",
        "schema_path",
        "expected_type",
        "observed_type",
        "position",
    ],
}


def candidate_profile(candidate_id, *, dtype="float32", devices=1):
    profile = chat_stop_profile(candidate_id, dtype=dtype, devices=devices)
    profile.update(version=VERSION, parser_contract=copy.deepcopy(PARSER_CONTRACT))
    return profile


def _failure(content, failure, *, tool_name=None):
    return {"role": "assistant", "content": content}, {
        "version": DIAGNOSTICS_VERSION,
        "parser": PARSER_CONTRACT["parser"],
        "status": "rejected",
        "tool_name": tool_name,
        "failure": failure,
    }


def _syntax(reason, *, field_path=None, schema_path=None, expected_type=None, observed_type=None):
    return {
        "stage": "native_xml",
        "reason": reason,
        "field_path": field_path,
        "schema_path": schema_path,
        "expected_type": expected_type,
        "observed_type": observed_type,
        "position": None,
    }


def _reject_constant(value):
    raise ValueError("Nonfinite JSON constants are not allowed")


def parse_candidate_generated(raw, request):
    """Preserve v0.15 acceptance; only explain its existing rejections better."""
    content = raw.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()
    blocks = list(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.DOTALL))
    if content.count("<tool_call>") != len(blocks) or content.count("</tool_call>") != len(blocks):
        return _failure(content, _syntax("Incomplete native tool block"))
    schemas = {
        t["function"]["name"]: t["function"].get("parameters", {}) for t in request.get("tools", [])
    }
    calls = []
    for block in blocks:
        function = re.fullmatch(
            r"<function=([A-Za-z_][A-Za-z0-9_.-]*)>\s*(.*?)\s*</function>",
            block.group(1),
            re.DOTALL,
        )
        if function is None:
            return _failure(content, _syntax("Expected one native function block"))
        name, body = function.groups()
        params = list(
            re.finditer(
                r"<parameter=([A-Za-z_][A-Za-z0-9_.-]*)>\n?(.*?)\n?</parameter>", body, re.DOTALL
            )
        )
        residue = re.sub(
            r"<parameter=[A-Za-z_][A-Za-z0-9_.-]*>.*?</parameter>", "", body, flags=re.DOTALL
        )
        if residue.strip():
            return _failure(
                content,
                _syntax("Unexpected text inside native function parameters"),
                tool_name=name,
            )
        arguments = {}
        properties = schemas.get(name, {}).get("properties", {})
        for param in params:
            key, text = param.groups()
            schema = properties.get(key, {})
            kind = schema.get("type")
            if key in arguments:
                return _failure(
                    content, _syntax("Duplicate native parameter", field_path=[key]), tool_name=name
                )
            if kind == "string" or not kind:
                value = text
            elif kind == "boolean" and text in {"true", "false", "True", "False"}:
                value = text.lower() == "true"
            else:
                try:
                    value = json.loads(text, parse_constant=_reject_constant)
                except ValueError as error:
                    failure = exception_diagnostic(
                        error,
                        stage="native_parameter_json",
                        field_path=[key],
                        schema_path=["properties", key, "type"],
                        expected_type=kind,
                    )
                    return _failure(content, failure, tool_name=name)
                allowed = {
                    "object": isinstance(value, dict),
                    "array": isinstance(value, list),
                    "integer": type(value) is int,
                    "number": type(value) in (int, float),
                    "null": value is None,
                    "boolean": type(value) is bool,
                }
                try:
                    matches_type = allowed.get(kind, False)
                except TypeError:
                    matches_type = False
                if not matches_type:
                    failure = {
                        **_syntax(
                            "Native parameter does not match public schema type",
                            field_path=[key],
                            schema_path=["properties", key, "type"],
                            expected_type=kind,
                            observed_type=json_type(value),
                        ),
                        "stage": "native_parameter_type",
                    }
                    return _failure(content, failure, tool_name=name)
            arguments[key] = value
        calls.append(
            {
                "id": "call_" + uuid.uuid4().hex,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
            }
        )
    message = {
        "role": "assistant",
        "content": re.sub(r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL).strip()
        if calls
        else content,
    }
    if calls:
        message["tool_calls"] = calls
    return message, None


class CandidateActor(ChatStopActor):
    def __init__(self, *args, inference_profile, **kwargs):
        # The old loader appends factual module/device/version metadata before
        # constructing cls. Change the runtime identity BEFORE owner creation.
        profile = copy.deepcopy(inference_profile)
        profile.update(version=VERSION, parser_contract=copy.deepcopy(PARSER_CONTRACT))
        super().__init__(*args, inference_profile=profile, **kwargs)

    @classmethod
    def from_candidate(cls, model_path, *, manifest, profile, output, recipe=None):
        expected = candidate_profile(
            profile["candidate_id"], dtype=profile["dtype"], devices=profile["devices"]
        )
        if profile != expected:
            raise ValueError("Undeclared v0.17 candidate profile changes")
        numeric_profile = chat_stop_profile(
            profile["candidate_id"], dtype=profile["dtype"], devices=profile["devices"]
        )
        return super().from_candidate(
            model_path, manifest=manifest, profile=numeric_profile, output=output, recipe=recipe
        )

    def parse_response(self, raw, request):
        return parse_candidate_generated(raw, request)

    def prepare_request(self, request):
        rendered, messages, projection = super().prepare_request(request)
        projection = {
            **projection,
            "version": VERSION,
            "parser_contract": copy.deepcopy(PARSER_CONTRACT),
        }
        return rendered, messages, projection
