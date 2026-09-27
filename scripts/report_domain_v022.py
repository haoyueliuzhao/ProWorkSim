"""Read-only N1/W1/B1/R1 accounting. Never score, replay, sample, or update."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time

VERSION = 'domain-terminal-accounting-v0.22'
LINES = ('N1', 'W1', 'B1', 'R1')
TOTAL_GPU_SECONDS = 7200


def reference(path):
    path = Path(path).resolve()
    if not path.is_file():
        return None
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return {'path': str(path), 'sha256': sha.hexdigest(), 'bytes': path.stat().st_size}


def read(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).is_file() else default


def pick(value, keys):
    return {key: value.get(key) for key in keys}


def conjunction(values):
    values = list(values)
    if any(value is False for value in values):
        return False
    return True if values and all(value is True for value in values) else None


def terminal(state):
    return (state.get('ended_at') is not None and state.get('exit_code') is not None
            and state.get('status') in {'complete', 'stopped', 'failed', 'error', 'closed'})


def decode_json_stream(text):
    """Read both pretty concatenated objects and JSONL; expose partial tails."""
    decoder, values, offset = json.JSONDecoder(), [], 0
    while offset < len(text):
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset == len(text):
            break
        try:
            value, end = decoder.raw_decode(text, offset)
        except json.JSONDecodeError as error:
            return values, {'complete': False, 'tail_offset': offset,
                            'tail_characters': len(text) - offset, 'error': str(error)}
        if not isinstance(value, dict):
            return values, {'complete': False, 'tail_offset': offset,
                            'error': 'Resource stream item is not an object'}
        values.append(value)
        offset = end
    return values, {'complete': True, 'tail_offset': None, 'tail_characters': 0}


def resources(path, state):
    if not path.exists():
        return {'reference': None, 'available': False, 'execution_samples': None}
    data = path.read_bytes()
    rows, decoding = decode_json_stream(data.decode())
    start, end = state.get('started_at'), state.get('ended_at')
    execution = [row for row in rows if isinstance(row.get('sample', {}).get('time'), (int, float))
                 and start is not None and row['sample']['time'] >= start
                 and (end is None or row['sample']['time'] <= end)]
    peaks = {}
    for key in ('rss_bytes', 'all_lines_rss_bytes', 'artifact_bytes', 'own_gpu_memory_mib'):
        values = [row[key] for row in execution if isinstance(row.get(key), (int, float))]
        peaks[key] = max(values) if values else None
    failures, parse_errors, competition = Counter(), Counter(), {}
    card_used, last_time = [], None
    for row in execution:
        sample = row['sample']
        last_time = sample['time']
        for query in ('gpus', 'processes'):
            command = sample.get(query)
            if not isinstance(command, dict) or command.get('returncode') != 0:
                failures[query] += 1
        if any(sample.get(query, {}).get('returncode') != 0 for query in ('gpus', 'processes')):
            continue
        cards = {}
        try:
            for line in sample['gpus'].get('stdout', '').splitlines():
                fields = [part.strip() for part in line.split(',')]
                cards[int(fields[0])] = {'uuid': fields[1], 'free_mib': float(fields[3]),
                                         'total_mib': float(fields[4]), 'utilization_percent': float(fields[5])}
        except (ValueError, IndexError):
            parse_errors['gpus'] += 1
            continue
        card = cards.get(state.get('gpu'))
        if card is None:
            parse_errors['selected_gpu_missing'] += 1
            continue
        card_used.append(card['total_mib'] - card['free_mib'])
        for line in sample['processes'].get('stdout', '').splitlines():
            try:
                uuid, pid, memory, _ = [part.strip() for part in line.split(',', 3)]
                pid, memory = int(pid), float(memory)
            except (ValueError, IndexError):
                parse_errors['processes'] += 1
                continue
            if uuid != card['uuid'] or pid == state.get('pid'):
                continue
            key = (uuid, pid)
            found = competition.setdefault(key, {'pid': pid, 'gpu_uuid': uuid,
                'first_observed_at': sample['time'], 'last_observed_at': sample['time'],
                'samples': 0, 'peak_memory_mib': memory, 'first_sample': pick(card, ('free_mib', 'total_mib', 'utilization_percent'))})
            found['samples'] += 1
            found['last_observed_at'] = sample['time']
            found['peak_memory_mib'] = max(found['peak_memory_mib'], memory)
    return {'available': True, 'reference': {'path': str(path.resolve()),
            'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)},
            'decoding': decoding, 'decoded_samples': len(rows), 'execution_samples': len(execution),
            'pre_or_post_execution_samples': len(rows) - len(execution), 'last_execution_sample_at': last_time,
            'sampled_peaks': peaks, 'selected_card_total_used_peak_mib': max(card_used) if card_used else None,
            'query_failures': {query: failures[query] for query in ('gpus', 'processes')},
            'parse_errors': dict(parse_errors), 'other_pids_on_selected_card': list(competition.values()),
            'scope': 'Execution interval only. Discrete samples, not continuous hardware peaks. rss includes worker descendants; own_gpu_memory is the supervisor-selected worker PID only. Other PIDs are observed co-residency, not proof of causation or ownership. Card CSV is index,uuid,name,freeMiB,totalMiB,utilization. artifact_bytes measures the entire shared run tree and must not be summed across lines.'}


def calls(folder):
    references = []
    grouped = defaultdict(lambda: {'attempts': 0, 'actual_generations': 0,
        'local_context_400': 0, 'other_or_unclassified': 0,
        'prompt_tokens': 0, 'completion_tokens': 0, 'statuses': Counter(), 'actor_identities': {}})
    for path in sorted((folder / 'resident/calls').glob('*.json')):
        row = read(path)
        references.append(reference(path))
        group = grouped[str(row.get('online_window_id'))]
        group['attempts'] += 1
        group['statuses'][str(row.get('status'))] += 1
        identity = row.get('actor_identity')
        group['actor_identities'][json.dumps(identity, sort_keys=True)] = identity
        if row.get('status') == 200 and row.get('raw_output_ids'):
            group['actual_generations'] += 1
            usage = row.get('response', {}).get('usage', {})
            group['prompt_tokens'] += usage.get('prompt_tokens', 0)
            group['completion_tokens'] += len(row['raw_output_ids'])
        elif (row.get('status') == 400 and not row.get('raw_output_ids')
              and row.get('response', {}).get('error', {}).get('code') == 'context_length_exceeded'):
            group['local_context_400'] += 1
        else:
            group['other_or_unclassified'] += 1
    for group in grouped.values():
        group['actor_identities'] = list(group['actor_identities'].values())
        group['statuses'] = dict(group['statuses'])
    totals = {key: sum(group[key] for group in grouped.values()) for key in
              ('attempts', 'actual_generations', 'local_context_400', 'other_or_unclassified', 'prompt_tokens', 'completion_tokens')}
    return {'observed_totals': totals, 'windows': dict(grouped), 'references': references,
            'scope': 'Saved resident calls only; Only status400 with error.code=context_length_exceeded and no output is a local context rejection, not remote service downtime. N1 replays and R1 training recomputations are not generation calls. Zero observed records is not an assertion that an unfinished line will generate none.'}


def episode(folder):
    manifest_path = folder / 'episode/manifest.json'
    manifest = read(manifest_path, {})
    exp_ref = manifest.get('experience', {})
    path = manifest_path.parent / exp_ref.get('path', 'experience.json')
    experience = read(path, {})
    events = experience.get('events', [])
    model_calls = [event for event in events if event.get('kind') == 'model_call']
    decisions = {(event.get('worker_id'), event.get('payload', {}).get('call_id'))
                 for event in model_calls if event.get('payload', {}).get('call_id')}
    flush = [event for event in events if event.get('kind') == 'model_boundary_error'
             and event.get('payload', {}).get('status') == 'model_budget_exhausted'
             and 'max_decisions' in event['payload'].get('limits', [])
             and not event['payload'].get('model_call_id')]
    return {'manifest': reference(manifest_path), 'experience': reference(path),
            'closed': manifest.get('status') == 'closed' if manifest else None,
            'recorded_model_decisions': len(decisions) if manifest else None,
            'model_call_event_rows': len(model_calls) if manifest else None,
            'non_generating_budget_flush': len(flush) if manifest else None,
            'format_feedback': sum(event.get('kind') == 'model_format_feedback' for event in events) if manifest else None,
            'experience_matches_manifest': (reference(path)['sha256'] == exp_ref.get('sha256'))
            if exp_ref and path.exists() else None}


def probability(path):
    value = read(path)
    if value is None:
        return None
    rows = value if isinstance(value, list) else value.get('rows', [])
    return {'reference': reference(path), 'decisions': len(rows),
            'output_targets': sum(len(row.get('actual_behavior_logprobs', [])) for row in rows),
            'all_passed': conjunction(row.get('passed') for row in rows),
            'max_abs_delta': max((row.get('max_abs_delta', 0) for row in rows), default=None),
            'max_row_mean_abs_delta': max((row.get('mean_abs_delta', 0) for row in rows), default=None)}


def update(folder, report, is_terminal):
    path = folder / 'update/report.json'
    saved = read(path, {})
    known_steps = report.get('actor_steps') is not None and report.get('critic_steps') is not None
    keys = ('version', 'window_id', 'status', 'stage', 'actor_optimizer_steps', 'critic_optimizer_steps',
            'training_happened', 'backward_decisions_completed', 'admitted_decisions', 'scheduled_slots',
            'admitted_output_tokens', 'behavior_probability_passed', 'composition', 'advantage',
            'target_normalization_scope', 'actor_update_enabled', 'zero_signal_window',
            'before_actor_identity', 'after_actor_identity', 'resource', 'gradient_norms',
            'changed_actor_elements', 'post_update_additional_actor_forwards', 'actor_steps_total', 'critic_steps_total')
    return {'reference': reference(path), 'last_persisted': pick(saved, keys),
            'terminal_actor_steps': report.get('actor_steps') if is_terminal and known_steps else None,
            'terminal_critic_steps': report.get('critic_steps') if is_terminal and known_steps else None,
            'behavior_probability': probability(folder / 'update/behavior-probability-check.json'),
            'gradient_probability': probability(folder / 'update/gradient-probability-check.json'),
            'artifacts': {name: reference(folder / 'update' / name) for name in
                ('admission.json', 'shared-before.pt', 'gradient-probability-check.json', 'losses.json',
                 'signal-diagnostics.json', 'gradients-before-clip.pt', 'post-update-sampled-policy.json')},
            'checkpoint_reference': reference(folder / 'checkpoint/checkpoint.json'),
            'checkpoint': report.get('checkpoint'),
            'scope': 'Persisted progress is not terminal parameter proof. Missing final step or gradient records remain null; old partial gradients are never credited to R1.'}


def work_row(row, folder, expected_actor=None):
    assessment = row.get('assessment', {})
    guard = row.get('evaluation_guard', {})
    identity = row.get('actor_identity')
    return {**pick(row, ('slot', 'case_id', 'arm', 'sampling_seed', 'status', 'started_at', 'ended_at', 'actor_identity', 'error')),
            'assessment': pick(assessment, ('version', 'eligible', 'reward', 'completed', 'components',
                'record_trust', 'independent_assessability', 'preparation_credited', 'mapper')),
            'assessment_reference': reference(folder / 'assessment.json'),
            'evaluation_guard': pick(guard, ('learning_unchanged', 'rng_restored_exactly')),
            'matches_expected_actor': identity == expected_actor if identity and expected_actor else None,
            'episode': episode(folder)}


def line_report(name, root):
    line, folder = root / name, root / name / 'actual'
    state, report = read(line / 'state.json', {}), read(folder / 'report.json', {})
    is_terminal = terminal(state)
    result = {'execution_terminal': is_terminal, 'state': pick(state, ('status', 'attempted', 'source', 'plan',
        'gpu', 'pid', 'started_at', 'ended_at', 'exit_code', 'elapsed_gpu_seconds', 'stop_reason', 'budget_seconds')),
        'references': {'state': reference(line / 'state.json'), 'report': reference(folder / 'report.json'),
                       'model_log': reference(line / 'model.log')},
        'last_persisted_report_status': report.get('status'), 'resources': resources(line / 'resources.jsonl', state),
        'resident_calls': calls(folder), 'identity_and_guards': pick(report, ('initial_actor_identity',
            'final_actor_identity', 'actor_identity_unchanged', 'final_identity_matches_initial',
            'source_before', 'source_after', 'source_unchanged', 'actor_steps', 'critic_steps'))}
    if name == 'N1':
        rows = []
        for row in report.get('rows', []):
            rows.append({**pick(row, ('request', 'record', 'input_tokens', 'output_tokens', 'status', 'actual_backward',
                'backward_attempted', 'parameter_steps', 'raw_tokens_and_behavior_preserved', 'all_output_targets_included',
                'forward_seconds', 'backward_seconds', 'probability_dtype', 'probability_requires_grad',
                'gradient_tensors', 'finite_gradients', 'nonzero_gradient_elements', 'peak_gpu_allocated_bytes',
                'forward_peak_gpu_allocated_bytes', 'actor_identity_unchanged')),
                'probability': pick(row.get('probability', {}), ('max_abs_delta', 'mean_abs_delta', 'passed'))})
        result['numerical'] = {**pick(report, ('qualification_passed', 'new_sampling', 'actual_backward_calls',
            'backward_calls_attempted', 'parameter_steps', 'learning_state_guard', 'scope')),
            'output_probability_targets': sum(row.get('output_tokens', 0) for row in rows), 'rows': rows}
    elif name == 'W1':
        result['work'] = {'planned': report.get('planned_episodes'), 'not_started': report.get('not_started'),
            'rows': [work_row(row, folder / f"slot-{row['slot']}", report.get('initial_actor_identity')) for row in report.get('rows', [])],
            'original_scores_unchanged': True, 'training_projection': report.get('training_projection')}
        paired = defaultdict(list)
        for row in result['work']['rows']:
            paired[row['case_id']].append(row)
        result['work']['pairs'] = [{'case_id': key, 'arms': {row['arm']: row['assessment']['reward'] for row in rows},
            'paired_seed_equal': len(rows) == 2 and rows[0]['sampling_seed'] == rows[1]['sampling_seed']}
            for key, rows in paired.items()]
        result['work']['global_frozen_policy_guard'] = conjunction([
            report.get('final_identity_matches_initial'), report.get('source_unchanged'),
            *(report.get(key) == 0 if report.get(key) is not None else None for key in ('actor_steps', 'critic_steps'))
        ]) if is_terminal else None
        result['work']['all_closed_episode_guards'] = conjunction(
            conjunction([row['status'] == 'closed', row['matches_expected_actor'],
                row['evaluation_guard']['learning_unchanged'], row['evaluation_guard']['rng_restored_exactly']])
            for row in result['work']['rows']) if is_terminal else None
        milestone_path = line / 'milestones-final.json'
        result['work']['readonly_milestones'] = reference(milestone_path)
    elif name == 'B1':
        rows = report.get('train_rows', read(folder / 'train-progress.json', []))
        result['training'] = {'rows': [{**pick(row, ('slot', 'case_id', 'status', 'started_at', 'ended_at', 'record_validity')),
            'reward': pick(row.get('reward', {}), ('eligible', 'reward', 'completed', 'record_trust', 'independent_assessability')),
            'projection': pick(row.get('projection', {}), ('actual_trainable_token_count', 'has_complete_trainable_actual_members',
                'has_actual_trainable_tokens', 'token_projection_members', 'normalization_preserves_scheduled_slot')),
            'episode': episode(folder / f"train-{row['slot']}")} for row in rows],
            'declaration': reference(folder / 'train-declaration.json'), 'learner_execution_profile': report.get('learner_execution_profile')}
        result['update'] = update(folder, report, is_terminal)
    else:
        result['recovery'] = pick(report, ('old_B1_status_preserved', 'no_step_proof', 'admission_reconstruction',
            'admission_after_restore', 'new_training_model_calls', 'last_persisted_discarded_backward_decisions',
            'unpersisted_in_progress_backward_work', 'learner_execution_profile', 'recomputed_training_decisions_planned',
            'original_window', 'restoration', 'after_update_actor_identity', 'scope', 'error'))
        result['update'] = update(folder, report, is_terminal)
        rows = report.get('post_rows', read(folder / 'post-progress.json', []))
        result['post_development'] = {'planned': 2, 'observed_rows': [work_row(row, folder / f"post-{row['slot']}",
            report.get('after_update_actor_identity')) for row in rows],
            'terminal_closed_count': sum(row.get('status') == 'closed' for row in rows) if is_terminal else None,
            'scope': 'Two new reserved post-update development cases; different from W1 and training materials. No matched pre-update evaluation and no learning-gain estimate.'}
    return result


def summarize(root, takeover_launch=None):
    root = Path(root).resolve()
    lines = {name: line_report(name, root) for name in LINES}
    final = all(line['execution_terminal'] for line in lines.values())
    elapsed = {name: line['state']['elapsed_gpu_seconds'] for name, line in lines.items()}
    known = {name: value for name, value in elapsed.items() if lines[name]['execution_terminal'] and isinstance(value, (int, float))}
    total = sum(known.values()) if final and len(known) == len(LINES) else None
    artifact_values = [line['resources'].get('sampled_peaks', {}).get('artifact_bytes') for line in lines.values()]
    artifact_values = [value for value in artifact_values if value is not None]
    takeover_launch = Path(takeover_launch) if takeover_launch else root.parent / 'v022-b1-amendment-launch.json'
    takeover_log = takeover_launch.with_name('v022-b1-amendment-observer.log')
    log = takeover_log.read_text() if takeover_log.exists() else ''
    rejection = 'Only the identified own worker and its separate observer can be amended' in log
    result = {'version': VERSION, 'generated_at_epoch': time.time(), 'final': final,
        'scope': 'Read-only original artifacts; no model calls, numerical replay, world execution, reward re-evaluation, retries, or raw-file writes. Missing or unfinished terminal facts remain null. Original failures and recovery costs are both retained.',
        'reporter': reference(Path(__file__)), 'run_root': str(root), 'lines': lines,
        'accounting': {'limit_gpu_seconds': TOTAL_GPU_SECONDS, 'final_gpu_seconds': total,
            'known_terminated_gpu_seconds': sum(known.values()), 'known_terminated_by_line': known,
            'within_total_gpu_budget': total <= TOTAL_GPU_SECONDS if total is not None else
                (False if sum(known.values()) > TOTAL_GPU_SECONDS else None),
            'sampled_shared_artifact_tree_peak_bytes': max(artifact_values) if artifact_values else None,
            'scope': 'Sum one-device supervisor elapsed time including model loading, failed B1, all R1 recomputation and post-development. Overlapping wall-clock intervals count once per active GPU line. R1 prior_gpu_seconds is not added again. Artifact maxima describe the shared tree and are not additive. Snapshot subtotal excludes still-running elapsed time and is only a lower bound.'},
        'failed_resource_amendment': {'launch': reference(takeover_launch), 'log': reference(takeover_log),
            'source_script': reference(root.parent / 'frozen-v022-resource-amendment/scripts/amend_bridge_supervision_v022.py'),
            'plan': reference(root.parent / 'frozen-v022-resource-amendment/examples/id-vtdo-v22/b1-resource-amendment.json'),
            'ownership_guard_rejection_observed': rejection if log else None,
            'takeover_completed': False if rejection else None,
            'new_model_launched_by_amendment': False if rejection else None,
            'additional_model_gpu_seconds': 0 if rejection else None,
            'scope': 'Failed supervisor-only amendment is retained separately; it did not replace the original B1 supervisor or constitute the subsequent R1 restoration.'},
        'interpretation': {'training_trajectory_generation': 'Only original B1 collection. R1 reuses its same24 decisions, exact saved tokens/admission and before-update state; recomputation is additional cost, never new trajectories.',
            'numerical_qualification': 'N1 finite fixed-request probability and actual backward witnesses; does not certify arbitrary future long trajectories.',
            'work_comparison': 'W1 fixed-policy12 paired development episodes. Original scores copied, not recomputed. Preparation and CPU milestone diagnostics are not model accomplishments.',
            'learning_claim': 'At most one actor/critic update and two different post-update development cases establish an executable bridge only; no matched learning-effect estimate.'}}
    result['lines']['B1']['no_step_evidence_from_R1'] = lines['R1']['recovery'].get('no_step_proof')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=Path('runs/domain-v022'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    parser.add_argument('--takeover-launch', type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.run.resolve()):
        raise ValueError('Reporting output must be outside the original run tree')
    result = summarize(args.run, args.takeover_launch)
    if args.require_final and not result['final']:
        raise ValueError('All four actual supervisor endpoints are required for a final report')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'final': result['final'],
                      'accounting': result['accounting']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
