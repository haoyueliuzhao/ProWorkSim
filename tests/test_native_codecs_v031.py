"""Native v0.31 codec controls; no model weights, generation or GPU execution."""

import copy
import json
from pathlib import Path

import pytest

pytest.importorskip('jsonschema', reason='Run these controls in the existing managed SDK/resident environment')

from proworksim.native_codecs_v031 import (  # noqa: E402
    MISTRAL_FORMAT, SWE_FORMAT, SWE_MANUAL_VERSION, _swe_manual, parse_code_response, parse_mistral_v13_generated,
    parse_swe_xml_generated, prepare_code_request, prepare_swe_xml_request, xml_call_text,
)

ROOT = Path(__file__).resolve().parents[1]


def tools():
    return [{'type': 'function', 'function': {'name': 'record_fact', 'description': 'Record public values.',
        'parameters': {'type': 'object', 'properties': {
            'code': {'type': 'string'}, 'revision': {'type': 'integer', 'minimum': 0},
            'payload': {'type': 'object', 'properties': {
                'items': {'type': 'array', 'items': {'type': ['string', 'integer']}},
                'enabled': {'type': 'boolean'}, 'reference': {'$ref': '#/$defs/reference'},
            }, 'required': ['items', 'enabled', 'reference'], 'additionalProperties': False},
            'optional_value': {'type': ['string', 'null']},
        }, 'required': ['code', 'revision'], 'additionalProperties': False,
            '$defs': {'reference': {'type': 'object', 'properties': {
                'version': {'type': 'integer'}, 'label': {'type': 'string'},
            }, 'required': ['version', 'label'], 'additionalProperties': False}}}}}]


def request():
    return {'messages': [{'role': 'system', 'content': 'Use only public facts.'},
                         {'role': 'user', 'content': 'Perform the public operation.'}],
            'tools': tools(), 'temperature': 0.7, 'max_tokens': 2048}


def decoded(raw, supplied=None):
    message, error = parse_swe_xml_generated(raw, supplied or request())
    assert error is None
    return json.loads(message['tool_calls'][0]['function']['arguments'])


def test_xml_preserves_nested_json_types_string_whitespace_and_delimiter_literals():
    expected = {'code': '  <parameter=x>literal &amp;\n</parameter>  ', 'revision': 17,
                'payload': {'items': ['alpha', 4], 'enabled': True,
                            'reference': {'version': 2, 'label': '<tag>'}},
                'optional_value': None}
    wire = xml_call_text('record_fact', expected, request())
    assert decoded(wire + '<|im_end|>') == expected
    assert '&lt;parameter=' in wire and '&amp;amp;' in wire
    expected['optional_value'] = 'null'
    assert decoded(xml_call_text('record_fact', expected, request())) == expected


@pytest.mark.parametrize('raw', [
    '<function=execute_bounded_tool>{"name":"record_fact","arguments":{"code":"x","revision":17}}</function>',
    '<function=record_fact><parameter=code>x</parameter><parameter=revision>17</parameter><parameter=extra>1</parameter></function>',
    '<function=record_fact><parameter=code>x</parameter><parameter=code>y</parameter><parameter=revision>17</parameter></function>',
    '<function=record_fact><parameter=code>x</parameter></function>',
    '<function=record_fact><parameter=code>x</parameter><parameter=revision>true</parameter></function>',
    '<function=record_fact><parameter=code>x</parameter><parameter=revision>17.0</parameter></function>',
    '<function=record_fact><parameter=code>x</parameter><parameter=revision>NaN</parameter></function>',
    '<function=record_fact><parameter=code>x</parameter><parameter=revision>-1</parameter></function>',
    '<function=record_fact><parameter=code>x</parameter><parameter=revision>17</parameter></function><function=record_fact></function>',
    '<tool_call>{"name":"record_fact","arguments":{"code":"x","revision":17}}</tool_call>',
    '<tool_call><function=record_fact><parameter=code>x</parameter><parameter=revision>17</parameter></function></tool_call>',
    '<function=record_fact><parameter=code>x</parameter><parameter=revision>17</parameter></function> unexpected suffix',
    '<function=record_fact><parameter=code>x</parameter><parameter=revision>17</parameter></function><|im_end|><|im_end|>',
])
def test_one_declared_xml_protocol_rejects_unsupported_or_ambiguous_outputs(raw):
    before = raw
    message, error = parse_swe_xml_generated(raw, request())
    assert error and not message.get('tool_calls')
    assert message['content'] == before


