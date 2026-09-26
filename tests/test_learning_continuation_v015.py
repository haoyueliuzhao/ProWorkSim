"""One CPU wiring check for original S1 source -> future pilot source."""
import json
from pathlib import Path

from scripts import continue_learning_v015 as continuation
from scripts.run_learning_pilot_v015 import normalize_config


def test_selection_handoff_preserves_original_protocol_and_uses_new_execution_source(tmp_path, monkeypatch):
    old = tmp_path/'screen-source'
    old.mkdir()
    protocol = old/'screen.json'
    actual = Path(__file__).resolve().parents[1]/'examples/learning-v15/screen-chatstop-qwen35-9b.json'
    protocol.write_bytes(actual.read_bytes())
    config = {'project': str(tmp_path), 'source': str(tmp_path/'future-pilot-source'), 'source_commit': 'fixture',
              'python': '/fixture/model-python', 'launcher_python': '/fixture/plain-python',
              'launcher': '/fixture/launcher.py', 'environment': {}, 'launch_directory': str(tmp_path/'launch'),
              'study_manifest': str(tmp_path/'manifest.json'), 'screen_supervisor': str(tmp_path/'supervisor.json')}
    for key in ('study_manifest', 'screen_supervisor'):
        Path(config[key]).write_text('{}')
    job = {'name': 'qwen35-9b', 'model_path': str(tmp_path/'model'), 'weight_manifest': str(tmp_path/'weights.json')}
    supervisor = {'status': 'complete', 'jobs': [{'name': 'qwen35-9b', 'status': 'complete'}],
                  'config': {'source': str(old), 'candidates': [job]}}
    def report(_, *, project_root, source_root):
        assert source_root == str(old)
        return {'fixture': 'not a model measurement'}
    def write_report(value, destination):
        destination.mkdir()
        (destination/'report.json').write_text(json.dumps(value))
    monkeypatch.setattr(continuation, 'build_report', report)
    monkeypatch.setattr(continuation, 'write_report', write_report)
    monkeypatch.setattr(continuation, 'resource_report', lambda _: {})
    monkeypatch.setattr(continuation, 'validated_readiness', lambda *_: {'qwen35-9b': True})
    monkeypatch.setattr(continuation, 'choose', lambda *_: {'status': 'selected', 'selected': {
        'candidate_id': 'qwen35-9b', 'screen_protocol': continuation.ref(protocol)}})
    output = tmp_path/'continuation'
    output.mkdir()
    pilot, _ = continuation.after_screen(config, supervisor, output)
    normalized = normalize_config(pilot)
    assert normalized['source'] == config['source']
    assert normalized['selected_screen_protocol'] == str(protocol)
    assert normalized['physical_gpus'] == {'mc': [0], 'rtg': [1]}
    assert Path(normalized['selection_record']).is_file()
