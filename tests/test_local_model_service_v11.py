from proworksim.local_model_service import completed_tokens, parse_generated


def test_all_calls_retained_and_one_malformed_block_prevents_partial_execution():
    good = '<tool_call>{"name":"read_object","arguments":{"alias":"a"}}</tool_call>'
    message, error = parse_generated(good + good)
    assert error is None
    assert len(message['tool_calls']) == 2
    for malformed in ['<tool_call>{nope}</tool_call>', '<tool_call>{"name":']:
        message, error = parse_generated(good + malformed)
        assert error
        assert 'tool_calls' not in message
        assert good in message['content']


def test_text_is_not_fabricated_into_a_tool_action():
    message, error = parse_generated('Finished the task.<|im_end|>')
    assert error is None
    assert message == {'role': 'assistant', 'content': 'Finished the task.'}


def test_both_configured_eos_tokens_stop_before_batch_padding():
    assert completed_tokens([7, 151643, 151645, 151645], [151645, 151643]) == ([7, 151643], True)
    assert completed_tokens([7, 151645, 151645], [151645, 151643]) == ([7, 151645], True)
    assert completed_tokens([7, 8], [151645, 151643]) == ([7, 8], False)
