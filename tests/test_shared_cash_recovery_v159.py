"""CPU-only recovery guard: one original account; never re-enter consumed slots."""
from contextlib import contextmanager
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_api_v157 as original
from proworksim import software_benchmark_host_api_v159 as host
from proworksim.software_benchmark_api_recovery_v159 import audit,validate_recovery_plan
from proworksim.software_benchmark_candidates_v054 import reference


def fixture(tmp_path):
    rows=[]
    for n in range(24):
        for g in original.GROUP_IDS:
            rows.append({'slot_id':f'v157:repo__task-{n}:REVIEW2_{g}:seed{n}',
                'instance_id':f'repo__task-{n}','slot_index':15700+len(rows),'group_id':g,
                'condition':g,'condition_id':g,'organization_id':'REVIEW2','seed':n,
                'configuration':{'path':'original-fixed-config','sha256':'a'*64},
                'fixed_members':['member_001','member_002'],'wave':1 if n<12 else 2})
    plan={'rows':rows};panel=tmp_path/'panel.json';panel.write_text(json.dumps(plan))
    ledger=tmp_path/'original.sqlite';authority=tmp_path/'authority.json'
    authority.write_text(json.dumps({'version':original.AUTHORITY_VERSION,'ledger_path':str(ledger),
        'cap_nanoyuan':500_000_000_000,'panel_sha256':reference(panel)['sha256'],'approved':True}))
    api=original.group_api('C0',ledger,max_concurrency=16,panel_ref=reference(panel),cash_authority_ref=reference(authority))
    book=api.BudgetLedger()
    row=rows[0]
    book.reserve(logical_id=row['slot_id']+':member_001:0001',attempt_index=1,slot_id=row['slot_id'],
        member_id='member_001',condition='C0',usage_id='agent',request_sha256='a'*64,
        prompt_upper_bound=100,max_output_tokens=100)
    return plan,book


def test_readonly_snapshot_retains_inflight_and_blocks_handover(tmp_path):
    plan,book=fixture(tmp_path)
    before=book.path.read_bytes();value=audit(book.path,plan)
    assert value['used_teams']==1 and value['unused_teams']==71
    assert value['totals']['inflight_requests']==1 and value['totals']['held_or_unknown_nanoyuan']==1_000_000
    assert value['new_cash_allowance_nanoyuan']==0 and book.path.read_bytes()==before
    recovery={'rows':plan['rows'][1:],'admitted_original_slots':value['admitted_original_slots'],
        'used_original_slots':value['used_original_slots']}
    with pytest.raises(ValueError,match='drain'):validate_recovery_plan(recovery,plan,value)


def test_settled_and_unknown_funds_stay_in_original_account_and_identity_is_frozen(tmp_path):
    plan,book=fixture(tmp_path);request=plan['rows'][0]['slot_id']+':member_001:0001:http-1'
    book.failed(request,original.TransportFailure('transport_exception',phase='body'))
    value=audit(book.path,plan)
    recovery={'rows':deepcopy(plan['rows'][1:]),'admitted_original_slots':value['admitted_original_slots'],
        'used_original_slots':value['used_original_slots']}
    assert validate_recovery_plan(recovery,plan,value)
    assert value['totals']['remaining_peak_upper_nanoyuan']==500_000_000_000-1_000_000
    assert value['totals']['uncertain_requests']==1
    recovery['rows'][0]['seed']+=1
    with pytest.raises(ValueError,match='byte-for-byte'):validate_recovery_plan(recovery,plan,value)


def test_transport_factory_cannot_reacquire_consumed_or_duplicate_team(tmp_path,monkeypatch):
    plan,book=fixture(tmp_path);runtime=host.DeepSeekRuntime()
    runtime.rows={r['slot_id']:r for r in plan['rows']}
    runtime.admitted_original_slots=frozenset(runtime.rows)
    runtime.used_original_slots=frozenset()
    runtime._route_claimed=set()
    @contextmanager
    def read(group):
        with sqlite3.connect(book.path) as db:yield db
    monkeypatch.setattr(host.original,'ledger_read',read)
    monkeypatch.setattr(host,'HostTeamTransport',lambda runtime,row,out:SimpleNamespace(slot_id=row['slot_id']))
    with pytest.raises(ValueError,match='already dispatched'):
        runtime.transport_factory(plan['rows'][0],tmp_path/'used')
    row=plan['rows'][1]
    assert runtime.transport_factory(row,tmp_path/'unused').slot_id==row['slot_id']
    with pytest.raises(ValueError,match='second model transport'):
        runtime.transport_factory(row,tmp_path/'duplicate')
    assert book.snapshot()['remaining_nanoyuan']==500_000_000_000-1_000_000


def test_exact_old_live_coexistence_does_not_open_unused_or_other_slots(tmp_path):
    plan,book=fixture(tmp_path);value=audit(book.path,plan)
    recovery={'rows':plan['rows'][1:],'admitted_original_slots':value['admitted_original_slots'],
        'used_original_slots':value['used_original_slots']}
    proof={'passed':True,'old_new_generation_admission_closed':True,'active_old_slots':value['used_original_slots']}
    assert validate_recovery_plan(recovery,plan,value,coexistence=proof)
    with pytest.raises(ValueError,match='coexistence'):
        validate_recovery_plan(recovery,plan,value,coexistence={**proof,'active_old_slots':[plan['rows'][1]['slot_id']]})
    with pytest.raises(ValueError,match='coexistence'):
        validate_recovery_plan(recovery,plan,value,coexistence={**proof,'old_new_generation_admission_closed':False})
    assert book.snapshot()['unknown_tokens_upper']==200