@pytest.mark.parametrize('payload', [
    '{"items":[true],"enabled":true,"reference":{"version":2,"label":"ok"}}',
    '{"items":[1],"enabled":"true","reference":{"version":2,"label":"ok"}}',
    '{"items":[1],"enabled":true,"reference":{"version":2.0,"label":"ok"}}',
    '{"items":[1],"enabled":true,"reference":{"version":2,"label":"ok","hidden":1}}',
    '{"items":[1],"items":[2],"enabled":true,"reference":{"version":2,"label":"ok"}}',
])
def test_nested_schema_constraints_and_duplicate_json_keys_are_not_repaired(payload):
    raw = ('<function=record_fact><parameter=code>x</parameter><parameter=revision>17</parameter>'
           '<parameter=payload>' + payload + '</parameter></function>')
    message, error = parse_swe_xml_generated(raw, request())
    assert error and not message.get('tool_calls')


class CapturingTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        self.messages, self.kwargs = copy.deepcopy(messages), kwargs
        return json.dumps(messages, ensure_ascii=False)


def test_swe_render_disables_hf_json_tools_and_preserves_public_input_and_history():
    supplied = request()
    raw = xml_call_text('record_fact', {'code': 'x', 'revision': 17}, supplied)
    assistant, error = parse_swe_xml_generated(raw + '<|im_end|>', supplied)
    assert error is None
    supplied['messages'].extend([assistant, {'role': 'tool', 'tool_call_id': assistant['tool_calls'][0]['id'],
                                           'content': '{"recorded":true}'},
                                {'role': 'user', 'content': 'Continue from the real result.'}])
    original = copy.deepcopy(supplied)
    tokenizer = CapturingTokenizer()
    rendered, actual, projection = prepare_swe_xml_request(supplied, tokenizer)
    assert supplied == original
    assert tokenizer.kwargs == {'tools': None, 'tokenize': False, 'add_generation_prompt': True}
    assert actual[2] == {'role': 'assistant', 'content': raw}
    assert actual[3] == supplied['messages'][3]
    assert 'staff_done' not in actual[0]['content'] and 'staff_wait' not in actual[0]['content']
    assert 'execute_bounded_tool' not in rendered
    assert projection['history_projection'][0]['original_xml_content_preserved']
    assert projection['native_format'] == SWE_FORMAT


def test_swe_history_must_agree_with_original_structured_call():
    supplied = request()
    assistant, _ = parse_swe_xml_generated(
        '<function=record_fact><parameter=code>x</parameter><parameter=revision>17</parameter></function>', supplied)
    assistant['tool_calls'][0]['function']['arguments'] = '{"code":"y","revision":17}'
    supplied['messages'].append(assistant)
    with pytest.raises(ValueError, match='history and structured public call disagree'):
        prepare_swe_xml_request(supplied, CapturingTokenizer())


def test_local_ref_string_and_composition_arguments_remain_typed():
    supplied = request()
    params = supplied['tools'][0]['function']['parameters']
    params['properties']['code'] = {'$ref': '#/$defs/raw_string'}
    params['$defs']['raw_string'] = {'type': 'string', 'minLength': 1}
    params['properties']['mixed'] = {'oneOf': [{'type': 'null'}, {'type': 'object',
        'properties': {'value': {'type': 'number'}}, 'required': ['value'], 'additionalProperties': False}]}
    expected = {'code': 'raw value', 'revision': 2, 'mixed': {'value': 1.5}}
    assert decoded(xml_call_text('record_fact', expected, supplied), supplied) == expected


def test_mistral_rejects_unprovided_staff_done_and_duplicate_args_without_changing_format():
    supplied = request()
    raw = '[TOOL_CALLS]record_fact[ARGS]{"code":"x","revision":17}</s>'
    message, error = parse_mistral_v13_generated(raw, supplied)
    assert error is None
    assert len(message['tool_calls'][0]['id']) == 9
    for invalid in ['[TOOL_CALLS]staff_done[ARGS]{}</s>',
                    '[TOOL_CALLS]record_fact[ARGS]{"code":"x","code":"y","revision":17}</s>',
                    '[TOOL_CALLS]record_fact[ARGS]{"code":"x","revision":true}</s>']:
        message, error = parse_mistral_v13_generated(invalid, supplied)
        assert error and not message.get('tool_calls')
        assert message['content'] == invalid


