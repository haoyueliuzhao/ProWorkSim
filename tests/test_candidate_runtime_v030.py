"""Native tool syntax and exact prompt-token ownership; no model weights."""

import copy
import json

import pytest

from proworksim.candidate_runtime_v030 import (
    MistralNativeTokenizer, NativePrompt, candidate_profile, mistral_message_projection,
    parse_mistral_generated,
)


def test_native_prompt_retains_encoder_ids_without_text_retokenization():
    prompt = NativePrompt('[INST]hello[/INST]', [1, 100, 999, 101])
    tokenizer = object.__new__(MistralNativeTokenizer)
    assert tokenizer(prompt, add_special_tokens=False) == {'input_ids': [1, 100, 999, 101]}
    assert copy.deepcopy(prompt).input_ids == prompt.input_ids
    assert json.loads(json.dumps({'audit': prompt})) == {'audit': '[INST]hello[/INST]'}
    with pytest.raises(ValueError, match='original native'):
        tokenizer(str(prompt), add_special_tokens=False)


def test_mistral_native_call_ids_and_arguments_are_stable_and_exact():
    raw = '[TOOL_CALLS]read_file[ARGS]{"path":"app.py","start_line":1,"max_lines":180}</s>'
    request = {'messages': [{'role': 'user', 'content': 'Inspect code'}]}
    first, error = parse_mistral_generated(raw, request)
    assert error is None
    assert len(first['tool_calls']) == 1
    call = first['tool_calls'][0]
    assert len(call['id']) == 9 and call['id'].isalnum()
    assert json.loads(call['function']['arguments']) == {'path': 'app.py', 'start_line': 1, 'max_lines': 180}
    assert parse_mistral_generated(raw, request)[0] == first
    assert parse_mistral_generated(raw, {'messages': []})[0] != first


@pytest.mark.parametrize('raw', [
    '[TOOL_CALLS]one[ARGS]{}[TOOL_CALLS]two[ARGS]{}</s>',
    '[TOOL_CALLS]one[ARGS]{"path":',
    '[TOOL_CALLS]one[ARGS]"not an object"</s>',
    '[TOOL_CALLS] [{"name":"one","arguments":{}}]</s>',
])
def test_bad_native_output_is_not_repaired_into_a_tool_call(raw):
    message, error = parse_mistral_generated(raw, {})
    assert error
    assert 'tool_calls' not in message
    assert message['content'] == raw.removesuffix('</s>').strip()


def test_fixed_models_have_single_gpu_and_unchanged_original_probability_gate():
    for name in ('swe-next-14b', 'devstral-small-2507'):
        profile = candidate_profile(name)
        assert profile['devices'] == 1
        assert profile['max_context_tokens'] == 16384
        assert profile['max_output_tokens'] == 2048
        assert profile['logprob_max_atol'] == 0.02
        assert profile['logprob_mean_atol'] == 0.002
        assert profile['top_p'] == 1 and profile['top_k'] == 0
    with pytest.raises(ValueError, match='two predeclared'):
        candidate_profile('new-model-after-seeing-low-scores')


def test_native_role_projection_keeps_every_original_message_without_fake_ack():
    messages = [
        {'role': 'system', 'content': 'system'},
        {'role': 'user', 'content': 'initial real observation'},
        {'role': 'assistant', 'tool_calls': [{'id': 'abcdef123', 'function': {'name': 'read_file', 'arguments': {}}}], 'content': ''},
        {'role': 'tool', 'tool_call_id': 'abcdef123', 'content': '{"error":"FileNotFoundError"}'},
        {'role': 'user', 'content': 'current real observation'},
        {'role': 'user', 'content': 'separate actual feedback'},
    ]
    original = copy.deepcopy(messages)
    selected, proof = mistral_message_projection(messages)
    assert messages == original
    assert [m['role'] for m in selected] == ['system', 'user', 'assistant', 'tool']
    envelope = json.loads(selected[-1]['content'])
    assert envelope['original_tool_message'] == messages[3]
    assert [row['message'] for row in envelope['subsequent_user_messages']] == messages[4:]
    assert proof['source_message_indices_per_native_message'] == [[0], [1], [2], [3, 4, 5]]
    assert selected[:3] == messages[:3]
    assert selected[-1]['tool_call_id'] == messages[3]['tool_call_id']
