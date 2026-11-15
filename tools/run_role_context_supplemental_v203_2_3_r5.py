"""Serial, exception-isolated supplemental code grading; no model calls."""
import argparse,json,time,sqlite3
from pathlib import Path
from proworksim import software_benchmark_supplemental_v203_2_3_r5 as g
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.storage import atomic_write,json_bytes
s=g.scope;OUT=g.OUT

def prepare():
    inventory=s.load(reference(OUT/'inventory.json'));items=[r for r in inventory['rows'] if r['state']=='locked_supplemental_candidate_verified']
    a={'version':'v203.2.3-supplemental-only-authority-r5','source':reference(g.__file__),'inventory':reference(OUT/'inventory.json'),'model_calls_allowed':0,'allowed_resource_keys':['score-'+str(r['row']['slot_index']) for r in items],'user_instruction':'Keep cumulative CNY130; only grade existing candidates; do not rerun models.','original_generation_states_preserved':True,'maximum_concurrent_graders':1,'no_shared_host_changes':True}
    s.retain(OUT/'authorization.json',a)
    api=g.factory();manifest=s.retain(OUT/'scorer-manifest.json',api.scorer.installation_manifest());requests=[]
    for item in items:
        row=item['row'];key='score-'+str(row['slot_index']);folder=s.GRADING_ROOT/key
        if (folder/'started.json').exists() or (s.BATCH_ROOT/'resource-claims'/(key+'.json')).exists():raise ValueError('Scoring resource already consumed')
        original=s.load(item['original_lock']);receipt=s.load(item['patch_receipt'])
        lock=s.retain(OUT/'locks'/(str(row['slot_index'])+'.json'),{**original,'patch_receipt':{**receipt,'patch':item['patch']},'supplemental_source':item['original_lock'],'generation_remains_technical_unknown':True})
        q=reference(s.COORDINATOR_ROOT/'qualifications'/(row['instance_id']+'.json'))
        api.scorer.validate_qualification(q,s.load(row['configuration']),reference(s.PLAN_FILE))
        request={'version':g.previous.VERSION,'resource_key':key,'instance_id':row['instance_id'],'plan':reference(s.PLAN_FILE),'configuration':row['configuration'],'candidate_lock':lock,'generation_result':item['result'],'measurement_kind':g.KIND,'source_slot_id':row['source_slot_id'],'slot_id':row['slot_id'],'qualification':q,'limits':api.scorer.LIMITS,'scorer_manifest':manifest,'cpuset_cpus':None,'directory':str(folder),'patch_kind':None,'delivery_evidence':None,**api.scorer.environment.request_fields(row['instance_id'])}
        api.scorer.validate_candidate_request(request,s.load(reference(s.PLAN_FILE))['resources'][key],s.load(row['configuration']),s.load(reference(s.PLAN_FILE)))
        requests.append(s.retain(folder/'request.json',request))
    return s.retain(OUT/'plan.json',{'requests':requests,'model_calls':0,'supplemental_not_valid_context_comparison':True})

def run():
    plan=s.load(reference(OUT/'plan.json'));api=g.factory();records=[]
    for ref in plan['requests']:
        req=s.load(ref)
        try:
            completion=api.run_request(ref)
            receipt_path=Path(req['directory'])/'receipt.json';qpath=Path(req['directory'])/'quiescence.json'
            receipt=s.load(reference(receipt_path)) if receipt_path.exists() else {};quiet=s.load(reference(qpath)) if qpath.exists() else {}
            known=completion.get('returncode')==0 and receipt.get('status')=='official_report' and type(receipt.get('resolved')) is bool and quiet.get('quiescent') and not quiet.get('cleanup_errors')
            record={'slot_id':req['slot_id'],'request':ref,'status':'scored' if known else 'technical_unknown','resolved':receipt.get('resolved') if known else None,'completion':completion,'receipt':reference(receipt_path) if receipt_path.exists() else None,'generation_remains_technical_unknown':True}
        except Exception as e:record={'slot_id':req['slot_id'],'status':'technical_unknown','error':{'type':type(e).__name__,'message':str(e)},'automatic_retry':False}
        records.append(record);atomic_write(OUT/'progress.json',json_bytes({'phase':'running','records':records,'planned':len(plan['requests']),'model_calls':0}));print(json.dumps({k:record.get(k) for k in ['slot_id','status','resolved','error']}),flush=True)
    atomic_write(OUT/'progress.json',json_bytes({'phase':'closed','records':records,'planned':len(plan['requests']),'model_calls':0}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');args=p.parse_args()
    if args.prepare:print(json.dumps(prepare()))
    else:run()