def test_actual_frozen_swe_tokenizer_uses_only_author_xml_content_protocol():
    transformers = pytest.importorskip('transformers')
    path = ROOT / 'runs/assets/models/swe-next-14b-5d9484d6b0e2'
    if not (path / 'tokenizer.json').exists():
        pytest.skip('Fixed tokenizer metadata is not present')
    tokenizer = transformers.AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    supplied = request()
    raw = xml_call_text('record_fact', {'code': 'cpu-tokenizer-only', 'revision': 17}, supplied)
    parsed, error = parse_code_response(raw + '<|im_end|>', supplied, 'swe-next-14b')
    assert error is None
    supplied['messages'].extend([parsed, {'role': 'tool', 'tool_call_id': parsed['tool_calls'][0]['id'],
                                        'content': '{"ok":false,"error":"actual CPU protocol fixture"}'},
                                {'role': 'user', 'content': 'Read the actual feedback and continue.'}])
    rendered, messages, projection = prepare_code_request(supplied, tokenizer, 'swe-next-14b')
    ids = tokenizer(rendered, add_special_tokens=False)['input_ids']
    assert len(ids) + 2048 <= 16384
    assert '<|im_start|>assistant\n<function=record_fact>' in rendered
    assert 'For each function call, return a json object' not in rendered
    assert 'staff_done' not in rendered
    assert messages[-2]['content'] == supplied['messages'][-2]['content']
    assert projection['hf_template_tools_argument'] is None


def test_actual_frozen_mistral_v13_ids_and_tool_user_envelope():
    pytest.importorskip('mistral_common')
    from mistral_common.protocol.instruct.messages import AssistantMessage
    from mistral_common.protocol.instruct.tool_calls import FunctionCall, ToolCall
    from proworksim.candidate_runtime_v030 import MistralNativeTokenizer, NativePrompt
    path = ROOT / 'runs/assets/models/devstral-small-2507-bd165ab26ceb'
    if not (path / 'tekken.json').exists():
        pytest.skip('Fixed tokenizer metadata is not present')
    tokenizer = MistralNativeTokenizer(path)
    supplied = request()
    assistant = AssistantMessage(tool_calls=[ToolCall(id='cpu000001',
        function=FunctionCall(name='record_fact', arguments={'code': 'cpu-only', 'revision': 17}))])
    output_ids = tokenizer.native.instruct_tokenizer.encode_assistant_message(
        assistant, is_before_last_user_message=False, continue_message=False)
    raw = tokenizer.decode(output_ids)
    message, error = parse_code_response(raw, supplied, 'devstral-small-2507')
    assert error is None
    response = {'role': 'tool', 'tool_call_id': message['tool_calls'][0]['id'],
                'content': '{"ok":false,"error":"CPU native role fixture"}'}
    user = {'role': 'user', 'content': 'Use this later public instruction without inventing a result.'}
    supplied['messages'].extend([message, response, user])
    before = copy.deepcopy(supplied)
    rendered, messages, projection = prepare_code_request(supplied, tokenizer, 'devstral-small-2507')
    assert supplied == before and isinstance(rendered, NativePrompt)
    assert tokenizer(rendered, add_special_tokens=False)['input_ids'] == list(rendered.input_ids)
    assert len(rendered.input_ids) + 2048 <= 16384
    assert 'staff_done' not in messages[0]['content'] and 'staff_wait' not in messages[0]['content']
    envelope = json.loads(messages[-1]['content'])
    assert envelope['original_tool_message'] == response
    assert envelope['subsequent_user_messages'][-1]['message'] == user
    assert projection['native_format'] == MISTRAL_FORMAT
    supplied['tools'].append({'type': 'function', 'function': {'name': 'staff_done', 'description': 'Stop.',
        'parameters': {'type': 'object', 'properties': {'reason': {'type': 'string'}},
                       'required': ['reason'], 'additionalProperties': False}}})
    _, messages, _ = prepare_code_request(supplied, tokenizer, 'devstral-small-2507')
    assert 'staff_done' in messages[0]['content'] and 'staff_wait' not in messages[0]['content']


def test_mistral_existing_prefix_is_not_misread_as_the_actual_args_object():
    raw = 'Native syntax uses [ARGS].\n[TOOL_CALLS]record_fact[ARGS]{"code":"x","revision":17}</s>'
    message, error = parse_mistral_v13_generated(raw, request())
    assert error is None
    assert message['content'] == 'Native syntax uses [ARGS].'
    assert json.loads(message['tool_calls'][0]['function']['arguments']) == {'code': 'x', 'revision': 17}


