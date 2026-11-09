from concurrent.futures import ThreadPoolExecutor
import json
import threading
import pytest
from proworksim import software_context_continuation_v182 as m


def test_parallel_resident_identity_is_created_once(tmp_path,monkeypatch):
    monkeypatch.setattr(m.scope,'API_ROOT',tmp_path)
    owner=m.Runtime.__new__(m.Runtime);owner.lock=threading.Lock()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:owner.resident({}),range(8)))
    assert len({v['identity']['sha256'] for v in results})==1
    assert len(list(tmp_path.glob('identity.json')))==1


def test_only_zero_call_zero_object_start_can_recover(tmp_path,monkeypatch):
    monkeypatch.setattr(m.original_scope,'LEDGER_FILE',tmp_path/'ledger.sqlite')
    monkeypatch.setattr(m.original_scope,'BATCH_ROOT',tmp_path/'objects')
    monkeypatch.setattr(m.original_scope,'API_ROOT',tmp_path/'old-owner')
    (tmp_path/'plan.json').write_text('{}')
    row={'slot_id':'v181:fixture','slot_index':18101}
    ledger=m.TaskLedger(path=tmp_path/'ledger.sqlite',plan={'rows':[row]})
    old={'row':row,'status':'technical_unknown','error':{'type':'FileExistsError','message':'before entry'}}
    m.original_scope.API_ROOT.mkdir()
    (m.original_scope.API_ROOT/'progress.json').write_text(json.dumps({'records':{row['slot_id']:old}}))
    with ledger.transaction() as db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',
        (row['slot_id'],'v181-full-task',40_000_000_000,'technical_unknown',0,1))
    ledger.admit_block([row])
    with ledger.transaction() as db:
        assert db.execute('SELECT status FROM jobs').fetchone()[0]=='running'
        assert json.loads(db.execute('SELECT prior_job FROM zero_call_recoveries_v182').fetchone()[0])['status']=='technical_unknown'
        assert db.execute('SELECT count(*) FROM requests').fetchone()[0]==0
    with pytest.raises(ValueError):ledger.admit_block([row])
    claims=m.original_scope.BATCH_ROOT/'resource-claims';claims.mkdir(parents=True)
    (claims/'actor-18101.json').write_text('{}')
    with pytest.raises(ValueError):m.startup_recovery_proof(row)
