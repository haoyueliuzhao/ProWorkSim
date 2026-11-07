"""Preserve primary diagnostic failures before interpreting optional child receipts.

This is an offline receipt reader. It cannot reserve, launch, retry, score, or
alter a diagnostic identity. Missing observation measurements are not failures
of a valid source/candidate or a successfully closed controller.
"""
from __future__ import annotations

import copy

VERSION = 'v143-primary-diagnostic-error-preservation-r1'


class DiagnosticFailure(RuntimeError):
    def __init__(self, report):
        self.report = copy.deepcopy(report)
        original = report.get('original_error')
        details = (f"{original.get('type', 'error')}: {original.get('message', '')}"
                   if isinstance(original, dict) else str(original or 'no original error supplied'))
        super().__init__(f"{report['classification']}: {details}; cleanup={report['cleanup_status']}")


def inspect_diagnostic(result_ref, specification, *, load, condition, shared_strategy,
                       controller_memory_bytes, gib=1024**3):
    """Return verified receipts or raise with all known original error evidence.

The caller may persist ``error.report`` under its new coordinator root. It must
not re-enter either the failed diagnostic identity or a paid model attempt.
"""
    report = {'version': VERSION, 'specification': copy.deepcopy(specification),
        'result': copy.deepcopy(result_ref), 'status': None, 'passed': False,
        'model_calls': None, 'original_error': None, 'cleanup_status': 'unknown',
        'cleanup': None, 'controller_result': None, 'automatic_retry': False}

    def failure(classification, *, inspection_error=None):
        report['classification'] = classification
        if inspection_error is not None:
            report['inspection_error'] = {'type': type(inspection_error).__name__,
                                           'message': str(inspection_error)}
        raise DiagnosticFailure(report)

    try:
        result = load(result_ref)
    except Exception as error:
        failure('diagnostic_result_unreadable', inspection_error=error)
    if not isinstance(result, dict):
        failure('diagnostic_result_not_object')
    report.update(status=result.get('status'), original_result_passed=result.get('passed'),
                  model_calls=result.get('model_calls'), original_error=copy.deepcopy(result.get('error')))
    quiet_ref = result.get('quiescence')
    if isinstance(quiet_ref, dict):
        report['cleanup'] = copy.deepcopy(quiet_ref)
        try:
            quiet = load(quiet_ref)
            if (isinstance(quiet, dict) and quiet.get('quiescent') is True
                    and quiet.get('all_owned_objects_removed') is True
                    and quiet.get('cleanup_errors') == [] and quiet.get('create_result_unknown') is False):
                report['cleanup_status'] = 'proven'
            else:
                report['cleanup_status'] = 'not_proven'
        except Exception as error:
            report['cleanup_read_error'] = {'type': type(error).__name__, 'message': str(error)}
    # Never dereference an optional controller result after a primary failure.
    if report['status'] != 'closed' or report['original_result_passed'] is not True or report['original_error']:
        failure('diagnostic_initialization_failed')
    if report['cleanup_status'] != 'proven':
        failure('diagnostic_cleanup_not_proven')
    if type(report['model_calls']) is not int or report['model_calls'] != 0:
        failure('diagnostic_zero_model_condition_not_proven')
    child_ref = result.get('controller_result')
    if not isinstance(child_ref, dict):
        failure('diagnostic_controller_receipt_missing')
    report['controller_result'] = copy.deepcopy(child_ref)
    try:
        child = load(child_ref)
    except Exception as error:
        failure('diagnostic_controller_receipt_unreadable', inspection_error=error)
    if not isinstance(child, dict):
        failure('diagnostic_controller_receipt_not_object')
    group = specification['organization_id']
    members = condition(group)['fixed_members']
    team = child.get('team_diagnostic', {})
    sessions = child.get('private_sessions', {})
    peak = child.get('process_resource_peak', {})
    registry = child.get('actual_member_registry', {})
    if (child.get('diagnostic_passed') is not True or not isinstance(team, dict)
            or team.get('passed') is not True or team.get('model_calls') != 0
            or team.get('organization_id') != group or team.get('fixed_members') != members
            or not isinstance(registry, dict) or set(registry) != set(members)
            or any(not isinstance(row, dict) or row.get('status') != 'live' for row in registry.values())
            or not isinstance(sessions, dict) or set(sessions) != set(members)
            or any(not isinstance(s, str) or not s for s in sessions.values())
            or len(set(sessions.values())) != len(members)
            or child.get('execution_alignment') != shared_strategy(group)
            or not isinstance(child.get('content_tokenizer'), dict)
            or not isinstance(peak, dict) or peak.get('measured') is not True
            or type(peak.get('peak_rss_bytes')) is not int
            or not 0 < peak['peak_rss_bytes'] <= controller_memory_bytes-2*gib):
        failure('diagnostic_private_runtime_contract_not_proven')
    return {**report, 'passed': True, 'classification': 'diagnostic_verified',
            'controller_peak': copy.deepcopy(peak),
            'scope': 'initialization_only_not_full_episode_peak',
            'observation_summary_required_for_business_closure': False}
