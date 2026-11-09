"""Reconcile logical SDK usage with original physical requests and retained holds."""
import json
import sqlite3
from . import software_benchmark_scope_v181 as scope

def validate_closed_usage(ledger,limits):
    slot=ledger.get('slot_id')
    calls=ledger.get('calls',[])
    if not slot and calls:slot=calls[0].get('team_slot_id')
    with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        physical=[dict(r) for r in db.execute('SELECT r.*,d.logical_id,d.token_hold FROM requests r JOIN context_requests_v181 d USING(request_id) WHERE job_id=?',(slot,))]
    successes=[r for r in physical if r['status']=='settled'];unknown=[r for r in physical if r['status']!='settled']
    actual=sum(json.loads(r['usage'])['total_tokens'] for r in successes)
    holds=sum(r['token_hold'] for r in unknown)
    ids={r['request_id'] for r in calls};settled={r['logical_id'] for r in successes}
    if (ledger.get('inflight') or ledger.get('uncertain_reserved_tokens') or actual!=ledger.get('known_actual_tokens')
        or ids!=settled or len(ids)!=len(successes) or actual+holds>limits['input_plus_output_tokens']
        or len(physical)>limits['all_model_attempts'] or any(r['status']=='reserved' or r['logical_id'] not in settled for r in unknown)):
        raise ValueError('Closed candidate does not reconcile to original physical billing')
    return {**ledger,'physical_attempts':len(physical),'physical_uncertain_reserved_tokens':holds,
        'physical_usage_complete':not unknown,'physical_actual_tokens':actual,
        'complete_actual_tokens':actual if not unknown else None,'logical_usage_retained':True}
