"""Read-only, frozen-snapshot token comparison of five teams and selected S1.

No model, scorer, Docker, service or experiment configuration is modified.
An incomplete panel never acquires a fabricated full-panel success rate.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import gzip
import json
from pathlib import Path
import statistics

from proworksim.software_benchmark_host_api_v132 import ledger_read
from proworksim.software_benchmark_scope_v132 import BATCH_ROOT, PLAN_FILE, GROUP_IDS

ROOT = BATCH_ROOT.parents[2]
DEFAULT = ROOT/'artifacts/software-benchmark-v133/token-comparison-r1'
S1 = ROOT/'artifacts/software-benchmark-v128/independent-count-audit-r1/selected-per-task.json'
S1_SUMMARY = S1.with_name('summary.json')
COVERAGE = ROOT/'artifacts/software-benchmark-v133/score-coverage-audit-r1/per-task.json'
SCORE_SUMMARY = COVERAGE.with_name('summary.json')
CLOSED = {'closed_candidate', 'closed_candidate_measurement_repaired', 'closed_export_repair_pending'}
FIELDS = ('input_tokens', 'output_tokens', 'total_tokens', 'cache_hit_tokens', 'cache_miss_tokens')


def load(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def reference(path):
    raw = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.gz':
        raw = (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()
        with path.open('xb') as stream:
            stream.write(gzip.compress(raw, mtime=0))
        return
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def capture(output):
    started = datetime.now(timezone.utc).isoformat()
    by_group = {}
    for group in GROUP_IDS:
        with ledger_read(group) as db:
            records = [dict(row) for row in db.execute(
                'SELECT r.request_id,r.slot_id,r.condition,r.usage_id,r.status,r.usage_json,'
                'r.reserved_nanoyuan,r.settled_nanoyuan,m.group_id,m.member_id '
                'FROM requests r LEFT JOIN member_requests m USING(request_id) ORDER BY r.request_id')]
        for row in records:
            row['usage'] = json.loads(row.pop('usage_json')) if row['usage_json'] else None
            if row['group_id'] != group or row['member_id'] is None:
                raise ValueError('A provider record lost its team/member accounting identity')
        by_group[group] = records
    value = {'version': 'v133-frozen-provider-usage-snapshot-r1',
        'read_started_utc': started, 'read_finished_utc': datetime.now(timezone.utc).isoformat(),
        'atomic_within_each_group': True, 'atomic_across_groups_or_score_snapshot': False,
        'plan': reference(PLAN_FILE), 'S1_selection': reference(S1),
        'S1_summary': reference(S1_SUMMARY), 'score_coverage': reference(COVERAGE),
        'score_summary': reference(SCORE_SUMMARY), 'groups': by_group,
        'new_API_calls': 0, 'Docker_operations': 0, 'experiment_mutations': 0}
    save(output/'usage-snapshot.json.gz', value)
    return value


def usage(records):
    known = [row for row in records if row['status'] == 'settled' and row['usage'] is not None]
    totals = dict.fromkeys(FIELDS, 0)
    purposes = defaultdict(lambda: dict.fromkeys(('requests', *FIELDS), 0))
    members = defaultdict(lambda: dict.fromkeys(('requests', *FIELDS), 0))
    for row in known:
        u = row['usage']
        inputs, outputs = int(u['prompt_tokens']), int(u['completion_tokens'])
        if inputs + outputs != int(u['total_tokens']):
            raise ValueError('Provider token arithmetic is inconsistent')
        hit = int(u.get('prompt_cache_hit_tokens', u.get('prompt_tokens_details', {}).get('cached_tokens', 0)))
        miss = int(u.get('prompt_cache_miss_tokens', inputs-hit))
        if hit + miss != inputs:
            raise ValueError('Cache decomposition differs from measured input usage')
        values = dict(zip(FIELDS, (inputs, outputs, inputs+outputs, hit, miss)))
        for key, value in values.items():
            totals[key] += value
            purposes[row['usage_id']][key] += value
            members[row['member_id']][key] += value
        purposes[row['usage_id']]['requests'] += 1
        members[row['member_id']]['requests'] += 1
    return {'requests': len(records), 'settled_requests': len(known),
        'statuses': dict(Counter(row['status'] for row in records)), 'known_tokens': totals,
        'all_request_usage_known': len(known) == len(records),
        'settled_CNY': str(Decimal(sum(row['settled_nanoyuan'] for row in known))/Decimal(10**9)),
        'uncertain_reserved_CNY': str(Decimal(sum(row['reserved_nanoyuan'] for row in records
                                                if row['status'] == 'uncertain'))/Decimal(10**9)),
        'inflight_reserved_CNY': str(Decimal(sum(row['reserved_nanoyuan'] for row in records
                                               if row['status'] == 'reserved'))/Decimal(10**9)),
        'by_purpose': dict(purposes), 'by_member': dict(members)}


def aggregate_s1(rows):
    totals = {key: sum(row['usage']['known_token_totals'][key] for row in rows) for key in FIELDS}
    return {'n': len(rows), 'known_tokens': totals,
        'requests': sum(row['usage']['requests'] for row in rows),
        'code_passed': sum(row['resolved'] is True for row in rows),
        'mean_total_tokens': totals['total_tokens']/len(rows) if rows else None,
        'mean_input_tokens': totals['input_tokens']/len(rows) if rows else None,
        'mean_output_tokens': totals['output_tokens']/len(rows) if rows else None}


def compare(output):
    existing = next((path for path in (output/'usage-snapshot.json.gz', output/'usage-snapshot.json')
                     if path.exists()), None)
    snapshot = load(existing) if existing is not None else capture(output)
    snapshot_file = existing or output/'usage-snapshot.json.gz'
    for field, path in [('plan', PLAN_FILE), ('S1_selection', S1), ('S1_summary', S1_SUMMARY),
                        ('score_coverage', COVERAGE), ('score_summary', SCORE_SUMMARY)]:
        if snapshot[field] != reference(path):
            raise ValueError('A bound analysis input changed; use a new dated report directory')
    plan, coverage = load(PLAN_FILE), load(COVERAGE)
    status = {row['slot_id']: row for row in coverage}
    s1_all = load(S1)
    baseline = {row['instance_id']: row for row in s1_all if row['arm'] == 'PROJECT'}
    if len(baseline) != 50 or len(status) != 250:
        raise ValueError('Keep exactly one prespecified selected attempt per original task and group')
    groups, tasks = {}, []
    for group in GROUP_IDS:
        rows = [row for row in plan['rows'] if row['organization_id'] == group]
        if {row['instance_id'] for row in rows} != set(baseline):
            raise ValueError('The comparison panels do not contain the same tasks')
        records = snapshot['groups'][group]
        by_slot = defaultdict(list)
        for record in records:
            by_slot[record['slot_id']].append(record)
        if set(by_slot)-{row['slot_id'] for row in rows}:
            raise ValueError('Unplanned or preparation usage entered the organization ledger')
        per_task = []
        for row in rows:
            item = usage(by_slot[row['slot_id']])
            observed = status[row['slot_id']]
            item.update({key: row[key] for key in ('slot_id', 'slot_index', 'instance_id', 'organization_id')})
            item['called'] = bool(item['requests'])
            item['generation_category_at_score_audit'] = observed['generation_category']
            item['trusted_closed_usage'] = (item['called'] and item['all_request_usage_known']
                                            and observed['generation_category'] in CLOSED)
            item['S1_selected'] = baseline[row['instance_id']]
            item['code'] = observed['code']
            item['delivery'] = observed['delivery']
            item['token_ratio_to_same_task_S1'] = (
                item['known_tokens']['total_tokens']/baseline[row['instance_id']]['usage']['known_token_totals']['total_tokens']
                if item['trusted_closed_usage'] else None)
            per_task.append(item)
        called = [row for row in per_task if row['called']]
        closed = [row for row in per_task if row['trusted_closed_usage']]
        settled = usage(records)
        same_baseline = aggregate_s1([baseline[row['instance_id']] for row in closed])
        closed_totals = {key: sum(row['known_tokens'][key] for row in closed) for key in FIELDS}
        closed_requests = sum(row['settled_requests'] for row in closed)
        closed_same_s1_tokens = same_baseline['known_tokens']['total_tokens']
        ratios = [row['token_ratio_to_same_task_S1'] for row in closed]
        whole = aggregate_s1(list(baseline.values()))
        comparison = {'n': len(closed), 'team_known_tokens': closed_totals,
            'team_mean_tokens': {key: value/len(closed) if closed else None for key, value in closed_totals.items()},
            'same_tasks_S1': same_baseline,
            'token_ratio_of_same_task_totals': closed_totals['total_tokens']/closed_same_s1_tokens if closed_same_s1_tokens else None,
            'mean_paired_token_difference': (closed_totals['total_tokens']-closed_same_s1_tokens)/len(closed) if closed else None,
            'median_task_token_ratio': statistics.median(ratios) if ratios else None,
            'tasks_using_more_tokens_than_S1': sum(value > 1 for value in ratios),
            'team_mean_API_requests': closed_requests/len(closed) if closed else None,
            'S1_same_tasks_mean_API_requests': same_baseline['requests']/len(closed) if closed else None,
            'team_mean_input_per_settled_API_request': closed_totals['input_tokens']/closed_requests if closed_requests else None,
            'S1_same_tasks_mean_input_per_API_request': same_baseline['known_tokens']['input_tokens']/same_baseline['requests'] if same_baseline['requests'] else None,
            'team_tasks_at_least_95pct_of_5M': sum(row['known_tokens']['total_tokens'] >= 4_750_000 for row in closed),
            'S1_same_tasks_at_least_95pct_of_5M': sum(baseline[row['instance_id']]['usage']['known_token_totals']['total_tokens'] >= 4_750_000 for row in closed),
            'ratio_to_full50_S1_mean_different_task_composition': (closed_totals['total_tokens']/len(closed)/whole['mean_total_tokens']) if closed else None,
            'selection_caveat': 'Trusted-closure subset, including cash-censored normal closures; not a random full-panel sample or causal estimate'}
        input_total = settled['known_tokens']['input_tokens']
        groups[group] = {'members': len(rows[0]['fixed_members']), 'planned_tasks': 50,
            'called_tasks': len(called), 'no_API_tasks': 50-len(called), 'trusted_closed_usage_tasks': len(closed),
            'all_observed_usage': settled,
            'known_tokens_per_called_task': settled['known_tokens']['total_tokens']/len(called) if called else None,
            'known_tokens_per_planned_task_not_solver_efficiency': settled['known_tokens']['total_tokens']/50,
            'all_called_usage_is_final': len(called) == len(closed),
            'cache_hit_share_of_known_input': settled['known_tokens']['cache_hit_tokens']/input_total if input_total else None,
            'output_share_of_known_tokens': settled['known_tokens']['output_tokens']/settled['known_tokens']['total_tokens'] if settled['known_tokens']['total_tokens'] else None,
            'condenser_share_of_known_tokens': settled['by_purpose'].get('condenser', {}).get('total_tokens', 0)/settled['known_tokens']['total_tokens'] if settled['known_tokens']['total_tokens'] else None,
            'same_task_closed_comparison': comparison,
            'official_score_snapshot': load(SCORE_SUMMARY)['groups'][group]}
        tasks.extend(per_task)
    report = {'version': 'v133-team-versus-historical-S1-usage-comparison-r1',
        'usage_snapshot': reference(snapshot_file),
        'score_audit_interval_utc': [load(SCORE_SUMMARY)['read_started_utc'], load(SCORE_SUMMARY)['read_finished_utc']],
        'usage_audit_interval_utc': [snapshot['read_started_utc'], snapshot['read_finished_utc']],
        'primary_baseline': 'PROJECT S1 v128 prespecified recovered selection; 50 tasks',
        'secondary_baseline': 'REF S1 external native OpenHands reference',
        'S1_baselines': {arm: aggregate_s1([row for row in s1_all if row['arm'] == arm]) for arm in ('PROJECT', 'REF')},
        'groups': groups,
        'interpretation': ['Every team has one shared5M pool, not5M per member.',
            'Known usage excludes unmeasured reserved calls; it is a lower bound for incomplete attempts.',
            'No-API tasks are not averaged into the solver token comparison.',
            'Same-task closure comparisons reduce task-composition differences but remain selected incomplete subsets.',
            'Matched token limits do not match batch cash caps, interface revisions, seeds or recovery policies.',
            'API input tokens include repeated schemas, observations and private histories; tool frequency is not an exact token attribution.',
            'Full-panel completion rates remain null until all50 outcomes are known.'],
        'new_API_calls': 0, 'new_scoring_calls': 0, 'Docker_operations': 0, 'experiment_mutations': 0}
    save(output/'summary.json', report)
    save(output/'per-task.json', tasks)
    return report


def derive_common(output):
    """Derive identical-task subsets from the existing immutable snapshot only."""
    tasks = load(output/'per-task.json')
    behavior_path = ROOT/'artifacts/software-benchmark-v133/collaboration-cost-evidence-r1/per-task.json'
    behavior = {row['slot_id']: row for row in load(behavior_path)}
    sets = {group: {row['instance_id'] for row in tasks
                   if row['organization_id'] == group and row['trusted_closed_usage']} for group in GROUP_IDS}
    results = {}
    for name, groups in [('common_first_four', GROUP_IDS[:4]), ('common_all_five', GROUP_IDS)]:
        common = sorted(set.intersection(*(sets[group] for group in groups)))
        chosen = {group: [row for row in tasks if row['organization_id'] == group
                         and row['instance_id'] in common] for group in groups}
        base = aggregate_s1([row['S1_selected'] for row in chosen[groups[0]]])
        entries = {}
        for group, rows in chosen.items():
            tokens = sum(row['known_tokens']['total_tokens'] for row in rows)
            calls = sum(row['settled_requests'] for row in rows)
            actions = [behavior[row['slot_id']] for row in rows]
            entries[group] = {'n': len(rows), 'mean_team_tokens': tokens/len(rows),
                'ratio_to_identical_task_S1': tokens/base['known_tokens']['total_tokens'],
                'mean_API_calls': calls/len(rows),
                'mean_input_per_API_call': sum(row['known_tokens']['input_tokens'] for row in rows)/calls,
                'tasks_more_tokens_than_S1': sum(row['token_ratio_to_same_task_S1'] > 1 for row in rows),
                'end_classes': dict(Counter(row['exclusive_end_class'] for row in actions)),
                'mean_collaboration_actions': sum(row['collaboration_operations'] for row in actions)/len(rows),
                'legal_submission_evidence_tasks': sum(row['legal_delivery_evidence'] for row in actions)}
        results[name] = {'task_ids': common, 'n': len(common), 'S1_PROJECT': base, 'groups': entries,
            'not_selected_on_official_scores': True,
            'still_selected_on_trusted_closure_and_partly_cash_censored': True}
    scored = [row for row in tasks if row['organization_id'] == 'MATRIX'
              and type(row['code'].get('resolved')) is bool]
    base = aggregate_s1([row['S1_selected'] for row in scored])
    team_tokens = sum(row['known_tokens']['total_tokens'] for row in scored)
    passes = sum(row['code']['resolved'] for row in scored)
    results['MATRIX_common_officially_scored'] = {'n': len(scored),
        'team_passed': passes, 'S1_passed': base['code_passed'],
        'team_total_tokens': team_tokens, 'S1_total_tokens': base['known_tokens']['total_tokens'],
        'team_mean_tokens': team_tokens/len(scored), 'S1_mean_tokens': base['mean_total_tokens'],
        'tokens_per_confirmed_success_including_failed_tasks': team_tokens/passes if passes else None,
        'S1_tokens_per_success_same_tasks': base['known_tokens']['total_tokens']/base['code_passed'] if base['code_passed'] else None,
        'nonrepresentative_early_scoring_subset': True}
    value = {'version': 'v133-identical-task-cost-subsets-r1',
        'source': reference(output/'per-task.json'), 'behavior': reference(behavior_path),
        'subsets': results, 'new_database_queries': 0, 'new_API_calls': 0, 'Docker_operations': 0}
    save(output/'matched-subsets.json', value)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--derive-common', action='store_true')
    parser.add_argument('--coverage-dir', type=Path, default=COVERAGE.parent)
    args = parser.parse_args()
    COVERAGE = args.coverage_dir/'per-task.json'
    SCORE_SUMMARY = args.coverage_dir/'summary.json'
    if args.derive_common:
        value = derive_common(args.output)
        print(json.dumps(value['subsets'], ensure_ascii=False))
        raise SystemExit(0)
    result = compare(args.output)
    print(json.dumps({group: {'called': value['called_tasks'], 'closed': value['trusted_closed_usage_tasks'],
        'closed_mean_tokens': value['same_task_closed_comparison']['team_mean_tokens']['total_tokens'],
        'same_tasks_S1_mean': value['same_task_closed_comparison']['same_tasks_S1']['mean_total_tokens'],
        'same_task_token_ratio': value['same_task_closed_comparison']['token_ratio_of_same_task_totals'],
        'mean_calls': value['same_task_closed_comparison']['team_mean_API_requests'],
        'same_tasks_S1_mean_calls': value['same_task_closed_comparison']['S1_same_tasks_mean_API_requests'],
        'cache_hit_share': value['cache_hit_share_of_known_input']} for group, value in result['groups'].items()}, ensure_ascii=False))
