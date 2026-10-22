"""Small r2 scope/restore adapter control; r1 codec controls remain reusable."""
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
spec = importlib.util.spec_from_file_location('history_r2_control_target', ROOT / 'tools/archive_closed_history_text_v055_r2.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
real_candidates = m.candidates()
assert len(real_candidates) == len(set(real_candidates)) == 261
assert not any(p.name == 'pretraining-admission.json' for p in real_candidates)
assert not any(p.parent.name.startswith('software-learning-v050-resume-') and p.name == 'entries.json' for p in real_candidates)
original_codec = m.codec.digest_path(m.CODEC)
fixture = Path(tempfile.mkdtemp(prefix='pws-history-text-r2-control-', dir='/tmp'))
m.ROOT, m.OUT = fixture, fixture / 'archive'
m.OUT.mkdir()
a = fixture / 'runs/closed/runtime.json'
b = fixture / 'runs/closed/experience.json'
a.parent.mkdir(parents=True)
body = b'{"historical_fixture":true}\n' * 1024
a.write_bytes(body)
b.write_bytes(body)
m.CANDIDATES = fixture / 'candidates.json'
m.CANDIDATES.write_text('{}')
supervisor = m.codec.put(fixture / 'supervisor.json', {'status': 'complete', 'ended_at': 1})
audit = m.codec.put(fixture / 'audit.json', {'queue_exhausted': True, 'current_seeds': {'fixture': True}})
rows = [{'original': m.codec.digest_path(p), 'identity': m.codec.identity(p),
         'supervisor': {'reference': supervisor}} for p in (a, b)]
plan = {'version': m.VERSION, 'source': m.codec.digest_path(m.__file__),
        'codec_source': original_codec, 'candidate_manifest': m.codec.digest_path(m.CANDIDATES),
        'candidate_count': 2, 'current_reference_audit': audit, 'allowlist': rows,
        'excluded_candidates': [], 'content_groups': {rows[0]['original']['sha256']: [str(a), str(b)]},
        'default_restore_root': str(m.OUT / 'restored')}
plan_ref = m.codec.put(m.OUT / 'plan.json', plan)
class Space:
    free = 1024**4

with patch.object(m, 'candidates', return_value=[a, b]), \
        patch.object(m, 'current_seeds', return_value={'fixture': True}), \
        patch.object(m, 'process_use', return_value={'matches': [], 'fixture_only': True}), \
        patch.object(m.shutil, 'disk_usage', return_value=Space()):
    summary_ref = m.archive(plan_ref)
    summary = m.codec.load_ref(summary_ref)
    assert summary['archived_paths'] == 2 and summary['unique_archive_objects'] == 1
    assert not summary['failures'] and not a.exists() and not b.exists()
    marker = json.loads(a.with_name(a.name + '.archive.json').read_bytes())
    assert marker['restore_tool'] == m.__file__
    m.configure(plan_ref)
    m.codec.restore(plan_ref, selected=str(a))
    restored = m.OUT / 'restored/runs/closed/runtime.json'
    assert restored.read_bytes() == body and not a.exists()
    try:
        m.codec.restore(plan_ref, selected=str(a))
    except FileExistsError:
        pass
    else:
        raise AssertionError('r2 restore overwrote existing output')
    escaped = dict(plan, allowlist=[{**rows[0], 'original': {**rows[0]['original'], 'path': str(fixture / 'outside.json')}}])
    escaped_ref = m.codec.put(m.OUT / 'escaped-plan.json', escaped)
    try:
        m.configure(escaped_ref)
    except ValueError:
        pass
    else:
        raise AssertionError('r2 plan escaped its candidate allowlist')
assert m.codec.digest_path(m.CODEC) == original_codec
meta = fixture / 'host-metadata.json'
meta.write_text(json.dumps({'refs': [str(a)] * 5000, 'self': str(meta)}))
with patch.object(m, 'current_seeds', return_value={'path': str(meta)}):
    observed = m.reference_audit([a, b])
assert observed['candidate_matches'] == [str(a)]
assert observed['pending_queue_payload'] == 'deduplicated_paths_only_not_parsed_documents'
assert observed['peak_pending_paths'] == 1
out = ROOT / 'artifacts/software-benchmark-v055/history-text-archive-r2/cpu-control-r2.json' 
print(json.dumps(m.codec.put(out, {'version': 'v055-history-text-r2-adapter-control', 'passed': True,
    'checks': ['261_distinct_fixed_candidates', 'old_14_paths_not_repeated',
               'r2_markers_name_r2_restore_tool', 'r2_scope_escape_rejected',
               'r2_default_restore_new_directory_exact', 'restore_overwrite_rejected',
               'r1_codec_source_unchanged', 'reference_queue_is_deduplicated_paths_only',
               'exact_live_dependency_match_recorded'],
    'real_historical_files_modified': 0, 'model_calls': 0, 'fixture': str(fixture),
    'source': m.codec.digest_path(m.__file__), 'codec_source': original_codec,
    'control_source': m.codec.digest_path(__file__)})))
