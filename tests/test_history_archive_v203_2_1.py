"""Small synthetic real zstd roundtrip and destructive-boundary controls."""
import importlib.util
import json
from pathlib import Path
import pytest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def archive(tmp_path,monkeypatch):
    path=ROOT/'tools/archive_passive_pilot_history_v203_2_1.py'
    spec=importlib.util.spec_from_file_location('archive_v203_2_1_control',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    batch=tmp_path/'batch';episode=batch/'episodes/1';root=episode/'controller-output/model-ledger'
    root.mkdir(parents=True);(batch/'resource-claims').mkdir();(batch/'resource-claims/allocation.lock').write_text('')
    m.OUT=tmp_path/'archives';m.OUT.mkdir();m.ART=tmp_path/'artifacts';m.BATCHES=(batch,)
    # Synthetic5KiB fixtures exercise real zstd; temporary filesystem size is
    # not the production data1 admission test.
    monkeypatch.setattr(m.shutil,'disk_usage',lambda path:SimpleNamespace(free=500*1024**3))
    q=m.save(episode/'quiescence.json',{'quiescent':True,'all_owned_objects_removed':True,
        'cleanup_errors':[],'create_result_unknown':False,'retained_objects':[]})
    r=m.save(episode/'result.json',{'status':'closed','quiescence':q})
    protected=m.save(root/'ledger.json',{'protected':True})
    (root/'request-0001.json').write_text(json.dumps({'input':'hello'*1000})+'\n')
    (root/'response-0001.json').write_text('{"output":"ok"}\n')
    rows=[{'relative':p.name,'original_canonical_path':str(p),**m.identity(p)}
          for p in [root/'request-0001.json',root/'response-0001.json']]
    item={'root':str(root),'batch':str(batch),'episode':str(episode),'item_id':'fixture-1',
        'result':r,'quiescence':q,'protected':[protected],'files':rows}
    plan=m.save(tmp_path/'plan.json',{'synthetic_only':True})
    return m,item,plan


def test_real_roundtrip_release_restore_keeps_canonical_bytes_and_summary(archive):
    m,item,plan=archive;root=Path(item['root']);prior=m.ref(root/'request-0001.json')
    result=m.archive_one(item,plan)
    assert result['source_files_released']==2
    assert not (root/'request-0001.json').exists()
    assert m.checked(item['protected'][0]).is_file()
    restored=m.restore(m.OUT/item['item_id']/'verified.json','request-0001.json')
    assert restored['restored']==prior and restored['old_checked_reference_compatible']
    assert (root/'request-0001.json').stat().st_mtime_ns==item['files'][0]['mtime_ns']
    with pytest.raises(FileExistsError):m.restore(m.OUT/item['item_id']/'verified.json','request-0001.json')


def test_bad_archive_never_releases_originals_and_changed_source_rejected(archive):
    m,item,_=archive;root=Path(item['root']);packed,rows=m.encode(root,item['files'],m.OUT/'bad')
    with packed.open('r+b') as stream:stream.seek(0);stream.write(b'BAD!')
    with pytest.raises((ValueError,EOFError,m.tarfile.ReadError)):m.verify(packed,rows)
    assert all((root/r['relative']).is_file() for r in rows)
    (root/'request-0001.json').write_text('changed')
    with pytest.raises(ValueError):m.unchanged(root,item['files'])


def test_scope_and_live_reference_guards(archive):
    m,item,_=archive
    for path in ['ledger.json','summary.json','events.jsonl','patch.json','score.json',
                 'collaboration-observation/summary.json','collaboration-observation/public-test-reports/'+('a'*64)+'.json']:
        assert not m.selected(path)
    assert m.selected('tokenize-0001.json')
    assert m.selected('request-capture-v181/'+('a'*64)+'/provenance.json')
    assert m.selected('collaboration-observation/source-presentations/'+('a'*64)+'.json')
    with (Path(item['root'])/'request-0001.json').open('rb'):
        with pytest.raises(PermissionError,match='live own-process'):m.quiet(item)
    active=Path(item['batch'])/'resource-claims/active-actor-0.json';active.write_text('{}')
    with pytest.raises(PermissionError,match='active resource'):m.quiet(item)
