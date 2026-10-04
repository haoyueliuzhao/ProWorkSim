"""Declared v0.31 software-model wire protocols, with no model execution.

SWE-Next uses the author's single XML function/parameter content protocol inside
its official Qwen chat boundaries. Devstral retains native v13 token IDs. Only
public tool schemas determine names, argument types and guidance; no fallback
parser or task-answer repair is applied to model output.
"""

import copy
from functools import lru_cache
import json
import math
import re
from xml.sax.saxutils import escape, unescape

from .candidate_runtime_v030 import (
    MistralNativeTokenizer, NativePrompt, mistral_message_projection, parse_mistral_generated,
)
from .storage import digest, json_bytes
from .training import normalize_messages

VERSION = 'native-codecs-v0.31'
SWE_FORMAT = 'swe_next_author_openhands_xml_v031'
SWE_MANUAL_VERSION = 'native-swe-public-manual-v0.31-r3'
MISTRAL_FORMAT = 'mistral_common_v13_provided_tools_v031'
SWE_AUTHOR_COMMIT = 'b55c0841f364f9fe7363b2012cd0ae8d8afdf872'
NAME = r'[A-Za-z_][A-Za-z0-9_.-]*'
FUNCTION_START = re.compile(r'<function\s*=')
FUNCTION_END = re.compile(r'</function\s*>')
FUNCTION = re.compile(r'<function\s*=\s*(' + NAME + r')\s*>(.*)</function\s*>', re.DOTALL)
PARAMETER = re.compile(r'<parameter\s*=\s*(' + NAME + r')\s*>(.*?)</parameter\s*>', re.DOTALL)
QWEN_EOS = ('<|im_end|>', '<|endoftext|>')


