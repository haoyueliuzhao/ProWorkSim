"""Independent temporary cash stores and source-bound team/member routing."""
from __future__ import annotations

import copy
import json
import socket
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_api_v131 as money
from proworksim import software_benchmark_host_api_v131 as host
from proworksim.software_benchmark_alignment_contract_v131 import GROUP_IDS, condition
from proworksim.storage import digest, json_bytes


def row(group, number=1):
    spec = condition(group)
    return {'slot_id': f"v131:fixture__repo-{number}:{spec['condition_id']}:{number}",
        'instance_id': f'fixture__repo-{number}', 'condition_id': spec['condition_id'],
        'organization_id': group, 'fixed_members': spec['fixed_members']}


def reserve(ledger, task, *, member='member_001', sequence=1, prompt=10, output=20):
    return ledger.reserve(request_id=task['slot_id']+f':{member}:{sequence:04d}',
        slot_id=task['slot_id'], condition=task['condition_id'], usage_id='agent',
        request_sha256='a'*64, max_output_tokens=output, prompt_upper_bound=prompt,
        member_id=member)


@pytest.fixture
def stores(tmp_path, monkeypatch):
    def deny(*_args, **_kwargs):
        raise AssertionError('A monetary CPU control cannot open the network or API key')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    monkeypatch.setattr(money.original, 'load_api_key', deny)
    paths = {group: tmp_path/(group+'.sqlite') for group in GROUP_IDS}
    monkeypatch.setattr(host.scope, 'LEDGER_FILES', paths)
    host.api_for.cache_clear()
    apis = {group: host.api_for(group) for group in GROUP_IDS}
    ledgers = {group: api.BudgetLedger(paths[group], max_concurrency=host.scope.MAX_GENERATIONS)
               for group, api in apis.items()}
    yield apis, ledgers
    host.api_for.cache_clear()


def test_five_100_caps_request_reservation_and_no_borrow(stores):
    apis, ledgers = stores
    task = row('CHIEF')
    first = reserve(ledgers['CHIEF'], task, prompt=100, output=20)
    assert first['reserved_nanoyuan'] == 100*2000+20*8000
    assert money.MAX_PROFILE_RESERVATION_NANOYUAN == 458752000
    assert first['reserved_nanoyuan'] < money.MAX_PROFILE_RESERVATION_NANOYUAN
    before = {group: ledger.snapshot()['remaining_cny'] for group, ledger in ledgers.items()}
    with ledgers['CHIEF']._transaction() as db:
        db.execute("UPDATE requests SET status='settled',settled_nanoyuan=?,usage_json=?",
                   (money.CAP_NANOYUAN-1, json.dumps({'total_tokens': 1})))
    with pytest.raises(apis['CHIEF'].BudgetStopped, match='group_cash'):
        reserve(ledgers['CHIEF'], row('CHIEF', 2))
    assert host.budget_status('CHIEF')['state'] == 'cash_exhausted'
    for group in GROUP_IDS[1:]:
        assert ledgers[group].snapshot()['remaining_cny'] == before[group] == 100
        assert host.budget_status(group)['state'] == 'ready'
    assert all(api.CAP_NANOYUAN == 100*money.NANOYUAN for api in apis.values())


def test_bounded_unknown_holds_only_its_team_and_does_not_stop_the_group(stores):
    apis, ledgers = stores
    task = row('REVIEW')
    ref = reserve(ledgers['REVIEW'], task)
    ledgers['REVIEW'].uncertain(ref['request_id'], {'reason': 'CPU_fixture_network_unknown',
        'error_type': 'TimeoutError', 'shared_system_failure': False})
    status = host.budget_status('REVIEW')
    assert status['state'] == 'ready' and status['can_start_generation']
    assert float(status['uncertain_reserved_CNY']) > 0
    with pytest.raises(apis['REVIEW'].BudgetStopped, match='team_has_unclosed_or_unknown'):
        reserve(ledgers['REVIEW'], task, member='member_002')
    reserve(ledgers['REVIEW'], row('REVIEW', 2))
    assert host.budget_status('CHIEF')['remaining_CNY'] == '100.0'


