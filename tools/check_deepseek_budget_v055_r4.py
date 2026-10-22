"""Meaningful CPU controls for migration preservation, withholding and hard gates."""
from __future__ import annotations
import argparse
from copy import deepcopy
from contextlib import ExitStack
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

import migrate_deepseek_budget_v055_r4 as migration
from proworksim import software_benchmark_deepseek_api_v055 as old
from proworksim import software_benchmark_deepseek_api_v055_r4 as new
from proworksim.software_benchmark_candidates_v054 import write_new


def body(identity, *, output=1, model=old.MODEL):
    return {'id':identity,'model':model,'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'fixture'}}],
            'usage':{'prompt_tokens':10,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10,
                     'completion_tokens':output,'total_tokens':10+output}}


class Transport:
    def __init__(self,response):self.response=response;self.calls=0;self.last_request=None
    def request(self,method,path,payload):
        assert method=='POST' and path=='/chat/completions'
        self.calls+=1;self.last_request=deepcopy(payload)
        return deepcopy(self.response)


def reserve(ledger,identity):
    return ledger.reserve(request_id=identity,slot_id=identity,condition='MATCH-nonthinking',usage_id='agent',
                          request_sha256='fixture',max_output_tokens=2048,prompt_upper_bound=20)


def copy_database(source,target):
    with sqlite3.connect(source) as src,sqlite3.connect(target) as dst:src.backup(dst)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    checks=[]
    with tempfile.TemporaryDirectory(prefix='v055-budget-r4-control-') as temporary, ExitStack() as isolation:
        root=Path(temporary).resolve();path=root/'ledger.sqlite3'
        real_connect=sqlite3.connect
        opened_databases=[]

        def fixture_connect(database,*positional,**keywords):
            value=str(database)
            plain=value[5:].split('?',1)[0] if value.startswith('file:') else value
            actual=Path(plain).resolve()
            if not actual.is_relative_to(root):
                raise AssertionError('CPU control refused SQLite I/O outside its isolated fixture root')
            opened_databases.append(str(actual))
            return real_connect(database,*positional,**keywords)

        isolation.enter_context(patch.object(sqlite3,'connect',side_effect=fixture_connect))
        # Prove the independent boundary rejects the real path before any SQLite
        # open, even if a future default-argument regression is introduced.
        try:sqlite3.connect(migration.LEDGER)
        except AssertionError:pass
        else:raise AssertionError('Fixture guard did not reject the real ledger path')
        old.BudgetLedger(path)
        with sqlite3.connect(path) as db:
            rows=[('fixture-'+str(i),'fixture-'+str(i),'MATCH-nonthinking','agent','settled','fixture',2113536000,
                   1000000,2048,20,'2026-10-22T01:00:00+00:00') for i in range(22745)]
            db.executemany('''INSERT INTO requests(request_id,slot_id,condition,usage_id,status,request_sha256,
                reserved_nanoyuan,settled_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',rows)
            for identity in sorted(migration.UNKNOWN_IDS):
                db.execute('''INSERT INTO requests(request_id,slot_id,condition,usage_id,status,request_sha256,
                    reserved_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc,failure_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)''',(identity,identity,'PROJECT-thinking','agent','uncertain','fixture',
                        2113536000,2048,20,'2026-10-22T01:00:00+00:00',old._json({'reason':migration.HALT})))
            db.execute("INSERT INTO metadata VALUES ('halted',?)",(migration.HALT,))
        queue=root/'queue';queue.mkdir()
        audit=root/'audit.json';audit.write_text(json.dumps({'version':'v055-readonly-provider-output-bound-halt-audit-r1','ledger_mutations':0}))
        with patch.object(migration,'LEDGER',path),patch.object(migration,'QUEUE',queue), \
                patch.object(migration,'require_drained',return_value={'fixture':True,'workers':0}):
            plan=migration.freeze(root/'migration/plan.json',audit)
            receipt_ref=migration.apply(Path(plan['path']),plan['sha256'])
        receipt=json.loads(Path(receipt_ref['path']).read_text())
        assert receipt['ledger_before']['requests_sha256']==receipt['ledger_after']['requests_sha256']
        assert receipt['ledger_after']['request_count']==22747
        assert receipt['ledger_after']['adjustments_nanoyuan']==6258688000
        assert receipt['ledger_after']['halted'] is None
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT previous_halt FROM budget_policy_migrations').fetchone()[0]==migration.HALT
        checks.append('actual_migration_preserves_all_22747_fixture_request_rows_adds_two_holds_and_retains_halt_history')
        try:old.BudgetLedger(path)
        except ValueError:pass
        else:raise AssertionError('Old policy can reopen migrated ledger')
        checks.append('old_client_policy_refuses_migrated_ledger')
        ledger=new.BudgetLedger(path)
        assert ledger.snapshot()['historical_supplemental_holds_cny']==6.258688
        transport=Transport(body('normal'))
        client=new.DeepSeekClient(ledger_path=path,api_key='fixture',allowed_tool_names=[],transport=transport)
        request={'model':old.MODEL,'messages':[{'role':'user','content':'neutral fixture'}],
                 'max_tokens':2048,'thinking':{'type':'disabled'},'stream':False}
        response=client.complete(request,request_id='normal',slot_id='normal',condition='MATCH-nonthinking',prompt_upper_bound=20)
        assert response['id']=='normal' and transport.last_request['max_tokens']==2048
        row=ledger.request_status('normal');assert row['reserved_nanoyuan']==5242880000 and row['max_output_tokens']==2048
        checks.append('normal_request_payload_unchanged_and_cash_reserved_at_absolute_model_bound')
        transport.response=body('over-request',output=2049)
        try:client.complete(request,request_id='over-request',slot_id='over-request',condition='MATCH-nonthinking',prompt_upper_bound=20)
        except old.APIUncertainFailure:pass
        else:raise AssertionError('Scientifically overlong response reached the caller')
        row=ledger.request_status('over-request')
        assert row['status']=='settled' and json.loads(row['usage_json'])['completion_tokens']==2049
        assert row['response_id']=='over-request' and row['response_sha256']
        assert ledger.snapshot()['halted'] is None
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT scope FROM provider_protocol_events WHERE request_id='over-request'").fetchone()[0]=='task'
            assert db.execute("SELECT usage_json FROM response_observations WHERE request_id='over-request'").fetchone()[0]
        transport.response=body('after-over-request')
        client.complete(request,request_id='after-over-request',slot_id='after-over-request',condition='MATCH-nonthinking')
        calls=transport.calls
        try:client.complete(request,request_id='over-request',slot_id='over-request',condition='MATCH-nonthinking')
        except old.BudgetStopped:pass
        else:raise AssertionError('Replay was allowed')
        assert transport.calls==calls
        checks.append('output_over_request_settles_fee_retains_usage_withholds_response_without_stopping_other_tasks_or_replay')
        cases={'above_absolute':body('above_absolute',output=new.MAX_OUTPUT_TOKENS+1),
               'wrong_model':body('wrong_model',model='unapproved-model'),
               'bad_usage':body('bad_usage'),
               'duplicate_id':body('normal'),
               'cash_bound':body('cash_bound')}
        cases['bad_usage']['usage']['total_tokens']=999
        for name,value in cases.items():
            clone=root/(name+'.sqlite3');copy_database(path,clone);target=new.BudgetLedger(clone);reserve(target,name)
            if name=='cash_bound':
                with sqlite3.connect(clone) as db:db.execute('UPDATE requests SET reserved_nanoyuan=1 WHERE request_id=?',(name,))
            try:target.settle(name,value)
            except old.BudgetStopped:pass
            else:raise AssertionError(name+' did not retain shared hard halt')
            assert target.snapshot()['halted'] and target.request_status(name)['status']=='uncertain'
            with sqlite3.connect(clone) as db:
                assert db.execute('SELECT response_sha256 FROM response_observations WHERE request_id=?',(name,)).fetchone()[0]
        checks.append('absolute_output_invalid_usage_wrong_model_duplicate_identity_and_cash_violation_hard_halt_with_metadata')
        for i in range(64):reserve(ledger,'concurrency-'+str(i))
        try:reserve(ledger,'concurrency-65')
        except old.ConcurrencyBusy:pass
        else:raise AssertionError('Shared API concurrency exceeded 64')
        for i in range(64):ledger.uncertain('concurrency-'+str(i),{'reason':'CPU_fixture_unknown'})
        with sqlite3.connect(path) as db:
            current=ledger.snapshot()['committed_upper_cny']
            amount=new.CAP_NANOYUAN-round(current*new.NANOYUAN)-new.ABSOLUTE_RESERVATION_NANOYUAN+1
            db.execute('INSERT INTO budget_adjustments VALUES (?,?,?,?,?,?)',('fixture-cap','fixture-cap',amount,'fixture',old._now(),'{}'))
        try:reserve(ledger,'cash-cap-refused')
        except old.BudgetStopped:pass
        else:raise AssertionError('Supplemental adjustments escaped the 2000CNY gate')
        checks.append('64_inflight_limit_and_2000CNY_cap_include_supplemental_holds')
        assert new.BudgetStopped is old.BudgetStopped and new.APIUncertainFailure is old.APIUncertainFailure
        assert new.DeepSeekClient.complete is old.DeepSeekClient.complete
        checks.append('native_project_condenser_share_unchanged_client_complete_and_exception_identities')
        assert opened_databases and all(Path(item).is_relative_to(root) for item in opened_databases)
        checks.append('all_SQLite_connections_explicitly_confined_to_fixture_root_real_ledger_open_refused')
    value={'version':new.VERSION,'passed':True,'checks':checks,'actual_experiment_ledger_mutations':0,
           'real_API_calls':0,'model_calls':0,'GPU_loads':0,'formal_claims':0,'services_modified':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);print(json.dumps(write_new(args.output,value)))


if __name__=='__main__':main()
