"""Read original v049 DA evidence plus the two r2g DB terminal archives.

Standard library only. Never imports a world/model/tokenizer or deserializes .pt.
The existing pure-JSON behavior reader is reused only for closed DB archives.
No output is written while the selected supervisor/workers are still in flight.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
ANALYSIS = Path(__file__).resolve().parent
DEFAULT_ROOT = BASE / 'runs/software-learning-v049-dev-resume-r2g'
OLD_ROOT = BASE / 'runs/software-learning-v049-resume-r1'
OLD_REPORT = ANALYSIS / 'development-four-work-facts.json'
WORKERS = ('dev-B-DB-s1', 'dev-B-DB-s2')
DB_IDS = ('org49-dev-DB-s1-B', 'org49-dev-DB-s2-B')
GUARDS = ('learning_unchanged', 'rng_restored_exactly',
          'software_binding_unchanged', 'actor_identity_unchanged')


def read(path):
    path = Path(path)
    if path.suffix != '.json':
        raise ValueError('JSON evidence reader cannot load non-JSON states')
    return json.loads(path.read_text())


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def ref(path):
    path = Path(path).resolve()
    if path.suffix == '.pt':
        raise ValueError('Tensor-state reads are outside this analysis')
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def optional(path):
    return read(path) if Path(path).is_file() else None


def preserved(source):
    actual = ref(source['path'])
    if actual['sha256'] != source['sha256']:
        raise ValueError('Original evidence changed: ' + source['path'])
    return actual


def load_behavior_reader():
    path = ANALYSIS / 'read_r1_new_collection_behavior.py'
    spec = importlib.util.spec_from_file_location('v049_pure_json_behavior_reader', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.folder_for = lambda root, unit: Path(unit['episode_folder'])
    return module, ref(path)


def readiness(root):
    supervisor = optional(root / 'supervisor.json')
    if supervisor is None:
        return False, 'supervisor_not_created', None
    states = supervisor.get('states', {})
    if set(states) != set(WORKERS):
        return False, 'two_frozen_worker_states_not_available', supervisor
    if not supervisor.get('ended_at'):
        return False, 'supervisor_not_terminal', supervisor
    if any(state.get('status') not in {'complete', 'stopped', 'not_applicable'}
           for state in states.values()):
        return False, 'worker_not_terminal', supervisor
    for worker, sid in zip(WORKERS, DB_IDS):
        state = states[worker]
        if not state.get('attempted'):
            continue
        output = root / worker / 'actual'
        folder = output / 'episodes' / sid
        if not (output / 'report.json').is_file():
            return False, 'attempted_worker_report_missing:' + worker, supervisor
        if state.get('status') == 'complete' and not all((folder / name).is_file() for name in
                ('slot-result.json', 'mechanical-measurement.json', 'evaluation-guard.json')):
            return False, 'complete_worker_closed_receipts_missing:' + worker, supervisor
    return True, 'saved_terminal_supervisor', supervisor



def resource_history(plan):
    """Read the retained zero-worker stop, not any historical model state."""
    prior = plan.get('resource_resume_of')
    if prior is None:
        return None
    supervisor_source = preserved(prior['supervisor'])
    previous = read(supervisor_source['path'])
    states = previous.get('states', {})
    stop_source = next(item for item in prior['retained_waiting_files']
                       if Path(item['path']).name == 'gpu-scope-amendment-stop.json')
    stop_ref = preserved(stop_source)
    stop = read(stop_ref['path'])
    zero_workers = (set(states) == set(WORKERS)
        and all(state.get('attempted') is False for state in states.values())
        and all(state.get('elapsed_gpu_seconds', 0) == 0 for state in states.values())
        and stop.get('new_GPU_workers') == 0 and stop.get('new_model_calls') == 0)
    if not zero_workers:
        raise ValueError('Prior r2 wait was not the frozen zero-worker resource stop')
    return {'root': prior['root'], 'supervisor': previous, 'explicit_stop_receipt': stop,
        'saved_supervisor_source': supervisor_source, 'explicit_stop_source': stop_ref,
        'retained_waiting_file_manifest_as_frozen': prior['retained_waiting_files'],
        'new_model_workers': 0, 'new_model_calls': 0, 'gpu_worker_seconds': 0,
        'original_exception_not_reclassified': True,
        'scope': 'Retain original signal-15/KeyboardInterrupt stop plus explicit user-scope amendment. This wait had no model worker, generation or GPU-worker cost; original eight files are never written.'}


def resources_receipt(path, state):
    """Summarize already saved telemetry/guard decisions, never query a GPU."""
    path = Path(path)
    if not path.is_file():
        return None
    raw = path.read_bytes()
    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    guards = [row.get('guard', {}) for row in records]
    def extrema(key, minimum=False):
        values = [row.get(key) for row in records if type(row.get(key)) in (int, float)]
        return (min(values) if minimum else max(values)) if values else None
    def guard_extrema(key):
        values = [row.get(key) for row in guards if type(row.get(key)) in (int, float)]
        return max(values) if values else None
    times = [row.get('sample', {}).get('time') for row in records]
    times = [value for value in times if type(value) in (int, float)]
    gpu_indices = sorted({row['target_gpu_index'] for row in guards if row.get('target_gpu_index') is not None})
    gpu_uuids = sorted({row['target_gpu_uuid'] for row in guards if row.get('target_gpu_uuid')})
    pids = sorted({row['worker_pid'] for row in guards if row.get('worker_pid') is not None})
    stops = [{'sample_index': index, 'stop_reason': row['stop_reason']}
             for index, row in enumerate(guards) if row.get('stop_reason')]
    issues = []
    if gpu_indices and gpu_indices != [state.get('gpu')]:
        issues.append('telemetry_gpu_differs_from_supervisor')
    if gpu_uuids and gpu_uuids != [state.get('gpu_uuid')]:
        issues.append('telemetry_uuid_differs_from_supervisor')
    if pids and pids != [state.get('pid')]:
        issues.append('telemetry_pid_differs_from_supervisor')
    return {'source': {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)},
        'saved_samples': len(records), 'first_sample_time': min(times) if times else None,
        'last_sample_time': max(times) if times else None,
        'physical_gpu_indices_observed': gpu_indices, 'gpu_uuids_observed': gpu_uuids,
        'worker_pids_observed': pids, 'binding_issues': issues,
        'saved_guard_fresh_counts': dict(Counter(str(row.get('fresh')) for row in guards)),
        'saved_guard_stale_counts': dict(Counter(str(row.get('stale')) for row in guards)),
        'saved_guard_stop_reasons': stops,
        'maximum_own_gpu_memory_mib_as_saved': guard_extrema('own_gpu_memory_mib'),
        'maximum_rss_bytes_as_saved': extrema('rss_bytes'),
        'maximum_artifact_bytes_as_saved': extrema('artifact_bytes'),
        'minimum_volume_free_bytes_as_saved': extrema('volume_free_bytes', minimum=True),
        'scope': 'Saved samples and original guard decisions only; no GPU API or process probe, no reconstructed continuous resource guarantee.'}


def worker_host_receipt(root, worker, state, plan):
    folder = root / worker
    launch_path = folder / 'worker-launch.json'
    launch = optional(launch_path)
    allowed = plan.get('gpu_preference', [])
    return {'worker': worker, 'state': state, 'supervisor_source': ref(root / 'supervisor.json'),
        'physical_gpu': state.get('gpu'), 'physical_gpu_uuid': state.get('gpu_uuid'),
        'physical_gpu_in_amended_plan': state.get('gpu') in allowed if state.get('attempted') else None,
        'worker_launch': launch, 'worker_launch_source': ref(launch_path) if launch else None,
        'actual_launch_command_matches_supervisor': launch.get('actual_command') == state.get('command') if launch else None,
        'launch_gpu_matches_supervisor': str(launch.get('physical_gpu')) == str(state.get('gpu')) if launch else None,
        'launch_source_matches_plan': launch.get('source') == plan.get('source') if launch else None,
        'launch_receipt_alone_proves_process_started': False,
        'resources': resources_receipt(folder / 'resources.jsonl', state),
        'optional_stop_receipt_sources': {str(path.relative_to(folder)): ref(path)
            for path in sorted(folder.glob('*stop*.json'))},
        'scope': 'Actual command comes from r2g worker-launch receipt plus supervisor process identity; retained requested r2 command is prelaunch intent, not actual executable identity.'}


def guard_report(row, plan):
    loaded = row.get('loaded_state') or {}
    restored = loaded.get('restored') or {}
    guard = row.get('evaluation_guard') or {}
    close = row.get('frozen_collection_close') or {}
    inventory = plan['resume_inventory']
    actual_checkpoint = loaded.get('checkpoint')
    expected_checkpoint = inventory['B_checkpoint']
    return {'loaded_branch': loaded.get('branch'),
        'loaded_steps_as_saved': {'actor': loaded.get('actor_steps'), 'critic': loaded.get('critic_steps')},
        'loaded_checkpoint_matches_plan_reference': actual_checkpoint == expected_checkpoint if loaded else None,
        'loaded_state_sha_matches_original_B': restored.get('state', {}).get('sha256') == inventory['B_state']['sha256'] if restored else None,
        'serialized_reload_exact_as_saved': restored.get('serialized_reload_exact'),
        'evaluation_flags_as_saved': {key: guard.get(key) for key in GUARDS},
        'frozen_collection_close_status': close.get('status'),
        'frozen_collection_training_happened': close.get('training_happened'),
        'frozen_collection_actor_steps': close.get('actor_optimizer_steps'),
        'frozen_collection_critic_steps': close.get('critic_optimizer_steps'),
        'scope': 'Read saved JSON restoration and guard receipts; no checkpoint tensor reload/comparison. Missing fields remain null, and cleanup guards do not make DA2 a closed episode.'}

def version_files(folder, state, point):
    artifact = state['artifacts'][point['object_id']]
    path = (folder / 'episode/end/control/versions' / point['object_id'] /
            point['version_id'] / artifact['filename'])
    receipt = ref(path)
    declared = artifact['versions'][point['version_id']]['sha256']
    if receipt['sha256'] != declared:
        raise ValueError('Immutable archived file version hash mismatch')
    return read(path)['files'], receipt


def point_key(point):
    if not isinstance(point, dict):
        return None
    obj = point.get('object_id', point.get('artifact_id'))
    return (obj, point.get('version_id')) if obj and point.get('version_id') else None


def ancestor(state, earlier, later):
    target, start = point_key(earlier), point_key(later)
    if not target or not start:
        return None
    pending, visited, malformed = [start], set(), False
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        artifact = state.get('artifacts', {}).get(current[0], {})
        version = artifact.get('versions', {}).get(current[1])
        if not isinstance(version, dict):
            malformed = True
            continue
        for parent in version.get('derived_from', []):
            key = point_key(parent)
            if key is None:
                malformed = True
            else:
                pending.append(key)
    return None if malformed else False


def compact_event(event):
    keys = ('sequence', 'kind', 'actor_id', 'patch_id', 'delivery_id', 'source_reference',
            'previous_reference', 'input_reference', 'files_sha256', 'source_sha256',
            'test_sequence', 'passed', 'executed', 'included_patch_ids', 'operation_id', 'action_id')
    return {key: event[key] for key in keys if key in event}


def full_tree_work(folder, result, mechanical):
    """Describe exact archived bytes, tests and final fixed tree; no re-acceptance."""
    state_path = folder / 'episode/end/control/state.json'
    state = read(state_path)
    world = state.get('software_events', [])
    final = result.get('deadline_receipt', {}).get('locked_submission')
    final_files = None
    final_source = None
    if final:
        final_files, final_source = version_files(folder, state, final['source_reference'])
    adoptions = []
    for event in world:
        if event.get('kind') != 'candidate_adopted':
            continue
        before, before_ref = version_files(folder, state, event['previous_reference'])
        after, after_ref = version_files(folder, state, event['source_reference'])
        candidate, candidate_ref = version_files(folder, state, event['input_reference'])
        expected_hash = event['candidate_binding']['files_sha256']
        exact = after == candidate and hashlib.sha256(encoded(after)).hexdigest() == expected_hash
        subsequent_tests = []
        for test in world:
            if (test.get('kind') != 'test' or test.get('actor_id') != event['actor_id']
                    or test['sequence'] <= event['sequence']):
                continue
            tested, tested_ref = version_files(folder, state, test['source_reference'])
            if tested == after:
                subsequent_tests.append({**compact_event(test), 'exact_files_equal_adopted_tree': True,
                                         'archive_source': tested_ref})
        final_lineage = ancestor(state, event['source_reference'], final['source_reference']) if final else None
        same_final_actor = bool(final) and final['actor_id'] == event['actor_id']
        final_same_tree = final_files == after if final_files is not None else False
        bound_test = next((test for test in subsequent_tests
                           if final and test['sequence'] == final.get('test_sequence')), None)
        peer = event['candidate_binding']['author'] != event['actor_id']
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        chain = (peer and bool(changed) and exact and same_final_actor and final_same_tree
                 and final_lineage is True and bound_test is not None)
        adoptions.append({'world_event': compact_event(event), 'recipient': event['actor_id'],
            'author': event['candidate_binding']['author'], 'peer_source': peer,
            'files_equal_before_adoption': before == after, 'changed_paths': changed,
            'exact_fixed_candidate_files_confirmed': exact,
            'candidate_files_sha256': expected_hash,
            'subsequent_recipient_tests_on_exact_adopted_files': subsequent_tests,
            'final_delivery_by_recipient': same_final_actor,
            'final_files_exactly_equal_adopted_files': final_same_tree,
            'adoption_on_final_version_lineage': final_lineage,
            'final_bound_test_is_one_of_these_same_tree_tests': bound_test is not None,
            'nonidentity_peer_full_tree_to_own_test_to_final_fixed_delivery_chain': chain,
            'sources': {'before': before_ref, 'after': after_ref, 'candidate': candidate_ref},
            'causal_delivery_gain_or_Contribution': 'not_inferred'})
    feedback = mechanical.get('feedback', {}).get('feedback_records', []) if mechanical else []
    relevant = []
    for record in feedback:
        if record.get('tool') in {'adopt_candidate', 'run_tests', 'fix_patch', 'submit_integration'}:
            relevant.append({key: record.get(key) for key in
                ('feedback_id', 'tool', 'member', 'experience_sequence', 'originating_call_id',
                 'feedback_ok', 'presentation', 'actual_followup', 'no_actual_followup')})
    final_test = next((compact_event(event) for event in world
                      if final and event.get('kind') == 'test'
                      and event.get('sequence') == final.get('test_sequence')), None)
    return {'adoptions': adoptions, 'fixed_delivery': final, 'final_files_source': final_source,
        'final_bound_test_original_event': final_test,
        'fixed_and_submit_events': [compact_event(event) for event in world
                                   if event.get('kind') in {'patch_fixed', 'submit'}],
        'relevant_original_feedback_records': relevant,
        'source_world_archive': ref(state_path),
        'scope': 'Exact full-file-map facts only. New output is not accepted or tested. A missing full-tree chain does not prove absence of every semantic or partial partner use.'}


def analyze_closed(folder, unit, reader):
    result = read(folder / 'slot-result.json')
    mechanical = read(folder / 'mechanical-measurement.json')
    behavior = reader.analyze_slot(folder.parent, {**unit, 'episode_folder': str(folder)})
    budget = result['team_budget']['model']
    failed = [record for record in mechanical['feedback'].get('feedback_records', [])
              if record.get('feedback_ok') is False]
    return {'slot_id': unit['slot_id'], 'root': unit['root'], 'sampling_seed': unit['sampling_seed'],
        'first_member': unit['first_member'], 'status': 'closed', 'formal_result': {key: result.get(key)
            for key in ('R_joint', 'R_token', 'Q_joint', 'Q_token', 'submitted', 'complete_delivery',
                        'administrative_censoring')},
        'usage': result['usage'], 'known_complete_response_tokens': result['usage']['total_tokens'],
        'full_actual_tokens': result['usage']['total_tokens'] if result['usage'].get('uncertain_usage_attempts') == 0 else None,
        'ledger_charged_tokens': budget['charged_tokens'], 'member_tests': result['team_budget']['tests']['used'],
        'episode_start_steps': result.get('episode_start_steps'), 'learning_binding': result.get('learning_binding'),
        'evaluation_guard': read(folder / 'evaluation-guard.json'),
        'frozen_collection_close': optional(folder / 'frozen-collection-close/report.json'),
        'behavior': behavior, 'full_tree_work': full_tree_work(folder, result, mechanical),
        'tool_refusals': [{key: record.get(key) for key in ('feedback_id', 'tool', 'member',
            'experience_sequence', 'feedback_ok')} for record in failed],
        'feedback_denominators': mechanical['feedback']['denominators'],
        'page_denominators': mechanical['feedback']['page_denominators'],
        'resource_refusal_counts': behavior['mechanical']['refusal_counts'],
        'mechanical_decision': mechanical['decision'],
        'sources': {name: ref(folder / name) for name in ('slot-result.json', 'team-budget.json',
            'mechanical-measurement.json', 'evaluation-guard.json', 'model-scenario.json')}}


def analyze_unclosed(folder, unit, worker_state):
    attempted = worker_state.get('attempted') is True
    evidence = optional(folder / 'organization-evidence.json')
    scenario = optional(folder / 'model-scenario.json')
    budget = optional(folder / 'team-budget.json')
    usage = evidence.get('total_usage') if evidence else None
    binding = (scenario or {}).get('variation', {}).get('organization_runtime', {})
    return {'slot_id': unit['slot_id'], 'root': unit['root'], 'sampling_seed': unit['sampling_seed'],
        'first_member': unit['first_member'], 'status': 'technical_unknown' if attempted else 'not_started',
        'formal_result': {key: None for key in ('R_joint', 'R_token', 'Q_joint', 'Q_token')},
        'usage': usage, 'known_complete_response_tokens': usage.get('total_tokens') if usage else (None if attempted else 0),
        'full_actual_tokens': None if attempted else 0,
        'ledger_charged_tokens': budget['model']['charged_tokens'] if budget else (None if attempted else 0),
        'member_tests': budget['tests']['used'] if budget else (None if attempted else 0),
        'episode_start_steps': binding.get('episode_start_steps'), 'learning_binding': binding.get('learning_binding'),
        'evaluation_guard': optional(folder / 'evaluation-guard.json'),
        'interruption': optional(folder / 'interruption.json'),
        'feedback_denominators': None, 'page_denominators': None,
        'resource_refusal_counts': None, 'mechanical_decision': None,
        'full_tree_work': None, 'scope': 'No synthetic closure, feedback denominator or acceptance from missing artifacts.',
        'sources': {name: ref(folder / name) for name in ('organization-evidence.json', 'team-budget.json',
            'model-scenario.json', 'interruption.json', 'evaluation-guard.json') if (folder / name).is_file()}}


def old_rows():
    saved = read(OLD_REPORT)
    original = {row['slot_id']: row for row in saved['rows']}
    expected = ('org49-dev-DA-s1-B', 'org49-dev-DA-s2-B')
    if set(original) != set(expected) or saved['aggregate']['F_B'] is not None:
        raise ValueError('Require the unchanged original two-DA unknown-preserving summary')
    rows = []
    for sid in expected:
        row = copy.deepcopy(original[sid])
        for name in ('team-budget.json', 'episode/manifest.json', 'slot-result.json', 'interruption.json'):
            if name in row['sources']:
                preserved(row['sources'][name])
        if sid.endswith('s2-B') and (OLD_ROOT / 'dev-B/actual/episodes' / sid / 'slot-result.json').exists():
            raise ValueError('Original DA2 unknown must not be retroactively overwritten')
        usage = row.get('usage', row.get('known_complete_response_usage'))
        row['usage'] = usage
        row['known_complete_response_tokens'] = usage['total_tokens']
        row['full_actual_tokens'] = usage['total_tokens'] if sid.endswith('s1-B') else None
        row['ledger_charged_tokens'] = usage['budget_charged_tokens']
        row['stage'] = 'original_r1_retained_once'
        row['original_snapshot_source'] = ref(OLD_REPORT)
        if sid.endswith('s1-B'):
            folder = OLD_ROOT / 'dev-B/actual/episodes' / sid
            row['full_tree_work'] = full_tree_work(folder, read(folder / 'slot-result.json'),
                                                   read(folder / 'mechanical-measurement.json'))
        else:
            row['feedback_denominators'] = None
            row['page_denominators'] = None
            row['resource_refusal_counts'] = None
            row['mechanical_decision'] = None
            row['full_tree_work'] = None
        rows.append(row)
    return saved, rows


def total_known(rows, field):
    values = [row.get(field) for row in rows]
    return sum(value for value in values if type(value) in (int, float)), all(value is not None for value in values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--output', type=Path, default=ANALYSIS / 'development-four-work-facts-r2g.json')
    parser.add_argument('--check-ready', action='store_true')
    args = parser.parse_args()
    root = args.run_root.resolve()
    ready, reason, supervisor = readiness(root)
    if not ready or args.check_ready:
        print(json.dumps({'ready': ready, 'reason': reason, 'fact_files_written': False}))
        return
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Preserve existing final analysis; choose a separate output explicitly')
    plan = read(root / 'plan.json')
    if plan.get('version') != 'software-learning-original-B-development-resume-v0.49-r2g':
        raise ValueError('This final resource-adapted report requires the actual frozen r2g plan')
    resource_amendment = resource_history(plan)
    units = plan['resume_inventory']['remaining_development_units']
    if [unit['unit_id'] + '-B' for unit in units] != list(DB_IDS):
        raise ValueError('Only the two original DB units may be merged')
    original, rows = old_rows()
    reader, reader_ref = load_behavior_reader()
    worker_receipts = []
    for worker, unit in zip(WORKERS, units):
        unit = {**unit, 'slot_id': unit['unit_id'] + '-B'}
        output = root / worker / 'actual'
        folder = output / 'episodes' / unit['slot_id']
        if (folder / 'slot-result.json').is_file():
            row = analyze_closed(folder, unit, reader)
        else:
            row = analyze_unclosed(folder, unit, supervisor['states'][worker])
        row['stage'] = 'r2g_original_unstarted_DB_first_execution'
        row['worker'] = worker
        row['worker_state'] = supervisor['states'][worker]
        row['loaded_state'] = optional(output / 'loaded-state.json')
        row['worker_report'] = optional(output / 'report.json')
        row['worker_sources'] = {name: ref(output / name) for name in
                                ('loaded-state.json', 'report.json') if (output / name).is_file()}
        row['guard_report'] = guard_report(row, plan)
        row['worker_elapsed_gpu_seconds'] = supervisor['states'][worker].get('elapsed_gpu_seconds')
        row['slot_result_source'] = row['sources'].get('slot-result.json')
        usage = row.get('usage') or {}
        row['usage_summary'] = {key: usage.get(key) for key in
            ('decisions', 'attempts', 'output_bearing_calls', 'prompt_tokens',
             'completion_tokens', 'total_tokens', 'budget_charged_tokens',
             'uncertain_usage_attempts')}
        row['usage_summary']['member_tests'] = row.get('member_tests')
        rows.append(row)
        worker_receipts.append(worker_host_receipt(root, worker, supervisor['states'][worker], plan))
    ids = [row['slot_id'] for row in rows]
    if ids != ['org49-dev-DA-s1-B', 'org49-dev-DA-s2-B', *DB_IDS] or len(set(ids)) != 4:
        raise ValueError('Count each original development slot exactly once')
    complete = [row for row in rows if row['status'] == 'closed']
    known_tokens, coverage = total_known(rows, 'known_complete_response_tokens')
    charged, charge_coverage = total_known(rows, 'ledger_charged_tokens')
    tests, tests_coverage = total_known(rows, 'member_tests')
    feedback_rows = [row for row in rows if row.get('feedback_denominators') is not None]
    reasons = Counter()
    for row in feedback_rows:
        reasons.update(row['feedback_denominators'].get('no_followup_reasons', {}))
    feedback_totals = {key: sum(row['feedback_denominators'].get(key, 0) for row in feedback_rows)
        for key in ('all_saved_feedback_units', 'protocol_feedback_saved_exactly',
                    'with_later_actual_generation', 'presented_in_later_actual_generation',
                    'presented_in_first_actual_followup', 'without_later_actual_generation')}
    old_seconds = original['aggregate']['worker_gpu_seconds']
    new_seconds = sum(state.get('elapsed_gpu_seconds', 0) for state in supervisor['states'].values())
    aggregate = {'planned_unique_B_slots': 4, 'status_counts': dict(Counter(row['status'] for row in rows)),
        'formal_known_count': len(complete), 'known_R_joint': [row['formal_result']['R_joint'] for row in rows],
        'known_Q_joint': [row['formal_result']['Q_joint'] for row in rows],
        'F_B': None, 'Q_B': None, 'full_actual_tokens': None,
        'estimand_reason': 'Original DA2 remains technical unknown; known successes never replace the original four-slot denominator.',
        'known_complete_response_tokens': known_tokens, 'known_usage_artifact_coverage': coverage,
        'ledger_charged_tokens_known_sum': charged, 'ledger_artifact_coverage': charge_coverage,
        'member_tests_known_sum': tests, 'test_count_artifact_coverage': tests_coverage,
        'usage_counters_from_available_ledgers': {key: sum((row.get('usage') or {}).get(key, 0) for row in rows)
            for key in ('decisions', 'attempts', 'output_bearing_calls', 'prompt_tokens', 'completion_tokens',
                        'total_tokens', 'uncertain_usage_attempts')},
        'feedback_full_four_slot_denominator': None,
        'feedback_measured_closed_slot_ids': [row['slot_id'] for row in feedback_rows],
        'feedback_measured_subset_totals': feedback_totals,
        'feedback_measured_subset_no_followup_reasons': dict(reasons),
        'old_r1_development_worker_seconds_once': old_seconds,
        'old_r2_wait_gpu_worker_seconds': resource_amendment['gpu_worker_seconds'],
        'new_r2g_development_worker_seconds': new_seconds,
        'new_r2_development_worker_seconds': new_seconds,
        'unique_development_worker_seconds': old_seconds + new_seconds,
        'new_learning_steps': {'actor': 0, 'critic': 0, 'backward': 0},
        'causal_learning_gain': None, 'Contribution': None}
    report = {'version': 'v049-original-four-B-development-r2g-readonly-v2',
        'r2g_supervisor_status': supervisor['status'], 'r2g_ended_at': supervisor['ended_at'],
        'r2_supervisor_status': supervisor['status'], 'r2_ended_at': supervisor['ended_at'],
        'retained_field_alias_scope': 'The pre-existing r2_* report keys name this continuation and alias the actual r2g evidence below. Original waiting r2 is exclusively resource_amendment; it has zero model workers.',
        'actual_run_root': str(root), 'resource_amendment': resource_amendment,
        'actual_resource_plan': {'gpu_preference': plan['gpu_preference'], 'limits': plan['limits'],
            'new_budget_caps': plan['new_budget_caps'], 'resource_protocol': plan['resource_protocol'],
            'resource_cpu_controls': plan['resource_cpu_controls'],
            'frozen_original_inventory_resources_unchanged': plan['inventory']['resources']},
        'supervisor_launch': optional(root / 'launch.json'),
        'supervisor_launch_source': ref(root / 'launch.json'),
        'aggregate': aggregate, 'rows': rows, 'worker_receipts': worker_receipts,
        'retained_original_snapshot': ref(OLD_REPORT), 'original_supervisor': ref(OLD_ROOT / 'supervisor.json'),
        'r2g_plan': ref(root / 'plan.json'), 'r2g_supervisor': ref(root / 'supervisor.json'),
        'r2_plan': ref(root / 'plan.json'), 'r2_supervisor': ref(root / 'supervisor.json'),
        'analysis_program': ref(__file__), 'pure_json_behavior_reader': reader_ref,
        'new_model_calls': 0, 'new_GPU_calls': 0, 'new_tokenizer_calls': 0,
        'new_test_or_acceptance_calls': 0, 'new_training_exports': 0, 'tensor_files_read': 0,
        'original_files_modified': False, 'old_costs_counted_once': True,
        'scope': 'Only saved original DA and first-run DB evidence. No reranking, retry, Mapper/learning re-export, re-acceptance or unknown-to-zero imputation.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded(report))
    lines = ['# v049 原四槽 B 开发：r1＋r2g 只读合并', '',
        '逐槽读取原件，原r1两DA只计一次，r2g只加入原两DB首次执行；旧r2为零worker等待及主动资源扩展停止，不占模型样本或GPU worker成本。DA2的正式结果、完整实际费用和完整四槽F_B均保持null。没有重新模型生成、分词、测试、验收、训练导出或读取.pt。', '',
        '| 槽 | 阶段 | 状态 | R / Q | 完整回包 | 已知token | 账本扣账 | 测试 |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for row in rows:
        usage = row.get('usage') or {}
        lines.append(f"| {row['slot_id']} | {row['stage']} | {row['status']} | {row['formal_result']['R_joint']} / {row['formal_result']['Q_joint']} | {usage.get('output_bearing_calls')} | {row['known_complete_response_tokens']} | {row['ledger_charged_tokens']} | {row['member_tests']} |")
    lines += ['', f"已保存完整回包费用合{known_tokens} token，账本扣账已知合{charged}，成员测试{tests}。完整实际费用及F_B/Q_B仍null；DA2的不确定预约不能当作实际生成token。", '',
        f"GPU worker：原开发{old_seconds}秒只计一次；新r2g {new_seconds}秒；唯一开发合{old_seconds + new_seconds}秒。训练计算与采集费用不在这里重复相加。", '',
        f"反馈统计只覆盖已有正式测量的槽{aggregate['feedback_measured_closed_slot_ids']}：{feedback_totals}；无后继原因{dict(reasons)}。缺少DA2完整反馈测量，四槽反馈分母保持null。", '']
    lines += ['## 实际 GPU 调度与原资源守卫', '',
        f"实际候选物理卡：{plan['gpu_preference']}；继承原库存中的3457字面保持历史身份，实际调度以r2g资源协议、plan和worker-launch为准。",
        f"旧r2主动停止保留：{resource_amendment['supervisor']['status']}，worker/调用/GPU worker秒均0；原signal15/KeyboardInterrupt与另存资源扩展回执并列，不回写旧异常分类。", '']
    for receipt in worker_receipts:
        resource = receipt.get('resources') or {}
        lines += [f"- {receipt['worker']}：物理GPU {receipt['physical_gpu']}，UUID {receipt['physical_gpu_uuid']}；实际launch与supervisor命令一致={receipt['actual_launch_command_matches_supervisor']}；保存资源样本{resource.get('saved_samples')}条，原资源stop原因{resource.get('saved_guard_stop_reasons')}，绑定问题{resource.get('binding_issues')}。"]
    lines += ['', 'worker-launch中的requested r2命令是继承预启动意图；actual_command与supervisor进程身份记录真实r2g执行。资源汇总读取既有采样，不新调用GPU，也不将离散采样升级为连续无风险保证。', '']
    for row in rows:
        lines += [f"## {row['slot_id']}", '',
            f"起始步骤：{row.get('episode_start_steps', row.get('independent_start_binding_from_original_model_scenario', {}).get('episode_start_steps'))}。",
            f"B绑定：{row.get('learning_binding', row.get('independent_start_binding_from_original_model_scenario', {}).get('learning_binding'))}。",
            f"单槽guard：{ {key:(row.get('evaluation_guard') or {}).get(key) for key in GUARDS} }。",
            f"新DB保存的恢复/关闭回执摘要：{row.get('guard_report')}。",
            f"反馈：{row.get('feedback_denominators')}；分页：{row.get('page_denominators')}。",
            f"局部资源拒绝：{row.get('resource_refusal_counts')}；机械判断：{row.get('mechanical_decision')}。", '']
        work = row.get('full_tree_work')
        if work:
            lines += [f"最后固定交付：{work['fixed_delivery']}。", f"原绑定测试事件：{work['final_bound_test_original_event']}。"]
            if not work['adoptions']:
                lines.append('原件没有完整候选采用事件；不据此推断所有语义伙伴信息均未使用。')
            for adoption in work['adoptions']:
                lines.append(f"采用事件{adoption['world_event']['sequence']}：{adoption['author']}→{adoption['recipient']}，改变路径{adoption['changed_paths']}；精确采用={adoption['exact_fixed_candidate_files_confirmed']}，同树本人测试{[x['sequence'] for x in adoption['subsequent_recipient_tests_on_exact_adopted_files']]}；该非同值伙伴整树进入最终固定交付链={adoption['nonidentity_peer_full_tree_to_own_test_to_final_fixed_delivery_chain']}。")
            lines.append('采用、本人同树测试、原固定交付是文件动作事实，不自动等于交付收益或Contribution。')
        elif row['slot_id'] == 'org49-dev-DA-s2-B':
            lines.append('保留原中断与第5attempt未知：39347完整回包token＋13049不确定预约，账本52396；单槽cleanup guard不证明可精确恢复第5生成，原正式结果和完整费用仍null。')
        else:
            lines.append('没有足够正式闭合/文件链原件；未根据现存工作区补验或补造终态。')
        lines.append('')
    lines += ['完整四槽结果缺证，不能以已知成功子集宣称F_B=1或学习改善。源文件SHA、每次采用前后/来源整文件树凭据、原同树测试与实际反馈呈现细节保留在JSON。', '']
    args.output.with_suffix('.md').write_text('\n'.join(lines))
    print(json.dumps({'output': str(args.output), 'aggregate': aggregate}, ensure_ascii=False))


if __name__ == '__main__':
    main()