def test_author_openhands_reasoning_prefix_is_preserved_with_exactly_one_call():
    supplied = request()
    raw = 'I will record the observed public values.\n<function=record_fact>\n<parameter=code>x</parameter>\n<parameter=revision>17</parameter>\n</function>'
    message, error = parse_swe_xml_generated(raw + '<|im_end|>', supplied)
    assert error is None and message['content'] == raw
    supplied['messages'].append(message)
    _, actual, projection = prepare_swe_xml_request(supplied, CapturingTokenizer())
    assert actual[-1]['content'] == raw
    assert projection['history_projection'][-1]['original_xml_content_preserved']


def test_author_multiline_parameter_frame_does_not_become_path_or_string_data():
    supplied = {'tools': [{'type': 'function', 'function': {'name': 'file_editor',
        'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'},
            'file_text': {'type': 'string'}}, 'required': ['path', 'file_text'], 'additionalProperties': False}}}]}
    raw = ('Reasoning before the author-style function call.\n<function=file_editor>\n'
           '<parameter=path>\npublic-note.json\n</parameter>\n'
           '<parameter=file_text>\nThis value\ncan span\nmultiple lines\n</parameter>\n</function>')
    assert decoded(raw, supplied) == {'path': 'public-note.json', 'file_text': 'This value\ncan span\nmultiple lines'}


def test_exact_string_framing_preserves_code_indentation_and_additional_boundary_lfs():
    supplied = request()
    expected = {'code': '\n    def f():\n        return " leading and trailing spaces "  \n\n', 'revision': 17}
    assert decoded(xml_call_text('record_fact', expected, supplied), supplied) == expected
    # Author parser accepts layout whitespace around the equals-form tag; this
    # remains the same XML protocol, not an attribute-form or JSON fallback.
    raw = '<function = record_fact >\n<parameter = code >\n    keep indentation  \n</parameter>\n<parameter = revision >17</parameter>\n</function>'
    assert decoded(raw, supplied) == {'code': '    keep indentation  ', 'revision': 17}


EMPTY_PARAMETER_CASES = json.loads(
    (ROOT / 'tests/fixtures/native_swe_empty_parameter_v031r3.json').read_text()
)['cases']


@pytest.mark.parametrize('case', EMPTY_PARAMETER_CASES)
def test_saved_actual_empty_parameter_outputs_remain_rejected_and_empty_calls_pass(case):
    supplied = {'tools': [case['tool']]}
    message, error = parse_swe_xml_generated(case['raw_generated_text'], supplied)
    assert error == case['protocol_parse_error']
    assert message == {'role': 'assistant', 'content': case['raw_generated_text']}
    name = case['tool']['function']['name']
    assert decoded('<function=' + name + '>\n</function><|im_end|>', supplied) == {}


def test_saved_actual_schema_violation_remains_rejected_without_correcting_value():
    case = json.loads((ROOT / 'tests/fixtures/native_swe_schema_rejection_v031r3.json').read_text())['cases'][0]
    message, error = parse_swe_xml_generated(case['raw_generated_text'], {'tools': [case['tool']]})
    assert error == case['protocol_parse_error']
    assert '200 is greater than the maximum of 180' in error
    assert message == {'role': 'assistant', 'content': case['raw_generated_text']}


def test_empty_call_manual_examples_depend_only_on_complete_public_schemas():
    supplied = request()
    supplied['tools'].extend(copy.deepcopy(case['tool']) for case in EMPTY_PARAMETER_CASES[::2])
    # No top-level required field, but the complete schema still forbids {}.
    supplied['tools'].append({'type': 'function', 'function': {'name': 'constrained_optional',
        'parameters': {'type': 'object', 'properties': {'flag': {'type': 'boolean'}},
                       'allOf': [{'minProperties': 1}], 'additionalProperties': False}}})
    original = copy.deepcopy(supplied)
    manual = _swe_manual(supplied)
    for name in ('run_tests', 'diff_workspace'):
        assert '<function=' + name + '>\n</function>' in manual
    for name in ('record_fact', 'constrained_optional', 'staff_wait', 'staff_done', 'unprovided_tool'):
        assert '<function=' + name + '>' not in manual
    assert 'Omit optional parameters' in manual
    assert 'never emit an empty parameter name' in manual
    supplied['messages'] = [{'role': 'user', 'content': 'SECRET_TASK_ANSWER_NEVER_IN_MANUAL'}]
    assert _swe_manual(supplied) == manual
    assert 'SECRET_TASK_ANSWER_NEVER_IN_MANUAL' not in manual
    _, _, projection = prepare_swe_xml_request(original, CapturingTokenizer())
    assert projection['public_manual_version'] == SWE_MANUAL_VERSION
    assert projection['version'] == 'native-codecs-v0.31'
