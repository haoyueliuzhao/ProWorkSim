import json,sqlite3
from proworksim import software_context_budget_runtime_v188 as r
from proworksim.software_benchmark_candidates_v054 import reference

def test_new_owner_activity_does_not_invalidate_finished_predecessor(tmp_path,monkeypatch):
    old=tmp_path/'old';old.mkdir()
    batch=tmp_path/'batch';claims=batch/'resource-claims';claims.mkdir(parents=True)
    ledger=tmp_path/'ledger.sqlite'
    with sqlite3.connect(ledger) as db:
        db.execute('CREATE TABLE requests(job_id TEXT,status TEXT)')
        db.execute('INSERT INTO requests VALUES(?,?)',('new-owner-job','reserved'))
    quiet=old/'quiet.json';quiet.write_text(json.dumps({'all_owned_objects_removed':True,'cleanup_errors':[]}))
    result=old/'result.json';result.write_text(json.dumps({'quiescence':reference(quiet)}))
    (old/'final.json').write_text(json.dumps({'stage':'closed','generation_active':0,'grading_active':0,
        'records':{'old-job':{'result':reference(result)}}}))
    (claims/'active-grader-0.json').write_text(json.dumps({'spec':{'slot_id':'new-owner-job'}}))
    monkeypatch.setattr(r,'OLD',old);monkeypatch.setattr(r.scope,'BATCH_ROOT',batch);monkeypatch.setattr(r.scope,'LEDGER_FILE',ledger)
    assert r.predecessor_closed()
    occupied=claims/'active-actor-0.json';occupied.write_text(json.dumps({'spec':{'slot_id':'old-job'}}))
    assert not r.predecessor_closed()
    occupied.unlink()
    with sqlite3.connect(ledger) as db:db.execute('INSERT INTO requests VALUES(?,?)',('old-job','reserved'))
    assert not r.predecessor_closed()
