"""Four public/checkpoint-only offline index probes, no scores/patches/API."""
import json,time,resource,os,gc
from pathlib import Path
from proworksim.software_project_navigation_v221 import RepositoryIndex
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/software-benchmark-v221/offline-navigation-r3'
def main():
 os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(180,180));OUT.mkdir(parents=True,exist_ok=False)
 plan=json.loads((R/'artifacts/software-benchmark-v218/protocol-r1/candidate-tasks.json').read_text());results=[]
 for i in (1,4,5,6):
  row=next(r for r in plan['rows'] if r['index']==i);root=R/f'runs/software-benchmark-v218/pilot8-r1/task-{i:02d}/PREFIX';state=json.loads((root/'decision-state.json').read_text());graph=state['project_relations'];rels=[r for r in graph['relations'] if isinstance(r.get('version'),dict) and r['version'].get('object_id')=='obj-c567f5b9c7d905481548e89b'];latest=max(rels,key=lambda r:r['observed_order'])['version']
  path=root/'prepared/world/control/versions'/latest['object_id']/latest['version_id']/'member_001.json';snapshot_ref=reference(path);bundle=json.loads(path.read_text());index=RepositoryIndex('member_001');query=row['public_problem'].splitlines()[0]+' '+ ' '.join(x['exact_public_quote'] for x in row['requirements'])
  start=time.perf_counter();cold=dict(index.update(bundle['files'],latest,entry_metadata=bundle.get('entry_metadata')));cold_seconds=time.perf_counter()-start
  start=time.perf_counter();lex=index.query(query,project=graph,limit=8,max_chars=8000,use_graph=False);lex_seconds=time.perf_counter()-start
  start=time.perf_counter();mixed=index.query(query,project=graph,limit=8,max_chars=8000,use_graph=True);mixed_seconds=time.perf_counter()-start
  start=time.perf_counter();warm=dict(index.update(bundle['files'],latest,entry_metadata=bundle.get('entry_metadata')));warm_seconds=time.perf_counter()-start
  assert warm['parsed_files']==0 and set(lex['global_lexical_top_paths'])<=set(h['path'] for h in mixed['hits'])
  assert all(h['path'] in bundle['files'] for h in mixed['hits']) and len(json.dumps(mixed,ensure_ascii=False))<=8000
  assert snapshot_ref==reference(path)
  result={'index':i,'instance_id':row['instance_id'],'query':query,'snapshot':snapshot_ref,'graph':reference(root/'decision-state.json'),'source_reference':latest,'cold':cold,'warm':warm,'cold_seconds':cold_seconds,'warm_update_seconds':warm_seconds,'lexical_query_seconds':lex_seconds,'mixed_query_seconds':mixed_seconds,'lexical':lex,'mixed':mixed,'new_graph_candidates':[h['path'] for h in mixed['hits'] if h['path'] not in {x['path'] for x in lex['hits']}],'output_chars':len(json.dumps(mixed,ensure_ascii=False)),'no_reference_patch_or_score_used':True,'not_accuracy_or_token_savings_measure':True}
  results.append(result);print(i,'files',cold['indexed_files'],'cold',round(cold_seconds,3),'warm',round(warm_seconds,3),'chars',result['output_chars'],'new',result['new_graph_candidates'],flush=True)
  (OUT/f'task-{i:02d}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');del bundle,index;gc.collect()
 summary={'passed':True,'cases':len(results),'new_model_calls':0,'new_containers':0,'source_unchanged':True,'all_global_top3_retained':True,'all_warm_parsed_files_zero':True,'max_output_chars':max(r['output_chars'] for r in results),'cold_seconds':[r['cold_seconds'] for r in results],'warm_seconds':[r['warm_update_seconds'] for r in results],'graph_adds_candidates_cases':sum(bool(r['new_graph_candidates']) for r in results),'cannot_claim_accuracy_or_provider_token_gain':True}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
