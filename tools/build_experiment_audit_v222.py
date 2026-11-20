"""Incremental v222 audit after the published v217-v221 cutoff; no historical totals repeated."""
import collections,csv,datetime,hashlib,json,sqlite3,zipfile
from pathlib import Path
from zoneinfo import ZoneInfo
from proworksim.software_benchmark_candidates_v054 import reference,checked
R=Path(__file__).resolve().parents[1];O=R/'artifacts/experiment-audit-v222-20261120';D=R/'docs/experiments/software-benchmark-v222-audit-report.md';B=R/'runs/software-benchmark-v222/paired4-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 O.mkdir(parents=True,exist_ok=True);sources={}
 def src(p):
  p=Path(p).resolve();ref=reference(p);sources[str(p)]=ref;return ref
 def checked_read(ref):
  p=checked(ref);src(p);return read(p)
 finished=read(B/'finished.json');src(B/'finished.json');assert finished['status']=='completed'
 planp=R/'artifacts/software-benchmark-v222/protocol-r1/candidate-tasks.json';plan=read(planp);src(planp)
 rows=[];proposals=[];prefixes=[];locks=[];generator_payload_matches=[];schema_pairs={}
 for row in plan['rows']:
  t=B/f'task-{row["index"]:02d}';state=read(t/'PREFIX/decision-state.json');prefix=read(t/'PREFIX/result.json');src(t/'PREFIX/decision-state.json');src(t/'PREFIX/result.json');src(t/'PREFIX/checkpoint/manifest.json')
  prefixes.append({'task':row['instance_id'],'trigger':state['checkpoint_trigger'],'prefix_tokens':state['prefix_tokens'],'flags':state['reason_flags']})
  for z in ('L','G'):
   ep=t/z;gen=t/f'GEN-{z}';result=finished['results'][str(row['index'])+':'+z]
   checked_read(result['episode']);scores={k:checked_read(ref) for k,ref in result['scores'].items()}
   assert scores['code']['status']=='official_report' and scores['code']['resolved']==result['code_correct']
   assert scores['delivery']['status']=='no_legal_delivery' and result['legal_correct'] is False
   bank=read(gen/'candidate-bank.json');diag=read(gen/'generator-diagnostics.json');info=read(gen/'information-audit.json');bd=read(ep/'boundary.json');perf=read(ep/'performance.json');r=read(ep/'result.json')
   for p in [gen/'candidate-bank.json',gen/'generator-diagnostics.json',gen/'information-audit.json',gen/'generator-visible-input.json',gen/'condition-state.json',ep/'boundary.json',ep/'performance.json',ep/'candidate-lock.json',ep/'actor/cleanup.json']:src(p)
   lockref=read(ep/'candidate-lock.json');lock=checked_read(lockref);locks.append({'task':row['instance_id'],'condition':z,'has_legal_submission':bool(lock.get('last_legal_delivery'))})
   visible=read(gen/'generator-visible-input.json');expect=json.dumps(visible,ensure_ascii=False)
   for p in sorted(gen.glob('physical-api/*/request.json')):
    q=read(p);messages=q['payload']['wire']['messages'];match=any(m.get('role')=='user' and m.get('content')==expect for m in messages)
    assert match;generator_payload_matches.append({'task':row['instance_id'],'condition':z,'request':src(p),'visible_input_matches':match,'graph_id':bank['generator_received_graph_id']})
   counts=collections.Counter();errors=collections.Counter();selected=[];detail=[]
   for step in bd['outcomes']:
    dec=step.get('decision',{});rsp=step.get('response',{});tool=dec.get('action')
    if rsp.get('ok') is True:counts[tool]+=1
    if rsp.get('ok') is False:
     error=rsp.get('error') or {};code=(error.get('rejection') or {}).get('code') or error.get('type') or 'unclassified';errors[(tool,code)]+=1
    if tool in ('select_arrangement','offer_joint_arrangement','accept_joint_arrangement','change_dependency'):
     detail.append({'tool':tool,'arguments':dec.get('arguments'),'ok':rsp.get('ok'),'result':rsp.get('result'),'error':rsp.get('error')})
    if tool=='select_arrangement' and rsp.get('ok'):selected.append(dec['arguments']['decision'])
   official=scores['code']['official_result'][1][row['instance_id']];tests=official['tests_status'];fail={k:v['failure'] for k,v in tests.items()}
   schema_by_member={}
   for request_path in ep.glob('physical-api/*/request.json'):
    request=read(request_path)['payload']
    if request['usage_id']=='agent' and request['member_id'] not in schema_by_member:
     tools=request['wire']['tools'];schema_by_member[request['member_id']]={'count':len(tools),'sha256':hashlib.sha256(json.dumps(tools,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'source':src(request_path)}
     if len(schema_by_member)==2:break
   schema_pairs[row['instance_id']+':'+z]=schema_by_member
   candidate=bank['candidates'][bank['selected']]
   rows.append({'task':row['instance_id'],'condition':z,'code_correct':result['code_correct'],'correct_delivery':result['legal_correct'],'logical_tokens':result['logical_tokens'],'prefix_tokens':bank['prefix_tokens'],'generator_tokens':bank['actual_generator_tokens'],'continuation_tokens':result['logical_tokens']-bank['prefix_tokens']-bank['actual_generator_tokens'],'selected':bank['selected'],'alternatives':len(bank['candidates'])-1,'choice':selected,'successful_tools':dict(counts),'tool_errors':[{'tool':k[0],'code':k[1],'count':v} for k,v in errors.items()],'organization_actions':detail,'selected_candidate':candidate,'termination':bd['termination_class'],'failed_official_tests':fail,'generation_wall_seconds':r['finished']-r['started'],'prepare_seconds':r['API_admitted_at']-r['started'],'timing':perf['timing'],'scores':result['scores']})
   assert bd['execution_integrity_failure'] is None and bd['termination_class']=='budget_boundary_without_delivery'
   proposals.append({'task':row['instance_id'],'condition':z,'selected':bank['selected'],'valid_unique_adjustments':len(bank['candidates'])-1,'diagnostics':diag,'graph_levels':info['relations_by_level'],'cold_seconds':info['cold_seconds'],'index_MiB_estimated':info['estimated_index_object_bytes']/1024**2,'navigation_chars':len(json.dumps(info['navigation'],ensure_ascii=False)),'generator_tokens':bank['actual_generator_tokens']})
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  ledger=c.execute('SELECT slot,status,tokens,cost,body FROM requests WHERE slot LIKE "v222:%"').fetchall();cap=int(c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()[0]);total_cost=c.execute('SELECT sum(cost) FROM requests WHERE status="settled"').fetchone()[0]
 assert len(ledger)==629 and all(x[1]=='settled' for x in ledger)
 usage={'input_tokens':0,'output_tokens':0,'total_tokens':0,'cache_hit_tokens':0,'requests':len(ledger),'cost_CNY_upper':sum(r[3] for r in ledger)/1e9};stages={};models=collections.Counter();fingerprints=collections.Counter()
 for slot,status,tokens,cost,body in ledger:
  u=json.loads(body);models[u['provider_model']]+=1;fingerprints[u.get('system_fingerprint')]+=1
  kind='prefix' if slot.endswith(':PREFIX') else 'generator' if ':GEN-' in slot else 'continuation';stage=stages.setdefault(kind,{'requests':0,'tokens':0,'cost_CNY_upper':0});stage['requests']+=1;stage['tokens']+=tokens;stage['cost_CNY_upper']+=cost/1e9
  for k in ('input_tokens','output_tokens','total_tokens','cache_hit_tokens'):usage[k]+=u[k]
 assert usage['total_tokens']==36115969==usage['input_tokens']+usage['output_tokens']
 assert sum(r['logical_tokens'] for r in rows)-sum(p['prefix_tokens'] for p in prefixes)==usage['total_tokens']
 clean=[]
 for p in sorted(B.glob('task-*/*/actor/cleanup.json')):
  x=read(p);assert x['owned_actor_removed'] and not x['transport_errors'];clean.append({'source':src(p),'receipt':x})
 env=[]
 for p in sorted((R/'runs/software-benchmark-v222/environment-r1').glob('task-*/*/receipt.json')):
  x=read(p);assert x['status']=='official_report' and x['resolved']==(x['kind']=='gold') and x['cleanup_errors']==[];env.append(src(p))
 assert len(clean)==12 and len(env)==8
 perfp=R/'artifacts/software-benchmark-v222/performance-revision-r1/identity-benchmark-summary.json';perfg=R/'artifacts/software-benchmark-v222/performance-revision-r1/admission.json';performance=read(perfp);src(perfp);src(perfg)
 for p in ['docs/experiments/software-benchmark-v222-project-graph-paired-protocol.md','docs/experiments/software-benchmark-v222-1-runtime-performance.md','src/proworksim/software_project_information_v222.py','src/proworksim/software_organization_generator_v217.py','src/proworksim/software_organization_world_v213.py']:src(R/p)
 for task in plan['rows']:
  for member in ('member_001','member_002'):
   l=schema_pairs[task['instance_id']+':L'][member];g=schema_pairs[task['instance_id']+':G'][member];assert l['sha256']==g['sha256'] and l['count']==g['count']==57
 groups={z:{'n':4,'code':sum(r['code_correct'] for r in rows if r['condition']==z),'delivery':sum(r['correct_delivery'] for r in rows if r['condition']==z),'mean_tokens':sum(r['logical_tokens'] for r in rows if r['condition']==z)/4,'successful_locate_work':sum(r['successful_tools'].get('locate_work',0) for r in rows if r['condition']==z),'generator_tokens':sum(r['generator_tokens'] for r in rows if r['condition']==z)} for z in ('L','G')}
 facts={'cutoff':datetime.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),'v222':{'groups':groups,'episodes':rows,'prefixes':prefixes,'proposals':proposals,'generator_requests_presented':generator_payload_matches,'candidate_locks':locks,'actual_solver_schema_pairs':schema_pairs,'physical_usage':usage,'physical_stages':stages,'models':dict(models),'fingerprints':dict(fingerprints),'actor_cleanup':clean,'environment_control_sources':env,'finished':finished['at'],'budget_reservation_released':finished['envelope_released']},'related_performance_revision':{'source':reference(perfp),'admission':reference(perfg),'not_deployed_in_v222':True,'historical_measurements_not_recounted':True},'current_cash_reference':{'cap_CNY':cap/1e9,'remaining_CNY':(cap-total_cost)/1e9,'not_incremental_expenditure':True},'semantic_edge_precision':None,'necessary_edge_recall':None,'no_independent_necessary_relation_gold':True,'new_model_calls':0,'new_container_or_score_runs':0}
 save(O/'facts.json',facts);save(O/'sources.json',{'sources':list(sources.values())})
 with (O/'paired-results.csv').open('w',newline='') as f:
  writer=csv.writer(f);writer.writerow(['experiment','task','condition','code_correct','correct_delivery','logical_tokens','termination'])
  for e in rows:writer.writerow(['v222',e['task'],e['condition'],e['code_correct'],e['correct_delivery'],e['logical_tokens'],e['termination']])
 text=D.read_text()
 assert 'v216_2' not in facts
 assert len(rows)==8 and all(sum(r['condition']==z for r in rows)==4 for z in ('L','G'))
 for z,v in groups.items():assert f"{v['mean_tokens']:,.2f}" in text
 assert '36,115,969' in text and '60.45005944' in text
 checks={'scope':'v222_incremental_only','rows':8,'complete_pairs':4,'official_code_scores':8,'no_legal_delivery_endpoints':8,'settled_API_requests':629,'generator_payload_matches':len(generator_payload_matches),'actual_solver_tools_same_within_pairs':True,'physical_logical_usage_reconciled':True,'new_experiment_calls':0,'Word_generated':False,'report':reference(D),'facts':reference(O/'facts.json')}
 save(O/'publication-check.json',checks)
 package=O/'v222-incremental-audit-package.zip'
 # Keep full histories on disk; package bounded review excerpts and original summaries.
 chosen=[Path(x) for x in sources if any(x.endswith(suffix) for suffix in ('/result.json','/receipt.json','/decision-state.json','/candidate-bank.json','/generator-diagnostics.json','/information-audit.json','/performance.json','/cleanup.json')) and 'software-benchmark-v222/' in x]
 with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
  for p in [D,O/'facts.json',O/'paired-results.csv',O/'sources.json',O/'publication-check.json',Path(__file__)]:z.write(p,str(p.relative_to(R)))
  for p in chosen:z.write(p,'evidence/'+str(p.relative_to(R)))
 with zipfile.ZipFile(package) as z:
  assert z.testzip() is None
  for p in chosen:
   content=z.read('evidence/'+str(p.relative_to(R)));assert hashlib.sha256(content).hexdigest()==sources[str(p)]['sha256']
 save(O/'package-receipt.json',{'package':reference(package),'original_evidence_snapshots':len(chosen),'hashes_verified':True,'full_histories_included':False})
 print(json.dumps({'groups':groups,'usage':usage,'stages':stages,'prefix_sum':sum(p['prefix_tokens'] for p in prefixes),'logical_sum':sum(r['logical_tokens'] for r in rows),'sources':len(sources),'cleanup':len(clean),'gen_presented':len(generator_payload_matches)},ensure_ascii=False))
if __name__=='__main__':main()