def _bad_constant(value):
    raise ValueError('Nonfinite JSON value is not part of the public wire protocol: ' + value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON property: ' + key)
        result[key] = value
    return result


def strict_json(text):
    """Preserve JSON value types, rejecting duplicate keys and NaN/Infinity."""
    return json.loads(text, parse_constant=_bad_constant, object_pairs_hook=_unique_object)


def _local_references_only(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('$ref', '$dynamicRef') and (not isinstance(item, str) or not item.startswith('#')):
                raise ValueError('Tool schemas may reference only their supplied local definitions')
            _local_references_only(item)
    elif isinstance(value, list):
        for item in value:
            _local_references_only(item)


@lru_cache(maxsize=1)
def _validator_class():
    # JSON Schema is an existing managed SDK dependency. Keep pure imports of
    # this module usable outside that optional runtime; never fetch a schema.
    from jsonschema import Draft202012Validator, validators
    checker = Draft202012Validator.TYPE_CHECKER.redefine_many({
        'integer': lambda _checker, value: type(value) is int,
        'number': lambda _checker, value: type(value) in (int, float) and math.isfinite(value),
    })
    return validators.extend(Draft202012Validator, type_checker=checker)


def _resolved_schema(schema, root):
    """Resolve local JSON pointers only to decide this parameter's wire type."""
    seen = set()
    while isinstance(schema, dict) and '$ref' in schema:
        target = schema['$ref']
        if target in seen or not target.startswith('#/'):
            raise ValueError('Parameter wire type requires a noncyclic local JSON-pointer reference')
        seen.add(target)
        value = root
        for component in target[2:].split('/'):
            value = value[component.replace('~1', '/').replace('~0', '~')]
        schema = {**value, **{key: item for key, item in schema.items() if key != '$ref'}}
    return schema


@lru_cache(maxsize=64)
def _contracts(serialized_tools):
    tools = strict_json(serialized_tools)
    contracts = {}
    validator_cls = _validator_class()
    for tool in tools:
        if tool.get('type') != 'function' or not isinstance(tool.get('function'), dict):
            raise ValueError('Only explicit public function tools are supported')
        function = tool['function']
        name = function['name']
        if not isinstance(name, str) or re.fullmatch(NAME, name) is None or name in contracts:
            raise ValueError('Each supplied public function must have a unique valid name')
        schema = function.get('parameters', {})
        _local_references_only(schema)
        validator_cls.check_schema(schema)
        root = _resolved_schema(schema, schema)
        if root.get('type') != 'object' or not isinstance(root.get('properties', {}), dict):
            raise ValueError('Public arguments must be an object with explicitly supplied parameter names')
        contracts[name] = {'definition': function, 'schema': schema,
                           'properties': root.get('properties', {}), 'validator': validator_cls(schema)}
    return contracts


def _tool_contracts(request):
    return _contracts(json.dumps(request.get('tools') or [], ensure_ascii=False, sort_keys=True, allow_nan=False))


def _validate_arguments(name, arguments, contracts):
    if name not in contracts:
        raise ValueError('Function was not supplied in this request: ' + name)
    if not isinstance(arguments, dict):
        raise ValueError('Arguments must be a JSON object')
    contract = contracts[name]
    extra = set(arguments) - set(contract['properties'])
    if extra:
        raise ValueError('Parameter was not supplied in the public schema: ' + ', '.join(sorted(extra)))
    # Also reject nonfinite values under an unconstrained nested schema.
    json.dumps(arguments, ensure_ascii=False, allow_nan=False)
    error = next(contract['validator'].iter_errors(arguments), None)
    if error is not None:
        path = '.'.join(map(str, error.absolute_path)) or '<arguments>'
        raise ValueError('Public argument schema violation at ' + path + ': ' + error.message)


def _string_wire(schema, root):
    return _resolved_schema(schema, root).get('type') == 'string'


def _decode_parameter(text, schema, root):
    # A paired immediate boundary LF is structure, not value data. Exactly
    # one pair is removed; spaces, indentation and extra LFs remain intact.
    if len(text) >= 2 and text.startswith('\n') and text.endswith('\n'):
        text = text[1:-1]
    text = unescape(text)
    return text if _string_wire(schema, root) else strict_json(text)


def _content_without_terminal_eos(raw, eos_tokens):
    content = raw
    terminal = raw.rstrip()
    for token in eos_tokens:
        if terminal.endswith(token):
            content = terminal[:-len(token)] + raw[len(terminal):]
            break
    if any(token in content for token in eos_tokens):
        raise ValueError('EOS marker appears inside or more than once in the output')
    return content


def _read_xml_call(content, contracts):
    starts = list(FUNCTION_START.finditer(content))
    if len(starts) != 1 or len(FUNCTION_END.findall(content)) != 1:
        raise ValueError('Exactly one complete XML function call is required')
    if '<tool_call>' in content or '</tool_call>' in content:
        raise ValueError('The author OpenHands XML profile does not use a tool_call wrapper')
    function = FUNCTION.fullmatch(content[starts[0].start():].rstrip())
    if function is None:
        raise ValueError('Expected optional reasoning prefix, one XML function, and no suffix')
    name, body = function.groups()
    if name not in contracts:
        raise ValueError('Function was not supplied in this request: ' + name)
    contract = contracts[name]
    arguments, cursor = {}, 0
    for parameter in PARAMETER.finditer(body):
        if body[cursor:parameter.start()].strip():
            raise ValueError('Unexpected text between XML parameter elements')
        key, value = parameter.groups()
        if key in arguments:
            raise ValueError('Duplicate XML parameter: ' + key)
        if key not in contract['properties']:
            raise ValueError('Parameter was not supplied in the public schema: ' + key)
        if re.search(r'<parameter\s*=|</parameter\s*>', value):
            raise ValueError('Literal XML protocol delimiters in a value require entity escaping')
        arguments[key] = _decode_parameter(value, contract['properties'][key], contract['schema'])
        cursor = parameter.end()
    if body[cursor:].strip():
        raise ValueError('Unexpected or incomplete XML parameter content')
    _validate_arguments(name, arguments, contracts)
    return name, arguments


def xml_call_text(name, arguments, request):
    """Encode typed public arguments for CPU controls/history, never sample repair."""
    contracts = _tool_contracts(request)
    _validate_arguments(name, arguments, contracts)
    contract = contracts[name]
    elements = []
    for key, value in arguments.items():
        text = value if _string_wire(contract['properties'][key], contract['schema']) else json.dumps(
            value, ensure_ascii=False, allow_nan=False)
        body = escape(text)
        if _string_wire(contract['properties'][key], contract['schema']):
            body = '\n' + body + '\n'
        elements.append('<parameter=' + key + '>' + body + '</parameter>')
    return '<function=' + name + '>\n' + '\n'.join(elements) + '\n</function>'


def _call_id(request, raw, length=32):
    value = digest(json_bytes([VERSION, request, raw]))[:length]
    return value if length == 9 else 'call_' + value


def parse_swe_xml_generated(raw, request):
    """Optional original reasoning, one author OpenHands XML call, no suffix."""
    try:
        content = _content_without_terminal_eos(raw, QWEN_EOS)
        name, arguments = _read_xml_call(content, _tool_contracts(request))
        return {'role': 'assistant', 'content': content, 'tool_calls': [{
            'id': _call_id(request, raw), 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False, allow_nan=False)},
        }]}, None
    except (ValueError, TypeError, KeyError) as error:
        return {'role': 'assistant', 'content': raw}, 'invalid_swe_xml_v031: ' + str(error)


