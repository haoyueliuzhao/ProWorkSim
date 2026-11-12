import json
import sqlite3
import pytest
from proworksim import software_benchmark_deepseek_api_v203_2_1 as api
from proworksim.software_benchmark_candidates_v054 import reference


def setup(tmp_path):
    rows=[{'slot_id':f'v203.2.1:fixture__repo-{i}:REVIEW2:1','organization_id':'REVIEW2',
        'group_id':'REVIEW2','condition_id':'REVIEW2','fixed_members':['member_001','member_002']} for i in range(12)]
    panel=tmp_path/'panel.json';panel.write_text(json.dumps({'rows':rows}))
    ledger=tmp_path/'pilot.sqlite';authority=tmp_path/'authority.json'
    authority.write_text(json.dumps({'version':api.AUTHORITY_VERSION,'ledger_path':str(ledger),
        'cap_nanoyuan':150_000_000_000,'panel_sha256':reference(panel)['sha256'],'approved':True}))
    view=api.group_api('REVIEW2',ledger,max_concurrency=8,panel_ref=reference(panel),cash_authority_ref=reference(authority))
    return rows,view,view.BudgetLedger()


def request(row,ordinal=1,member='member_001',purpose='agent'):
    return {'logical_id':row['slot_id']+f':{member}:{ordinal:04d}','attempt_index':1,
        'slot_id':row['slot_id'],'member_id':member,'condition':'REVIEW2','usage_id':purpose,
        'request_sha256':'a'*64,'prompt_upper_bound':1000,'max_output_tokens':100}


def test_full_team_reservation_preserves_cash_and_started_work(tmp_path):
    rows,view,ledger=setup(tmp_path)
    for row in rows[:3]:ledger.cash_admission(row['slot_id'])
    with pytest.raises(api.PreDispatchBudgetStopped):ledger.cash_admission(rows[3]['slot_id'])
    r=ledger.reserve(**request(rows[0]))
    assert ledger.cash_admission()['remaining_team_holds_nanoyuan']==(15_000_000-1100)*8000
    # Request can execute from an already reserved team even though another
    # whole team cannot be admitted. No calls or actual costs are generated.
    assert r.endswith(':http-1')
    ledger.cash_admission(rows[1]['slot_id'],close=True)
    ledger.cash_admission(rows[3]['slot_id'])
    assert ledger.cash_admission()['settled_or_reserved_nanoyuan']+ledger.cash_admission()['remaining_team_holds_nanoyuan']<=view.CAP_NANOYUAN


def test_exact_identity_and_shared_token_cap_remain(tmp_path):
    rows,_,ledger=setup(tmp_path)
    with pytest.raises(api.PreDispatchBudgetStopped):ledger.reserve(**request(rows[0]))
    ledger.cash_admission(rows[0]['slot_id']);rid=ledger.reserve(**request(rows[0]))
    with pytest.raises(api.PreDispatchBudgetStopped):ledger.reserve(**request(rows[0]))
    with pytest.raises(ValueError):ledger.reserve(**request(rows[0],purpose='compressor'))
    with sqlite3.connect(ledger.path) as db:
        db.execute("UPDATE requests SET status='settled',settled_nanoyuan=999,usage_json=? WHERE request_id=?",
            (json.dumps({'total_tokens':4_999_999}),rid))
    with pytest.raises(api.PreDispatchBudgetStopped,match='shared_team'):
        ledger.reserve(**request(rows[0],ordinal=2,member='member_002',purpose='condenser'))


def test_observer_capture_failure_never_replaces_transport_result():
    transport=api.DirectHTTPS('cpu-placeholder',timeout_seconds=1)
    def fail(*args):raise OSError('injected observer-only failure')
    transport.physical_capture=fail
    transport.capture_raw('HTTP_REQUEST',b'{"cpu":true}')
    assert transport.capture_faults==1


def test_unentered_hold_is_returned_and_paid_hold_cannot_be_erased(tmp_path):
    rows,_,ledger=setup(tmp_path)
    for row in rows[:3]:ledger.cash_admission(row['slot_id'])
    ledger.release_unentered(rows[0]['slot_id'])
    ledger.cash_admission(rows[0]['slot_id'])
    ledger.reserve(**request(rows[0]))
    with pytest.raises(ValueError):ledger.release_unentered(rows[0]['slot_id'])
    with pytest.raises(ValueError):ledger.cash_admission(rows[0]['slot_id'],close=True)


def test_physical_capture_on_fifo_thread_preserves_exact_HTTP_bytes(tmp_path,monkeypatch):
    import base64,threading
    from types import SimpleNamespace
    from proworksim.software_benchmark_host_api_v203_2_1 import HostTeamTransport
    from proworksim.software_observer_journal_v203_2_1 import ObserverJournal
    body=b'\n\n{"id":"cpu", "usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}'
    seen={}
    class Response:
        status=200;length=0;chunked=False
        def __init__(self):self.sent=False
        def read1(self,n):
            if self.sent:return b''
            self.sent=True;return body
        def close(self):pass
    class Connection:
        def __init__(self,*a,**kw):self.sock=SimpleNamespace(settimeout=lambda *_:None)
        def connect(self):pass
        def request(self,*a,**kw):seen['wire_bytes']=kw['body']
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(api.http.client,'HTTPSConnection',Connection)
    transport=api.DirectHTTPS('cpu-placeholder',timeout_seconds=1)
    permits=object();client=SimpleNamespace(transport=transport,http_slots=permits)
    runtime=SimpleNamespace(clients={'REVIEW2':SimpleNamespace(fork_for_episode=lambda:client)},http_slots=permits)
    route=HostTeamTransport(runtime,{'slot_id':'cpu','condition_id':'REVIEW2','group_id':'REVIEW2'},tmp_path)
    transport.capture_context={'physical_id':'cpu:http-1','logical_id':'cpu','slot_id':'cpu','member_id':'member_001'}
    wire={'model':'cpu','messages':[]}
    def run():seen['response']=transport.request('POST','/chat/completions',wire)
    t=threading.Thread(target=run);t.start();t.join(3);assert not t.is_alive()
    assert seen['response']==json.loads(body) and not getattr(transport,'capture_faults',0)
    with ObserverJournal(route.physical_journal_path) as journal:records=list(journal.records())
    assert len(records)==2
    assert base64.b64decode(records[0]['payload']['raw_base64'])==seen['wire_bytes']==api.canonical(wire).encode()
    assert base64.b64decode(records[1]['payload']['raw_base64'])==body
