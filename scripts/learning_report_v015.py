"""Read-only S1/N0/N1 accounting from frozen protocols and saved measurements.

No model, checkpoint tensor, SQL, world evaluator or optimizer is loaded.
Unknown/unstarted measurements stay unknown. Output must be a new directory.
"""
import argparse
import copy
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

from scripts.learning_study_report_v014 import Reader, steps_for_window
from scripts.online_report_v013 import _reward, _support, summarize_events

VERSION = 'learning-readonly-v0.15'
TERMINAL = {'complete', 'error', 'interrupted', 'stopped_probability_mismatch', 'finished', 'failed'}
TASKS = {'handoff', 'implement', 'review', 'pair', 'chain'}


def _path(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _value(value):
    return value.get('value') if isinstance(value, dict) else value


def _unique(slots):
    seen, result = set(), []
    for row in slots:
        key = row.get('measurement_key') or row['planned_slot_key']
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def aggregate(slots):
    """Raw measurement counted once; missing rewards are never filled with zero."""
    unique = _unique(slots)
    states = Counter(row['state'] for row in unique)
    known = [r for r in unique if r['state'] == 'closed_known']
    complete_values = [r['reward'].get('completed') for r in known]
    components = defaultdict(Counter)
    for row in known:
        for part in row['reward'].get('components', []):
            count = components[part['term_id']]
            count['measured'] += 1
            count['achieved'] += part.get('achieved') is True
            count['missing_achieved'] += type(part.get('achieved')) is not bool
            if _finite(part.get('score')):
                count['score_sum'] += part['score']
                count['score_count'] += 1
            else:
                count['missing_score'] += 1
    counts = {k: states.get(k, 0) for k in ('closed_known', 'closed_unknown', 'open', 'interrupted_open', 'not_started')}
    counts.update(planned=len(slots), distinct_planned_or_measured=len(unique),
                  duplicate_measurement_references=len(slots)-len(unique),
                  closed=counts['closed_known']+counts['closed_unknown'],
                  started=len(unique)-counts['not_started'])
    all_known = bool(unique) and len(known) == len(unique)
    all_completed_known = all_known and all(type(v) is bool for v in complete_values)
    return {'counts': counts, 'observed_reward_count': len(known),
            'observed_reward_sum': sum(r['reward']['reward'] for r in known),
            'mean_reward': sum(r['reward']['reward'] for r in known)/len(unique) if all_known else None,
            'completed_work_count': sum(v is True for v in complete_values),
            'completed_work_measured_count': sum(type(v) is bool for v in complete_values),
            'completed_work_rate': sum(v is True for v in complete_values)/len(unique) if all_completed_known else None,
            'components': {k: dict(v) for k, v in components.items()},
            'record_counts': dict(Counter(str(r.get('record_validity')) for r in unique if r['state'].startswith('closed'))),
            'V_counts': dict(Counter(str(r.get('V')) for r in unique if r['state'].startswith('closed'))),
            'method_labels': dict(Counter((r.get('method') or {}).get('class_id') or 'unmapped_or_missing' for r in unique if r['state'].startswith('closed'))),
            'method_scope': 'Descriptive per-episode labels only; not support or empirical b. Saved b remains per original window/xi/theta/Gamma/member.',
            'missing_rule': 'Rates/means withheld unless all distinct planned measurements are known. No reward or completion is imputed for unknown/open/not_started.'}


def _traces(events):
    rows, seen = [], set()
    for event in events:
        if event.get('kind') != 'model_attempt' or event['payload'].get('stage') != 'finished':
            continue
        payload = event['payload']
        body = (payload.get('response') or {}).get('body') or {}
        trace = body.get('token_trace')
        if not isinstance(trace, dict):
            continue
        key = (event.get('worker_id'), body.get('id') or payload.get('attempt_id') or payload.get('call_id'))
        if key in seen:
            continue
        seen.add(key)
        inputs, outputs = trace.get('input_ids'), trace.get('output_ids')
        issues = []
        if not isinstance(inputs, list) or not isinstance(outputs, list):
            issues.append('missing_original_token_ids')
        n_in, n_out = len(inputs) if isinstance(inputs, list) else None, len(outputs) if isinstance(outputs, list) else None
        usage = body.get('usage') or {}
        if n_in is not None and usage.get('prompt_tokens') not in (None, n_in):
            issues.append('input_token_trace_usage_disagree')
        if n_out is not None and usage.get('completion_tokens') not in (None, n_out):
            issues.append('output_token_trace_usage_disagree')
        logps = trace.get('behavior_logprobs')
        rows.append({'member': event.get('worker_id'), 'call_id': payload.get('call_id'), 'response_id': body.get('id'),
                     'sequence': event['sequence'], 'input_tokens': n_in, 'output_tokens': n_out,
                     'input_plus_output': n_in+n_out if n_in is not None and n_out is not None else None,
                     'behavior_logprob_count': len(logps) if isinstance(logps, list) else None,
                     'actor_identity': body.get('actor_identity'),
                     'sampling': {k: trace.get(k) for k in ('sampling_temperature', 'sampling_top_p', 'sampling_top_k')},
                     'effective_generation': body.get('effective_generation'),
                     'inference_profile_sha256': body.get('inference_profile_sha256'),
                     'protocol_parse_error': body.get('protocol_parse_error'), 'issues': issues})
    return {'calls': rows, 'measured_calls': len(rows),
            'input_tokens': sum(r['input_tokens'] for r in rows if r['input_tokens'] is not None),
            'output_tokens': sum(r['output_tokens'] for r in rows if r['output_tokens'] is not None),
            'max_input_plus_output': max((r['input_plus_output'] for r in rows if r['input_plus_output'] is not None), default=None),
            'scope': 'Lengths of saved actual token IDs only; no retokenization and no probability recomputation. Missing traces are not reconstructed.'}


def _case_metadata(slot, episode, fallback):
    recorded = (episode or {}).get('scenario', {}).get('variation', {}).get('online_case', {})
    case = {**recorded, **slot.get('case', {})}
    case_id = slot.get('case_id') or case.get('case_id')
    task = slot.get('task') or case.get('task') or (case_id or '').rsplit('-', 1)[-1]
    if task not in TASKS:
        raise ValueError('Unknown task; declare slot.task explicitly for new responsibilities')
    match = re.search(r'(?:^|-)f(\d+)(?:-|$)', case_id or '')
    fact = slot.get('fact_id', slot.get('fact_position', case.get('fact_position', int(match[1]) if match else None)))
    retail_pool = re.match(r'^uci-(train|development|locked)-f', case_id or '')
    old_pool = re.match(r'^(.+)-v14-f', case_id or '')
    inferred_pool = retail_pool[1] if retail_pool else old_pool[1] if old_pool else None
    inferred_family = 'uci-online-retail-352' if retail_pool else 'constructed-finite-team-sql' if old_pool else None
    return {'case_id': case_id, 'task': task, 'fact': fact,
            'pool': slot.get('pool', case.get('pool', inferred_pool)), 'family': slot.get('family', case.get('family', inferred_family)),
            'repeat': slot.get('repeat', slot.get('replicate_index', fallback)),
            'repeat_source': 'declared' if 'repeat' in slot or 'replicate_index' in slot else 'within_window_same_case_order',
            'sampling_seed': slot.get('sampling_seed'),
            'deployment': 'shared_weight_team' if task in {'pair', 'chain'} else 'single_role'}


def _slot(reader, folder, slot, summary, declaration, terminal, planned_key, repeat):
    manifest = reader.read(folder / 'episode/manifest.json')
    interrupted = reader.read(folder / 'interruption.json')
    saved = summary.get(slot['slot_id'], {})
    reward, validity = saved.get('reward'), saved.get('work_validity')
    if manifest and manifest.get('status') == 'closed' and (reward is None or validity is None):
        rollout = reader.read(folder / 'team-rollout.json')
        if rollout:
            reward, validity = rollout.get('reward_eligibility'), rollout.get('work_validity')
    reward = _reward(reward)
    closed = bool(manifest and manifest.get('status') == 'closed')
    numeric = bool(reward and reward.get('eligible') is True and _finite(reward.get('reward')))
    state = ('closed_known' if numeric else 'closed_unknown') if closed else (
        'interrupted_open' if manifest and terminal else 'open' if manifest else 'not_started')
    manifest_ref = reader.ref(folder / 'episode/manifest.json')
    row = {**_case_metadata(slot, manifest, repeat), 'slot_id': slot['slot_id'], 'planned_slot_key': planned_key,
           'state': state, 'measurement_key': 'episode:' + manifest_ref['sha256'] if manifest_ref else None,
           'episode_id': (manifest or {}).get('episode_id'), 'episode_manifest_ref': manifest_ref,
           'prepared_world_exists': (folder / 'world').is_dir(), 'reward': reward,
           'work_validity': copy.deepcopy(validity), 'V': _value(validity),
           'record_validity': _value((validity or {}).get('components', {}).get('record')),
           'active_members': (declaration or {}).get('active_members'),
           'method': reader.read(folder / 'mapping.json'), 'boundary': saved.get('boundary'),
           'original_slot_status': saved.get('status'),
           'termination': (manifest or {}).get('termination'), 'interruption': interrupted,
           'sampling': None}
    events, events_path, scope = None, None, None
    if closed:
        events_path = folder / 'episode' / manifest['experience']['path']
        history = reader.read(events_path, optional=False)
        if reader.ref(events_path)['sha256'] != manifest['experience']['sha256']:
            raise ValueError('Closed experience hash differs from saved manifest')
        events = history['events'][manifest['experience']['start']:manifest['experience']['end']]
        scope = 'original_closed_episode_interval'
    elif manifest:
        runtime = (interrupted or {}).get('runtime') or reader.read(folder / 'runtime.json')
        if runtime and isinstance(runtime.get('experience'), dict):
            events = runtime['experience']['events']
            events_path = folder / ('interruption.json' if (interrupted or {}).get('runtime') else 'runtime.json')
            scope = 'saved_open_prefix_only'
    # Do not duplicate giant live runtime/event payloads in the summary.
    row['interruption'] = None if interrupted is None else {k: v for k, v in interrupted.items() if k != 'runtime'}
    if events is not None:
        measured = summarize_events(events, declared_transport='resident_direct')
        row['sampling'] = {'scope': scope, 'events_ref': reader.ref(events_path),
                           **{k: measured[k] for k in ('totals', 'members', 'resources', 'record_issues')},
                           'context_stops': sum(a['status'] == 'backend_context_limit' for a in measured['attempts']),
                           'attempt_statuses': dict(Counter(a['status'] for a in measured['attempts'])),
                           'token_traces': _traces(events)}
    return row


def _sampling(slots):
    measured = [r['sampling'] for r in _unique(slots) if r['sampling'] is not None]
    totals = Counter()
    for row in measured:
        totals.update(row['totals'])
    return {'measured_episodes_or_prefixes': len(measured), 'totals': dict(totals),
            'context_stops': sum(r['context_stops'] for r in measured),
            'trace_calls': sum(r['token_traces']['measured_calls'] for r in measured),
            'trace_input_tokens': sum(r['token_traces']['input_tokens'] for r in measured),
            'trace_output_tokens': sum(r['token_traces']['output_tokens'] for r in measured),
            'scope': 'Actual recorded measurement counted once. Missing/live unrecorded usage is unknown, not invented zero cost.'}


def _run(reader, job, project, source):
    root = _path(project, job['run'])
    protocol_path = _path(source, job['protocol'])
    protocol = reader.read(protocol_path, optional=False)
    actual = reader.read(root / 'online/protocol.json')
    runner = reader.read(root / 'online/report.json') or {}
    owner = reader.read(root / 'resident/owner.json') or {}
    initial = reader.read(root / 'online/initial-checkpoint/checkpoint.json')
    terminal = runner.get('status') in TERMINAL or job.get('status') in TERMINAL
    records = {r['window_id']: r for r in runner.get('windows', [])}
    windows, slots, groups, issues = [], [], [], []
    if actual is not None and actual != protocol:
        issues.append('saved_protocol_differs_from_declared_protocol')
    for wi, spec in enumerate(protocol['windows']):
        mode = spec.get('mode', protocol.get('mode', 'online'))
        if mode not in {'online', 'evaluate'}:
            raise ValueError('Window must explicitly have online/evaluate mode')
        labels = {k: spec.get(k, protocol.get(k, job.get(k))) for k in ('stage', 'phase', 'node')}
        folder = root / f'online/window-{wi}'
        collection = folder / 'collection'
        declaration = reader.read(collection / 'declaration.json')
        saved_summary = reader.read(collection / 'summary.json')
        progress = reader.read(collection / 'progress.json') if saved_summary is None else None
        summary_rows = saved_summary.get('slots', []) if saved_summary else progress or []
        if isinstance(summary_rows, dict):
            summary_rows = summary_rows.get('slots', [])
        summary = {r['slot_id']: r for r in summary_rows}
        record = records.get(spec['window_id'], {})
        update_path = folder / ('evaluation' if mode == 'evaluate' else 'update') / 'report.json'
        update = reader.read(update_path) or record.get('update')
        started = bool(record or declaration or folder.exists())
        steps = steps_for_window(mode, update, started)
        guard = reader.read(folder / 'evaluation-guard.json')
        row = {'index': wi, 'window_id': spec['window_id'], 'mode': mode, **labels,
               'template': spec.get('template'), 'status': record.get('status', 'started_unrecorded' if started else 'not_started'),
               'collection_actor_identity': (declaration or {}).get('actor_identity'),
               'before_actor_identity': record.get('before_actor_identity') or (update or {}).get('before_actor_identity'),
               'after_actor_identity': record.get('after_actor_identity') or (update or {}).get('after_actor_identity'),
               'steps': steps, 'update': {k: copy.deepcopy((update or {}).get(k)) for k in (
                   'status', 'stage', 'training_happened', 'behavior_probability_passed', 'error', 'interruption', 'admitted_decisions',
                   'scheduled_slots', 'admitted_output_tokens', 'gradient_norms', 'zero_signal_window')},
               'update_ref': reader.ref(update_path), 'checkpoint': reader.read(folder / 'checkpoint/checkpoint.json'),
               'evaluation_guard': guard, 'evaluation_guard_ref': reader.ref(folder / 'evaluation-guard.json'),
               'declaration_ref': reader.ref(collection / 'declaration.json'), 'slots': []}
        if mode == 'evaluate' and started and guard is None:
            row['guard_state'] = 'unrecorded'
        elif mode == 'evaluate' and guard:
            row['guard_state'] = 'recorded'
            if guard.get('learning_unchanged') is not True or guard.get('rng_restored_exactly') is not True:
                issues.append({'window_id': spec['window_id'], 'reason': 'evaluation_guard_not_confirmed'})
            if ('learning_before_sha256' in guard and 'learning_after_sha256' in guard
                    and guard['learning_before_sha256'] != guard['learning_after_sha256']):
                issues.append({'window_id': spec['window_id'], 'reason': 'evaluation_guard_actual_fingerprints_differ'})
        occurrence = Counter()
        for si, slot in enumerate(spec['slots']):
            case_id = slot.get('case_id') or slot.get('case', {}).get('case_id')
            decl_slot = next((s for s in (declaration or {}).get('slots', []) if s['slot_id'] == slot['slot_id']), None)
            value = _slot(reader, collection / f'slot-{si}', slot, summary, decl_slot, terminal,
                          f"{job['name']}::{spec['window_id']}::{slot['slot_id']}", occurrence[case_id])
            occurrence[case_id] += 1
            row['slots'].append(value)
            slots.append(value)
        row['progress'], row['sampling'] = aggregate(row['slots']), _sampling(row['slots'])
        support = reader.read(collection / 'support.json')
        row['support'] = _support(support)
        row['support_ref'] = reader.ref(collection / 'support.json')
        if support and declaration and support.get('actor_identity') != declaration.get('actor_identity'):
            issues.append({'window_id': spec['window_id'], 'reason': 'support_actor_identity_differs_from_collection'})
        row['support_scope'] = 'Original window-local xi/theta/Gamma/member blocks only; b is not merged across windows, candidates or seeds.'
        grouped = defaultdict(list)
        for value in row['slots']:
            grouped[(value['family'], value['pool'], value['task'], value['fact'])].append(value)
        for (family, pool, task, fact), values in grouped.items():
            groups.append({'window_id': spec['window_id'], 'mode': mode, **labels,
                           'family': family, 'pool': pool, 'task': task, 'fact': fact, **aggregate(values),
                           'repeats': [{k: copy.deepcopy(v.get(k)) for k in (
                               'slot_id', 'case_id', 'repeat', 'repeat_source', 'sampling_seed', 'state', 'reward',
                               'record_validity', 'V', 'method', 'episode_manifest_ref')} for v in values]})
        windows.append(row)
    step_counts = {k: sum(w['steps'][k] for w in windows if w['steps'][k] is not None) for k in ('actor', 'critic')}
    unknown_steps = [w['window_id'] for w in windows if any(w['steps'][k] is None for k in ('actor', 'critic'))]
    for key, count in step_counts.items():
        if not unknown_steps and runner.get(key + '_steps_total') not in (None, count):
            issues.append('saved_' + key + '_cumulative_total_differs_from_observed_increments')
    launch = _path(project, job['launch']) if job.get('launch') else None
    launch_record = reader.read(str(launch) + '.launch.json') if launch else None
    return {'name': job['name'], 'candidate_id': job.get('candidate_id', protocol.get('candidate_id')),
            'condition': job.get('condition', protocol.get('condition')), 'seed': job.get('seed', protocol.get('replicate_index', protocol.get('seed'))),
            'declared_job': copy.deepcopy(job), 'root': str(root.resolve()),
            'runner_status': runner.get('status', 'not_started_or_unrecorded'), 'terminal': terminal,
            'stop_or_error': {k: runner.get(k) for k in ('status', 'stage', 'error', 'interruption', 'stopped_window', 'last_safe_checkpoint')},
            'protocol_ref': reader.ref(protocol_path), 'saved_protocol_equals_declared': actual == protocol if actual else None,
            'runner_report_ref': reader.ref(root / 'online/report.json'), 'owner': owner,
            'initial_checkpoint': initial, 'final_actor_identity': runner.get('final_actor_identity'),
            'source_before': reader.read(root / 'source-before.json'), 'source_after': reader.read(root / 'source-after.json'),
            'source_comparison': reader.read(root / 'source-comparison.json'),
            'launch_record': launch_record,
            'launch_refs': {suffix: reader.ref(str(launch)+suffix) for suffix in ('.launch.json', '.resources.jsonl', '.log')} if launch else None,
            'windows': windows, 'task_fact_summaries': groups, 'progress': aggregate(slots), 'sampling': _sampling(slots),
            'observed_optimizer_step_increments': step_counts, 'unknown_step_windows': unknown_steps,
            'recorded_cumulative_final_steps': {k: runner.get(k+'_steps_total') for k in ('actor', 'critic')}, 'issues': issues}


def build_report(manifest, *, project_root, source_root):
    reader = Reader()
    manifest = Path(manifest).resolve()
    declared = reader.read(manifest, optional=False)
    jobs = declared['jobs']
    if len({j['name'] for j in jobs}) != len(jobs):
        raise ValueError('Job names must be unique')
    project, source = Path(project_root).resolve(), Path(source_root).resolve()
    if len({_path(project, j['run']).resolve() for j in jobs}) != len(jobs):
        raise ValueError('Each raw run must appear once; represent shared baselines by baseline_references')
    runs = [_run(reader, j, project, source) for j in jobs]
    slots = [s for r in runs for w in r['windows'] for s in w['slots']]
    screen = []
    for run in runs:
        selected = [s for w in run['windows'] if w.get('stage') == 'screen' for s in w['slots'] if s['task'] in {'implement', 'review'}]
        screen.append({'name': run['name'], 'candidate_id': run['candidate_id'], 'condition': run['condition'],
                       'selection_metric': 'Original full responsibility completed on implement+review; partial R is not completion.',
                       **aggregate(selected), 'by_task': {task: aggregate([s for s in selected if s['task'] == task]) for task in ('implement', 'review')}})
    result = {'version': VERSION, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Read-only actual source records; no regrading, model execution, tensor loading, world action or probability recomputation.',
              'manifest_ref': reader.ref(manifest), 'project_root': str(project), 'source_root': str(source),
              'runs': runs, 'progress': aggregate(slots), 'sampling': _sampling(slots),
              'screening_primary': screen,
              'observed_optimizer_step_increments': {k: sum(r['observed_optimizer_step_increments'][k] for r in runs) for k in ('actor', 'critic')},
              'unknown_step_runs': [r['name'] for r in runs if r['unknown_step_windows']],
              'declared_baseline_references': copy.deepcopy(declared.get('baseline_references', [])),
              'baseline_scope': 'References only, not extra measurements; reuse validity is not inferred here.',
              'sources': list(reader.refs.values())}
    return result


def write_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    lines = ['# v0.15 saved-measurement report', '', 'Read-only snapshot; missing outcomes remain unknown.', '',
             '| Job | Candidate | Condition | Planned | Closed | Unknown | Not started | Completed | Actor steps |',
             '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for run in report['runs']:
        p, c = run['progress'], run['progress']['counts']
        lines.append(f"| {run['name']} | {run['candidate_id']} | {run['condition']} | {c['planned']} | {c['closed']} | {c['closed_unknown']} | {c['not_started']} | {p['completed_work_count']} | {run['observed_optimizer_step_increments']['actor']} |")
    lines.extend(['', 'Completed counts use original full-responsibility flags. They do not replace the task/fact/repeat records, missing denominators, evaluation guards or per-window support blocks in report.json.', ''])
    (output / 'report.md').write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.manifest, project_root=args.project, source_root=args.source)
    write_report(report, args.output)
    print(json.dumps({'version': VERSION, 'jobs': len(report['runs']), 'counts': report['progress']['counts'], 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
