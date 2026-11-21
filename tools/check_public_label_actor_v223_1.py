"""One owned networkless Django actor, one public baseline test, zero model calls."""
import json,time,traceback
from pathlib import Path
from types import SimpleNamespace
from proworksim.software_organization_actor_v223_1 import Actor,FILES
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1];OUT=R/'runs/software-benchmark-v223-1/public-label-control-r1'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def main():
 OUT.mkdir(parents=True,exist_ok=False);row=json.loads((R/'artifacts/software-benchmark-v223-1/protocol-r1/candidate-tasks.json').read_text())['rows'][0];actor=Actor(row,OUT/'actor');result={'passed':False,'model_calls':0,'public_tests':0}
 try:
  actor.start();deadline=SimpleNamespace(hard_at=min(actor.hard_at-1,time.monotonic()+240));actor.bind_deadline(deadline)
  from proworksim.software_organization_world_v223_1 import library
  entry,selection=library.selected_entry(actor.entry,{'kind':'django','targets':['tests.utils_tests.test_timezone']},files=actor.baseline['files'],entry_metadata=actor.baseline['entry_metadata'])
  assert selection['targets']==['utils_tests.test_timezone']
  request={'version':'v141-role-baseline-managed-world-r1','instance_id':row['instance_id'],'actor_id':'member_001','organization_id':'FREE2','call_index':1,'source_reference':{'object_id':'v2231-public-selector-control','version_id':'original-baseline'},'tree_sha256':actor.baseline['tree']['tree_sha256'],'hard_deadline_monotonic':deadline.hard_at,'hidden_evaluation':False,'arbitrary_command':False,'public_test_selection_revision':'v110-public-test-selection-r1','public_test_selection':selection}
  save(OUT/'request.json',request);response=actor.test(files=actor.baseline['files'],entry_metadata=actor.baseline['entry_metadata'],request=request);save(OUT/'response.json',response)
  assert response['execution']['executed'] and response['execution']['argv']==entry['argv'] and response['execution']['public_test_selection']==selection
  assert response['counts']['tests_run']>0 and response['passed'] is True
  result.update(passed=True,public_tests=1,counts=response['counts'],selection=selection,library=reference(FILES['public_test_library_sha256']),network='none',host_mounts=[],original_source_only=True)
 except BaseException as e:result['error']={'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}
 finally:
  actor.close();result['cleanup']=json.loads((OUT/'actor/cleanup.json').read_text());save(OUT/'summary.json',result)
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
