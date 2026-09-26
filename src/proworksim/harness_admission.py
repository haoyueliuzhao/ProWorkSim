"""H1 launch admission before model/dependency loading; no queue or model work.

Planning protocols fail closed. This first gate supports only the complete
three-arm original S1 and both new candidate H1 arms. Single-model fallback
requires a separately reviewed protocol revision, never an unfinished peer.
"""
import copy
import importlib
from pathlib import Path
import sys

from .storage import digest, json_bytes, read_json

VERSION = 'h1-launch-admission-v0.16'
NEW = {'qwen35-9b', 'qwen38-27b'}
ALL = NEW | {'qwen25-7b'}
SOURCE_FILES = ('scripts/online_learning_v015.py', 'scripts/build_harness_study_v016.py',
                'src/proworksim/harness_admission.py', 'src/proworksim/harness_collection.py',
                'src/proworksim/harness_sdk.py', 'src/proworksim/harness_port.py',
                'src/proworksim/harness_runtime.py')


def require(condition, message):
    if not condition:
        raise ValueError('H1 admission: ' + message)


def checked_ref(record, *, root=None):
    require(isinstance(record, dict) and record.get('path') and record.get('sha256'), 'missing immutable file reference')
    path = Path(record['path'])
    if not path.is_absolute():
        require(root is not None, 'relative evidence needs an explicit root')
        path = Path(root) / path
    require(path.is_file() and digest(path.read_bytes()) == record['sha256'], 'evidence bytes changed: ' + str(path))
    return path.resolve()


def body_hash(protocol):
    body = copy.deepcopy(protocol)
    body.pop('launch_gate', None)
    return digest(json_bytes(body))


def _helpers():
    # The common runner is also invoked by filename, where only scripts/ and
    # src/ are on sys.path. Resolve these local, committed helpers explicitly.
    root = str(Path(__file__).resolve().parents[2])
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        return (importlib.import_module('scripts.build_harness_study_v016'),
                importlib.import_module('scripts.select_candidate_v015'))
    finally:
        if added:
            sys.path.remove(root)


def _guard(value):
    before = value.get('learning_before_sha256')
    require(value.get('learning_unchanged') is True and value.get('rng_restored_exactly') is True
            and isinstance(before, dict) and bool(before) and before == value.get('learning_after_sha256')
            and value.get('rng_before_sha256') and value['rng_before_sha256'] == value.get('rng_after_restore_sha256'),
            'actual evaluation learning/RNG guard did not pass')


