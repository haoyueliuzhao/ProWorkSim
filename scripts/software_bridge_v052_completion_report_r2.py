"""Independent r2 report adapter: same12 statistics plus zero-model r1 costs.

The original completion reporter and its controls remain unchanged. Only the
accepted continuation version/root and the separately bound bootstrap stage
are adapted; actual reporting is read-only and never executes model/tests.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from types import FunctionType

from scripts import software_bridge_v052_completion_report as base

VERSION = 'software-bridge-v052-completion-report-r2-v1'
RESUME_VERSION = 'software-openhands-bridge-resume-r2-v0.52'
RESUME_ROOT_NAME = 'software-bridge-v052-resume-r2'
BOOTSTRAP_ROOT_NAME = 'software-bridge-v052-resume-r1'
BOOTSTRAP_AUDIT_SHA256 = 'bd8ac03925f41c352290e974ec2d89fbba7f66c3522899043c5481e5e679685a'
BOOTSTRAP_SECONDS = 15.057310104370117
AUDIT_SUPPORT_KEY = 'resume_r1_zero_model_failure'


def validate_bootstrap(audit):
    """Pure rejection gate: operational worker cost without new model exposure."""
    if (audit.get('version') != 'v052-resume-r1-zero-entry-readonly-audit-v1'
            or audit.get('passed') is not True or audit.get('host_status') != 'paused'
            or not base.original.finite_number(audit.get('host_ended_at'))
            or Path(audit['root']).name != BOOTSTRAP_ROOT_NAME
            or not audit.get('checks') or not all(value is True for value in audit['checks'].values())):
        raise ValueError('A fully bound terminal zero-entry bootstrap audit is required')
    ledger = audit['original_ledger']
    zero_fields = ('known_actual_tokens', 'uncertain_reservation_tokens', 'started_generations',
                   'complete_generations', 'ledger_tokens', 'complete_actual_tokens',
                   'new_actor_steps', 'new_critic_steps', 'new_backward_calls')
    if (any(type(ledger.get(key)) is not int or ledger[key] != 0 for key in zero_fields)
            or ledger.get('integrity_errors') != []):
        raise ValueError('Bootstrap cannot contain generation, unknown reservation or model updates')
    outcomes = ledger.get('outcomes', [])
    if (tuple(row['slot_id'] for row in outcomes) != base.REMAINING
            or any(row.get('started') is not False or row.get('closed') is not False for row in outcomes)):
        raise ValueError('Bootstrap cannot contain any slot-start entry')
    rows = audit['rows']
    if tuple(row['slot_id'] for row in rows) != base.REMAINING:
        raise ValueError('Bootstrap is limited to the original three identities')
    attempts = []
    for row in rows:
        if (row.get('host_state') != 'stopped'
                or any(row.get(key) is not False for key in ('slot_entered', 'model_loader_entered',
                                                            'generation_started', 'business_sample_exposure_added'))
                or any(row.get(key) != 0 for key in ('new_model_calls', 'known_actual_tokens', 'uncertain_reservation_tokens'))
                or len(row.get('attempts', [])) != 1):
            raise ValueError('Bootstrap rows must prove no model or scientific sample entry')
        attempt = row['attempts'][0]
        absent = attempt.get('absent_before_model_paths', {})
        required = [Path(audit['root']) / 'slots' / row['slot_id'] / 'started.json',
                    *[Path(attempt['output']) / name for name in ('task.json', 'resident', 'resident/calls', 'prepared', 'episode')]]
        if (attempt.get('exit_code') != 1 or attempt.get('failure_present_in_log') is not True
                or attempt.get('all_expected_pre_model_paths_absent') is not True
                or any(absent.get(str(path)) is not True for path in required)
                or any(value is not True for value in absent.values())):
            raise ValueError('Bootstrap model/slot absence must be explicit, not assumed from a zero ledger')
        attempts.append(attempt)
    cost = audit['worker_cost']
    intervals = cost['intervals']
    if (len(intervals) != 3 or cost.get('unique_intervals') != 3
            or {item['output'] for item in intervals} != {item['output'] for item in attempts}
            or len({item['output'] for item in intervals}) != 3
            or any(not Path(item['output']).resolve().is_relative_to(Path(audit['root']).resolve()) for item in intervals)
            or any(not base.original.finite_number(item.get('seconds')) or item['seconds'] < 0
                   or not base.original.finite_number(item.get('ended_at')) for item in intervals)
            or sum(item['seconds'] for item in intervals) != BOOTSTRAP_SECONDS
            or cost.get('known_interval_seconds') != BOOTSTRAP_SECONDS
            or cost.get('gpu_worker_seconds') != BOOTSTRAP_SECONDS
            or cost.get('unknown_seconds_intervals') != 0):
        raise ValueError('Keep exactly the three bound bootstrap worker intervals and their nonzero cost')
    return cost


def read_continuation_r2(root, first, first_ref):
    if Path(root).resolve().name != RESUME_ROOT_NAME:
        raise ValueError('Use only the independent original-three resume-r2 root')
    # The original function code is unchanged. Its only private global override
    # selects the explicitly authorized new host version, not a new row policy.
    namespace = {**base.__dict__, 'RESUME_VERSION': RESUME_VERSION}
    reader = FunctionType(base.read_continuation.__code__, namespace, base.read_continuation.__name__)
    stage = reader(root, first, first_ref)
    plan = base.checked(stage['plan'])
    audit_ref = plan.get('supporting_references', {}).get(AUDIT_SUPPORT_KEY)
    if not isinstance(audit_ref, dict) or audit_ref.get('sha256') != BOOTSTRAP_AUDIT_SHA256:
        raise ValueError('r2 plan must bind the exact immutable zero-entry r1 audit')
    audit = base.checked(audit_ref)
    validate_bootstrap(audit)
    stage['bootstrap_audit'] = audit_ref
    return stage


def include_bootstrap(report, audit, audit_ref):
    """Add cost only; preserve every row, model-ledger value and statistic."""
    bootstrap_cost = validate_bootstrap(audit)
    if (audit_ref.get('sha256') != BOOTSTRAP_AUDIT_SHA256 or report.get('logical_slots') != 12
            or len(report.get('rows', [])) != 12 or len(report.get('stages', [])) != 2
            or Path(report['root']).name != RESUME_ROOT_NAME):
        raise ValueError('Add bootstrap cost once to the bound original12 r2 report only')
    combined = copy.deepcopy(report)
    intervals = combined['worker_cost']['intervals'] + copy.deepcopy(bootstrap_cost['intervals'])
    identities = [str(Path(item['output']).resolve()) for item in intervals if item.get('output')]
    if len(identities) != len(intervals) or len(set(identities)) != len(identities):
        raise ValueError('An attempt output may appear only once across all three stages')
    original_worker = report['worker_cost']
    full = base.sum_known(original_worker.get('gpu_worker_seconds'), bootstrap_cost['gpu_worker_seconds'])
    combined['worker_cost'].update(
        unique_intervals=len(intervals), intervals=intervals,
        known_interval_seconds=base.sum_known(original_worker.get('known_interval_seconds'), bootstrap_cost['known_interval_seconds']),
        gpu_worker_seconds=full, gpu_worker_hours=full / 3600 if full is not None else None,
        unknown_seconds_intervals=original_worker.get('unknown_seconds_intervals'),
        scope='Original first-stage plus unique scientific r2 worker intervals, and zero-model r1 bootstrap intervals exactly once; no nested times.')
    bootstrap_stage = {'kind': 'zero_model_bootstrap_only', 'root': audit['root'], 'audit': copy.deepcopy(audit_ref),
                       'host_status': audit['host_status'], 'host_ended_at': audit['host_ended_at'],
                       'scientific_rows_added': 0, 'model_ledger_added': 0,
                       'original_ledger': copy.deepcopy(audit['original_ledger']),
                       'worker_cost': copy.deepcopy(bootstrap_cost)}
    combined['stages'].insert(1, bootstrap_stage)
    combined.update(version=VERSION, bootstrap_audit=copy.deepcopy(audit_ref), bootstrap_scientific_rows_added=0,
                    bootstrap_model_calls_added=0, bootstrap_worker_seconds_added=BOOTSTRAP_SECONDS,
                    scientific_inventory_unchanged=True,
                    bootstrap_stage_included_once=True)
    combined['interpretation'] += [
        'The failed r1 bootstrap entered no slot/model/generation; it adds no scientific row or model fee, but its three worker lifetimes add15.057310104370117 seconds once.',
        'First-stage nine rows and r2 replacement three remain the same12. r1 is an operational stage, not three new samples.',
    ]
    return combined


def summarize(first_stage, root):
    # Retain the original summary/merge/statistics implementation. Only its
    # continuation reader is privately bound to r2; no old source is edited.
    namespace = {**base.__dict__, 'read_continuation': read_continuation_r2}
    summary_function = FunctionType(base.summarize.__code__, namespace, base.summarize.__name__)
    report = summary_function(first_stage, root)
    plan = base.checked(report['plan'])
    audit_ref = plan['supporting_references'][AUDIT_SUPPORT_KEY]
    audit = base.checked(audit_ref)
    combined = include_bootstrap(report, audit, audit_ref)
    combined.update(report_source=base.original.source(__file__),
                    original_completion_reporter_source=base.original.source(base.__file__),
                    narrow_private_bindings={
                        'read_continuation': 'Exact original code; RESUME_VERSION global set to r2 only',
                        'summarize': 'Exact original code; read_continuation global set to r2 reader only',
                        'statistics': 'Original merge_stages/metrics_for/bounded unchanged; add bootstrap worker costs afterwards'})
    return combined


def markdown(report):
    return base.markdown(report) + '\nr1 零模型启动阶段没有新增科学行或模型账单；' \
        '三个 worker 区间 15.057310104370117 秒单列且仅计一次。r2 仍仅替换原三个未开始槽。\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-stage', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--markdown', type=Path)
    args = parser.parse_args()
    outputs = [p for p in (args.output, args.markdown) if p is not None]
    if len({p.resolve() for p in outputs}) != len(outputs) or any(p.exists() for p in outputs):
        raise FileExistsError('r2 completion outputs must be new; original reports are immutable')
    report = summarize(args.first_stage, args.root)
    encoded = [(args.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')]
    if args.markdown is not None:
        encoded.append((args.markdown, markdown(report)))
    for path, text in encoded:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x') as stream:
            stream.write(text)
    print(json.dumps({'output': base.original.source(args.output), 'status_counts': report['status_counts'],
                      'billing': report['billing'], 'worker_seconds': report['worker_cost']['gpu_worker_seconds']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