def test_token_pool_is_shared_across_members_before_dispatch(stores):
    apis, ledgers = stores
    task = row('MATRIX')
    ledger = ledgers['MATRIX']
    with ledger._transaction() as db:
        for index in range(50):
            prompt = 90000 if index < 49 else 70000
            usage = {'prompt_tokens': prompt, 'completion_tokens': 10000, 'total_tokens': prompt+10000}
            amount = prompt*2000+10000*8000
            request_id = task['slot_id']+f':member_001:{index+1:04d}'
            db.execute('INSERT INTO requests (request_id,slot_id,condition,usage_id,status,request_sha256,'
                'reserved_nanoyuan,settled_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc,usage_json) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (request_id,task['slot_id'],task['condition_id'],'agent','settled','a'*64,amount,amount,
                 10000,prompt,'CPU',json.dumps(usage)))
            db.execute('INSERT INTO member_requests VALUES (?,?,?)', (request_id,'MATRIX','member_001'))
    with pytest.raises(apis['MATRIX'].BudgetStopped, match='shared_team_limit'):
        reserve(ledger, task, member='member_002', prompt=10000, output=15000)
    assert ledger.snapshot()['attempts'] == 50
    reserve(ledger, task, member='member_002', prompt=1000, output=1000)
    assert ledger.snapshot()['attempts'] == 51


def test_host_rejects_foreign_member_schema_and_preserves_member_cash_identity(stores, tmp_path, monkeypatch):
    apis, _ledgers = stores
    task = row('REVIEW')
    api = apis['REVIEW']
    schemas = {member: [{'type':'function','function':{'name':'read_file',
        'description': member, 'parameters': {'type':'object','properties':{},'additionalProperties':False}}}]
        for member in task['fixed_members']}

    class FakeTransport:
        calls = 0
        def request(self, method, path, payload):
            assert (method,path) == ('POST','/chat/completions')
            self.calls += 1
            assert payload['user_id'] == api.slot_user_id(task['slot_id']+':member_001', task['condition_id'])
            return {'id':'cpu-response-'+str(self.calls),'model':'deepseek-flash',
                'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'CPU'}}],
                'usage':{'prompt_tokens':10,'completion_tokens':3,'total_tokens':13,
                         'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10}}
    transport = FakeTransport()
    client = api.DeepSeekClient(api_key='CPU fixture', allowed_tool_names={'read_file'},
        max_concurrency=host.scope.MAX_GENERATIONS, transport=transport)
    runtime = SimpleNamespace(clients={'REVIEW':SimpleNamespace(fork_for_episode=lambda: client)},
        schemas={'REVIEW':schemas}, counter=lambda wire: {'prompt_tokens':10,'request_sha256':digest(json_bytes(wire))},
        http_slots=host.threading.BoundedSemaphore(1))
    route = host.HostTeamTransport(runtime, task, tmp_path/'route')
    monkeypatch.setattr(host.scope, 'require_allowed', lambda *args, **kwargs: {})
    wire = {'model':'deepseek-flash','messages':[{'role':'user','content':'CPU'}],
        'stream':False,'thinking':{'type':'disabled'},'temperature':1.0,'top_p':1.0,
        'max_tokens':20,'tool_choice':'auto','tools':schemas['member_001'],
        'user_id':api.slot_user_id(task['slot_id']+':member_001',task['condition_id'])}
    payload = {'wire':wire,'member_id':'member_001','team_slot_id':task['slot_id'],
        'slot_id':task['slot_id'],'condition':task['condition_id'],'usage_id':'agent',
        'request_id':task['slot_id']+':member_001:0001','prompt_upper_bound':10}
    changed = copy.deepcopy(payload)
    changed['wire']['tools'] = schemas['member_002']
    with pytest.raises(ValueError, match='another member tool schema'):
        route.post('/chat/completions', changed)
    changed = {**payload, 'member_id':'member_002'}
    with pytest.raises(ValueError, match='cache identity'):
        route.post('/chat/completions', changed)
    assert transport.calls == 0
    route.post('/chat/completions', payload)
    assert transport.calls == 1
    with client.ledger._connect() as db:
        record = dict(db.execute('SELECT r.slot_id,m.member_id FROM requests r JOIN member_requests m USING(request_id)').fetchone())
    assert record == {'slot_id':task['slot_id'],'member_id':'member_001'}
    # A definitely unsent reservation wait releases the global HTTP gate.
    original_complete = client.complete
    busy, returned = host.threading.Event(), {}
    reservations = []
    def wait_once(request, **metadata):
        reservations.append(metadata['request_id'])
        if len(reservations) == 1:
            busy.set()
            raise api.PreDispatchConcurrencyBusy('CPU fixture: cash reserved by another in-flight request')
        return original_complete(request, **metadata)
    monkeypatch.setattr(client, 'complete', wait_once)
    next_payload = {**payload, 'request_id': task['slot_id']+':member_001:0002'}
    thread = host.threading.Thread(target=lambda: returned.update(body=route.post('/chat/completions', next_payload)))
    thread.start()
    assert busy.wait(2)
    assert runtime.http_slots.acquire(timeout=1)
    runtime.http_slots.release()
    thread.join(3)
    assert not thread.is_alive() and returned['body']['id'] == 'cpu-response-2'
    assert reservations == [next_payload['request_id'], next_payload['request_id']]
    assert transport.calls == 2  # Only one additional fake send, not two.
