"""Small actual threaded queues, fake world/provider/scorer; no Docker or API."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim.software_benchmark_group_admission_v132 import DrainControl, FairAdmission
from proworksim.software_benchmark_host_memory_v132 import HostMemoryGate


def module():
    spec = importlib.util.spec_from_file_location('pilot_v142_test', Path(__file__).parents[1]/'tools/run_role_pilot_v142.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def fixture(tmp_path, monkeypatch, *, fail_slot=None, unknown_usage=False, bad_cleanup=False, drain_cash=False):
    mod = module()
    rows = [{'slot_id': f'cpu:{g}:{n}', 'slot_index': i*2+n, 'organization_id': g,
             'group_id': g, 'instance_id': 'fixture__cpu-'+str(n), 'seed': 141}
            for i,g in enumerate(mod.GROUP_IDS) for n in range(2)]
    plan = {'rows': rows}
    write_new(tmp_path/'plan.json', plan)
    monkeypatch.setattr(mod.scope, 'PLAN_FILE', tmp_path/'plan.json')
    monkeypatch.setattr(mod.scope, 'BATCH_ROOT', tmp_path)
    consumed, generated, scores = set(), [], []
    monkeypatch.setattr(mod.scope, 'never_consumed', lambda row: row['slot_id'] not in consumed)
    control = DrainControl(tmp_path/'drain.json', batch_root=tmp_path, groups=mod.GROUP_IDS, maximum=3)
    admission = FairAdmission(mod.GROUP_IDS, control=control, maximum=3, maximum_startups=2)
    memory = HostMemoryGate(maximum=2)
    lock = threading.Lock()
    score_started, following_generation = threading.Event(), threading.Event()

    def usages(row):
        call = {'call_id': row['slot_id']+':request', 'purpose': 'agent', 'prompt_tokens': 20,
                'completion_tokens': 3, 'reasoning_tokens': None, 'prompt_cache_hit_tokens': 10,
                'prompt_cache_miss_tokens': 10, 'accounted_cost_cny': '0.01', 'member_id': 'member_001'}
        if unknown_usage and row['slot_index'] == 0:
            return {'calls': [], 'unresolved_calls': [{'call_id': call['call_id'], 'reserved_tokens': 42}],
                    'usage_capture_complete': False}
        return {'calls': [call], 'unresolved_calls': [], 'usage_capture_complete': True}

    runtime = SimpleNamespace(for_group=lambda g: SimpleNamespace(
        settled_route_witnesses=lambda: {'PROJECT': 'CPU'}, logical_resident=lambda: {},
        transport_factory=lambda *args: {}, usage_for_slot=usages))

    def episode(row, resident, *, stop_event, api_transport_factory):
        assert not stop_event.is_set()
        consumed.add(row['slot_id'])
        api_transport_factory(row, tmp_path)
        with lock:
            generated.append(row['slot_id'])
        if score_started.is_set():
            following_generation.set()
        time.sleep(.025)
        if score_started.is_set():
            following_generation.set()
        quiet = write_new(tmp_path/f"quiet-{row['slot_index']}.json", {
            'quiescent': not bad_cleanup, 'all_owned_objects_removed': not bad_cleanup,
            'cleanup_errors': [], 'create_result_unknown': False})
        return write_new(tmp_path/f"result-{row['slot_index']}.json", {
            'status': 'technical_unknown' if row['slot_id'] == fail_slot else 'closed',
            'slot_id': row['slot_id'], 'quiescence': quiet})

    def prepare_score(result_ref, *, endpoint):
        result = mod.scope.load(result_ref)
        row = next(r for r in rows if r['slot_id'] == result['slot_id'])
        key = ('score-' if endpoint == 'code' else 'delivery-score-')+str(row['slot_index'])
        folder = tmp_path/'grading'/key
        folder.mkdir(parents=True)
        return write_new(folder/'request.json', {'resource_key': key, 'directory': str(folder),
            'slot_id': row['slot_id'], 'instance_id': row['instance_id'], 'candidate_lock': {'sha256': 'a'*64}})

    def score(ref, *, stop_event):
        request = mod.scope.load(ref)
        assert not stop_event.is_set()
        score_started.set()
        # While scoring waits, independently admitted generation can progress.
        time.sleep(.4)
        identity = write_new(Path(request['directory'])/'identity.json', {
            'request': ref, 'candidate_lock': request['candidate_lock'], 'endpoint': 'code'})
        write_new(Path(request['directory'])/'receipt.json', {
            'resource_key': request['resource_key'], 'slot_id': request['slot_id'],
            'identity': identity, 'status': 'official_report', 'resolved': True})
        scores.append(request['slot_id'])
        return {'status': 'process_exited', 'returncode': 0}

    grading = SimpleNamespace(prepare_score=prepare_score, run_request=score, trustworthy_cleanup=lambda _:True,
        delivery_disposition=lambda *_: {'status': 'same_tree_official_result_reused', 'resolved': True,
                                        'scoring_request': None})
    def money(_):
        return {'state': 'cash_exhausted' if drain_cash and generated else 'ready',
                'can_start_generation': not (drain_cash and generated), 'cap_CNY': '400.00'}
    c = mod.Coordinator(runtime=runtime, implementation=SimpleNamespace(run_episode=episode),
        grading=grading, memory=memory, admission=admission, plan=plan,
        qualifications={r['instance_id']: {'passed': True} for r in rows},
        output=tmp_path/'output', cash_status=money)
    return c, memory, generated, scores, following_generation


def test_local_unknown_preserves_queue_denominator_and_async_scoring(tmp_path, monkeypatch):
    c, memory, generated, scores, overlap = fixture(tmp_path, monkeypatch, fail_slot='cpu:FREE2:0', unknown_usage=True)
    try:
        result = c.execute()
    finally:
        memory.close()
    assert len(generated) == 6 and len(scores) == 5
    assert overlap.is_set(), 'Slow scoring must overlap later generation'
    assert not c.stop_new_generation.is_set()
    rows = json.loads((tmp_path/'output/task-outcomes.json').read_text())['rows']
    assert len(rows) == 6
    unknown = next(r for r in rows if r['slot_id'] == 'cpu:FREE2:0')
    assert unknown['generation_status'] == 'technical_unknown' and unknown['resolved'] is None
    assert result['actual_token_consumption']['S1']['mean_tokens_all_planned'] is None
    assert result['actual_token_consumption']['REVIEW2']['mean_tokens_all_planned'] == 23
    assert all(r['resolved'] is True for r in rows if r['slot_id'] != 'cpu:FREE2:0')


def test_shared_cash_drains_admissions_keeps_entered_and_scores(tmp_path, monkeypatch):
    c, memory, generated, scores, _ = fixture(tmp_path, monkeypatch, drain_cash=True)
    try:
        c.execute()
    finally:
        memory.close()
    assert 0 < len(generated) < 6 and len(scores) == len(generated)
    assert not c.entered_stop.is_set()
    assert len(c.task_records()) == 6
    assert any(r['generation_status'] == 'not_started' for r in c.task_records())


def test_cleanup_uncertainty_drains_common_dispatch_and_no_replay(tmp_path, monkeypatch):
    c, memory, generated, scores, _ = fixture(tmp_path, monkeypatch, bad_cleanup=True)
    try:
        c.execute()
    finally:
        memory.close()
    assert c.stop_new_generation.is_set() and c.stop_new_scoring.is_set()
    assert len(generated) == len(set(generated)) < 6
    assert scores == [] and not c.entered_stop.is_set()


def test_official_receipt_cannot_reuse_foreign_candidate(tmp_path, monkeypatch):
    mod = module()
    request = write_new(tmp_path/'request.json', {'resource_key': 'score-0', 'directory': str(tmp_path),
        'slot_id': 'cpu', 'candidate_lock': {'sha256': 'a'*64}})
    identity = write_new(tmp_path/'identity.json', {'request': request, 'candidate_lock': {'sha256': 'b'*64}, 'endpoint': 'code'})
    write_new(tmp_path/'receipt.json', {'resource_key': 'score-0', 'slot_id': 'cpu',
        'identity': identity, 'status': 'official_report', 'resolved': True})
    with pytest.raises(PermissionError):
        mod.official_endpoint(request, {'returncode': 0}, cleanup_proven=True)
