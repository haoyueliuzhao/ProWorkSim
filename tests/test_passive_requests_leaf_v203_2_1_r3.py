"""Leaf-only identity, shared-cash admission and gate/phase resource controls."""
import sqlite3
from types import SimpleNamespace
import pytest
from proworksim import software_benchmark_scope_passive_leaf_v203_2_1_r3 as scope
from proworksim import software_benchmark_episode_passive_leaf_v203_2_1_r3 as episode
from proworksim import software_benchmark_alignment_contract_v203_2_1 as alignment
from proworksim import software_benchmark_sdk_bundle_v203_2_1 as bundle
from proworksim import software_benchmark_host_api_passive_leaf_v203_2_1_r3 as host
from proworksim.software_benchmark_candidates_v054 import reference,write_new


def test_single_original_identity_real_episode_and_disjoint_envelopes():
 plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)));row=plan['rows'][0]
 old=next(r for r in scope.parent.load(reference(scope.parent.PLAN_FILE))['rows'] if r['instance_id']==scope.TASK)
 assert {k:v for k,v in row.items() if k not in {'configuration','slot_index'}}=={k:v for k,v in old.items() if k not in {'configuration','slot_index'}}
 assert row['slot_index']==2032307 and row['generation_token_upper_bound']==5_000_000
 assert scope.LEDGER_FILE==scope.parent.LEDGER_FILE and scope.BUDGET_BASELINE_FILE==scope.parent.BUDGET_BASELINE_FILE
 assert scope.MAX_GENERATIONS==scope.MAX_GRADERS==scope.MAX_STARTUPS==1 and scope.MAX_HTTP_CONCURRENCY==8
 assert set(map(int,scope.cpu_set('actor').split(',')))==set(map(int,scope.cpu_set('coordinator').split(',')))=={64,65,66,67}
 assert scope.cpu_set('controller')=='68,69' and scope.cpu_set('grader')=='64,65,66,67'
 value=episode.build_episode(scope=scope,guard=lambda *a,**k:{'status':'approved','execution_alignment_version':alignment.VERSION,'source_index':{'CPU_only':True},'plan':reference(scope.PLAN_FILE)})
 assert value._run.__globals__['BATCH']==scope.BATCH_ROOT and value._run.__globals__['runtime'] is bundle
 value._row_and_config(row,False)
 assert value.wait_capacity.__globals__['capacity'] is value.capacity


def test_other_paid_requests_allowed_but_own_request_or_admission_rejected(tmp_path,monkeypatch):
 plan=scope.load(reference(scope.PLAN_FILE));slot=plan['rows'][0]['slot_id'];db_path=tmp_path/'shared.sqlite'
 with sqlite3.connect(db_path) as db:
  db.execute('CREATE TABLE requests(slot_id TEXT)');db.execute('CREATE TABLE team_admissions(slot_id TEXT,state TEXT)')
  db.execute('INSERT INTO requests VALUES(?)',('another_already_paid_original_task',))
 monkeypatch.setattr(scope,'LEDGER_FILE',db_path)
 monkeypatch.setattr(scope,'gate_status',lambda:{'passed':True})
 out=scope.validate_first_model_admission();assert out['own_provider_requests']==0 and out['existing_other_requests']==1
 with sqlite3.connect(db_path) as db:db.execute('INSERT INTO team_admissions VALUES(?,?)',(slot,'started'))
 with pytest.raises(PermissionError):scope.validate_first_model_admission()
 with sqlite3.connect(db_path) as db:
  db.execute('DELETE FROM team_admissions');db.execute('INSERT INTO requests VALUES(?)',(slot,))
 with pytest.raises(PermissionError):scope.validate_first_model_admission()
 monkeypatch.setattr(scope,'gate_status',lambda:{'passed':False})
 with pytest.raises(PermissionError,match='cannot bypass'):scope.validate_first_model_admission()


def test_parent_gate_and_ca_both_required_and_scoring_waits_for_pair_cleanup(tmp_path,monkeypatch):
 gate=tmp_path/'engineering-gate.json';monkeypatch.setattr(scope,'PARENT_GATE_FILE',gate)
 assert scope.gate_status()['passed'] is False
 gate.write_text('{"passed":false}')
 assert scope.gate_status()['reason']=='parent_engineering_failed'
 value={'passed':True,'predeclared_indices':[2032200,2032201],'scores_used_for_gate':False,'shared_host_usage_complete':True}
 gate.write_text(__import__('json').dumps(value))
 assert scope.gate_status()['passed'] is True  # real completed CA receipts, no rescoring
 ca=tmp_path/'ca.json';ca.write_text('{"qualification_passed":false}')
 monkeypatch.setattr(scope,'CA_RESULT_FILE',ca)
 assert scope.gate_status()['passed'] is False
 monkeypatch.setattr(scope,'physical_capacity',lambda:{'passed':True,'CPU_fixture':True})
 assert scope._budget([],6,48*scope.GIB,4*scope.GIB)['reserved_memory_bytes_after']==56*scope.GIB
 assert scope._budget([],4,16*scope.GIB,0)['reserved_memory_bytes_after']<=56*scope.GIB
 with pytest.raises(scope.ResourceBusy):scope._budget([{'spec':{'role':'actor'}}],4,16*scope.GIB,0)
 with pytest.raises(scope.ResourceBusy):scope._budget([{'spec':{'role':'score'}}],6,48*scope.GIB,4*scope.GIB)


def test_actual_host_initializer_uses_only_leaf_request_guard_and_shared_HTTP_limit(tmp_path,monkeypatch):
 db_path=tmp_path/'shared.sqlite'
 with sqlite3.connect(db_path) as db:
  db.execute('CREATE TABLE requests(slot_id TEXT)');db.execute('CREATE TABLE team_admissions(slot_id TEXT,state TEXT)')
  db.execute('INSERT INTO requests VALUES(?)',('another_paid_original_task',))
 schema=tmp_path/'schemas.json';schema.write_text('{"schemas":{"REVIEW2":{}}}')
 monkeypatch.setattr(scope,'LEDGER_FILE',db_path)
 monkeypatch.setattr(scope,'gate_status',lambda:{'passed':True})
 monkeypatch.setattr(scope,'require_allowed',lambda *a,**k:{'CPU_fixture':True})
 monkeypatch.setattr(host,'_paths',lambda:(scope,schema,None))
 monkeypatch.setattr(host,'OfficialDeepSeekCounter',lambda *a,**k:object())
 fake=SimpleNamespace(POLICY={'max_concurrency':8},load_api_key=lambda path:'CPU-only-not-a-real-key')
 monkeypatch.setattr(host,'api_for',lambda group:fake)
 seen={}
 def construct(**kwargs):
  seen.update(kwargs);return SimpleNamespace(clients={},http_slots=object())
 monkeypatch.setattr(host,'runtime_for',construct)
 runtime=host.DeepSeekRuntime().initialize_for_run()
 assert list(runtime.rows)==[scope.load(reference(scope.PLAN_FILE))['rows'][0]['slot_id']]
 assert seen['max_concurrency']==8 and seen['api_key']=='CPU-only-not-a-real-key'
