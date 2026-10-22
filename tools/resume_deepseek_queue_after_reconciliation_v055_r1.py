"""One administrative queue resume after independently approved ledger reconciliation.

This tool never writes SQLite, changes a formal row, starts a service, or repeats
an entered episode. All financial tables are fingerprinted, including any new
supplemental holds. The final accounting receipt must explicitly authorize the
queue resume and bind its authoritative total to that entire read-only snapshot.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from urllib.parse import quote

from proworksim.software_benchmark_candidates_v054 import reference,checked,write_new
from proworksim.software_benchmark_queue_v055 import ROOT,load,now
from proworksim.storage import atomic_write,json_bytes,digest

VERSION='v055-queue-resume-after-reconciliation-r1'
QUEUE=ROOT/'runs/software-benchmark-v055/queue-r1'
CAP=2000*10**9


def _quoted(name):return '"'+name.replace('"','""')+'"'


def readonly_ledger_fingerprint(path):
    """No old requests-only sum: bind every ordinary financial table and schema."""
    path=Path(path).resolve()
    db=sqlite3.connect('file:'+quote(str(path),safe='/')+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        definitions=db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        if not {'metadata','requests'}<={row['name'] for row in definitions}:
            raise ValueError('Unknown ledger core schema')
        sha=hashlib.sha256();counts={};table_hashes={}
        for definition in definitions:
            name,sql=definition['name'],definition['sql']
            if 'VIRTUAL TABLE' in sql.upper():raise ValueError('Virtual financial tables require explicit separate review')
            sha.update(json_bytes({'table':name,'schema':sql}))
            columns=[row['name'] for row in db.execute('PRAGMA table_info('+_quoted(name)+')')]
            count=0;table_hash=hashlib.sha256()
            for row in db.execute('SELECT * FROM '+_quoted(name)+' ORDER BY '+','.join(map(_quoted,columns))):
                value={key:({'blob_hex':val.hex()} if isinstance(val,bytes) else val) for key,val in dict(row).items()}
                sha.update(json_bytes(value));count+=1
                table_hash.update((json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode())
            counts[name]=count;table_hashes[name]=table_hash.hexdigest()
        metadata=dict(db.execute('SELECT name,value FROM metadata'))
        policy=json.loads(metadata['policy'])
        inflight=db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]
        expected_tables={'metadata','requests','budget_adjustments','response_observations',
                         'provider_protocol_events','budget_policy_migrations'}
        if set(counts)!=expected_tables:
            raise ValueError('Unreviewed financial/audit table set; do not omit unknown holds')
        if db.execute('SELECT COUNT(*) FROM budget_adjustments WHERE amount_nanoyuan<0').fetchone()[0]:
            raise ValueError('Negative supplemental holds are not authorized')
        adjustments=db.execute('SELECT COALESCE(SUM(amount_nanoyuan),0) FROM budget_adjustments').fetchone()[0]
        committed=db.execute('SELECT COALESCE(SUM(COALESCE(settled_nanoyuan,reserved_nanoyuan)),0) FROM requests').fetchone()[0]+adjustments
        return {'ledger_path':str(path),'all_tables_sha256':sha.hexdigest(),'table_row_counts':counts,
            'accounting_tables':sorted(name for name in counts if name!='metadata'),
            'policy_sha256':hashlib.sha256(metadata['policy'].encode()).hexdigest(),
            'cap_nanoyuan':policy['cap_nanoyuan'],'max_concurrency':policy['max_concurrency'],
            'halted':metadata.get('halted'),'inflight_count':inflight,'reserved_count':inflight,
            'requests_sha256':table_hashes['requests'],'adjustments_sha256':table_hashes['budget_adjustments'],
            'policy_raw_sha256':hashlib.sha256(metadata['policy'].encode()).hexdigest(),
            'adjustments_nanoyuan':adjustments,'committed_nanoyuan':committed,'sqlite_read_only':True}
    finally:db.close()


def resume_state(state,authorization,ledger,authorization_ref,quiescence_ref):
    """Pure state transition; final financial amounts come from approved evidence."""
    if (authorization.get('version')!=VERSION or authorization.get('queue_resume_authorized') is not True
            or authorization.get('ledger_integrity_restored') is not True
            or authorization.get('all_financial_components_accounted') is not True):
        raise ValueError('No independently approved complete financial reconciliation')
    expected=authorization['ledger_after']
    for key in ('ledger_path','all_tables_sha256','accounting_tables','policy_sha256','cap_nanoyuan','max_concurrency','halted','inflight_count'):
        if ledger.get(key)!=expected.get(key):raise ValueError('Ledger differs from reviewed reconciliation: '+key)
    committed=authorization.get('committed_nanoyuan')
    if committed!=ledger.get('committed_nanoyuan'):
        raise ValueError('Authoritative total must include every supplemental hold')
    if (ledger['cap_nanoyuan']!=CAP or ledger['max_concurrency']!=64 or ledger['halted'] is not None
            or ledger['inflight_count']!=0 or type(committed) is not int or not 0<=committed<CAP
            or authorization.get('can_admit_minimum_request') is not True):
        raise ValueError('A hard budget/inflight/integrity gate still blocks resume')
    if (state.get('dispatch_stopped') is not True or state.get('stop_reason')!='shared_budget_or_accounting_gate'
            or state.get('status')!='budget_closed_with_pending' or not state.get('ended_utc')):
        raise ValueError('Queue has not reached its drained accounting-stop boundary')
    if len(state['rows'])!=3000:raise ValueError('The full original 3000-slot inventory is required')
    pending=[]
    for row in state['rows']:
        generation=row['generation']
        if generation['status'] in ('intent','running'):raise ValueError('Existing generation must finish before budget-policy transition')
        if any(score['status'] in ('pending','intent','running') for score in row['scores']):
            raise ValueError('Scoring must drain before one-time queue adoption')
        if generation['status']=='pending':
            if any(generation.get(key) for key in ('job','unit','directory','completion','result','dispatched_utc','entered')):
                raise ValueError('A pending slot contains prior entry evidence; never replay it')
            pending.append(row['slot']['slot_id'])
    if not pending:raise ValueError('No original unentered inventory remains')
    if any(item.get('worker',{}).get('status') in ('intent','running') for item in state['preparation'].values()):
        raise ValueError('Preparation workers have not drained')
    history=state.get('accounting_queue_recoveries',[])
    if any(item['authorization']==authorization_ref for item in history):raise ValueError('The same one-time authorization was already used')
    changed=deepcopy(state)
    changed['dispatch_stopped']=False;changed['status']='running'
    changed.pop('stop_reason',None);changed.pop('ended_utc',None)
    changed.setdefault('accounting_queue_recoveries',[]).append({'version':VERSION,'authorization':authorization_ref,
        'worker_quiescence':quiescence_ref,'adopted_utc':now(),'original_pending_count':len(pending),
        'original_pending_slot_ids_sha256':digest(json_bytes(pending)),
        'original_rows_and_exceptions_unchanged':True,'ledger_written':False,'entered_slots_replayed':0})
    changed['updated_utc']=now()
    assert changed['rows']==state['rows'] and changed['exceptions']==state['exceptions']
    # Keep the old halted budget observation as historical data. The next valid
    # coordinator tick replaces it from its own matching approved ledger policy.
    return changed


def inactive_coordinator(unit):
    if not unit.startswith('proworksim-v055-deepseek-six-conditions-') or not unit.endswith('.service'):
        raise ValueError('Unexpected coordinator unit')
    run=subprocess.run(['systemctl','--user','show',unit,'--property=ActiveState,MainPID,LoadState'],
                       capture_output=True,text=True,check=True,timeout=15)
    value=dict(line.split('=',1) for line in run.stdout.splitlines() if '=' in line)
    if value.get('LoadState') not in ('loaded','not-found') or value.get('ActiveState') not in ('inactive','failed') or value.get('MainPID')!='0':
        raise ValueError('Previous coordinator is not proven stopped')
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorization',required=True,type=Path);parser.add_argument('--sha256',required=True)
    parser.add_argument('--quiescence',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();authref=reference(args.authorization)
    if authref['sha256']!=args.sha256:raise ValueError('Recovery authorization SHA mismatch')
    authorization=load(authref);quietref=reference(args.quiescence);quiet=load(quietref)
    # No default live path mutation: these exact externally supplied receipts
    # must exist and describe the final legally reconciled, stopped boundary.
    if (quiet.get('all_registered_scopes_inactive') is not True
            or quiet.get('all_generation_scoring_preparation_workers_inactive') is not True):
        raise ValueError('Missing independent worker/scope quiescence proof')
    args.output=args.output.resolve()
    if not args.output.is_relative_to(ROOT/'runs/software-benchmark-v055'):
        raise ValueError('Recovery evidence must remain separate in v055')
    with (QUEUE/'coordinator.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        controller=inactive_coordinator(authorization['previous_coordinator_unit'])
        before_ref=reference(QUEUE/'state.json')
        if quiet.get('queue_state')!=before_ref or authorization.get('queue_state_before')!=before_ref:
            raise ValueError('Queue drifted after the reviewed stopped boundary')
        state=load(before_ref);plan=load(state['plan'])
        if authorization['ledger_after']['ledger_path']!=plan['ledger_path']:
            raise ValueError('No alternate or reset ledger is allowed')
        load(authorization['legal_reconciliation_receipt'])
        fingerprint=readonly_ledger_fingerprint(plan['ledger_path'])
        changed=resume_state(state,authorization,fingerprint,authref,quietref)
        args.output.parent.mkdir(parents=True,exist_ok=False)
        kept=write_new(args.output.parent/'state-before.json',state)
        intent=write_new(args.output.parent/'intent.json',{'version':VERSION,'authorization':authref,'quiescence':quietref,
            'before':before_ref,'preserved_before':kept,'read_only_ledger_fingerprint':fingerprint,
            'previous_coordinator':controller,'source':reference(__file__),'ledger_writes':0,'services_started':0})
        if reference(QUEUE/'state.json')!=before_ref:raise ValueError('Queue changed despite exclusive lease')
        atomic_write(QUEUE/'state.json',json_bytes(changed))
        print(json.dumps(write_new(args.output,{'version':VERSION,'intent':intent,'after':reference(QUEUE/'state.json'),
            'changed_top_level_fields':sorted(key for key in set(state)|set(changed) if state.get(key)!=changed.get(key)),
            'formal_rows_unchanged':True,'failure_history_unchanged':True,'ledger_written':False,'services_started':0})))


if __name__=='__main__':main()
