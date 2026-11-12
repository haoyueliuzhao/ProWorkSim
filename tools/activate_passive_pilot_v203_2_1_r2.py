"""Initialize the newly authorized ledger and launch the sealed owned pilot."""
import argparse
import json
from pathlib import Path
from proworksim import software_benchmark_scope_v203_2_1_r2 as scope
from proworksim import software_benchmark_host_api_v203_2_1_r2 as host
from proworksim.software_benchmark_candidates_v054 import reference


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true',required=True)
    parser.parse_args()
    scope.require_allowed('v203.2.1.run')
    if (scope.API_ROOT/'execution-started.json').exists():
        raise ValueError('Never automatically restart a consumed coordinator')
    admission=scope.dispatch_view().physical_capacity()
    if admission.get('passed') is not True:
        raise ValueError('Declared host resource headroom is not available')
    # Restore only unused operational admissions. Preserve immutable original
    # zero-call results, cleanup records and the complete transition in SQLite.
    import sqlite3, time
    from proworksim import software_benchmark_scope_v203_2_1 as old_scope
    parent_final=scope.load(reference(old_scope.API_ROOT/'coordinator-finalization.json'))
    released=scope.load(parent_final['coordinator_release'])
    if parent_final.get('cleanup_errors') or list((old_scope.BATCH_ROOT/'resource-claims').glob('active-*.json')):
        raise ValueError('Prior runtime cleanup is not proven')
    if released.get('released') is not True:
        raise ValueError('Prior coordinator reservation was not released')
    old_plan=scope.load(reference(old_scope.PLAN_FILE))
    new_plan=scope.load(reference(scope.PLAN_FILE))
    if new_plan.get('zero_request_redeployment_evidence'):
        scope.load(new_plan['zero_request_redeployment_evidence'])
    old_rows={r['slot_index']:r for r in old_plan['rows']}
    new_ids={r['slot_id'] for r in new_plan['rows']}
    witnesses=[]
    for index in (2032100,2032101):
        result_ref=reference(old_scope.BATCH_ROOT/f'episodes/{index}/result.json')
        result=scope.load(result_ref)
        if result.get('quiescence')!=reference(old_scope.BATCH_ROOT/f'episodes/{index}/quiescence.json'):
            raise ValueError('Cleanup evidence belongs to another physical attempt')
        quiet=scope.load(result['quiescence'])
        if (result.get('slot_id')!=old_rows[index]['slot_id'] or result.get('slot_id') not in new_ids
            or result.get('model_calls')!=0 or result.get('model_dispatch_started') is not False
            or quiet.get('quiescent') is not True or quiet.get('create_result_unknown') is not False
            or quiet.get('retained_objects')!=[] or quiet.get('all_owned_objects_removed') is not True
            or quiet.get('cleanup_errors')!=[]):
            raise ValueError('Only proven pre-model startup failures may reenter')
        witnesses.append({'slot_id':result['slot_id'],'result':result_ref,'quiescence':result['quiescence']})
    with sqlite3.connect(scope.LEDGER_FILE,isolation_level=None) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT count(*) FROM requests').fetchone()[0]!=0:
            raise ValueError('This deployment repair cannot reset a paid attempt')
        db.execute('CREATE TABLE IF NOT EXISTS zero_call_reentry_v20321(slot_id TEXT PRIMARY KEY,prior_state TEXT NOT NULL,evidence_json TEXT NOT NULL,observed REAL NOT NULL)')
        for witness in witnesses:
            row=db.execute('SELECT state FROM team_admissions WHERE slot_id=?',(witness['slot_id'],)).fetchone()
            if row is not None:
                if row[0]!='closed':raise ValueError('Prior team admission is not closed')
                db.execute('INSERT INTO zero_call_reentry_v20321 VALUES(?,?,?,?)',(witness['slot_id'],row[0],json.dumps(witness,sort_keys=True),time.time()))
                db.execute('DELETE FROM team_admissions WHERE slot_id=?',(witness['slot_id'],))
            else:
                prior=db.execute('SELECT prior_state,evidence_json FROM zero_call_reentry_v20321 WHERE slot_id=?',(witness['slot_id'],)).fetchone()
                if prior is None or prior[0]!='closed' or json.loads(prior[1])!=witness:
                    raise ValueError('Missing admission lacks the identical zero-call reentry proof')
        db.execute('COMMIT')
    balances=host.initialize_ledger()
    if any(v.get('known_actual_tokens') or v.get('reserved_or_unknown_nanoyuan') for v in balances.values()):
        raise ValueError('Fresh pilot ledger is not unused')
    scope.retain(scope.API_ROOT/'cash-initialization.json',{
        'same_existing_budget_CNY':'150.00','additional_budget_CNY':'0.00','states':balances,
        'operational_admission_reset_only':True,'paid_requests_or_costs_changed':False,
        'plan':reference(scope.PLAN_FILE),'admission':admission})
    from launch_passive_pilot_v203_2_1_r2 import launch
    print(json.dumps(launch(),ensure_ascii=False))


if __name__=='__main__':main()
