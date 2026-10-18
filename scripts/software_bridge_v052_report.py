"""Read a terminal v052 twelve-slot inventory once; never execute or rescore it.

Formal values need the original complete host state, closed/report/plan bindings,
continue verdict/measurement, native settlement and all episode guards. Raw
observations stay separate. Only this root's supervisor ledger and unique worker
intervals enter costs. No previous calibration or nested phase time is added.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.software_holdout_v051_report import bounded

VERSION = 'software-bridge-v052-final-v1'
CONDITIONS = ('OH_ref', 'PS1')
TASKS = tuple(f'cal2-{repo}-{number}' for repo in ('boltons', 'parse', 'xmltodict') for number in (1, 2))
PRIMARY = ('R_code', 'Q_task_terminal')
JOINT = ('R_joint', 'Q_joint')
GUARDS = ('learning_unchanged', 'rng_restored_exactly', 'software_binding_unchanged', 'actor_identity_unchanged')
ACCOUNTING_KEYS = ('prepared_requests', 'started_generations', 'complete_generations', 'known_actual_tokens',
                   'uncertain_reservation_tokens', 'complete_actual_tokens', 'ledger_tokens', 'all_started_settled')


def load(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return json.loads(raw), {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def source(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def points_to(reference, expected):
    return isinstance(reference, dict) and all(reference.get(key) == expected[key] for key in ('path', 'sha256', 'bytes'))


def pointer(reference, location):
    return {'source': reference, 'json_pointer': location}


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def endpoint(value, metric):
    if value is None:
        return None
    if metric in ('R_code', 'R_joint'):
        return value if type(value) is int and value in (0, 1) else None
    return value if finite_number(value) and 0 <= value <= 1 else None


def validate_panel(rows):
    expected = {(task, condition) for task in TASKS for condition in CONDITIONS}
    if (len(rows) != 12 or len({row['slot_id'] for row in rows}) != 12
            or {(row['task_id'], row['condition']) for row in rows} != expected):
        raise ValueError('Keep exactly the original six tasks and both conditions: twelve unique rows')


def formal_outcomes(original, host_state, report, *, source_bindings_closed):
    """Pure endpoint gate; R_code=0 after a safe local stop is an admissible value."""
    report = report or {}
    result, account = report.get('result', {}), report.get('accounting', {})
    raw = {metric: result.get(metric) for metric in (*PRIMARY, *JOINT)}
    reasons = []
    if host_state != 'complete':
        reasons.append('host_state_not_complete')
    if not source_bindings_closed:
        reasons.append('original_started_closed_report_plan_binding_incomplete')
    if report.get('status') != 'closed':
        reasons.append('worker_report_not_closed')
    if report.get('verdict', {}).get('decision') != 'continue':
        reasons.append('host_verdict_not_continue')
    if report.get('measurement', {}).get('decision') != 'continue':
        reasons.append('measurement_not_continue')
    if report.get('guard', {}).get('passed') is not True:
        reasons.append('actor_guard_missing_or_failed')
    if not all(report.get('episode_guard', {}).get(key) is True for key in GUARDS):
        reasons.append('episode_guard_missing_or_failed')
    if account.get('all_started_settled') is not True or account.get('integrity_errors') != []:
        reasons.append('native_receipt_settlement_or_integrity_unknown')
    if endpoint(raw['R_code'], 'R_code') is None:
        reasons.append('sole_terminal_code_unknown')
    if original['condition'] == 'OH_ref':
        if result.get('R_joint') is not None or result.get('project_delivery_endpoint') != 'not_applicable':
            reasons.append('native_joint_endpoint_not_applicable_contract_missing')
    elif (result.get('calibration_condition') != 'P' or result.get('slot_id') != original['slot_id']
          or endpoint(raw['R_joint'], 'R_joint') is None):
        reasons.append('managed_P_fixed_delivery_mapping_unknown')
    for key in ('actor_updates', 'critic_updates', 'new_backward_calls', 'new_parameter_updates'):
        if result.get(key, 0) != 0:
            reasons.append('unexpected_update:' + key)
    formal = {metric: endpoint(raw[metric], metric) if not reasons else None for metric in (*PRIMARY, *JOINT)}
    if original['condition'] == 'OH_ref':
        # N/A remains N/A even if the raw report contains an erroneous value.
        formal.update(R_joint=None, Q_joint=None)
    return raw, formal, reasons


def paired_two(rows, metric, *, raw=False):
    """New two-condition adapter; fixed six-task denominator, PS1 minus OH_ref."""
    validate_panel(rows)
    def value(row):
        return endpoint(row['raw_outcomes'][metric], metric) if raw else row[metric]
    index = {(row['task_id'], row['condition']): value(row) for row in rows}
    pairs, lower, upper = [], 0, 0
    for task in TASKS:
        left, right = index[task, 'PS1'], index[task, 'OH_ref']
        difference = left - right if left is not None and right is not None else None
        lower += (0 if left is None else left) - (1 if right is None else right)
        upper += (1 if left is None else left) - (0 if right is None else right)
        pairs.append({'task_id': task, 'PS1': left, 'OH_ref': right, 'difference': difference})
    known = [pair['difference'] for pair in pairs if pair['difference'] is not None]
    return {'left': 'PS1', 'right': 'OH_ref', 'denominator': 6, 'known_pairs': len(known),
            'mean': sum(known) / 6 if len(known) == 6 else None,
            'bounds': [lower / 6, upper / 6], 'pairs': pairs}


def metrics_for(rows, *, raw=False):
    validate_panel(rows)
    def value(row, metric):
        return endpoint(row['raw_outcomes'][metric], metric) if raw else row[metric]
    result = {}
    for metric in PRIMARY:
        result[metric] = {condition: bounded([value(row, metric) for row in rows if row['condition'] == condition])
                          for condition in CONDITIONS}
        result[metric]['PS1_minus_OH_ref'] = paired_two(rows, metric, raw=raw)
    for metric in JOINT:
        result[metric] = {
            'PS1': bounded([value(row, metric) for row in rows if row['condition'] == 'PS1']),
            'OH_ref': {'applicable': False, 'denominator': None, 'known': None, 'unknown': None,
                       'mean': None, 'bounds': None, 'reason': 'Native OH has no project fixed-delivery contract'},
            'PS1_minus_OH_ref': {'applicable': False, 'mean': None, 'bounds': None,
                                 'reason': 'A project-only endpoint has no native paired contrast'},
        }
    return result


def compact_usage(result, condition):
    source_value = result.get('ledger', {}) if condition == 'OH_ref' else result.get('usage', {})
    keys = ('decisions', 'attempts', 'complete_responses', 'output_bearing_calls', 'prompt_tokens',
            'completion_tokens', 'known_actual_tokens', 'total_tokens', 'uncertain_usage_attempts')
    return {key: source_value.get(key) for key in keys}


def compact_report(report, report_ref, condition):
    result = report.get('result', {})
    terminal = result.get('terminal_code', {})
    account = report.get('accounting', {})
    stop = report.get('measurement', {}).get('stop_assessment', {})
    local = stop.get('local_resource_rejections')
    reasons = ({member: proof.get('reason') for member, proof in local.items()}
               if isinstance(local, dict) else None)
    boundary = result.get('boundary')
    boundary_values = ({key: value for key, value in boundary.items()
                        if value is None or type(value) in (str, bool, int, float)}
                       if isinstance(boundary, dict) else None)
    return {
        'usage': compact_usage(result, condition),
        'usage_source': pointer(report_ref, '/result/ledger' if condition == 'OH_ref' else '/result/usage'),
        'native_accounting': {key: account.get(key) for key in ACCOUNTING_KEYS},
        'native_integrity_errors_count': len(account['integrity_errors']) if isinstance(account.get('integrity_errors'), list) else None,
        'native_accounting_source': pointer(report_ref, '/accounting'),
        'stop': {'native_status': result.get('status'), 'native_reason': result.get('stop_reason'),
                 'sdk_execution_status': result.get('sdk_execution_status'), 'boundary_scalars': boundary_values,
                 'measurement_classification': stop.get('classification'), 'local_resource_rejections': reasons,
                 'boundary_source': pointer(report_ref, '/result/boundary'),
                 'stop_assessment_source': pointer(report_ref, '/measurement/stop_assessment')},
        'submitted': result.get('submitted') if condition == 'PS1' else None,
        'role': {'protocol': 'official_native_single_agent' if condition == 'OH_ref' else 'managed_S1',
                 'managed_internal_condition': result.get('calibration_condition') if condition == 'PS1' else None,
                 'fixed_member': 'member_001' if condition == 'PS1' else None,
                 'native_role_does_not_imply_project_member': condition == 'OH_ref'},
        'guards': {'actor_passed': report.get('guard', {}).get('passed'),
                   **{key: report.get('episode_guard', {}).get(key) for key in GUARDS},
                   'source': pointer(report_ref, '/episode_guard'),
                   'actor_source': pointer(report_ref, '/guard')},
        'verdict': {'decision': report.get('verdict', {}).get('decision'),
                    'reasons': report.get('verdict', {}).get('reasons')},
        'measurement_decision': report.get('measurement', {}).get('decision'),
        'measurement_source': pointer(report_ref, '/measurement'),
        'final_tests': {
            'host_total_evaluation_attempts': result.get('host_final_evaluation_attempts'),
            'host_total_test_executions': result.get('host_final_test_executions'),
            'terminal_new_evaluation_attempts': terminal.get('new_evaluation_attempts'),
            'terminal_new_test_executions': terminal.get('new_test_executions'),
            'same_fixed_tree_assessment_reused': terminal.get('reused_same_fixed_tree_assessment'),
            'same_identity_authoritative_receipt_reused': terminal.get('same_identity_authoritative_receipt_reused'),
            'tests_total': terminal.get('tests_total'), 'tests_passed': terminal.get('tests_passed'),
            'test_nodes_observed': terminal.get('test_nodes_observed'),
            'all_expected_tests_observed': terminal.get('all_expected_tests_observed'),
            'source_attributable_collection_failure': terminal.get('source_attributable_collection_failure'),
            'source': pointer(report_ref, '/result/terminal_code'),
            'scope': 'Host totals already include fixed plus non-reused terminal execution; do not add terminal counts again. Missing collection nodes are not-run, not executed failures.',
        },
        'unique_candidate': {'OH_export': result.get('candidate_files'), 'OH_export_lock': result.get('candidate_lock'),
                             'shared_terminal_lock': terminal.get('lock'),
                             'files_sha256': terminal.get('files_sha256'),
                             'source': pointer(report_ref, '/result/terminal_code')},
    }


def worker_intervals(states):
    intervals, seen, issues = [], set(), []
    for slot, state in states.items():
        for attempt in state.get('attempts', []):
            output = attempt.get('output')
            if not output:
                issues.append({'slot_id': slot, 'kind': 'worker_output_identity_missing'})
                # Preserve an unknown interval; do not collapse it to zero cost.
                key = ('unknown', slot, len(intervals))
            else:
                key = str(Path(output).resolve())
            if key in seen:
                issues.append({'slot_id': slot, 'kind': 'duplicate_worker_interval_not_readded', 'output': output})
                continue
            seen.add(key)
            gpu = attempt.get('gpu')
            index = gpu.get('index') if isinstance(gpu, dict) else None
            if index is None:
                index = attempt.get('binding', {}).get('gpu_index')
            seconds = attempt.get('seconds')
            if not finite_number(seconds) or seconds < 0:
                seconds = None
            intervals.append({'slot_id': slot, 'output': output, 'pid': attempt.get('pid'), 'gpu_index': index,
                              'started_at': attempt.get('started_at'), 'ended_at': attempt.get('ended_at'),
                              'seconds': seconds, 'exit_code': attempt.get('exit_code'), 'reason': attempt.get('reason')})
    known = [row['seconds'] for row in intervals if row['seconds'] is not None]
    full = sum(known) if len(known) == len(intervals) else None
    return {'unique_intervals': len(intervals), 'known_interval_seconds': sum(known),
            'unknown_seconds_intervals': len(intervals) - len(known), 'gpu_worker_seconds': full,
            'gpu_worker_hours': full / 3600 if full is not None else None,
            'intervals': intervals, 'issues': issues,
            'scope': 'Whole unique worker intervals, including pre-model resource attempts. Nested native generation, test and phase time are not added.'}


def summarize(root):
    root = Path(root).resolve()
    plan, plan_ref = load(root / 'plan.json')
    supervisor, supervisor_ref = load(root / 'supervisor.json')
    if supervisor.get('status') not in ('complete', 'paused'):
        raise ValueError('Read only a terminal complete/paused host; do not report an in-flight snapshot as final')
    if not points_to(supervisor.get('plan'), plan_ref):
        raise ValueError('Supervisor does not bind this exact plan')
    original_rows = plan['rows']
    validate_panel(original_rows)
    if set(supervisor['states']) != {row['slot_id'] for row in original_rows}:
        raise ValueError('Supervisor must retain all and only the original twelve slots')
    rows, integrity = [], []
    for original in original_rows:
        slot = original['slot_id']
        state = supervisor['states'][slot]
        folder = root / 'slots' / slot
        started_path, closed_path = folder / 'started.json', folder / 'closed.json'
        row = {key: original.get(key) for key in ('slot_id', 'task_id', 'condition', 'seed', 'first_member')}
        row.update(host_state=state.get('status'), started=started_path.exists(),
                   status='not_started', raw_outcomes={metric: None for metric in (*PRIMARY, *JOINT)},
                   **{metric: None for metric in (*PRIMARY, *JOINT)})
        row['joint_applicable'] = row['condition'] == 'PS1'
        if row['started']:
            started, started_ref = load(started_path)
            row.update(status='technical_unknown', started_record=started_ref)
            report_path = Path(started['attempt']).resolve() / 'report.json'
            report = None
            bindings = started.get('row') == original and points_to(started.get('source_plan'), plan_ref)
            attempts = {str(Path(item['output']).resolve()) for item in state.get('attempts', []) if item.get('output')}
            bindings = bindings and str(report_path.parent) in attempts and report_path.parent.is_relative_to(root)
            if report_path.exists() and report_path.parent.is_relative_to(root):
                report, report_ref = load(report_path)
                row['worker_report'] = report_ref
                bindings = bindings and report.get('row') == original and points_to(report.get('source_plan'), plan_ref)
                if closed_path.exists():
                    closed, closed_ref = load(closed_path)
                    row['closed_record'] = closed_ref
                    bindings = bindings and points_to(closed.get('report'), report_ref) and closed.get('decision') == 'continue'
                else:
                    bindings = False
                raw, formal, reasons = formal_outcomes(original, state.get('status'), report,
                                                       source_bindings_closed=bindings)
                row.update(raw_outcomes=raw, **formal, formal_binding_issues=reasons)
                row.update(compact_report(report, report_ref, row['condition']))
                if not reasons:
                    row['status'] = 'closed'
                else:
                    integrity.append({'slot_id': slot, 'issues': reasons})
            else:
                row['formal_binding_issues'] = ['worker_report_missing_or_outside_root']
                integrity.append({'slot_id': slot, 'issues': row['formal_binding_issues']})
            interruption = report_path.parent / 'interruption.json'
            if interruption.exists() and report_path.parent.is_relative_to(root):
                row['interruption'] = source(interruption)
        elif state.get('status') == 'complete' or closed_path.exists():
            row['formal_binding_issues'] = ['completion_without_original_started_record']
            integrity.append({'slot_id': slot, 'issues': row['formal_binding_issues']})
        rows.append(row)
    ledger = supervisor.get('ledger', {})
    billing = {key: ledger.get(key) for key in ('known_actual_tokens', 'uncertain_reservation_tokens',
        'started_generations', 'complete_generations', 'ledger_tokens', 'complete_actual_tokens', 'logical_inventory',
        'new_actor_steps', 'new_critic_steps', 'new_backward_calls')}
    billing.update(source=pointer(supervisor_ref, '/ledger'),
        integrity_errors_count=len(ledger['integrity_errors']) if isinstance(ledger.get('integrity_errors'), list) else None,
        integrity_errors_source=pointer(supervisor_ref, '/ledger/integrity_errors'),
        scope='Only the current v052 supervisor actual-native ledger, used once; no v051 or nested cost added.')
    worker = worker_intervals(supervisor['states'])
    return {'version': VERSION, 'created_at_beijing': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'root': str(root), 'read_only': True, 'host_status': supervisor['status'],
        'host_started_at': supervisor.get('started_at'), 'host_ended_at': supervisor.get('ended_at'),
        'plan': plan_ref, 'supervisor': supervisor_ref, 'source_commit': plan.get('source_commit'),
        'model_admission': plan.get('model_admission'), 'report_source': source(__file__),
        'bounded_library': source(Path(__file__).with_name('software_holdout_v051_report.py')),
        'logical_slots': 12, 'logical_tasks': 6, 'conditions': list(CONDITIONS),
        'rows': rows, 'status_counts': dict(Counter(row['status'] for row in rows)),
        'formal_metrics': metrics_for(rows), 'raw_metrics': metrics_for(rows, raw=True),
        'all12_formal_primary_endpoints_known': all(row[metric] is not None for row in rows for metric in PRIMARY),
        'billing': billing, 'worker_cost': worker, 'integrity_issues': integrity + worker['issues'],
        'legacy_costs_included': False, 'nested_phase_times_added': False,
        'original_records_modified': False, 'new_model_calls': 0, 'new_scoring_calls': 0,
        'new_tokenizer_calls': 0, 'new_parameter_updates': 0, 'new_backward_calls': 0,
        'interpretation': [
            'Six fixed development tasks from three repositories; not a new independent holdout or vendor benchmark reproduction.',
            'Same raw/no-adapter project numerical provider; native OH tools/history/finish differ from managed S1 Gamma and fixed submission.',
            'Each task is equally weighted. Any required unknown makes the full mean or paired difference null; bounds are not confidence intervals.',
            'R_code/Q_task_terminal compare sole terminal production trees. PS1 R_joint/Q_joint are additional fixed-delivery endpoints; OH is not applicable.',
            'Safe context or budget closure with all source/guard/test bindings can have known code zero. A fault, missing guard or unstarted slot is not imputed zero.',
            'No rescore, model retry, additional seed or reward threshold. Report construction performs no new experiment.',
        ]}


def markdown(report):
    lines = ['# v052 原生OpenHands与受管S1桥接终态', '',
             f"宿主`{report['host_status']}`；原12行状态`{report['status_counts']}`。raw与正式结果分列，未知不填0。", '',
             '## 六题等权主端点', '', '| 端点/条件 | 已知/6 | 正式均值 | 未决界限 |', '|---|---:|---:|---|']
    for metric in PRIMARY:
        for condition in CONDITIONS:
            item = report['formal_metrics'][metric][condition]
            lines.append(f"| {metric}/{condition} | {item['known']}/6 | {item['mean']} | {item['bounds']} |")
        item = report['formal_metrics'][metric]['PS1_minus_OH_ref']
        lines.append(f"| {metric}/PS1−OH_ref | {item['known_pairs']}/6 pairs | {item['mean']} | {item['bounds']} |")
    lines += ['', '## 逐槽原始与正式端点', '',
              '| 槽 | 状态 | raw R_code | 正式R_code | raw Q_terminal | 正式Q_terminal | PS1 R_joint |',
              '|---|---|---:|---:|---:|---:|---:|']
    for row in report['rows']:
        joint = row['R_joint'] if row['joint_applicable'] else 'N/A'
        lines.append(f"| {row['slot_id']} | {row['status']} | {row['raw_outcomes']['R_code']} | {row['R_code']} | "
                     f"{row['raw_outcomes']['Q_task_terminal']} | {row['Q_task_terminal']} | {joint} |")
    lines += ['', 'OH固定交付端点不适用；PS1 R_joint/Q_joint六题摘要及raw指标见JSON。'
              '测试未观察节点保持not-run/未知，不冒称已执行失败。', '', '## 费用与限制', '',
              f"本轮账本：`{json.dumps(report['billing'], ensure_ascii=False)}`。", '',
              f"唯一worker `{report['worker_cost']['unique_intervals']}` 段，已知秒数 `{report['worker_cost']['known_interval_seconds']}`，"
              f"完整秒数 `{report['worker_cost']['gpu_worker_seconds']}`；缺失时不填0。", '',
              *['- ' + value for value in report['interpretation']], '',
              '完整来源与紧凑guard/停止/测试/复用字段见JSON；大段原始调用和测试正文仅在原worker report保留。']
    return '\n'.join(lines).replace('None', 'null') + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--markdown', type=Path)
    args = parser.parse_args()
    outputs = [path for path in (args.output, args.markdown) if path is not None]
    if len({path.resolve() for path in outputs}) != len(outputs) or any(path.exists() for path in outputs):
        raise FileExistsError('Each terminal report output must be new; never overwrite an original')
    report = summarize(args.root)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(encoded)
    if args.markdown is not None:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        with args.markdown.open('x') as stream:
            stream.write(markdown(report))
    print(json.dumps({'output': source(args.output), 'status_counts': report['status_counts'],
                      'billing': report['billing'], 'worker_seconds': report['worker_cost']['gpu_worker_seconds']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
