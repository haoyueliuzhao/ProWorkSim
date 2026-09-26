"""Complete metadata fixture for H1 launch gates; no models, tensors or jobs."""
import copy
from pathlib import Path

import pytest

from proworksim.harness_admission import SOURCE_FILES, VERSION, body_hash, validate_h1_launch
from proworksim.storage import digest, json_bytes
from scripts.build_harness_study_v016 import build_protocol, read, ref
from test_candidate_selection_v015 import binding_fixture, guard, save


def admission_fixture(tmp_path):
    supervisor, report, _ = binding_fixture(tmp_path / 'original')
    screens, protocols = {}, {}
    for run in report['runs']:
        run['progress']['counts'].update(distinct_planned_or_measured=36, closed_unknown=0, open=0,
                                         interrupted_open=0, not_started=0)
        run['observed_optimizer_step_increments'] = {'actor': 0, 'critic': 0}
        if run['candidate_id'] == 'qwen25-7b':
            run['root'] = str(tmp_path / 'old-baseline')
            save(Path(run['root']) / 'online/report.json', {'status': 'complete'})
            continue
        candidate = run['candidate_id']
        job = next(j for j in supervisor['config']['candidates'] if j['name'] == candidate)
        path = Path(job['screen_protocol'])
        screen = read(path)
        spec = {'window_id': 'fixture-screen-' + candidate, 'mode': 'evaluate', 'slots': [{}] * 36}
        screen.update(stage='screen', mode='evaluate', windows=[spec])
        save(path, screen)
        run['protocol_ref'] = ref(path)
        supervisor['source_identity']['files'][str(path)] = ref(path)['sha256']
        root = Path(run['root'])
        save(root / 'online/protocol.json', screen)
        save(root / 'launch-protocol.json', screen)
        save(root / 'online/report.json', {'status': 'complete', 'protocol_sha256': digest(json_bytes(screen))})
        run['windows'][0]['window_id'] = spec['window_id']
        screens[candidate], protocols[candidate] = screen, build_protocol(screen)
    s1report, s1supervisor = tmp_path / 's1-report.json', tmp_path / 's1-supervisor.json'
    save(s1report, report)
    save(s1supervisor, supervisor)
    current_root = tmp_path / 'final-source'
    source_files = {}
    for name in SOURCE_FILES:
        path = current_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# CPU fixture only; never executed\n')
        source_files[name] = digest(path.read_bytes())
    source = {'code_commit': 'a' * 40, 'code_dirty': False, 'source_tree_sha256': 'b' * 64}
    h0root = tmp_path / 'actual-h0-fixture'
    h0protocol = {'stage': 'H0_compatibility', 'windows': [{'slots': [{}, {}, {}]}]}
    save(h0root / 'launch-protocol.json', h0protocol)
    save(h0root / 'online/report.json', {'status': 'complete', 'actor_steps_total': 0, 'critic_steps_total': 0,
                                        'protocol_sha256': digest(json_bytes(h0protocol)),
                                        'windows': [{'status': 'complete', 'evaluation_guard': guard()}]})
    old_source = {'code_commit': 'c' * 40, 'code_dirty': False, 'source_tree_sha256': 'd' * 64}
    for name in ('source-before.json', 'source-after.json'):
        save(h0root / name, old_source)
    for i in range(3):
        save(h0root / f'online/window-0/collection/slot-{i}/episode/manifest.json', {'status': 'closed'})
    summary = {'status': 'complete', 'run_root': str(h0root), 'actual_generation_count': 1,
               'actor_steps_total': 0, 'critic_steps_total': 0, 'source_commit': old_source['code_commit'],
               'adapter_version': 'openhands-managed-worker-v0.16',
               'source_evidence': [ref(h0root / 'online/report.json'), ref(h0root / 'launch-protocol.json')]}
    summary_path = tmp_path / 'h0-summary.json'
    save(summary_path, summary)
    cpu = tmp_path / 'cpu-evidence.json'
    save(cpu, {'scope': 'artificial metadata fixture, no SDK run', 'passed': True})
    identity = protocols['qwen35-9b']['harness_identity']['openhands_v16']
    admission = {'version': VERSION, 'status': 'admitted',
                 'protocol_body_sha256': {k: body_hash(v) for k, v in protocols.items()},
                 'source_identity': source, 'source_files': source_files, 'harness_identity': identity,
                 'original_s1_report': ref(s1report), 'original_s1_supervisor': ref(s1supervisor),
                 'weight_manifests': {j['name']: ref(j['weight_manifest']) for j in supervisor['config']['candidates']},
                 'H0': {'review_status': 'accepted_for_h1', 'scope': 'compatibility_only_not_business_success',
                        'report': ref(summary_path), 'evidence_root': str(tmp_path),
                        'reviewed_source_identity': source, 'target_harness_identity': identity,
                        'tested_adapter_version': summary['adapter_version'],
                        'untested_model_changes': ['CPU-tested error-flag metadata revision only'],
                        'targeted_cpu_evidence': [ref(cpu)]}}
    admission_path = tmp_path / 'admission.json'
    save(admission_path, admission)
    protocol = protocols['qwen35-9b']
    protocol['launch_gate'] = {'version': VERSION, 'state': 'admitted', 'admission': ref(admission_path)}
    job = next(j for j in supervisor['config']['candidates'] if j['name'] == 'qwen35-9b')
    kwargs = {'model_path': job['model_path'], 'weight_manifest': job['weight_manifest'],
              'source_identity': source, 'source_root': current_root}
    return protocol, kwargs, admission, admission_path, report, s1report, h0root


