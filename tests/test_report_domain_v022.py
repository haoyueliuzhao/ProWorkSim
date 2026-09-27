import json

from scripts.report_domain_v022 import calls, decode_json_stream, summarize


def test_resource_stream_pretty_jsonl_and_partial_tail():
    first = {'sample': {'time': 1, 'gpus': {'stdout': 'a\nb'}}}
    second = {'sample': {'time': 2}}
    raw = json.dumps(first, indent=2) + '\n' + json.dumps(second) + '\n'
    rows, metadata = decode_json_stream(raw)
    assert rows == [first, second]
    assert metadata['complete'] is True
    rows, metadata = decode_json_stream(raw + '{"sample":')
    assert rows == [first, second]
    assert metadata['complete'] is False
    assert metadata['tail_characters'] > 0


def test_snapshot_unknown_and_final_cost_preserve_original_failure(tmp_path):
    def save(line, state, report):
        folder = tmp_path / line
        (folder / 'actual').mkdir(parents=True, exist_ok=True)
        (folder / 'state.json').write_text(json.dumps(state))
        (folder / 'actual/report.json').write_text(json.dumps(report))

    for name, seconds in [('N1', 10), ('W1', 20), ('B1', 30)]:
        save(name, {'status': 'stopped' if name == 'B1' else 'complete', 'started_at': 1,
                    'ended_at': seconds + 1, 'exit_code': -15 if name == 'B1' else 0,
                    'elapsed_gpu_seconds': seconds}, {'status': 'updating' if name == 'B1' else 'complete'})
    save('R1', {'status': 'running', 'started_at': 100}, {'status': 'recomputing_original_update'})
    snapshot = summarize(tmp_path)
    assert snapshot['final'] is False
    assert snapshot['accounting']['known_terminated_gpu_seconds'] == 60
    assert snapshot['accounting']['final_gpu_seconds'] is None
    assert snapshot['accounting']['within_total_gpu_budget'] is None
    assert snapshot['lines']['B1']['execution_terminal'] is True
    assert snapshot['lines']['B1']['update']['terminal_actor_steps'] is None
    assert snapshot['lines']['R1']['update']['gradient_probability'] is None
    assert snapshot['lines']['R1']['update']['terminal_actor_steps'] is None
    assert snapshot['lines']['R1']['post_development']['terminal_closed_count'] is None
    save('R1', {'status': 'complete', 'started_at': 100, 'ended_at': 140, 'exit_code': 0,
                'elapsed_gpu_seconds': 40}, {'status': 'complete', 'actor_steps': 1, 'critic_steps': 1})
    final = summarize(tmp_path)
    assert final['final'] is True
    assert final['accounting']['final_gpu_seconds'] == 100
    assert final['accounting']['known_terminated_by_line']['B1'] == 30
    assert final['lines']['R1']['update']['terminal_actor_steps'] == 1


def test_only_explicit_context_400_counts_as_context_rejection(tmp_path):
    folder = tmp_path / 'resident/calls'
    folder.mkdir(parents=True)
    for index, code in enumerate(['context_length_exceeded', 'invalid_request', None]):
        row = {'status': 400, 'raw_output_ids': [], 'response': {'error': {'code': code}}}
        (folder / f'{index}.json').write_text(json.dumps(row))
    report = calls(tmp_path)['observed_totals']
    assert report['attempts'] == 3
    assert report['local_context_400'] == 1
    assert report['other_or_unclassified'] == 2
