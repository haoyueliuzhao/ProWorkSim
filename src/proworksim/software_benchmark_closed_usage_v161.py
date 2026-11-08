"""Original closed-usage contract, bound to independent14 physical identities."""
from .software_benchmark_closed_usage_v159 import validate_usage

def validate_closed_usage(ledger,limits):
    # Called only by the trusted host after all controller writers stopped.
    from . import software_benchmark_scope_v161 as scope
    from .software_benchmark_host_api_v161 import usage_for_slot,original
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
