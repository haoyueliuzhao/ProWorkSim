"""Close against physical provider records, preserving auxiliary unknown holds."""
from __future__ import annotations
from .software_communication_finish_v159 import require_known_usage,retry_evidence

def validate_usage(ledger,limits,physical,*,physical_retry_rows=None):
    require_known_usage(ledger)
    provider=ledger.get('authoritative_provider_snapshot') or {}
    calls=physical.get('calls',[]);unknown=physical.get('unresolved_calls',[])
    ids=[x['call_id'] for x in calls+unknown]
    known=sum(x['prompt_tokens']+x['completion_tokens'] for x in calls)
    held=sum(x['reserved_tokens'] for x in unknown)
    proof=provider.get('retry_recovery_evidence') or {}
    if held:
        if physical_retry_rows is None:
            raise ValueError('Unknown retry holds require the original physical SQLite rows')
        actual_proof=retry_evidence(provider,physical_retry_rows)['retry_recovery_evidence']
        if proof!=actual_proof:raise ValueError('Controller retry proof differs from the actual physical account')
    approved={x['request_id']:x for x in proof.get('covered_retry_unknowns',[])+proof.get('compressor_unknowns',[])}
    if set(approved)!={x['call_id'] for x in unknown}:
        raise ValueError('Physical unknown attempts are not exactly the proved retained holds')
    for value in unknown:
        record=approved[value['call_id']]
        if (value['purpose']!=record['usage_id'] or value['status']!=record['status']
            or value['reserved_tokens']!=record['reserved_tokens']):
            raise ValueError('Unknown attempt purpose/status/hold changed at closure')
    if (len(ids)!=len(set(ids)) or len(ids)!=provider.get('attempts') or len(ids)!=ledger.get('attempts')
        or provider.get('inflight_count')!=0 or ledger.get('inflight') is not None
        or known!=provider.get('known_actual_tokens') or known!=ledger.get('known_actual_tokens')
        or held!=provider.get('uncertain_reserved_tokens') or held!=ledger.get('uncertain_reserved_tokens')
        or ledger.get('complete_actual_tokens')!=(None if unknown else known)
        or type(ledger.get('decisions')) is not int or not 0<=ledger['decisions']<=limits['agent_decisions']
        or len(ids)>limits['all_model_attempts'] or known+held>limits['input_plus_output_tokens']
        or ledger.get('token_limit')!=limits['input_plus_output_tokens']
        or ledger.get('all_model_attempt_limit')!=limits['all_model_attempts']
        or ledger.get('agent_decision_limit')!=limits['agent_decisions']
        or physical.get('usage_capture_complete') is not (not unknown)):
        raise ValueError('Closed team does not reconcile with its exact physical provider ledger')
    return ledger

def validate_closed_usage(ledger,limits):
    # Called only by the trusted host after all controller writers stopped.
    from . import software_benchmark_scope_v168 as scope
    from .software_benchmark_host_api_v168 import usage_for_slot,original
    from .software_benchmark_candidates_v054 import reference
    provider=ledger.get('authoritative_provider_snapshot') or {}
    team=provider.get('team_id')
    matches=[r for r in scope.load(reference(scope.PLAN_FILE))['rows'] if r['slot_id']==team]
    if len(matches)!=1:raise ValueError('Physical usage team is outside the new frozen panel')
    physical=usage_for_slot(matches[0]);rows=None
    if physical['unresolved_calls']:
        with original.ledger_read(matches[0]['group_id']) as db:
            rows=[dict(row) for row in db.execute('SELECT * FROM requests WHERE slot_id=?',(team,))]
    return validate_usage(ledger,limits,physical,physical_retry_rows=rows)
