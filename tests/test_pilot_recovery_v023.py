"""Two CPU recovery controls; fixture records are never pilot training data."""
import copy

import pytest

from proworksim import pilot_recovery_v023 as recovery
from proworksim.collaboration_training_v023 import HARNESS, training_admission
from proworksim.online_support import declare_window, expected_window
from proworksim.online_training import prepare_window, recipe_config, tensor_tree_digest
from proworksim.storage import digest, json_bytes
from proworksim.templates import retail_collaboration_v023 as world
from test_online_training_v13 import _entry


def fixture_records(root, monkeypatch, identity, recipe, *, index=0, prior_steps=0):
    source = {'code_commit': 'explicit_CPU_source_fixture', 'code_dirty': False,
              'source_tree_sha256': digest(b'explicit CPU source fixture')}
    monkeypatch.setattr(recovery, 'code_identity', lambda: copy.deepcopy(source))
    monkeypatch.setattr(recovery, 'pid_alive', lambda _: False)
    actual = root / 'actual'
    folder = actual / f'window-{index}'
    update = folder / 'update'
    update.mkdir(parents=True)
    catalog = world.registry()
    contract = catalog['training_windows'][index]
    admission = training_admission(catalog, world.PIN_PATH)
    specs = []
    for slot in contract['slots']:
        case = world.case_spec(slot['case_id'])
        policies = {m: {'implementation': 'proworksim.work_view_v022.CompactWorkModelPolicy',
                       'config': {'weight_identity': identity, 'model_revision': identity['policy_version'],
                                  'temperature': .7, 'max_context_tokens': 16384, 'max_output_tokens': 2048,
                                  'budget': {'max_decisions': case['role_decision_limits'][m]}}}
                    for m in case['active_roles']}
        specs.append({'slot_id': slot['slot_id'], 'xi_id': case['case_id'],
                      'xi_fingerprint': digest(json_bytes(case)), 'active_members': case['active_roles'],
                      'policies': policies, 'mapping_spec_id': 'explicit_CPU_fixture_unmapped'})
    declaration = declare_window(contract['window_id'], actor_identity=identity,
        gamma_identity={'harness': HARNESS, 'seeds': [s['sampling_seed'] for s in contract['slots']]}, slot_specs=specs)
    entries = []
    for spec in declaration['slots']:
        entry = _entry(identity, window=contract['window_id'], slot=spec['slot_id'])
        entry['active_members'] = spec['active_members']
        rollout = entry['rollout']
        rollout['members'] = {m: {'origin': 'target_model'} for m in spec['active_members']}
        rollout['window'] = expected_window(declaration, spec['slot_id'])
        rollout['manifest']['policies'] = spec['policies']
        original_events = copy.deepcopy(rollout['events'])
        rollout['events'] = []
        for member in spec['active_members']:
            for event in copy.deepcopy(original_events):
                event['sequence'] = len(rollout['events'])
                event['worker_id'] = member
                if 'call_id' in event['payload']:
                    event['payload']['call_id'] += ':' + member
                rollout['events'].append(event)
        entries.append(entry)
    prepared = prepare_window(entries, identity, contract['window_id'], recipe)
    checks = [{'call_id': row['call_id'], 'passed': True} for row in prepared['decisions']]
    plan = {'version': 'explicit_CPU_frozen_plan'}
    plan_path = root / 'plan.json'
    plan_path.write_bytes(json_bytes(plan))
    state = {'stage': 'train', 'status': 'stopped', 'stop_reason': 'task_time_budget',
             'pid': 123456, 'exit_code': -15, 'ended_at': 200, 'elapsed_gpu_seconds': 100,
             'source': source, 'task': {'kind': 'update', 'task': contract['window_id'] + ':update'}}
    report = {'source_before': source, 'plan': recovery.reference(plan_path)}
    progress = [{'window_index': i, 'window_id': catalog['training_windows'][i]['window_id'],
                 'status': 'closed', 'update': {'status': 'updated',
                  'actor_optimizer_steps': prior_steps if i == 0 else 0,
                  'critic_optimizer_steps': prior_steps if i == 0 else 0}} for i in range(index)]
    progress.append({'window_index': index, 'window_id': contract['window_id'], 'status': 'updating'})
    update_report = {'window_id': contract['window_id'], 'status': 'preparing', 'stage': 'backward',
        'scheduled_slots': 6, 'admitted_decisions': len(prepared['decisions']),
        'actor_optimizer_steps': 0, 'critic_optimizer_steps': 0, 'training_happened': False,
        'behavior_probability_passed': True, 'backward_decisions_completed': 1}
    files = {root / 'state.json': state, actual / 'report.json': report,
             actual / 'training-progress.json': progress, actual / 'admission.json': admission,
             folder / 'declaration.json': declaration, folder / 'entries.json': entries,
             update / 'admission.json': prepared, update / 'report.json': update_report,
             update / 'behavior-probability-check.json': checks}
    for path, value in files.items():
        path.write_bytes(json_bytes(value))
    (update / 'shared-before.pt').write_bytes(b'explicit CPU placeholder used only for no-step file proof')
    return plan, folder, prepared


