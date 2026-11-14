"""Necessary controls for paid-parent conservation and the real admission queue."""
from concurrent.futures import Future
import importlib.util,json,sqlite3
from types import SimpleNamespace
from proworksim import software_benchmark_scope_v203_2_3_r3 as scope
from proworksim.software_benchmark_candidates_v054 import reference


def coordinator(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('recovery_runner',scope.ROOT/'tools/run_role_context_pilot_v203_2_3_r3.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    plan=scope.load(reference(scope.PLAN_FILE))
    control=runner.DrainControl(tmp_path/'control.json',batch_root=tmp_path,groups=runner.GROUP_IDS,maximum=2)
    admission=runner.ConditionAdmission(runner.GROUP_IDS,control=control,maximum=2,maximum_startups=2,pressure_probe=lambda:{'passed':True})
    runtime=SimpleNamespace(for_group=lambda g:SimpleNamespace(settled_route_witnesses=lambda:{'PROJECT':'CPU'}))
    c=runner.Coordinator(runtime=runtime,implementation=None,grading=None,memory=None,admission=admission,
        plan=plan,qualifications={t:{'passed':True} for t in plan['environments']},output=tmp_path/'output',
        cash_status=lambda g:{'state':'ready','can_start_generation':True})
    monkeypatch.setattr(runner.scope,'require_runtime_gate',lambda:None)
    admitted=[]
    class Executor:
        def submit(self,fn,row):admitted.append(row);return Future()
    return c,Executor(),admitted


def finish_cpu(c,slot,tmp_path,*,ordinary_failure=False):
    future,row=next((f,r) for f,r in c.generation.items() if r['slot_id']==slot)
    del c.generation[future];c.admission.ready(row);c.admission.leave(row)
    quiet=tmp_path/(str(row['slot_index'])+'-quiet.json');quiet.write_text(json.dumps({'quiescent':True,'all_owned_objects_removed':True}))
    result=tmp_path/(str(row['slot_index'])+'-result.json');result.write_text(json.dumps({'slot_id':slot,'configuration':row['configuration'],
        'quiescence':reference(quiet),'status':'technical_unknown' if ordinary_failure else 'closed','failure_scope':'local'}))
    c.finished[slot]={'row':row,'result':reference(result),'status':'technical_unknown' if ordinary_failure else 'closed'}
    c.usage_records[slot]={'record':reference(result),'complete':True,'called':True}


def test_actual_admission_stops_third_slot_until_two_closed_rounds(tmp_path,monkeypatch):
    c,executor,admitted=coordinator(tmp_path,monkeypatch)
    c._admit(executor)
    assert {r['slot_id'] for r in admitted}==set(c.engineering_slots)
    first,second=c.engineering_slots
    finish_cpu(c,first,tmp_path,ordinary_failure=True)
    c._admit(executor)
    assert len(admitted)==2 and not c.engineering_gate_open
    finish_cpu(c,second,tmp_path)
    c._admit(executor)
    assert c.engineering_gate_open and len(admitted)>2
    assert all(r['slot_id'] not in c.engineering_slots for r in admitted[2:])


def test_original_sdk_failure_drains_new_work_without_cancelling_started(tmp_path,monkeypatch):
    c,executor,admitted=coordinator(tmp_path,monkeypatch);c._admit(executor)
    old=scope.PARENT_RUN_ROOT/'episodes/2032300/result.json'
    assert c.inspect_shared_system_fault({'row':admitted[0],'result':reference(old)})
    c._admit(executor)
    assert len(admitted)==2 and c.stop_new_generation.is_set() and not c.entered_stop.is_set()
    assert not c.engineering_gate_open


def test_parent_is_halted_and_only_remaining_allowance_is_active():
    handoff=scope.load(reference(scope.HANDOFF_FILE))
    assert handoff['parent_settled_nanoyuan']==1_246_862_000
    assert handoff['child_cap_nanoyuan']==128_753_138_000
    assert sum(handoff[k] for k in ('parent_settled_nanoyuan','parent_uncertain_reserved_nanoyuan','child_cap_nanoyuan'))==130_000_000_000
    with sqlite3.connect((scope.PREVIOUS_BATCH_ROOT/'ledgers/pilot.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
        assert db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
        assert db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]==48
    with sqlite3.connect(scope.LEDGER_FILE.resolve().as_uri()+'?mode=ro',uri=True) as db:
        policy=json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
        assert policy['cap_nanoyuan']==128_753_138_000 and db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]==0
    plan=scope.load(reference(scope.PLAN_FILE))
    assert len(plan['rows'])==12
    assert all(r['slot_id']!=r['original_slot_id'] for r in plan['rows'])
    assert sum(r['attempt_kind']=='independent_retest_after_technical_failure' for r in plan['rows'])==9
    assert sum(r['attempt_kind']=='first_paid_attempt_after_environment_preparation' for r in plan['rows'])==3