def _control_guidance(contracts):
    names = [name for name in ('staff_wait', 'staff_done') if name in contracts]
    return (' Available staff controls: ' + ', '.join(names)
            + '; they follow their supplied schemas and do not establish business success.') if names else ''


def _swe_manual(request):
    contracts = _tool_contracts(request)
    manual = (
        'This declared interface uses the SWE-Next author OpenHands XML content protocol. '
        'You may give reasoning before the function call. Emit exactly one complete function call '
        'and no text after it:\n'
        '<function=FUNCTION_NAME>\n<parameter=PARAMETER_NAME>VALUE</parameter>\n</function>\n'
        'Only the actual function names and parameter names listed below are available. '
        'Do not add a tool_call wrapper or a JSON function-call wrapper. '
        'Supply every required argument once. Omit optional parameters when they are not needed; '
        'never emit an empty parameter name or a placeholder parameter element. '
        'If the public schema accepts an empty argument object, use an empty function body:\n'
        '<function=FUNCTION_NAME>\n</function>\n'
        'Do not insert <parameter=></parameter> or text such as "no params" into that body. '
        'For a parameter whose declared type is exactly string '
        '(including a local reference to that type), VALUE is literal text. One immediate LF after the '
        'opening parameter tag and one immediate LF before its closing tag form an optional paired '
        'structural frame; only that one pair is removed. Other spaces, indentation and extra LFs '
        'are preserved. To retain boundary LFs in a string value, put them inside that frame. '
        'For every other type, including type unions, VALUE is strict JSON of that declared type. '
        'XML-escape &, < and > inside all values as &amp;, &lt; and &gt;; no other decoding or type repair is applied. '
        'Do not invent tool results. Only actual tool responses establish execution.'
        + _control_guidance(contracts)
    )
    empty_calls = ['<function=' + name + '>\n</function>' for name, row in contracts.items()
                   if row['validator'].is_valid({})]
    if empty_calls:
        manual += ('\n\nIndependent syntax examples for functions whose supplied public schemas accept '
                   'no arguments. Choose only one call per decision; these examples do not prescribe '
                   'a task action:\n' + '\n'.join(empty_calls))
    return manual + '\n\nAvailable public functions and complete argument schemas:\n' + '\n'.join(
        json.dumps(row['definition'], ensure_ascii=False, sort_keys=True, allow_nan=False)
        for row in contracts.values())


def prepare_swe_xml_request(request, tokenizer):
    original = normalize_messages(request['messages'])
    messages, history = [], []
    contracts = _tool_contracts(request)
    for index, message in enumerate(original):
        calls = message.get('tool_calls') or []
        if message['role'] == 'assistant' and calls:
            if len(calls) != 1:
                raise ValueError('SWE XML history requires exactly one original call per tool round')
            function = calls[0]['function']
            name, arguments = function['name'], function['arguments']
            _validate_arguments(name, arguments, contracts)
            content = message.get('content') or ''
            preserved = False
            if content:
                candidate = _content_without_terminal_eos(content, QWEN_EOS)
                parsed_name, parsed_arguments = _read_xml_call(candidate, contracts)
                if parsed_name != name or parsed_arguments != arguments:
                    raise ValueError('Original XML history and structured public call disagree')
                text, preserved = candidate, True
            else:
                text = xml_call_text(name, arguments, request)
            messages.append({'role': 'assistant', 'content': text})
            history.append({'original_message_index': index, 'original_message_sha256': digest(json_bytes(message)),
                            'native_message_sha256': digest(json_bytes(messages[-1])),
                            'original_xml_content_preserved': preserved,
                            'operation': 'preserved XML content' if preserved else 'typed public-call serialization'})
        else:
            messages.append(copy.deepcopy(message))
    manual = _swe_manual(request)
    if messages and messages[0]['role'] == 'system':
        messages[0]['content'] += '\n\n' + manual
    else:
        messages.insert(0, {'role': 'system', 'content': manual})
    rendered = tokenizer.apply_chat_template(messages, tools=None, tokenize=False, add_generation_prompt=True)
    return rendered, messages, {
        'version': VERSION, 'native_format': SWE_FORMAT, 'author_repository_commit': SWE_AUTHOR_COMMIT,
        'native_tool_prompt': 'public_schema_single_xml_text_manual', 'hf_template_tools_argument': None,
        'public_manual_version': SWE_MANUAL_VERSION,
        'request_sha256': digest(json_bytes(request)),
        'normalized_messages_sha256': digest(json_bytes(original)),
        'actual_prompt_messages_sha256': digest(json_bytes(messages)),
        'public_tool_schemas_sha256': digest(json_bytes(request.get('tools') or [])),
        'public_manual_sha256': digest(manual.encode()), 'history_projection': history,
        'rendered_prompt_sha256': digest(rendered.encode()),
        'scope': 'Official Qwen chat boundaries with the author OpenHands XML variant: optional original reasoning prefix, one call, no suffix. One paired boundary LF is structural; all other value whitespace survives. Raw request and sampled output token trace remain unchanged; no JSON tool-template injection or fallback parser.',
    }


