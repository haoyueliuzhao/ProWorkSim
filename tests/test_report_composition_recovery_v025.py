"""Finite read-only R1 fixtures; no model, world replay, tensor load or git."""
import copy
import json
from pathlib import Path

from proworksim.storage import json_bytes
from scripts.report_composition_recovery_v025 import STAGES, confirmation, markdown, report
from scripts.report_domain_v022 import reference


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def fixture(tmp_path):
    old, root = tmp_path/'original', tmp_path/'r1'
    source, new_source = {'source_tree_sha256': 'old'}, {'source_tree_sha256': 'r1'}
    catalog_path = Path('examples/retail-collaboration-v25/catalog.json').resolve()
    catalog_ref = reference(catalog_path)
    old_plan = tmp_path/'old-plan.json'
    put(old_plan, {'internal_gpu_seconds': 208800})
    old_supervisor = old/'supervisor.json'
    put(old_supervisor, {'source': source, 'plan': reference(old_plan), 'status': 'closed_with_incomplete_stages',
                         'ended_at': 100, 'terminated_gpu_seconds': 49415.01438975334})
    put(old/'support.json', {'selected_block': None, 'supports_by_xi': {}})
    put(old/'entries.json', [{} for _ in range(16)])
    marker = old/'support-complete.json'
    put(marker, {'source': source, 'entries': reference(old/'entries.json'), 'support': reference(old/'support.json')})
    put(old/'train_base/actual/update/admission.json', {'slot_count': 16, 'decisions': [{} for _ in range(283)]})
    old_report = tmp_path/'original-report.json'
    put(old_report, {'version': 'member-composition-report-v0.25', 'run_root': str(old), 'source': source,
        'report_kind': 'closed_incomplete', 'execution_terminal': True,
        'references': {'plan': reference(old_plan), 'supervisor': reference(old_supervisor), 'catalog': catalog_ref},
        'support': {'selected_block': None}, 'accounting': {'final_gpu_seconds': 49415.01438975334},
        'training_episode_consumptions_started': 16, 'new_actor_steps': 0, 'new_critic_steps': 0,
        'closed_new_episode_counts': {'support': 16, 'confirmation': 0, 'continuation': 0}})
    plan = tmp_path/'r1-plan.json'
    put(plan, {'original_run': str(old), 'original_supervisor': reference(old_supervisor),
        'original_report': reference(old_report), 'original_plan': reference(old_plan), 'original_support_complete': reference(marker),
        'catalog': catalog_ref, 'source_pin': None, 'internal_gpu_seconds': 91800})
    put(root/'supervisor.json', {'source': new_source, 'plan': reference(plan), 'status': 'closed_with_incomplete_stages', 'ended_at': 300})
    for stage in STAGES:
        state = {'attempted': False, 'status': 'not_started_endpoint_unavailable', 'ended_at': 300}
        if stage == 'train_base':
            state = {'attempted': True, 'status': 'stopped', 'exit_code': -15, 'started_at': 200, 'ended_at': 300, 'elapsed_gpu_seconds': 100}
        put(root/stage/'state.json', state)
    put(root/'train_base/actual/update/admission.json', {'slot_count': 16})
    put(root/'train_base/actual/update/report.json', {'status': 'preparing', 'stage': 'backward', 'backward_decisions_completed': 40, 'actor_optimizer_steps': 0, 'critic_optimizer_steps': 0})
    return old, root, old_report


def test_failed_R1_counts_old_failure_repeated_consumption_but_no_new_support(tmp_path):
    old, root, old_report = fixture(tmp_path)
    before = {str(p): p.read_bytes() for p in old.rglob('*') if p.is_file()}
    original_bytes = old_report.read_bytes()
    value = report(root)
    assert value['report_kind'] == 'closed_incomplete' and value['execution_terminal']
    assert value['planned_primary_composition_difference'] is None and value['parameter_learning_effect'] is None
    assert value['counts']['original_new_training_episodes'] == 16
    assert value['counts']['R1_new_training_episodes'] == value['counts']['R1_new_episodes_closed'] == 0
    assert value['counts']['cumulative_training_consumptions_started'] == 32
    assert value['training']['new_actor_steps'] is None  # Interrupted progress is not a terminal tensor identity.
    assert value['accounting']['R1_final_gpu_seconds'] == 100
    assert value['accounting']['cumulative_final_gpu_seconds'] == 49515.01438975334
    assert value['confirmation']['known'] == 0 and value['confirmation']['completed_fraction'] is None
    assert '原失败执行' in markdown(value)
    assert old_report.read_bytes() == original_bytes
    assert {str(p): p.read_bytes() for p in old.rglob('*') if p.is_file()} == before
    supervisor = json.loads((root/'supervisor.json').read_text())
    supervisor.update(status='running', ended_at=None)
    put(root/'supervisor.json', supervisor)
    live = report(root)
    assert live['report_kind'] == 'snapshot' and live['accounting']['R1_final_gpu_seconds'] is None


def test_v025_confirmation_keeps_known_failure_unknown_guard_and_closed_sampling_separate(tmp_path):
    catalog = json.loads(Path('examples/retail-collaboration-v25/catalog.json').read_text())
    folder = tmp_path/'confirm_base/actual'
    rows = []
    for index, slot in enumerate(catalog['confirmation_slots'][:2]):
        assessment = {'eligible': True, 'independent_assessability': 'known', 'completed': bool(index),
                      'work_components': {'full_responsibility': bool(index)}}
        assessment_path = folder/slot['slot_id']/'assessment.json'
        put(assessment_path, assessment)
        initial = 'canonical-' + slot['case_id']
        put(folder/slot['slot_id']/'preparation.json', {'prepared_business_state_sha256': initial,
            'prepared_business_state_hash_format': 'canonical-keys-v025-all-original-business-fields-and-immutable-file-bytes'})
        put(folder/slot['slot_id']/'episode/manifest.json', {'status': 'closed', 'scenario': {'variation': {'online_case': {'case_id': slot['case_id']}}}})
        rows.append({**slot, 'status': 'closed', 'assessment': assessment, 'assessment_ref': reference(assessment_path),
                     'actor_identity': 'after-actor', 'initial_business_state_sha256': initial,
                     'evaluation_guard': {'learning_unchanged': index == 0, 'rng_restored_exactly': True}})
    put(folder/'progress.json', rows)
    original = copy.deepcopy(rows)
    result = confirmation(tmp_path, catalog, 'after-actor')
    assert result['known'] == 1 and result['unknown'] == 11 and result['complete_responsibilities'] == 0
    assert result['rows'][0]['outcome']['value'] is False and result['rows'][1]['outcome']['value'] is None
    assert result['completed_fraction'] is None and result['descriptive_known_fraction'] == 0
    assert result['closed_new_episode_boundaries'] == 2 and result['parameter_learning_effect'] is None
    assert json.loads((folder/'progress.json').read_text()) == original
