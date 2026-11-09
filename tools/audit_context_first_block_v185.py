"""Read-only first preselected task block: actual HTTP and source estimates."""
import json,os,sqlite3
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,checked,write_new
from proworksim.software_input_provenance_v156 import BuiltRequest,estimate_fragment_tokens,normalized_usage
from proworksim.software_collaboration_observation_v141 import load_official_content_counter
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v181/full-context-pilot-r1'
OUT=ROOT/'artifacts/software-benchmark-v185/first-block-measurement-r1'

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 os.sched_setaffinity(0,{46,47})
 plan=json.loads((RUN/'execution-plan.json').read_bytes());rows=plan['rows'][:4]
 token=reference(ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')
 counter,meta=load_official_content_counter(token['path'],manifest_sha256=token['sha256'])
 result=[]
 with sqlite3.connect((ROOT/'runs/software-benchmark-v175/context-replay-r1/api-ledger.sqlite').as_uri()+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row
  for row in rows:
   folder=RUN/'episodes'/str(row['slot_index']);episode=json.loads((folder/'result.json').read_bytes());assert episode['status']=='closed'
   requests=[dict(r) for r in db.execute('SELECT * FROM requests WHERE job_id=?',(row['slot_id'],))]
   assert requests and all(r['status']=='settled' for r in requests)
   original={str(r['step']):r for r in requests};assert len(original)==len(requests)
   captures=list((folder/'controller-output/model-ledger/request-capture-v181').glob('*/provenance.json'))
   assert len(captures)==len(original)
   estimates=[]
   for path in captures:
    manifest=json.loads(path.read_bytes());rid=manifest['identity']['request_id'];physical=original[rid]
    assert manifest['payload_sha256']==physical['payload_sha']
    body=json.loads((path.parent/'response-original.json').read_bytes())
    assert body==json.loads(checked(json.loads(physical['response_ref'])).read_bytes())
    assert normalized_usage(body['usage'])==json.loads(physical['usage'])
    built=BuiltRequest((path.parent/'payload.json').read_bytes(),manifest)
    estimated=estimate_fragment_tokens(built,counter,tokenizer_id=meta['tokenizer_id'])
    estimates.append({k:v for k,v in estimated.items() if k!='pieces'})
   unknown=sum(v['unattributed_fragment_tokens_estimate'] for v in estimates)
   denominator=sum(v['fragment_count_sum'] for v in estimates)
   ref=write_new(OUT/(row['group_id']+'-sources.json'),estimates)
   result.append({'group':row['group_id'],'slot_id':row['slot_id'],'physical_requests':len(requests),
    'request_response_usage_exact_match':True,'local_estimated_unattributed_fraction':unknown/denominator,
    'local_estimated_unattributed':unknown,'local_estimated_denominator':denominator,'source_estimates':ref,
    'actual_tokens':sum(json.loads(r['usage'])['total_tokens'] for r in requests)})
 total_unknown=sum(r['local_estimated_unattributed'] for r in result);total=sum(r['local_estimated_denominator'] for r in result)
 value={'passed':all(r['local_estimated_unattributed_fraction']<=.02 for r in result),
  'scope':'first preselected four-condition task only, not the whole experiment','rows':result,
  'physical_requests':sum(r['physical_requests'] for r in result),'local_estimated_unattributed_fraction':total_unknown/total,
  'provider_exact_source_mapping_claimed':False,'new_API_calls':0,'new_Docker_objects':0,'scores_used_for_selection':False}
 ref=write_new(OUT/'summary.json',value);print(json.dumps({'summary':ref,**{k:value[k] for k in ('passed','physical_requests','local_estimated_unattributed_fraction')}}))
if __name__=='__main__':main()
