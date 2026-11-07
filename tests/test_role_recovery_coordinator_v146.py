"""Small threaded recovery queue controls; no API, containers or services."""
from __future__ import annotations

from collections import Counter
import importlib.util
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim.software_benchmark_group_admission_v132 import DrainControl, FairAdmission
from proworksim.software_benchmark_host_memory_v132 import HostMemoryGate


def module():
    path = Path(__file__).parents[1]/'tools/run_role_recovery_v146.py'
    spec = importlib.util.spec_from_file_location('role_recovery146_cpu', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def fixture(tmp_path, monkeypatch, *, cash_after_entry=False, second_unknown=False):
    mod = module()
    first = [{'slot_id':f'cpu:{group}:{n}:attempt1','slot_index':i*2+n,
              'organization_id':group,'group_id':group,'instance_id':'fixture__cpu-'+str(n),
              'seed':141, 'recovery_round':1,'original_slot_id':f'old:{group}:{n}',
              'original_generation_result':{'CPU_original':True},'retry_of_slot_id':None}
             for i,group in enumerate(mod.GROUP_IDS) for n in range(2)]
    second = [{**row,'slot_id':row['slot_id'].replace('attempt1','attempt2'),
               'slot_index':row['slot_index']+4,'recovery_round':2,
               'retry_of_slot_id':row['slot_id']} for row in first]
    plan = {'rows':first+second}
    write_new(tmp_path/'plan.json', plan)
    monkeypatch.setattr(mod.scope, 'PLAN_FILE', tmp_path/'plan.json')
    monkeypatch.setattr(mod.scope, 'BATCH_ROOT', tmp_path)
    monkeypatch.setattr(mod.scope, 'API_ROOT', tmp_path/'output')
    monkeypatch.setattr(mod.scope, 'MAX_GENERATIONS', 2)
    monkeypatch.setattr(mod.scope, 'MAX_GRADERS', 2)
    consumed, generated, scored, first_completed = set(), [], [], set()
    monkeypatch.setattr(mod.scope, 'never_consumed', lambda row:row['slot_id'] not in consumed)
    control = DrainControl(tmp_path/'drain.json', batch_root=tmp_path, groups=mod.GROUP_IDS, maximum=2)
    admission = FairAdmission(mod.GROUP_IDS, control=control, maximum=2, maximum_startups=2)
    memory = HostMemoryGate(maximum=2)
    score_active = threading.Event()
    overlap = threading.Event()
    network_slot = first[0]['slot_id']
    score_retry_slot = first[2]['slot_id']
    normal_failed_slot = first[1]['slot_id']

    def usage(row):
        return {'calls':[{'call_id':row['slot_id']+':request','purpose':'agent',
                         'prompt_tokens':20,'completion_tokens':3,'reasoning_tokens':None,
                         'prompt_cache_hit_tokens':10,'prompt_cache_miss_tokens':10,
                         'accounted_cost_cny':'0.01','member_id':'member_001'}],
                'unresolved_calls':[], 'usage_capture_complete':True}

    runtime = SimpleNamespace(for_group=lambda group:SimpleNamespace(
        settled_route_witnesses=lambda:{'PROJECT':'CPU'}, logical_resident=lambda:{},
        transport_factory=lambda *args:{}, usage_for_slot=usage))

    def episode(row, resident, *, stop_event, api_transport_factory):
        assert not stop_event.is_set()
        if row['recovery_round'] == 2:
            assert first_completed == {r['slot_id'] for r in first}
        consumed.add(row['slot_id'])
        api_transport_factory(row, tmp_path)
        generated.append(row['slot_id'])
        time.sleep(.08)
        if score_active.is_set():
            overlap.set()
        quiet = write_new(tmp_path/f"quiet-{row['slot_index']}.json", {
            'quiescent':True,'all_owned_objects_removed':True,'cleanup_errors':[],
            'create_result_unknown':False})
        unknown = row['slot_id'] == network_slot or (
            second_unknown and row.get('retry_of_slot_id') == network_slot)
        ref = write_new(tmp_path/f"result-{row['slot_index']}.json", {
            'status':'technical_unknown' if unknown else 'closed',
            'slot_id':row['slot_id'],'quiescence':quiet})
        if row['recovery_round'] == 1:
            first_completed.add(row['slot_id'])
        return ref

    def request_for(result_ref, *, endpoint, retry=False):
        result = mod.scope.load(result_ref)
        row = next(r for r in plan['rows'] if r['slot_id'] == result['slot_id'])
        prefix = 'score-' if endpoint == 'code' else 'delivery-score-'
        key = prefix+('retry-' if retry else '')+str(row['slot_index'])
        folder = tmp_path/'grading'/key
        folder.mkdir(parents=True)
        return write_new(folder/'request.json', {'resource_key':key,'directory':str(folder),
            'slot_id':row['slot_id'],'instance_id':row['instance_id'],
            'generation_result':result_ref,'candidate_lock':{'sha256':'a'*64}})

    def retry_request(ref):
        request = mod.scope.load(ref)
        return request_for(request['generation_result'], endpoint='code', retry=True)

    def score(ref, *, stop_event):
        request = mod.scope.load(ref)
        assert not stop_event.is_set()
        score_active.set()
        time.sleep(.3)
        retry = '-retry-' in request['resource_key']
        unknown = request['slot_id'] == score_retry_slot and not retry
        identity = write_new(Path(request['directory'])/'identity.json', {
            'request':ref,'candidate_lock':request['candidate_lock'],'endpoint':'code'})
        write_new(Path(request['directory'])/'receipt.json', {
            'resource_key':request['resource_key'],'slot_id':request['slot_id'],
            'identity':identity,'status':'technical_unknown' if unknown else 'official_report',
            'resolved':None if unknown else request['slot_id'] != normal_failed_slot})
        scored.append((request['slot_id'],retry))
        return {'status':'process_exited','returncode':0}

    grading = SimpleNamespace(prepare_score=request_for, prepare_score_retry=retry_request,
        run_request=score, trustworthy_cleanup=lambda ref:True,
        delivery_disposition=lambda *args:{'status':'same_tree_official_result_reused',
                                          'resolved':True,'scoring_request':None})
    def money(group):
        return {'state':'cash_exhausted' if cash_after_entry and consumed else 'ready',
                'can_start_generation':not (cash_after_entry and consumed),'cap_CNY':'99.1863482'}
    def classifier(row):
        return {'classification':'exhausted_transient_http','retry_eligible':True,'requests':[]}
    coordinator = mod.Coordinator(runtime=runtime, implementation=SimpleNamespace(run_episode=episode),
        grading=grading,memory=memory,admission=admission,plan=plan,
        qualifications={row['instance_id']:{'passed':True} for row in first},
        output=tmp_path/'output', cash_status=money, recovery_classifier=classifier)
    return coordinator,memory,generated,scored,overlap,network_slot,normal_failed_slot,score_retry_slot


def test_transport_failure_isolated_then_independent_retry_and_async_same_lock_rescore(tmp_path, monkeypatch):
    c,memory,generated,scored,overlap,network,normal_failed,score_retry = fixture(tmp_path,monkeypatch)
    try:
        summary = c.execute()
    finally:
        memory.close()
    assert len(generated) == len(set(generated)) == 5
    assert generated[-1] == network.replace('attempt1','attempt2')
    assert normal_failed.replace('attempt1','attempt2') not in generated
    assert not c.stop_new_generation.is_set() and overlap.is_set()
    counts = Counter(slot for slot,_ in scored)
    assert counts[score_retry] == 2 and counts[normal_failed] == 1
    assert len(c.score_attempts) == 5
    assert c.completed_scores[score_retry+':code']['official_endpoint']['resolved'] is True
    assert summary['planned_original_cases'] == 4 and summary['reserved_attempt_ceiling'] == 8
    rows = c.task_records()
    assert next(r for r in rows if r['slot_id'] == network)['generation_status'] == 'technical_unknown'
    assert sum(r['generation_status'] == 'not_activated' for r in rows) == 3
    assert all(r['first_planned_attempt'] is False for r in rows)


def test_second_transport_failure_remains_queued_without_third_generation(tmp_path, monkeypatch):
    c,memory,generated,_,_,network,_,_ = fixture(tmp_path,monkeypatch,second_unknown=True)
    try:
        c.execute()
    finally:
        memory.close()
    assert len(generated) == 5
    item = c.recovery_queue[network.replace('attempt1','attempt2')]
    assert item['state'] == 'retry_limit_reached'
    assert not c.stop_new_generation.is_set()


def test_cash_boundary_keeps_unused_identities_without_blocking_entered_work(tmp_path, monkeypatch):
    c,memory,generated,_,_,_,_,_ = fixture(tmp_path,monkeypatch,cash_after_entry=True)
    try:
        c.execute()
    finally:
        memory.close()
    assert 0 < len(generated) < 4
    assert not c.entered_stop.is_set()
    assert any(item['state'] == 'waiting_cash' for item in c.recovery_queue.values())
    assert len(c.task_records()) == 8


def test_manager_clean_file_cache_does_not_mask_real_anonymous_pressure(tmp_path):
    mod = module()
    gib = 1024**3
    for name,value in {'memory.current':29*gib,'memory.high':30*gib,'memory.max':32*gib,
                       'memory.swap.current':0,'memory.swap.max':0}.items():
        (tmp_path/name).write_text(str(value))
    (tmp_path/'memory.pressure').write_text('some avg10=0.00 avg60=0.00 total=0\nfull avg10=0.00 avg60=0.00 total=0\n')
    (tmp_path/'memory.events').write_text('oom 0\noom_kill 0\nmax 0\n')
    def stat(anon,file,dirty=0):
        (tmp_path/'memory.stat').write_text(
            f'anon {anon}\nfile {file}\nshmem 0\nfile_dirty {dirty}\nfile_writeback 0\nunevictable 0\n')
    stat(4*gib,25*gib)
    assert mod.manager_pressure_working_set(tmp_path)['passed']
    stat(29*gib,0)
    assert not mod.manager_pressure_working_set(tmp_path)['passed']
    stat(4*gib,25*gib,25*gib)
    assert not mod.manager_pressure_working_set(tmp_path)['passed']
    (tmp_path/'memory.swap.max').write_text('1')
    with pytest.raises(PermissionError):
        mod.manager_pressure_working_set(tmp_path)
