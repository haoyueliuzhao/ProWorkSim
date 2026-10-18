"""Merge the immutable first nine and only the three original unstarted slots.

Read-only reporting: no scoring, model replay, native-call traversal, or updates
to the misleadingly named original first-stage final.json.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import software_bridge_v052_report as original
from scripts.software_holdout_v051_report import bounded

VERSION = 'software-bridge-v052-completion-report-v1'
RESUME_VERSION = 'software-openhands-bridge-resume-r1-v0.52'
FIRST_STAGE_SHA256 = '5a5f6efb564de1615819fe002d61715a1e235265781a55d0bffc1e21cfb38335'
REMAINING = ('v052-cal2-xmltodict-1-PS1', 'v052-cal2-xmltodict-2-PS1',
             'v052-cal2-xmltodict-2-OH_ref')
INTERRUPTED = ('v052-cal2-boltons-2-PS1', 'v052-cal2-parse-1-PS1',
               'v052-cal2-parse-2-PS1', 'v052-cal2-xmltodict-1-OH_ref')
IDENTITY = ('slot_id', 'task_id', 'condition', 'seed', 'first_member')
METRICS = (*original.PRIMARY, *original.JOINT)
COST_FIELDS = ('known_actual_tokens', 'uncertain_reservation_tokens', 'started_generations',
               'complete_generations', 'ledger_tokens', 'new_actor_steps', 'new_critic_steps', 'new_backward_calls')


def checked(reference):
    data, actual = original.load(reference['path'])
    if not original.points_to(reference, actual):
        raise ValueError('Bound report/plan source bytes changed')
    return data


def validate_first_stage(first):
    original.validate_panel(first['rows'])
    if (first.get('version') != original.VERSION or first.get('host_status') != 'paused'
            or Counter(row['status'] for row in first['rows']) != Counter(closed=5, technical_unknown=4, not_started=3)):
        raise ValueError('Keep the sealed first-stage five closed/four unknown/three not-started inventory')
    if tuple(row['slot_id'] for row in first['rows'] if row['status'] == 'not_started') != REMAINING:
        raise ValueError('Only the original three unstarted slots are eligible')
    unknown = [row for row in first['rows'] if row['status'] == 'technical_unknown']
    if ({row['slot_id'] for row in unknown} != set(INTERRUPTED)
            or any(row.get(metric) is not None for row in unknown for metric in METRICS)):
        raise ValueError('The four interrupted outcomes must remain unknown')


def read_three_rows(root, plan, plan_ref, supervisor):
    """Use the existing formal/compact row contracts without the old full12 gate."""
    rows, issues = [], []
    for source_row in plan['rows']:
        slot = source_row['slot_id']
        state = supervisor['states'][slot]
        folder = root / 'slots' / slot
        started_path, closed_path = folder / 'started.json', folder / 'closed.json'
        row = {key: source_row.get(key) for key in IDENTITY}
        row.update(host_state=state.get('status'), started=started_path.exists(), status='not_started',
                   joint_applicable=row['condition'] == 'PS1',
                   raw_outcomes=dict.fromkeys(METRICS), **dict.fromkeys(METRICS))
        if row['started']:
            started, started_ref = original.load(started_path)
            row.update(status='technical_unknown', started_record=started_ref)
            attempt = Path(started['attempt']).resolve()
            report_path = attempt / 'report.json'
            within = attempt.is_relative_to(root / 'workers' / slot)
            attempt_paths = {str(Path(item['output']).resolve()) for item in state.get('attempts', []) if item.get('output')}
            binding = (started.get('row') == source_row and original.points_to(started.get('source_plan'), plan_ref)
                       and str(attempt) in attempt_paths and within)
            if within and report_path.is_file():
                report, report_ref = original.load(report_path)
                row['worker_report'] = report_ref
                binding = (binding and report.get('row') == source_row
                           and original.points_to(report.get('source_plan'), plan_ref))
                if closed_path.is_file():
                    closed, closed_ref = original.load(closed_path)
                    row['closed_record'] = closed_ref
                    binding = (binding and original.points_to(closed.get('report'), report_ref)
                               and closed.get('decision') == 'continue')
                else:
                    binding = False
                raw, formal, reasons = original.formal_outcomes(source_row, state.get('status'), report,
                                                               source_bindings_closed=binding)
                row.update(raw_outcomes=raw, **formal, formal_binding_issues=reasons)
                row.update(original.compact_report(report, report_ref, row['condition']))
                if not reasons:
                    row['status'] = 'closed'
            else:
                row['formal_binding_issues'] = ['worker_report_missing_or_outside_root']
            interruption = attempt / 'interruption.json'
            if within and interruption.is_file():
                row['interruption'] = original.source(interruption)
        elif state.get('status') == 'complete' or closed_path.exists():
            row['formal_binding_issues'] = ['completion_without_original_started_record']
        if row.get('formal_binding_issues'):
            issues.append({'slot_id': slot, 'issues': row['formal_binding_issues']})
        rows.append(row)
    return rows, issues


def read_continuation(root, first, first_ref):
    root = Path(root).resolve()
    plan, plan_ref = original.load(root / 'plan.json')
    supervisor, supervisor_ref = original.load(root / 'supervisor.json')
    old_plan = checked(first['plan'])
    predecessors = plan.get('predecessor_references', {})
    expected_refs = {'predecessor_plan': first['plan'], 'predecessor_supervisor': first['supervisor'],
                     'predecessor_stage_report': first_ref}
    if (plan.get('version') != RESUME_VERSION or Path(plan['predecessor_root']).resolve() != Path(first['root']).resolve()
            or any(not original.points_to(predecessors.get(key), value) for key, value in expected_refs.items())
            or plan.get('original_rows') != old_plan['rows']):
        raise ValueError('Continuation must bind the sealed first stage and its exact original twelve rows')
    expected_rows = [row for row in old_plan['rows'] if row['slot_id'] in REMAINING]
    if tuple(row['slot_id'] for row in expected_rows) != REMAINING or plan['rows'] != expected_rows:
        raise ValueError('Continuation may contain only the original three unchanged rows, in order')
    if (root == Path(first['root']).resolve() or not original.points_to(supervisor.get('plan'), plan_ref)
            or supervisor.get('status') not in ('complete', 'paused')
            or not original.finite_number(supervisor.get('ended_at'))
            or set(supervisor['states']) != set(REMAINING)
            or any(state.get('status') not in ('complete', 'stopped', 'not_started')
                   or any(not original.finite_number(attempt.get('ended_at')) for attempt in state.get('attempts', []))
                   for state in supervisor['states'].values())):
        raise ValueError('Read only the distinct terminal continuation root with no active attempts')
    rows, issues = read_three_rows(root, plan, plan_ref, supervisor)
    ledger = supervisor['ledger']
    if ledger.get('logical_inventory') != 3:
        raise ValueError('Continuation ledger is for three new logical slots only')
    billing = {key: ledger.get(key) for key in (*COST_FIELDS, 'complete_actual_tokens', 'logical_inventory')}
    billing.update(source=original.pointer(supervisor_ref, '/ledger'),
                   integrity_errors_count=len(ledger['integrity_errors']) if isinstance(ledger.get('integrity_errors'), list) else None,
                   integrity_errors_source=original.pointer(supervisor_ref, '/ledger/integrity_errors'))
    return {'root': str(root), 'plan': plan_ref, 'supervisor': supervisor_ref,
            'host_status': supervisor['status'], 'host_started_at': supervisor.get('started_at'),
            'host_ended_at': supervisor['ended_at'], 'rows': rows, 'billing': billing,
            'worker_cost': original.worker_intervals(supervisor['states']), 'integrity_issues': issues,
            'resume_release': plan.get('resume_release'), 'resume_protocol': plan.get('resume_protocol'),
            'resume_controls': plan.get('resume_controls')}


def sum_known(left, right):
    return left + right if original.finite_number(left) and original.finite_number(right) else None


def merge_stages(first, continuation):
    """Pure merge. Preserve old nine rows verbatim and old uncertainty once."""
    validate_first_stage(first)
    new = continuation['rows']
    if tuple(row['slot_id'] for row in new) != REMAINING or len(new) != 3:
        raise ValueError('Replace exactly the original three; no extra or interrupted row')
    if (Path(first['root']).resolve() == Path(continuation['root']).resolve()
            or original.points_to(continuation['plan'], first['plan'])):
        raise ValueError('A stage cannot be added to itself')
    old_index = {row['slot_id']: row for row in first['rows']}
    for row in new:
        if any(row.get(key) != old_index[row['slot_id']].get(key) for key in IDENTITY):
            raise ValueError('A replacement changed the original row/seed/condition identity')
    replacement = {row['slot_id']: row for row in new}
    rows = [copy.deepcopy(replacement.get(row['slot_id'], row)) for row in first['rows']]
    original.validate_panel(rows)
    old_cost, new_cost = first['worker_cost'], continuation['worker_cost']
    intervals = copy.deepcopy(old_cost['intervals']) + copy.deepcopy(new_cost['intervals'])
    identities = [str(Path(row['output']).resolve()) for row in intervals if row.get('output')]
    if len(identities) != len(intervals) or len(set(identities)) != len(identities):
        raise ValueError('Unique worker intervals may be included only once across both stages')
    old_bill, new_bill = first['billing'], continuation['billing']
    billing = {key: sum_known(old_bill.get(key), new_bill.get(key)) for key in COST_FIELDS}
    full = sum_known(old_bill.get('complete_actual_tokens'), new_bill.get('complete_actual_tokens'))
    billing.update(complete_actual_tokens=full if billing['uncertain_reservation_tokens'] == 0 else None,
                   logical_inventory=12, stage_logical_inventories=[12, 3],
                   scope='First-stage sealed scalars once plus continuation-only ledger once; overlapping inventory is not15 slots.')
    seconds = sum_known(old_cost.get('gpu_worker_seconds'), new_cost.get('gpu_worker_seconds'))
    worker = {'unique_intervals': len(intervals), 'intervals': intervals,
              'known_interval_seconds': sum_known(old_cost.get('known_interval_seconds'), new_cost.get('known_interval_seconds')),
              'unknown_seconds_intervals': sum_known(old_cost.get('unknown_seconds_intervals'), new_cost.get('unknown_seconds_intervals')),
              'gpu_worker_seconds': seconds, 'gpu_worker_hours': seconds / 3600 if seconds is not None else None,
              'issues': copy.deepcopy(old_cost.get('issues', [])) + copy.deepcopy(new_cost.get('issues', [])),
              'scope': 'Unique full worker intervals; first-stage loader/retry costs retained, nested generation/test time not added.'}
    return {'rows': rows, 'status_counts': dict(Counter(row['status'] for row in rows)),
            'formal_metrics': original.metrics_for(rows), 'raw_metrics': original.metrics_for(rows, raw=True),
            'overall_primary_metrics': {metric: bounded([row[metric] for row in rows]) for metric in original.PRIMARY},
            'all12_formal_primary_endpoints_known': all(row[metric] is not None for row in rows for metric in original.PRIMARY),
            'billing': billing, 'worker_cost': worker, 'retained_original_rows': 9, 'replaced_original_not_started_rows': 3,
            'original_four_technical_unknown_preserved': True,
            'stages': [{'kind': 'original_first_stage', 'root': first['root'], 'plan': first['plan'],
                        'supervisor': first['supervisor'], 'host_status': first['host_status'],
                        'billing': copy.deepcopy(old_bill), 'worker_cost': copy.deepcopy(old_cost)},
                       {'kind': 'original_three_continuation', 'root': continuation['root'],
                        'plan': continuation['plan'], 'supervisor': continuation['supervisor'],
                        'host_status': continuation['host_status'], 'billing': copy.deepcopy(new_bill),
                        'worker_cost': copy.deepcopy(new_cost)}]}


def summarize(first_stage, root):
    first, first_ref = original.load(first_stage)
    if first_ref['sha256'] != FIRST_STAGE_SHA256:
        raise ValueError('Use the exact immutable first-stage report, despite its original final.json filename')
    validate_first_stage(first)
    continuation = read_continuation(root, first, first_ref)
    merged = merge_stages(first, continuation)
    return {'version': VERSION, 'created_at_beijing': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            'read_only': True, 'root': continuation['root'], 'first_stage_report': first_ref,
            'first_stage_report_original_name_preserved': True, 'plan': continuation['plan'],
            'supervisor': continuation['supervisor'], 'host_status': continuation['host_status'],
            'host_started_at': continuation['host_started_at'], 'host_ended_at': continuation['host_ended_at'],
            'logical_slots': 12, 'logical_tasks': 6, 'conditions': list(original.CONDITIONS), **merged,
            'row_stage_sources': {row['slot_id']: original.pointer(continuation['plan'], '/rows')
                                 if row['slot_id'] in REMAINING else original.pointer(first_ref, '/rows')
                                 for row in merged['rows']},
            'integrity_issues': copy.deepcopy(first['integrity_issues']) + continuation['integrity_issues']
                                + continuation['worker_cost']['issues'],
            'resume_release': continuation['resume_release'], 'resume_protocol': continuation['resume_protocol'],
            'resume_controls': continuation['resume_controls'],
            'report_source': original.source(__file__), 'row_contract_source': original.source(original.__file__),
            'new_inventory_allowance': {'slots': 3, 'tokens': 1500000, 'decisions': 384, 'attempts': 384, 'PS1_public_tests': 64},
            'old_budget_transferred': False, 'original_records_modified': False, 'nested_phase_times_added': False,
            'new_model_calls': 0, 'new_scoring_calls': 0, 'new_tokenizer_calls': 0,
            'new_parameter_updates': 0, 'new_backward_calls': 0,
            'interpretation': copy.deepcopy(first['interpretation']) + [
                'This is the unique original12 inventory, not15 samples. First nine rows remain verbatim; only original three unstarted identities are replaced.',
                'Four interrupted outcomes remain null. Complete call billing does not prove a terminal business score or exact recovery state.',
                'The original14512 uncertain reservation remains uncertain; complete actual generation cost stays null after continuation.',
                'The original file named final.json remains the immutable first-stage report; each stage binds its own plan and supervisor.',
            ]}


def markdown(report):
    text = original.markdown(report).replace('# v052 原生OpenHands与受管S1桥接终态', '# v052 原十二槽唯一接续合并报告', 1)
    return text + '\n首阶段九行原样保留，仅替换原三个未开始槽；四中断评分与 14512 不确定预约保留。' \
        '完整实际 token 成本仍为 null，分阶段标量与来源见 JSON；未重评分或恢复中断回合。\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-stage', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--markdown', type=Path)
    args = parser.parse_args()
    outputs = [p for p in (args.output, args.markdown) if p is not None]
    if len({p.resolve() for p in outputs}) != len(outputs) or any(p.exists() for p in outputs):
        raise FileExistsError('Completion outputs must be new; original reports are immutable')
    report = summarize(args.first_stage, args.root)
    for path, text in [(args.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'),
                       *(([(args.markdown, markdown(report))]) if args.markdown is not None else [])]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x') as stream:
            stream.write(text)
    print(json.dumps({'output': original.source(args.output), 'status_counts': report['status_counts'],
                      'billing': report['billing']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