def validate_h1_launch(protocol, *, model_path, weight_manifest, restore_checkpoint=None,
                       source_identity=None, source_root=None):
    """Return immutable admission evidence; non-H1 protocols retain old behavior."""
    gate = protocol.get('launch_gate', {})
    h1 = (protocol.get('stage') == 'H1_development' or gate.get('version') == VERSION
          or any(w.get('stage') == 'H1_development' for w in protocol.get('windows', [])))
    if not h1:
        return {'status': 'not_H1', 'original_execution_contract_unchanged': True}
    require(gate.get('version') == VERSION and gate.get('state') == 'admitted',
            'planning-only H1 protocol is not executable; global admission is absent')
    require(not restore_checkpoint, 'H1 must start from the fresh public base, never restore a checkpoint')
    path = checked_ref(gate.get('admission'))
    admission = read_json(path)
    require(admission.get('version') == VERSION and admission.get('status') == 'admitted', 'formal admission is not complete')
    require(set(admission.get('protocol_body_sha256', {})) == NEW, 'this gate requires both H1 model arms; single-model downgrade needs a protocol revision')
    candidate = protocol.get('candidate_id')
    require(candidate in NEW and admission['protocol_body_sha256'][candidate] == body_hash(protocol), 'H1 protocol body differs from admitted recipe/budgets')
    root = Path(source_root or Path(__file__).resolve().parents[2]).resolve()
    if source_identity is None:
        from .audit import code_identity
        source_identity = code_identity()
    require(source_identity.get('code_dirty') is False and source_identity.get('code_commit')
            and source_identity == admission.get('source_identity'), 'current source is dirty or differs from final admitted source')
    files = admission.get('source_files', {})
    require(set(files) == set(SOURCE_FILES) and all(digest((root / name).read_bytes()) == expected for name, expected in files.items()),
            'runner/harness/builder file differs from admitted source')
    expected_harness = protocol.get('harness_identity', {}).get('openhands_v16')
    require(isinstance(expected_harness, dict) and expected_harness == admission.get('harness_identity'), 'final harness version/SDK/context identity differs')
    require(protocol.get('mode') == 'evaluate' and all(w.get('mode') == 'evaluate' for w in protocol.get('windows', []))
            and protocol.get('expected_optimizer_steps') == {'actor': 0, 'critic': 0}
            and protocol.get('initialization', {}).get('restore_checkpoint_permitted') is False
            and protocol.get('initialization', {}).get('kind') == 'fresh_public_base'
            and protocol.get('recipe', {}).get('seed') == protocol.get('initialization', {}).get('seed') == 2026093041,
            'H1 initialization or pure evaluation contract differs')
    builder, selection = _helpers()
    report = read_json(checked_ref(admission.get('original_s1_report')))
    supervisor = read_json(checked_ref(admission.get('original_s1_supervisor')))
    require(len(report.get('runs', [])) == 3 and {r.get('candidate_id') for r in report['runs']} == ALL,
            'complete original three-arm S1 report required')
    for run in report['runs']:
        counts = run.get('progress', {}).get('counts', {})
        require(run.get('runner_status') == 'complete' and counts.get('planned') == counts.get('closed_known') == 36,
                'all original S1 arms must close before either H1 arm starts')
        actual = read_json(Path(run['root']) / 'online/report.json')
        require(actual.get('status') == 'complete', 'original S1 runner still running or stopped incompletely')
    # Existing validator binds both actual S0/S1 queue commands, source freezes,
    # owner identities and manifests. Training-ready False does not exclude H1.
    readiness = selection.validated_readiness(supervisor, report)
    require(set(readiness) == NEW, 'both corrected-native inference entries are required')
    jobs = {r['name']: r for r in supervisor['config']['candidates']}
    for name in sorted(NEW):
        source_protocol = Path(jobs[name]['screen_protocol'])
        screen = read_json(source_protocol)
        builder.validate_original_s1(screen, source_protocol, report)
        planned = builder.build_protocol(screen)
        require(body_hash(planned) == admission['protocol_body_sha256'][name], 'H1 fixed paired plan differs from original candidate runtime/recipe')
    expected_manifest = checked_ref(admission.get('weight_manifests', {}).get(candidate))
    original_manifest = checked_ref(selection.ref(jobs[candidate]['weight_manifest']))
    require(Path(weight_manifest).resolve() == expected_manifest == original_manifest
            and Path(model_path).resolve() == Path(jobs[candidate]['model_path']).resolve(),
            'launch model path or weight manifest differs from original admitted candidate')
    require(set(admission.get('weight_manifests', {})) == NEW, 'both original model manifests must be bound')
    for name in NEW:
        require(checked_ref(admission['weight_manifests'][name]) == Path(jobs[name]['weight_manifest']).resolve(),
                'peer model manifest differs from the completed original screen')
    h0 = admission.get('H0', {})
    require(h0.get('review_status') == 'accepted_for_h1' and h0.get('scope') == 'compatibility_only_not_business_success',
            'explicit H0 compatibility review is absent; business success is not this gate')
    summary = read_json(checked_ref(h0.get('report')))
    h0root = Path(summary['run_root']).resolve()
    require(summary.get('status') == 'complete' and summary.get('actual_generation_count', 0) > 0
            and summary.get('actor_steps_total') == summary.get('critic_steps_total') == 0,
            'H0 actual model summary has not completed without updates')
    for evidence in summary.get('source_evidence', []):
        checked_ref(evidence, root=h0.get('evidence_root'))
    require(bool(summary.get('source_evidence')), 'H0 must retain actual original artifact references')
    h0runner = read_json(h0root / 'online/report.json')
    h0protocol = read_json(h0root / 'launch-protocol.json')
    require(h0runner.get('status') == 'complete' and h0runner.get('actor_steps_total') == h0runner.get('critic_steps_total') == 0
            and h0protocol.get('stage') == 'H0_compatibility'
            and h0runner.get('protocol_sha256') == digest(json_bytes(h0protocol))
            and sum(len(w['slots']) for w in h0protocol['windows']) == 3,
            'H0 original three-slot run/protocol differs from compatibility summary')
    before = read_json(h0root / 'source-before.json')
    require(before == read_json(h0root / 'source-after.json') and before.get('code_dirty') is False
            and summary.get('source_commit') == before.get('code_commit'), 'H0 actual source changed or summary differs')
    require(len(h0runner.get('windows', [])) == len(h0protocol['windows']), 'H0 window count differs')
    for index, window in enumerate(h0runner['windows']):
        require(window.get('status') == 'complete', 'H0 window did not finish')
        _guard(window.get('evaluation_guard', {}))
        for slot in range(len(h0protocol['windows'][index]['slots'])):
            episode = read_json(h0root / f'online/window-{index}/collection/slot-{slot}/episode/manifest.json')
            require(episode.get('status') == 'closed', 'H0 original episode not closed')
    require(h0.get('reviewed_source_identity') == source_identity
            and h0.get('target_harness_identity') == expected_harness
            and h0.get('tested_adapter_version') == summary.get('adapter_version'),
            'H0 review does not bind the final target source and tested adapter version')
    if h0['tested_adapter_version'] != expected_harness.get('adapter_version'):
        require(h0.get('untested_model_changes') and h0.get('targeted_cpu_evidence'),
                'post-H0 harness changes need explicit limitation and targeted CPU evidence')
        for evidence in h0['targeted_cpu_evidence']:
            checked_ref(evidence)
    return {'version': VERSION, 'status': 'admitted', 'admission': copy.deepcopy(gate['admission']),
            'original_s1_all_three_arms_complete': True, 'new_candidate_training_readiness': readiness,
            'H0_scope': h0['scope'], 'fresh_model': str(Path(model_path).resolve()),
            'weight_manifest': copy.deepcopy(admission['weight_manifests'][candidate]),
            'source_identity': source_identity, 'no_model_or_tensor_loaded_by_gate': True}
