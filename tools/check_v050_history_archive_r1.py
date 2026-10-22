"""One small local fixture verifies archive/readback/restore before real raw removal."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim')
spec=importlib.util.spec_from_file_location('archive',ROOT/'tools/archive_v050_history_r1.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root=Path(tempfile.mkdtemp(prefix='v050-archive-control-',dir='/tmp'))
m.ROOT=root;m.OUT=root/'archive';m.OUT.mkdir()
content=(b'closed historical fixture without model data\n'*4096)
a=root/'runs/closed/a.json';b=root/'runs/closed/b.json';a.parent.mkdir(parents=True)
a.write_bytes(content);b.write_bytes(content);m.ALLOWLIST=[a,b]
supervisor=m.put(root/'supervisor.json',{'status':'complete'})
audit=m.put(root/'audit.json',{'candidate_prefix_matches':[]})
rows=[{'original':m.digest_path(p),'identity':m.identity(p),'supervisor':{'reference':supervisor}} for p in (a,b)]
sha=hashlib.sha256(content).hexdigest()
plan=m.put(m.OUT/'plan.json',{'version':m.VERSION,'source':m.digest_path(m.__file__),'current_reference_audit':audit,
    'allowlist':rows,'content_groups':{sha:[str(a),str(b)]},'default_restore_root':str(m.OUT/'restored')})
with patch.object(m,'no_candidate_process_use',return_value={'fixture_only':True}):result_ref=m.archive(plan)
result=m.load_ref(result_ref)
assert len(result['removed_paths'])==2 and len(result['objects'])==1 and not result['failures']
assert not a.exists() and not b.exists() and a.with_name('a.json.archive.json').exists()
m.restore(plan)
assert (m.OUT/'restored/runs/closed/a.json').read_bytes()==content
assert (m.OUT/'restored/runs/closed/b.json').read_bytes()==content
try:m.restore(plan)
except FileExistsError:pass
else:raise AssertionError('Restore overwrite was not rejected')
m.restore(plan,original_paths=True,selected=str(a));assert a.read_bytes()==content
# A failed full readback must retain the original and never publish a verified object.
c=root/'runs/closed/c.json';c.write_bytes(content);row={'original':m.digest_path(c),'identity':m.identity(c)}
bad=root/'bad';bad.mkdir()
with patch.object(m.gzip,'open',return_value=io.BytesIO(b'not the source bytes')):
    try:m.make_object([row],bad)
    except ValueError:pass
    else:raise AssertionError('Incorrect readback was accepted')
assert c.read_bytes()==content and not (bad/(sha+'.json.gz')).exists()
out=ROOT/'runs/software-benchmark-v055/history-compression-readonly-r1/cpu-control.json'
receipt=m.put(out,{'version':'v050-history-archive-small-fixture-control-r1','passed':True,
    'checks':['identical_sources_share_one_verified_object','raw_removed_only_after_verified_archive',
              'archive_sidecars_retain_original_identity','default_restore_to_new_directory_exact_bytes',
              'overwrite_rejected','explicit_original_path_restore_exact_bytes','failed_readback_keeps_original'],
    'real_historical_files_modified':0,'real_queue_writes':0,'model_calls':0,
    'fixture_directory':str(root),'source':m.digest_path(m.__file__),'control_source':m.digest_path(__file__)})
print(json.dumps(receipt))
