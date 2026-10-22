"""Necessary pure-state and temporary SQLite controls; no live queue/database writes."""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile

ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim')
spec=importlib.util.spec_from_file_location('resume',ROOT/'tools/resume_deepseek_queue_after_reconciliation_v055_r1.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output=args.output.resolve();args.output.parent.mkdir(parents=True,exist_ok=False)
    fixture=Path(tempfile.mkdtemp(prefix='v055-resume-control-',dir='/tmp'));dbpath=fixture/'ledger.sqlite3'
    db=sqlite3.connect(dbpath)
    db.execute('CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
    db.execute('CREATE TABLE requests(request_id TEXT PRIMARY KEY,status TEXT,reserved_nanoyuan INTEGER,settled_nanoyuan INTEGER)')
    db.execute('CREATE TABLE budget_adjustments(adjustment_id TEXT PRIMARY KEY,request_id TEXT UNIQUE,amount_nanoyuan INTEGER NOT NULL,reason TEXT,created_utc TEXT,evidence_json TEXT)')
    for name in ('response_observations','provider_protocol_events','budget_policy_migrations'):
        db.execute('CREATE TABLE '+name+'(fixture_id TEXT PRIMARY KEY)')
    db.execute('INSERT INTO metadata VALUES (?,?)',('policy',json.dumps({'cap_nanoyuan':m.CAP,'max_concurrency':64},sort_keys=True)))
    db.execute('INSERT INTO requests VALUES (?,?,?,?)',('fixture-only','uncertain',2113536000,None))
    db.execute('INSERT INTO budget_adjustments VALUES (?,?,?,?,?,?)',('hold','fixture-only',3129344000,'fixture','fixture','{}'))
    db.commit();db.close()
    ledger=m.readonly_ledger_fingerprint(dbpath);assert ledger['committed_nanoyuan']==5242880000
    checks=['readonly_total_includes_supplemental_holds_and_fingerprints_all_financial_tables']
    state={'status':'budget_closed_with_pending','dispatch_stopped':True,'stop_reason':'shared_budget_or_accounting_gate',
        'ended_utc':'fixture','rows':[{'slot':{'slot_id':str(i)},'generation':{'status':'pending'},'scores':[]} for i in range(3000)],
        'preparation':{},'exceptions':[{'original_failure':'retained'}]}
    state['rows'][0]['generation']={'status':'technical_unknown','job':{'original':'retained'}}
    auth={'version':m.VERSION,'queue_resume_authorized':True,'ledger_integrity_restored':True,
        'all_financial_components_accounted':True,'ledger_after':deepcopy(ledger),
        'committed_nanoyuan':ledger['committed_nanoyuan'],'can_admit_minimum_request':True}
    resumed=m.resume_state(state,auth,ledger,{'authorization':'fixture'},{'quiescence':'fixture'})
    assert resumed['rows']==state['rows'] and resumed['exceptions']==state['exceptions']
    assert resumed['dispatch_stopped'] is False and resumed['status']=='running' and 'ended_utc' not in resumed
    assert state['dispatch_stopped'] is True
    checks.append('one_time_transition_only_reopens_unentered_inventory_rows_and_exceptions_unchanged')
    def rejected(s=state,a=auth,l=ledger):
        try:m.resume_state(s,a,l,{'authorization':'fixture'},{'quiescence':'fixture'})
        except ValueError:return
        raise AssertionError('Unsafe transition accepted')
    bad=deepcopy(auth);bad['queue_resume_authorized']=False;rejected(a=bad)
    bad=deepcopy(ledger);bad['halted']='still_halted';rejected(l=bad)
    bad=deepcopy(ledger);bad['all_tables_sha256']='stale';rejected(l=bad)
    bad=deepcopy(auth);bad['committed_nanoyuan']=2113536000;rejected(a=bad)
    checks.append('no_approval_halt_stale_fingerprint_and_omitted_adjustment_each_rejected')
    for change in ('generation','score','preparation','pending_evidence'):
        bad=deepcopy(state)
        if change=='generation':bad['rows'][1]['generation']['status']='running'
        elif change=='score':bad['rows'][1]['scores']=[{'status':'pending'}]
        elif change=='preparation':bad['preparation']={'fixture':{'worker':{'status':'running'}}}
        else:bad['rows'][1]['generation']['job']={'prior':'entry'}
        rejected(s=bad)
    checks.append('existing_generation_scoring_preparation_or_prior_entry_blocks_adoption')
    duplicate=deepcopy(state);duplicate['accounting_queue_recoveries']=resumed['accounting_queue_recoveries'];rejected(s=duplicate)
    checks.append('same_authorization_cannot_adopt_twice')
    receipt=m.write_new(args.output,{'version':'v055-queue-resume-state-cpu-control-r1','passed':True,'checks':checks,
        'source':m.reference(m.__file__),'control':m.reference(__file__),'fixture':str(fixture),
        'live_ledger_writes':0,'live_queue_writes':0,'services_started':0,'model_calls':0})
    print(json.dumps(receipt))

if __name__=='__main__':main()