def test_global_admission_rejects_early_changed_or_restored_launch(tmp_path):
    protocol, kwargs, admission, path, report, s1report, h0root = admission_fixture(tmp_path)
    valid = validate_h1_launch(protocol, **kwargs)
    assert valid['status'] == 'admitted' and valid['original_s1_all_three_arms_complete'] is True
    assert valid['new_candidate_training_readiness'] == {'qwen35-9b': True, 'qwen38-27b': False}
    assert valid['H0_scope'] == 'compatibility_only_not_business_success'
    planning = copy.deepcopy(protocol)
    planning['launch_gate'] = {'version': VERSION, 'state': 'planning_only'}
    with pytest.raises(ValueError, match='planning-only'):
        validate_h1_launch(planning, **kwargs)
    with pytest.raises(ValueError, match='never restore'):
        validate_h1_launch(protocol, **kwargs, restore_checkpoint='/any/previous/checkpoint')
    with pytest.raises(ValueError, match='final admitted source'):
        validate_h1_launch(protocol, **{**kwargs, 'source_identity': {**kwargs['source_identity'], 'code_commit': 'wrong'}})
    with pytest.raises(ValueError, match='weight manifest'):
        validate_h1_launch(protocol, **{**kwargs, 'weight_manifest': tmp_path / 'other.json'})
    # A complete 9B cannot open H1 while its registered 27B peer still runs.
    report['runs'][2]['runner_status'] = 'running'
    save(s1report, report)
    admission['original_s1_report'] = ref(s1report)
    save(path, admission)
    protocol['launch_gate']['admission'] = ref(path)
    with pytest.raises(ValueError, match='all original S1 arms'):
        validate_h1_launch(protocol, **kwargs)
    report['runs'][2]['runner_status'] = 'complete'
    save(s1report, report)
    admission['original_s1_report'] = ref(s1report)
    save(path, admission)
    protocol['launch_gate']['admission'] = ref(path)
    # Even when the summary still says complete, changed actual H0 evidence fails.
    raw = read(h0root / 'online/report.json')
    raw['status'] = 'running'
    save(h0root / 'online/report.json', raw)
    with pytest.raises(ValueError, match='evidence bytes changed'):
        validate_h1_launch(protocol, **kwargs)
    # Original S1/N0/N1/H0 protocols retain their own existing execution contract.
    assert validate_h1_launch({'stage': 'H0_compatibility'}, model_path='unused', weight_manifest='unused')['status'] == 'not_H1'
