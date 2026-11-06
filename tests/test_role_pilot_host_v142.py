"""Actual new host route and bounded probe with scripted, never-network transports."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_api_v142 as cash
from proworksim import software_benchmark_host_api_v142 as host
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_role_baseline_runtime_v141 import prepare_schema_inventory
from proworksim.storage import digest, json_bytes


def route_fixture(tmp_path, monkeypatch, group, *, uncertain=False):
    panel_ref = reference(host.scope.PANEL_FILE)
    panel = json.loads(Path(panel_ref['path']).read_text())
    row = next(r for r in panel['rows'] if r['organization_id'] == group)
    # Exact generated real world/private SDK declarations, not handwritten tools.
    schemas = prepare_schema_inventory()['schemas'][group]
    api = cash.group_api(group, tmp_path/'pilot.sqlite', max_concurrency=16, panel_ref=panel_ref)
    monkeypatch.setattr(host, 'api_for', lambda requested: api if requested == group else None)
    calls, guards, counter_wires = [], [], []

    class ScriptTransport:
        def request(self, method, path, payload):
            calls.append((method, path, copy.deepcopy(payload)))
            assert (method, path) == ('POST', '/chat/completions')
            if uncertain:
                raise TimeoutError('scripted response outcome unknown; no real HTTP')
            return {'id': 'cpu-'+group+'-'+str(len(calls)), 'model': 'deepseek-flash',
                'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'CPU'}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13,
                          'prompt_cache_hit_tokens': 4, 'prompt_cache_miss_tokens': 6}}

    client = api.DeepSeekClient(api_key='synthetic-CPU-only', allowed_tool_names={
        t['function']['name'] for tools in schemas.values() for t in tools}, transport=ScriptTransport())

    def counter(wire):
        counter_wires.append(copy.deepcopy(wire))
        return {'prompt_tokens': 10, 'request_sha256': digest(json_bytes(wire))}

    monkeypatch.setattr(host.scope, 'require_allowed', lambda operation, **identity: guards.append((operation, identity)))
    runtime = SimpleNamespace(clients={group: SimpleNamespace(fork_for_episode=lambda: client)},
        schemas={group: schemas}, counter=counter, http_slots=host.threading.BoundedSemaphore(16))
    route = host.HostTeamTransport(runtime, row, tmp_path/'route')

    def payload(member, ordinal=1, purpose='agent'):
        wire = {'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': 'Synthetic CPU'}],
            'stream': False, 'thinking': {'type': 'disabled'}, 'temperature': 1.0, 'top_p': 1.0,
            'max_tokens': 20, 'tool_choice': 'auto' if purpose == 'agent' else 'none',
            'user_id': api.slot_user_id(row['slot_id']+':'+member, row['condition_id'])}
        if purpose == 'agent':
            wire['tools'] = copy.deepcopy(schemas[member])
        return {'wire': wire, 'member_id': member, 'team_slot_id': row['slot_id'], 'slot_id': row['slot_id'],
            'condition': row['condition_id'], 'usage_id': purpose, 'prompt_upper_bound': 10,
            'request_id': row['slot_id']+f':{member}:{ordinal:04d}'}
    return route, client, api, row, payload, calls, guards, counter_wires


@pytest.mark.parametrize('group', ['S1', 'FREE2', 'REVIEW2'])
def test_actual_dynamic_inventory_member_request_and_receipt_binding(tmp_path, monkeypatch, group):
    route, client, _, row, payload, calls, guards, counter_wires = route_fixture(tmp_path, monkeypatch, group)
    members = row['fixed_members']
    assert len(members) == (1 if group == 'S1' else 2)
    for member in members:
        value = payload(member)
        count_payload = {k: value[k] for k in ('wire', 'member_id', 'team_slot_id')}
        counted = route.post('/tokenize', count_payload)
        assert counted['request_sha256'] == digest(json_bytes(value['wire']))
        returned = route.post('/chat/completions', value)
        assert returned['usage']['total_tokens'] == 13
        assert counter_wires[-2:] == [value['wire'], value['wire']]
    # One genuine condenser purpose through the same member/shared-team route.
    route.post('/chat/completions', payload(members[-1], 2, 'condenser'))
    with client.ledger._connect() as db:
        records = [dict(r) for r in db.execute('SELECT r.request_id,r.slot_id,r.usage_id,r.usage_json, '
            'm.group_id,m.member_id FROM requests r JOIN member_requests m USING(request_id) ORDER BY r.request_id')]
    assert len(records) == len(calls) == len(members)+1
    assert {r['group_id'] for r in records} == {group}
    assert {r['member_id'] for r in records} == set(members)
    assert {r['usage_id'] for r in records} == {'agent', 'condenser'}
    assert all(r['slot_id'] == row['slot_id'] and r['request_id'].startswith(row['slot_id']+':'+r['member_id']+':') for r in records)
    assert all(json.loads(r['usage_json'])['prompt_cache_hit_tokens'] == 4 for r in records)
    assert all(g == ('v142.api.request', {'slot_id': row['slot_id'], 'instance_id': row['instance_id']}) for g in guards)


def test_wrong_member_schema_search_and_count_rejected_before_transport(tmp_path, monkeypatch):
    route, _, _, _, payload, calls, _, _ = route_fixture(tmp_path, monkeypatch, 'REVIEW2')
    good = payload('member_001')
    foreign = copy.deepcopy(good)
    foreign['member_id'] = 'member_003'
    altered = copy.deepcopy(good)
    altered['wire']['tools'][0]['function']['description'] += ' unauthorized edit'
    search = copy.deepcopy(good)
    search['wire']['tools'] = [{'type': 'web_search'}]
    wrong_count = {**good, 'prompt_upper_bound': 11}
    other_member_cache = {**good, 'member_id': 'member_002'}
    wrong_purpose = {**good, 'usage_id': 'condenser'}
    for bad in (foreign, altered, search, wrong_count, other_member_cache, wrong_purpose):
        with pytest.raises(ValueError):
            route.post('/chat/completions', bad)
    with pytest.raises(ValueError, match='No search'):
        route.post('/search', {})
    assert calls == []


def test_uncertain_actual_host_dispatch_is_not_automatically_repeated(tmp_path, monkeypatch):
    route, client, api, _, payload, calls, _, _ = route_fixture(tmp_path, monkeypatch, 'FREE2', uncertain=True)
    with pytest.raises(api.APIUncertainFailure):
        route.post('/chat/completions', payload('member_002'))
    assert len(calls) == 1
    with client.ledger._connect() as db:
        row = dict(db.execute('SELECT status,settled_nanoyuan,reserved_nanoyuan FROM requests').fetchone())
    assert row['status'] == 'uncertain' and row['settled_nanoyuan'] is None and row['reserved_nanoyuan'] > 0
    # The HTTP permit is returned even when the one sent request is unknown.
    assert route.runtime.http_slots.acquire(blocking=False)
    route.runtime.http_slots.release()


def probe_module():
    path = Path(__file__).parents[1]/'tools/check_httpbin_direct_v142.py'
    spec = importlib.util.spec_from_file_location('probe_v142_CPU', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_direct_probe_scope_guard_precedes_dns_and_evidence_creation(tmp_path, monkeypatch):
    probe = probe_module()
    observed = []
    def denied(operation):
        observed.append(operation)
        raise PermissionError('Synthetic unapproved scope')
    monkeypatch.setattr(host.scope, 'require_allowed', denied)
    monkeypatch.setattr(probe.socket, 'getaddrinfo', lambda *_: pytest.fail('Guard must precede DNS'))
    monkeypatch.setattr(probe, 'INTENT', tmp_path/'intent.json')
    with pytest.raises(PermissionError):
        probe.run()
    assert observed == ['v142.prepare'] and not probe.INTENT.exists()


@pytest.mark.parametrize('strict_tls', [True, False])
def test_bounded_direct_probe_with_scripted_sockets_preserves_tls_and_scope(tmp_path, monkeypatch, strict_tls):
    probe = probe_module()
    guards, connects, names = [], [], []
    monkeypatch.setattr(host.scope, 'require_allowed', lambda operation: guards.append(operation))
    for key in ('INTENT', 'OUTPUT', 'RESOLUTION'):
        monkeypatch.setattr(probe, key, tmp_path/(key.lower()+'.json'))
    monkeypatch.setattr(probe.os, 'getuid', lambda: 1000)
    # These are CPU test addresses only. Every socket is a local Python object.
    monkeypatch.setattr(probe.socket, 'getaddrinfo', lambda *_: [(None,None,None,None,(ip,443))
        for ip in ('1.1.1.1', '8.8.8.8', '9.9.9.9')])
    monkeypatch.setattr(probe.signal, 'signal', lambda *_: None)
    monkeypatch.setattr(probe.signal, 'alarm', lambda *_: None)

    class Socket:
        def settimeout(self, *_):
            pass
        def connect(self, address):
            assert guards == ['v142.prepare']
            connects.append(address)
        def sendall(self, data):
            assert data.startswith(b'GET /get ')
        def makefile(self, *args, **kwargs):
            return io.BytesIO(json.dumps({'headers': {}, 'args': {}, 'url': 'https://httpbin.org/get'}).encode())
        def close(self):
            pass

    class Context:
        verify_mode = probe.ssl.CERT_REQUIRED if strict_tls else probe.ssl.CERT_NONE
        check_hostname = strict_tls
        def wrap_socket(self, sock, *, server_hostname):
            names.append(server_hostname)
            return sock

    class Connection:
        def __init__(self, hostname, port, timeout):
            assert hostname == 'httpbin.org' and port in {80,443} and timeout == 8
            self.sock = None
        def request(self, method, path, headers):
            assert (method,path,headers['Host']) == ('GET','/get','httpbin.org')
            self.sock.sendall(b'GET /get HTTP/1.1\r\nHost: httpbin.org\r\n\r\n')
        def getresponse(self):
            return SimpleNamespace(status=200, read=lambda maximum: self.sock.makefile('rb').read(maximum))
        def close(self):
            self.sock.close()

    monkeypatch.setattr(probe.socket, 'socket', lambda *_: Socket())
    monkeypatch.setattr(probe.ssl, 'create_default_context', Context)
    monkeypatch.setattr(probe.http.client, 'HTTPConnection', Connection)
    value = probe.run()
    evidence = json.loads(probe.OUTPUT.read_text())
    assert len(connects) == probe.MAX_CONNECTIONS == 4
    assert {ip for ip, _ in connects} == {'1.1.1.1', '8.8.8.8'}
    assert all(port in {80,443} for _,port in connects)
    assert 0 < evidence['application_bytes'] <= probe.MAX_APPLICATION_BYTES == 65536
    assert evidence['scope'] == reference(host.scope.__file__)
    assert evidence['proxy_used'] is False and evidence['automatic_retry'] is False
    assert value['passed'] is strict_tls
    assert names == ['httpbin.org']*2 if strict_tls else not names
    if strict_tls:
        resolution = json.loads(probe.RESOLUTION.read_text())
        assert resolution['scope'] == reference(host.scope.__file__) and resolution['hostname'] == 'httpbin.org'
    else:
        assert not probe.RESOLUTION.exists()
    budget = probe.ApplicationBudget()
    budget.consume(65536)
    with pytest.raises(RuntimeError):
        budget.consume(1)