def test_unstepped_proof_rejects_marker_live_process_or_numeric_failure(tmp_path, monkeypatch):
    identity = {'version': 'shared-actor-identity-v0.13', 'policy_version': 'fixture',
                'adapter_sha256': digest(b'a'), 'base_manifest_sha256': digest(b'b'),
                'inference_profile_sha256': digest(b'i')}
    recipe = recipe_config({'max_length': 16384, 'max_output_tokens': 2048})
    plan, folder, _ = fixture_records(tmp_path, monkeypatch, identity, recipe)
    accepted = recovery.admit_recovery(tmp_path, plan)
    assert accepted['prior_gpu_seconds'] == 100
    assert accepted['original_window_index'] == 0 and accepted['prior_steps'] == {'actor': 0, 'critic': 0}
    marker = folder / 'update/losses.json'
    marker.write_bytes(b'[]')
    with pytest.raises(ValueError, match='pre-step artifact'):
        recovery.admit_recovery(tmp_path, plan)
    marker.unlink()
    monkeypatch.setattr(recovery, 'pid_alive', lambda _: True)
    with pytest.raises(ValueError, match='dead worker'):
        recovery.admit_recovery(tmp_path, plan)
    monkeypatch.setattr(recovery, 'pid_alive', lambda _: False)
    report = recovery.read_json(folder / 'update/report.json')
    report['status'] = 'zero_step_probability_mismatch'
    (folder / 'update/report.json').write_bytes(json_bytes(report))
    with pytest.raises(ValueError, match='probability-qualified'):
        recovery.admit_recovery(tmp_path, plan)


def test_restore_keeps_prior_steps_optimizers_rng_and_exact_six_slot_admission(tmp_path, monkeypatch):
    torch = pytest.importorskip('torch')
    from test_online_training_v13 import _features, _owner, _sample_entry

    torch.manual_seed(29)
    base = {'manifest': {'sha256': digest(b'explicit tiny CPU base')}}
    original = _owner(tmp_path, torch, 'original-owner', base_identity=base)
    original.recipe.update(max_length=16384, max_output_tokens=2048)
    original.begin_window('v023-window-1')
    first = _sample_entry(original, reward=1)
    original.update_window([first], tmp_path / 'prior-update', feature_function=_features)
    assert original.actor_steps == original.critic_steps == 1
    original.begin_window('v023-window-2')
    stage = tmp_path / 'old-train'
    plan, folder, _ = fixture_records(stage, monkeypatch, original.freeze_identity(),
                                      original.recipe, index=1, prior_steps=1)
    saved = original._state_bundle()
    torch.save(saved, folder / 'update/shared-before.pt')
    admitted = recovery.admit_recovery(stage, plan)
    fresh = _owner(tmp_path, torch, 'restored-owner', base_identity=base)
    fresh.recipe.update(max_length=16384, max_output_tokens=2048)
    fresh.actor_parameters['lora_logits'].grad = torch.ones_like(fresh.actor_parameters['lora_logits'])
    fresh.actor_optimizer.param_groups[0]['lr'] = .99
    torch.manual_seed(314159)
    restored = recovery.restore_window(fresh, admitted)
    assert restored['restoration']['exact_state_restored'] is True
    assert restored['admission_reconstruction']['exactly_equal'] is True
    assert len(restored['entries']) == 6
    assert fresh.actor_steps == fresh.critic_steps == fresh.policy_revision == 1
    assert fresh.phase == 'collecting' and fresh.window_id == 'v023-window-2'
    assert fresh.used_window_ids == ['v023-window-1', 'v023-window-2']
    assert tensor_tree_digest(fresh._state_bundle(), torch) == tensor_tree_digest(saved, torch)
    assert fresh.actor_parameters['lora_logits'].grad is None
    assert restored['restoration']['partial_gradients_reused'] is False