def _mistral_guidance(request):
    contracts = _tool_contracts(request)
    return (
        'For this declared interface, emit exactly one native [TOOL_CALLS]function_name[ARGS]{argument_object}. '
        'Only the supplied function names are available: ' + ', '.join(contracts) + '. '
        'Arguments must match that function\'s complete public schema. '
        'Multiple calls are rejected together. Only actual tool responses establish execution; never invent results.'
        + _control_guidance(contracts)
        + ' In a native_transport_envelope, original_tool_message is the unchanged real tool response; '
        'subsequent_user_messages contain later user instructions or observations, with their original roles '
        'and complete text. Use the latest such user message as the current user input. '
        'Do not attribute a controller observation to a sampled model action.'
    )


def prepare_mistral_v13_request(request, tokenizer):
    from mistral_common.protocol.instruct.request import ChatCompletionRequest
    if not isinstance(tokenizer, MistralNativeTokenizer):
        raise ValueError('Require the existing frozen official Mistral v13 tokenizer wrapper')
    original = normalize_messages(request['messages'])
    messages, role_projection = mistral_message_projection(original)
    hint = _mistral_guidance(request)
    if messages and messages[0]['role'] == 'system':
        messages[0]['content'] += '\n' + hint
    else:
        messages.insert(0, {'role': 'system', 'content': hint})
    native_request = ChatCompletionRequest.from_openai(
        messages=messages, tools=request.get('tools') or None,
        model=request.get('model'), tool_choice='auto')
    if native_request.truncate_for_context_length:
        raise ValueError('Native hidden truncation is forbidden')
    encoded = tokenizer.native.encode_chat_completion(native_request)
    text = tokenizer.decode(encoded.tokens)
    prompt = NativePrompt(text, encoded.tokens)
    return prompt, messages, {
        'version': VERSION, 'native_format': MISTRAL_FORMAT,
        'native_tool_prompt': 'provided_functions_only_v13',
        'native_input_ids_sha256': digest(json_bytes(encoded.tokens)),
        'request_sha256': digest(json_bytes(request)),
        'normalized_messages_sha256': digest(json_bytes(original)),
        'actual_prompt_messages_sha256': digest(json_bytes(messages)),
        'native_role_projection': role_projection,
        'public_tool_schemas_sha256': digest(json_bytes(request.get('tools') or [])),
        'rendered_prompt_sha256': digest(text.encode()),
        'scope': 'Original official v13 native IDs and transparent role envelope; guidance mentions only supplied functions. No sampled output tokens changed.',
    }


def parse_mistral_v13_generated(raw, request):
    message, error = parse_mistral_generated(raw, request)
    if error is not None:
        return message, error
    try:
        calls = message.get('tool_calls') or []
        if len(calls) != 1:
            raise ValueError('Exactly one provided native function is required')
        call = calls[0]
        # The v0.30 grammar parser has already identified the only ARGS object.
        # Re-read that raw object strictly to reject duplicate/nonfinite values.
        block = raw.removesuffix('</s>').strip().split('[TOOL_CALLS]', 1)[1].split('[ARGS]', 1)[1]
        arguments = strict_json(block)
        _validate_arguments(call['function']['name'], arguments, _tool_contracts(request))
        call['function']['arguments'] = json.dumps(arguments, ensure_ascii=False, allow_nan=False)
        call['id'] = _call_id(request, raw, length=9)
        return message, None
    except (ValueError, TypeError, KeyError, IndexError) as exception:
        return {'role': 'assistant', 'content': raw}, 'invalid_mistral_v13_v031: ' + str(exception)


def prepare_code_request(request, tokenizer, candidate_id):
    if candidate_id == 'swe-next-14b':
        return prepare_swe_xml_request(request, tokenizer)
    if candidate_id == 'devstral-small-2507':
        return prepare_mistral_v13_request(request, tokenizer)
    raise ValueError('Only the two declared v0.31 new-model operating combinations are supported')


def parse_code_response(raw, request, candidate_id):
    if candidate_id == 'swe-next-14b':
        return parse_swe_xml_generated(raw, request)
    if candidate_id == 'devstral-small-2507':
        return parse_mistral_v13_generated(raw, request)
    raise ValueError('Only the two declared v0.31 new-model operating combinations are supported')
