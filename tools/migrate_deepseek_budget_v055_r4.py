"""Explicit one-time ledger reconciliation; never edit historical request rows.

Freeze is read-only. Apply is for the root coordinator after reviewing the plan,
with the model queue drained and its controller lock held. A pre-migration SQLite
backup, preserved hard-halt evidence and supplemental unknown-cost holds remain.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from proworksim import software_benchmark_deepseek_api_v055 as old
from proworksim import software_benchmark_deepseek_api_v055_r4 as new
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/'runs/software-benchmark-v055/budget-r1/ledger.sqlite3'
QUEUE=ROOT/'runs/software-benchmark-v055/queue-r1'
VERSION='v055-budget-protocol-bound-reconciliation-r4'
HALT='provider_usage_exceeded_authorized_request_bound'
PREVIOUS_UNIT='proworksim-v055-deepseek-six-conditions-native-host-r7.service'
UNKNOWN_IDS={
    'v055-PROJECT-thinking-astropy__astropy-13236:0024',
    'v055-PROJECT-nonthinking-pytest-dev__pytest-7490:0019'}


def connect(path,*,readonly=True):
    db=sqlite3.connect('file:'+str(path)+'?mode='+('ro' if readonly else 'rw'),uri=True,
                       timeout=30,isolation_level=None)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA busy_timeout=30000')
    if readonly:db.execute('PRAGMA query_only=ON')
    return db


def baseline(db):
    value=new.ledger_fingerprint(db)
    expected=old._json({**old.POLICY,'max_concurrency':64})
    policy=db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0]
    unknown=[dict(row) for row in db.execute("SELECT * FROM requests WHERE status='uncertain' ORDER BY request_id")]
    if (policy!=expected or value['halted']!=HALT or value['request_count']!=22747
            or value['reserved_count']!=0 or value['adjustments_sha256'] is not None
            or {row['request_id'] for row in unknown}!=UNKNOWN_IDS
            or any(row['reserved_nanoyuan']!=2113536000 or row['settled_nanoyuan'] is not None for row in unknown)
            or value['cap_nanoyuan']!=2000*old.NANOYUAN or value['max_concurrency']!=64):
        raise ValueError('Ledger is not the exact reviewed old bound-violation snapshot')
    return value,unknown,policy


def freeze(output,audit):
    audit_ref=reference(audit);audit_value=json.loads(checked(audit_ref).read_bytes())
    if audit_value.get('version')!='v055-readonly-provider-output-bound-halt-audit-r1' or audit_value.get('ledger_mutations')!=0:
        raise ValueError('Require the explicit read-only causal audit')
    with connect(LEDGER) as db:
        db.execute('BEGIN')
        before,unknown,policy=baseline(db)
    adjustments=[{'adjustment_id':'absolute-model-bound-r4:'+row['request_id'],
                  'request_id':row['request_id'],
                  'amount_nanoyuan':new.ABSOLUTE_RESERVATION_NANOYUAN-row['reserved_nanoyuan'],
                  'reason':'unrecoverable_prior_usage_retained_at_documented_absolute_model_peak_bound'} for row in unknown]
    projected=before['committed_nanoyuan']+sum(row['amount_nanoyuan'] for row in adjustments)
    if projected>new.CAP_NANOYUAN:raise ValueError('Supplemental holds would exceed the unchanged cap')
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=False)
    refs=[reference(__file__),reference(new.__file__),reference(old.__file__)]
    value={'version':VERSION,'created_utc':old._now(),'ledger_path':str(LEDGER),
        'queue_root':str(QUEUE),'previous_controller_unit':PREVIOUS_UNIT,'audit':audit_ref,
        'evidence_root':str(output.parent),'ledger_before':before,'previous_policy_raw':policy,
        'new_policy_raw':new.policy_text(),'new_policy_raw_sha256':hashlib.sha256(new.policy_text().encode()).hexdigest(),
        'historical_uncertain_requests':unknown,'adjustments':adjustments,
        'projected_committed_nanoyuan':projected,'files':refs,
        'request_rows_may_be_modified':False,'cap_cny':2000,'max_concurrency':64,
        'payload_max_tokens_changed':False,'automatic_request_or_slot_replay':False,
        'unknown_actual_usage_claimed_known':False,
        'queue_resume_authorized_after_atomic_reconciliation':True}
    return write_new(output,value)


def require_drained():
    output=subprocess.run(['systemctl','--user','show',PREVIOUS_UNIT,
        '--property=ActiveState,MainPID'],capture_output=True,text=True,check=True,timeout=15)
    state=dict(line.split('=',1) for line in output.stdout.splitlines() if '=' in line)
    if state.get('ActiveState') in {'active','activating','deactivating'} or int(state.get('MainPID','0')):
        raise ValueError('Original model coordinator must be stopped before migration')
    queue=json.loads((QUEUE/'state.json').read_bytes())
    if (not queue.get('dispatch_stopped') or any(row['generation']['status'] in {'running','intent'}
            or any(score['status'] in {'running','intent'} for score in row['scores']) for row in queue['rows'])
            or any(row.get('worker',{}).get('status')=='running' for row in queue['preparation'].values())):
        raise ValueError('Queue must be drained with its original dispatch stop retained')
    return {'unit':PREVIOUS_UNIT,**state,'queue_dispatch_stopped':True,
            'generation_scoring_and_preparation_workers_running':0}


def apply(plan_path,sha):
    plan_ref=reference(plan_path)
    if plan_ref['sha256']!=sha:raise ValueError('Migration plan SHA mismatch')
    plan=json.loads(checked(plan_ref).read_bytes())
    if (plan.get('version')!=VERSION or plan.get('ledger_path')!=str(LEDGER)
            or plan.get('new_policy_raw')!=new.policy_text() or plan.get('request_rows_may_be_modified') is not False):
        raise ValueError('Unsupported reviewed migration plan')
    for item in plan['files']:checked(item)
    checked(plan['audit'])
    directory=Path(plan['evidence_root'])
    with ExitStack() as stack:
        lock=stack.enter_context((QUEUE/'coordinator.lock').open('a'))
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        drained=require_drained()
        if (directory/'reconciliation.json').exists() or (directory/'ledger-before.sqlite3').exists():
            raise ValueError('One-time migration evidence already exists; do not replay')
        with connect(LEDGER) as source:
            source.execute('BEGIN')
            before,unknown,raw_policy=baseline(source)
            if before!=plan['ledger_before'] or unknown!=plan['historical_uncertain_requests']:
                raise ValueError('Reviewed request snapshot changed')
            backup=sqlite3.connect(directory/'ledger-before.sqlite3')
            try:source.backup(backup)
            finally:backup.close()
        backup_ref=reference(directory/'ledger-before.sqlite3')
        db=connect(LEDGER,readonly=False)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            current,unknown,raw_policy=baseline(db)
            if current!=before:raise ValueError('Ledger changed between snapshot and atomic migration')
            new.create_extension_tables(db)
            created=old._now()
            for adjustment in plan['adjustments']:
                row=db.execute('SELECT * FROM requests WHERE request_id=?',(adjustment['request_id'],)).fetchone()
                amount=new.ABSOLUTE_RESERVATION_NANOYUAN-row['reserved_nanoyuan']
                if amount!=adjustment['amount_nanoyuan'] or amount<0:raise ValueError('Adjustment bound changed')
                db.execute('INSERT INTO budget_adjustments VALUES (?,?,?,?,?,?)',(
                    adjustment['adjustment_id'],adjustment['request_id'],amount,adjustment['reason'],created,
                    old._json({'plan':plan_ref,'audit':plan['audit'],'old_request_row_unchanged':True,
                               'documented_absolute_input_tokens':new.MAX_INPUT_RESERVATION,
                               'documented_absolute_output_tokens':new.MAX_OUTPUT_TOKENS,
                               'absolute_peak_reservation_nanoyuan':new.ABSOLUTE_RESERVATION_NANOYUAN,
                               'exact_prior_usage_unknown':True})))
            db.execute("UPDATE metadata SET value=? WHERE name='policy'",(new.policy_text(),))
            migration_id='v055-budget-r4:'+plan_ref['sha256']
            db.execute('INSERT INTO budget_policy_migrations VALUES (?,?,?,?,?,?)',(
                migration_id,created,raw_policy,new.policy_text(),HALT,
                old._json({'plan':plan_ref,'audit':plan['audit'],'ledger_backup':backup_ref,'drained':drained})))
            result=db.execute("DELETE FROM metadata WHERE name='halted' AND value=?",(HALT,))
            if result.rowcount!=1:raise ValueError('Reviewed hard-halt identity changed')
            after=new.ledger_fingerprint(db)
            if (after['requests_sha256']!=before['requests_sha256'] or after['request_count']!=before['request_count']
                    or after['committed_nanoyuan']!=plan['projected_committed_nanoyuan']
                    or after['committed_nanoyuan']>new.CAP_NANOYUAN or after['halted'] is not None
                    or after['reserved_count']!=0 or after['cap_nanoyuan']!=new.CAP_NANOYUAN
                    or after['max_concurrency']!=64):
                raise ValueError('Atomic migration invariant failed')
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:db.close()
        return write_new(directory/'reconciliation.json',{'version':VERSION,'completed_utc':old._now(),
            'plan':plan_ref,'ledger_path':str(LEDGER),'ledger_before':before,'ledger_after':after,
            'ledger_backup':backup_ref,'drained':drained,'integrity_restored':True,
            'queue_resume_authorized':True,'queue_state_modified':False,
            'old_request_rows_unchanged':True,'supplemental_holds_retained':True,
            'old_usage_not_reconstructed':True,'model_calls':0,'formal_slot_replays':0,
            'previous_halt_retained_in_migration_table':True})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='operation',required=True)
    p=commands.add_parser('freeze');p.add_argument('--output',type=Path,required=True);p.add_argument('--audit',type=Path,required=True)
    p=commands.add_parser('apply');p.add_argument('--plan',type=Path,required=True);p.add_argument('--sha256',required=True)
    args=parser.parse_args()
    print(json.dumps(freeze(args.output,args.audit) if args.operation=='freeze' else apply(args.plan,args.sha256)))


if __name__=='__main__':main()
