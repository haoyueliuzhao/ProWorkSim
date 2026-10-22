"""Finalize seven saved hourly observations only after the six-hour deadline.

No live queue, SQLite ledger, process, GPU, payload, or service is opened. The
only writes are new immutable summary files. This is monitoring completion,
not an assertion that every experiment or technical exception is finished.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'runs/software-benchmark-v055/six-hour-monitor-r1'
ARTIFACT = ROOT / 'artifacts/software-benchmark-v055/six-hour-monitor-r1/final-summary.json'
VERSION = 'v055-six-hour-monitor-final-summary-r1'
FAMILIES = {'qwen': 1500, 'deepseek': 3000}
GROUPS = {'qwen': ('REF', 'MATCH', 'PROJECT'), 'deepseek': tuple(
    arm + '-' + mode for arm in ('REF', 'MATCH', 'PROJECT') for mode in ('nonthinking', 'thinking'))}
GEN_TERMINAL = {'closed', 'technical_unknown'}
SCORE_TERMINAL_OR_ABSENT = {'official_report', 'technical_unknown', 'not_created', 'not_applicable'}
CST = ZoneInfo('Asia/Shanghai')


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Observation timestamps require explicit timezone offsets')
    return result.astimezone(timezone.utc)


def reference_bytes(path, raw):
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def read_saved(name):
    """Names are chosen by this program, never read from a live-state reference."""
    path = RUN / name
    raw = path.read_bytes()
    return json.loads(raw), reference_bytes(path, raw)


def counts(value, *, label):
    if not isinstance(value, dict) or any(type(number) is not int or number < 0 for number in value.values()):
        raise ValueError('Invalid saved nonnegative counts: ' + label)
    return dict(value)


def generation(value):
    return {'normal_closed': value.get('closed', 0), 'technical_unknown': value.get('technical_unknown', 0),
        'running': value.get('running', 0), 'pending': value.get('pending', 0), 'intent': value.get('intent', 0),
        'other_nonterminal': {key: number for key, number in value.items()
                              if key not in GEN_TERMINAL | {'running', 'pending', 'intent'} and number},
        'nonterminal_count': sum(number for key, number in value.items() if key not in GEN_TERMINAL),
        'raw_status_counts': dict(value)}


def deltas(current, previous):
    return {key: current.get(key, 0) - previous.get(key, 0) for key in sorted(set(current) | set(previous))}


def decimal_delta(current, previous):
    if current is None or previous is None:
        return None
    return float(Decimal(str(current)) - Decimal(str(previous)))


def validate_inputs(schedule, schedule_ref, summaries, manager_plan, manager_plan_ref, managers, now):
    """One linear validation pass over saved denominators and observation points."""
    start, end = timestamp(schedule['started_utc']), timestamp(schedule['ends_utc'])
    if (schedule.get('version') != 'six-hour-monitor-r1' or schedule.get('sample_count') != 7
            or schedule.get('interval_seconds') != 3600 or (end - start).total_seconds() != 21600
            or schedule.get('formal_plan_denominators') != FAMILIES or schedule.get('timezone') != 'Asia/Shanghai'
            or [item['index'] for item in schedule['scheduled_samples']] != list(range(7))):
        raise ValueError('The frozen six-hour, seven-point, nine-group schedule differs')
    if now < end:
        raise ValueError('The six-hour monitoring deadline has not been reached')
    if (manager_plan.get('indices') != [3, 4, 5, 6]
            or manager_plan.get('original_schedule_sha256') != schedule_ref['sha256']
            or manager_plan.get('manager_unit') != 'proworksim-v054-formal-queue-supervision-r7.service'):
        raise ValueError('The independent r7 supplement plan does not match this schedule')
    expected_manager_dates = {row['index']: timestamp(row['due_utc']) for row in manager_plan['scheduled_samples']}
    previous_observed = None
    issues = []
    for index, sample in enumerate(summaries):
        due = timestamp(schedule['scheduled_samples'][index]['due_utc'])
        observed, finished = timestamp(sample['observed_utc']), timestamp(sample['collection_finished_utc'])
        if (sample.get('version') != 'nine-conditions-hourly-observation-v055-r1'
                or sample.get('index') != index or sample.get('schedule_sha256') != schedule_ref['sha256']
                or (due - start).total_seconds() != index * 3600
                or observed < due or observed > finished or finished > now
                or (previous_observed is not None and observed <= previous_observed)):
            raise ValueError('A saved hourly point has invalid identity, provenance or timing: ' + str(index))
        previous_observed = observed
        if not isinstance(sample.get('errors'), list):
            raise ValueError('Each observation must retain its explicit errors array')
        if sample['errors']:
            issues.append({'source': f'summary-{index:02d}.json', 'index': index, 'errors': sample['errors']})
        if set(sample['queues']) != set(FAMILIES):
            raise ValueError('Both original experiment families must be observed at every point')
        for family, denominator in FAMILIES.items():
            queue = sample['queues'][family]
            if set(queue['groups']) != set(GROUPS[family]):
                raise ValueError('A planned group is missing or substituted: ' + family)
            combined = Counter()
            for name in GROUPS[family]:
                group = queue['groups'][name]
                gen = counts(group['generation'], label=family + '/' + name + '/generation')
                if group.get('planned') != 500 or sum(gen.values()) != 500:
                    raise ValueError('The fixed per-group denominator of 500 was not preserved')
                combined.update(gen)
                for endpoint in ('code_score', 'delivery_score', 'delivery_lifecycle'):
                    score = counts(group[endpoint], label=family + '/' + name + '/' + endpoint)
                    if sum(score.values()) != 500:
                        raise ValueError('A saved scoring/lifecycle status table lost its 500-task denominator')
            total = counts(queue['generation_total'], label=family + '/generation_total')
            if sum(total.values()) != denominator or Counter(total) != combined:
                raise ValueError('Family denominator or aggregate disagrees with its groups: ' + family)
        if index >= 3:
            observed_manager = managers[index]
            supplement_time = timestamp(observed_manager['observed_utc'])
            supplement_finish = timestamp(observed_manager['collection_finished_utc'])
            original = observed_manager['original_snapshot']
            if (observed_manager.get('version') != manager_plan['version']
                    or observed_manager.get('index') != index
                    or observed_manager.get('plan_sha256') != manager_plan_ref['sha256']
                    or observed_manager.get('manager_unit') != manager_plan['manager_unit']
                    or original.get('index') != index or timestamp(original['observed_utc']) != observed
                    or supplement_time < expected_manager_dates[index]
                    or supplement_time > supplement_finish or supplement_finish > now):
                raise ValueError('A required r7 hourly supplement is missing its correct bound observation')
            if not isinstance(observed_manager.get('errors'), list):
                raise ValueError('r7 supplement must preserve its errors array')
            if observed_manager['errors']:
                issues.append({'source': f'manager-r7-{index:02d}.json', 'index': index,
                    'errors': observed_manager['errors']})
            queue_observed = observed_manager.get('queue', {})
            if queue_observed.get('expected_revision_binding_matches') is not True:
                issues.append({'source': f'manager-r7-{index:02d}.json', 'index': index,
                    'errors': [{'kind': 'r7_revision_binding_not_verified', 'observation': queue_observed}]})
    if timestamp(summaries[6]['observed_utc']) < end or timestamp(managers[6]['observed_utc']) < end:
        raise ValueError('The actual final observations have not reached the monitoring deadline')
    return issues


def main_summary(schedule, schedule_ref, summaries, summary_refs, manager_plan, manager_plan_ref, managers, manager_refs, now):
    issues = validate_inputs(schedule, schedule_ref, summaries, manager_plan, manager_plan_ref, managers, now)
    first, last = summaries[0], summaries[6]
    timeline = []
    for index, sample in enumerate(summaries):
        point = {'index': index, 'due_utc': schedule['scheduled_samples'][index]['due_utc'],
            'observed_utc': sample['observed_utc'], 'observed_cst': timestamp(sample['observed_utc']).astimezone(CST).isoformat(),
            'lateness_seconds': (timestamp(sample['observed_utc']) - timestamp(schedule['scheduled_samples'][index]['due_utc'])).total_seconds(),
            'families': {}, 'source_errors': sample['errors']}
        elapsed = None if index == 0 else (timestamp(sample['observed_utc']) - timestamp(summaries[index - 1]['observed_utc'])).total_seconds()
        point['elapsed_since_previous_seconds'] = elapsed
        for family in FAMILIES:
            queue = sample['queues'][family]
            current = queue['generation_total']
            row = {'planned': FAMILIES[family], 'generation': generation(current), 'groups': {}, 'queue_status': queue.get('status')}
            if index:
                previous = summaries[index - 1]['queues'][family]['generation_total']
                row['change_since_previous'] = deltas(current, previous)
                row['normal_closed_per_actual_hour'] = (current.get('closed', 0) - previous.get('closed', 0)) * 3600 / elapsed
            for group_name in GROUPS[family]:
                group = queue['groups'][group_name]
                point_group = {'planned': 500, 'generation': generation(group['generation'])}
                if index:
                    previous_group = summaries[index - 1]['queues'][family]['groups'][group_name]['generation']
                    point_group['change_since_previous'] = deltas(group['generation'], previous_group)
                row['groups'][group_name] = point_group
            point['families'][family] = row
        point['deepseek_cost_observation'] = sample.get('ledger')
        point['effective_qwen_manager'] = managers[index].get('manager') if index >= 3 else sample.get('manager_units', {}).get('qwen')
        point['effective_qwen_manager_source'] = f'manager-r7-{index:02d}.json' if index >= 3 else f'summary-{index:02d}.json'
        timeline.append(point)
    net, final_groups, nonterminal = {}, {}, {}
    for family in FAMILIES:
        initial, final = first['queues'][family]['generation_total'], last['queues'][family]['generation_total']
        net[family] = {'new_normal_closed': final.get('closed', 0) - initial.get('closed', 0),
            'new_generation_technical_unknown': final.get('technical_unknown', 0) - initial.get('technical_unknown', 0),
            'all_status_deltas': deltas(final, initial)}
        group_values = {}
        gen_nonterminal = generation(final)['nonterminal_count']
        score_nonterminal = 0
        for group_name in GROUPS[family]:
            value = last['queues'][family]['groups'][group_name]
            # Raw code/delivery/lifecycle tables retain technical_unknown,
            # not_created and not_applicable; none is turned into a model loss.
            result = {'planned': 500, 'generation': generation(value['generation']),
                'code_score_status_counts': value['code_score'], 'delivery_score_status_counts': value['delivery_score'],
                'delivery_lifecycle_status_counts': value['delivery_lifecycle'],
                'observed_resolved_code': value['observed_resolved_code'],
                'delivery_applicable': group_name.startswith('PROJECT'),
                'observed_resolved_delivery': value['observed_resolved_delivery'] if group_name.startswith('PROJECT') else None,
                'raw_observed_resolved_delivery_in_saved_summary': value['observed_resolved_delivery'],
                'pending_classification': value.get('pending_classification', {}),
                'full_panel_success_rate_reported': False}
            for endpoint in ('code_score', 'delivery_score'):
                result[endpoint + '_nonterminal_count'] = sum(number for key, number in value[endpoint].items()
                    if key not in SCORE_TERMINAL_OR_ABSENT)
                score_nonterminal += result[endpoint + '_nonterminal_count']
            group_values[group_name] = result
        final_groups[family] = group_values
        preparation = last['queues'][family].get('preparation_workers_running', 0)
        if type(preparation) is not int or preparation < 0:
            raise ValueError('Final preparation worker count is not a valid observation')
        nonterminal[family] = {'generation': gen_nonterminal, 'created_score_jobs': score_nonterminal,
            'preparation_workers': preparation, 'total_work_items': gen_nonterminal + score_nonterminal + preparation,
            'not_created_scores_are_not_automatically_counted_as_queued_jobs': True}
    net['all_nine_groups'] = {'new_normal_closed': sum(value['new_normal_closed'] for value in net.values()),
        'new_generation_technical_unknown': sum(value['new_generation_technical_unknown'] for value in net.values())}
    rates = {}
    for length in (1, 2, 3):
        earlier = summaries[6 - length]
        seconds = (timestamp(last['observed_utc']) - timestamp(earlier['observed_utc'])).total_seconds()
        before, after = earlier['queues']['qwen']['generation_total'], last['queues']['qwen']['generation_total']
        new_closed = after.get('closed', 0) - before.get('closed', 0)
        rates[f'last_{length}_scheduled_intervals'] = {'start_index': 6 - length, 'end_index': 6,
            'actual_elapsed_seconds': seconds, 'nominal_hours': length, 'new_normal_closed': new_closed,
            'new_generation_technical_unknown': after.get('technical_unknown', 0) - before.get('technical_unknown', 0),
            'normal_closed_per_actual_hour': new_closed * 3600 / seconds,
            'technical_unknown_is_not_counted_as_normal_completion': True}
    ledger_first, ledger_last = first.get('ledger'), last.get('ledger')
    cost = {'scope': 'Only saved DeepSeek ledger observations; Qwen GPU residence and qualification costs are not quantified here',
        'first': ledger_first, 'last': ledger_last, 'new_API_calls_by_summarizer': 0}
    if isinstance(ledger_first, dict) and isinstance(ledger_last, dict):
        cost['observed_change'] = {key: decimal_delta(ledger_last.get(key), ledger_first.get(key))
            for key in ('settled_cny', 'committed_cny', 'uncertain_and_adjustment_hold_cny', 'inflight_hold_cny', 'http_429_count')}
    start, end = timestamp(schedule['started_utc']), timestamp(schedule['ends_utc'])
    actual_first, actual_last = timestamp(first['observed_utc']), timestamp(last['observed_utc'])
    total_nonterminal = sum(item['total_work_items'] for item in nonterminal.values())
    generation_nonterminal = sum(item['generation'] for item in nonterminal.values())
    generation_unknown = sum(last['queues'][family]['generation_total'].get('technical_unknown', 0) for family in FAMILIES)
    score_unknown = {endpoint: sum(group[endpoint].get('technical_unknown', 0)
        for family in FAMILIES for group in last['queues'][family]['groups'].values())
        for endpoint in ('code_score', 'delivery_score')}
    code_reports_not_created = sum(group['code_score'].get('not_created', 0)
        for family in FAMILIES for group in last['queues'][family]['groups'].values())
    known_unfinished = (total_nonterminal > 0 or generation_unknown > 0 or any(score_unknown.values())
        or code_reports_not_created > 0 or bool(issues))
    # Even a fully drained, determinate queue cannot prove that the separate
    # exception review and formal scientific analysis were actually completed.
    all_finished = False if known_unfinished else None
    return {'version': VERSION, 'created_utc': now.isoformat(), 'created_cst': now.astimezone(CST).isoformat(),
        'six_hour_monitor_completed': True, 'all_required_hourly_observations_present': True,
        'all_primary_generation_inventories_terminal': generation_nonterminal == 0,
        'all_generation_results_determinate': generation_nonterminal == 0 and generation_unknown == 0,
        'all_primary_execution_work_terminal': total_nonterminal == 0,
        'generation_normal_closed_is_not_official_resolved': True,
        'all_experiments_finished': all_finished, 'all_experiments_finished_basis':
            'False when saved nonterminal work, generation/scoring technical unknowns, absent code reports or observation errors remain. '
            'Otherwise null: exception review and formal analysis completion are outside these hourly observations, so success is not asserted.',
        'scientific_followup_observations': {'generation_technical_unknown': generation_unknown,
            'score_technical_unknown_counts': score_unknown, 'code_reports_not_created': code_reports_not_created,
            'generation_and_score_unknown_counts_may_overlap_and_are_not_unique_task_counts': True,
            'exception_set_processing_completion_verified': False, 'formal_analysis_completion_verified': False},
        'all_observations_error_free': not issues, 'observation_errors': issues,
        'all_experiments_successful_claimed': False, 'technical_unknown_resolution_claimed': False,
        'window': {'timezone': 'Asia/Shanghai', 'planned_start_utc': start.isoformat(), 'planned_end_utc': end.isoformat(),
            'planned_start_cst': start.astimezone(CST).isoformat(), 'planned_end_cst': end.astimezone(CST).isoformat(),
            'planned_duration_seconds': (end - start).total_seconds(),
            'actual_first_sample_utc': actual_first.isoformat(), 'actual_last_sample_utc': actual_last.isoformat(),
            'actual_first_sample_cst': actual_first.astimezone(CST).isoformat(), 'actual_last_sample_cst': actual_last.astimezone(CST).isoformat(),
            'actual_sample_span_seconds': (actual_last - actual_first).total_seconds(),
            'baseline_lateness_seconds': (actual_first - start).total_seconds(),
            'baseline_note': 'The first actual sample was delayed; changes and rates use actual observations, not a fabricated on-time baseline.',
            'last_primary_collection_finished_utc': last['collection_finished_utc'],
            'last_r7_supplement_observed_utc': managers[6]['observed_utc'],
            'last_r7_supplement_collection_finished_utc': managers[6]['collection_finished_utc']},
        'planned_denominators': {'families': FAMILIES, 'per_group': 500, 'nine_group_total': 4500},
        'hourly_progress': timeline, 'net_generation_change_from_actual_baseline': net,
        'latest_qwen_completion_rates': rates, 'last_nine_groups': final_groups,
        'last_nonterminal_work': {**nonterminal, 'total_work_items': total_nonterminal},
        'last_family_state': {family: {key: last['queues'][family].get(key) for key in (
            'state', 'status', 'dispatch_stopped', 'stop_reason', 'waiting', 'host_revision', 'exception_reason_counts',
            'environment_coverage', 'last_disk_dispatch_admission', 'disk_reservations')} for family in FAMILIES},
        'cost': cost, 'last_resources': {key: last.get(key) for key in ('capacity', 'volumes', 'gpu_usage')},
        'last_manager_observations': {'original_schedule_units': last.get('manager_units'),
            'effective_qwen_r7': managers[6],
            'r6_inactive_is_not_used_as_evidence_of_a_qwen_r7_outage': True,
            'pool': last.get('manager_units', {}).get('pool'), 'cache': last.get('manager_units', {}).get('cache'),
            'r7_count_observation_is_later_and_kept_separate_from_per_group_summary06': True},
        'last_resident_pool': last.get('resident_pool'),
        'r7_manager_supplements': [managers[index] for index in (3, 4, 5, 6)],
        'sources': {'summarizer': reference_bytes(Path(__file__).resolve(), Path(__file__).read_bytes()),
            'schedule': schedule_ref, 'hourly_summaries': summary_refs,
            'r7_supplement_plan': manager_plan_ref, 'r7_supplements': [manager_refs[index] for index in (3, 4, 5, 6)]},
        'summarizer_scope': {'live_queue_reads': 0, 'live_ledger_reads': 0, 'GPU_queries': 0, 'model_calls': 0,
            'service_mutations': 0, 'queue_writes': 0, 'payload_scans': 0, 'tests_run': 0,
            'saved_live_state_references_followed': False, 'only_new_summary_files_written': True,
            'monitoring_period_repairs_and_model_preparation_are_not_claimed_to_have_zero_cost': True}}


def write_once(path, raw):
    """Create one immutable file; never overwrite an earlier final result."""
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return reference_bytes(path, raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish-copy', action='store_true', help='Also create the same immutable artifact copy')
    args = parser.parse_args()
    output = RUN / 'final-summary.json'
    if output.exists() or (args.publish_copy and ARTIFACT.exists()):
        raise FileExistsError('A final summary already exists; no recomputation or overwrite')
    schedule, schedule_ref = read_saved('schedule.json')
    # Early deadline gate avoids opening partial observations before the end.
    now = datetime.now(timezone.utc)
    if now < timestamp(schedule['ends_utc']):
        raise ValueError('Monitoring has not reached its planned end; finalization is refused')
    summaries, summary_refs = [], []
    for index in range(7):
        value, ref = read_saved(f'summary-{index:02d}.json')
        summaries.append(value)
        summary_refs.append(ref)
    manager_plan, manager_plan_ref = read_saved('manager-r7-plan.json')
    managers, manager_refs = {}, {}
    for index in (3, 4, 5, 6):
        managers[index], manager_refs[index] = read_saved(f'manager-r7-{index:02d}.json')
    value = main_summary(schedule, schedule_ref, summaries, summary_refs, manager_plan, manager_plan_ref,
        managers, manager_refs, datetime.now(timezone.utc))
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    result = {'run_summary': write_once(output, raw)}
    if args.publish_copy:
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        result['artifact_summary'] = write_once(ARTIFACT, raw)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
