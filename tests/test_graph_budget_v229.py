import pytest
from proworksim.software_graph_budget_v229 import WindowLedger,AdmissionStopped


def test_atomic_reallocation_and_limit(tmp_path):
    a={'scope':'independent','ledger':str(tmp_path/'ledger.sqlite'),'stage_cap_CNY':120,'account_cap_CNY':120}
    m=WindowLedger.create_independent(a);k='v229:case0';s=k+':PREFIX'
    m.reserve_case(k);m.admit(s,5_000_000)
    with m.db() as c:c.execute("insert into requests values('x',?,'settled',5000000000,1000000,null,null)",(s,))
    m.close(s)
    with pytest.raises(AdmissionStopped):m.reserve_case('v229:case1')
    with pytest.raises(ValueError):m.split(k,('KEEP','CHANGE'),0)
    assert m.split(k,('KEEP','CHANGE'),1_000_000)==4_000_000
    for arm in ('KEEP','CHANGE'):
        slot=k+':'+arm;m.admit(slot,4_000_000);m.close(slot)
    m.reserve_case('v229:case1');m.split('v229:case1',(),None)


def test_window_driver_shares_draft_fee_and_checks_both_scores(tmp_path,monkeypatch):
    from pathlib import Path
    from proworksim.storage import atomic_write,json_bytes
    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'tools'))
    import run_graph_learning_window_v229 as driver
    monkeypatch.setattr(driver,'OUT',tmp_path)
    meter=WindowLedger.create_independent({'scope':'independent','ledger':str(tmp_path/'l.sqlite'),'stage_cap_CNY':80,'account_cap_CNY':80})
    prefix=2_000_000;fee=2_000;rest=5_000_000-prefix-fee
    def fake(script,args,dest,filename):
        dest.mkdir();arm=dest.name
        if filename=='receipt.json':
            result={'status':'official_report','resolved':True}
        elif arm=='PREFIX':
            slot='v229:task-00:PREFIX';meter.admit(slot,5_000_000)
            with meter.db() as c:c.execute("insert into requests values('shared',?,'settled',5000000000,?,null,null)",(slot,prefix+fee))
            meter.close(slot)
            atomic_write(dest/'candidate-bank.json',json_bytes({'decision':{'q':{'KEEP':.5,'CHANGE':.5}},'osa_tokens':fee}))
            result={'status':'point_ready','prefix_tokens':prefix,'osa_tokens':fee}
        else:
            slot='v229:task-00:'+arm;meter.admit(slot,rest)
            atomic_write(dest/'common-state.json',json_bytes({'checkpoint':'same'}))
            atomic_write(dest/'assigned-graph.json',json_bytes({'decision':{'option':'K' if arm=='KEEP' else 'D1'},'changed':arm=='CHANGE'}))
            meter.close(slot);result={'status':'closed','logical_tokens':prefix+fee}
        atomic_write(dest/filename,json_bytes(result))
        return result
    monkeypatch.setattr(driver,'invoke',fake)
    r=driver.run_case({'index':0,'instance_id':'fixture','phase':'dev1','scorer_script':'fixture','source_index':0},tmp_path/'policy',meter)
    assert r['status']=='paired' and set(r['arms'])=={'KEEP','CHANGE'} and all(x['legal_correct'] for x in r['arms'].values())
    with meter.db() as c:assert c.execute("select sum(tokens) from requests").fetchone()==(prefix+fee,)
