"""Use only the unissued second correction; retain all original costs and inputs."""
import json,time,traceback
from pathlib import Path
from proworksim.storage import json_bytes,digest
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_organization_proposal_budget_v223_2 import prepare_dispatch,fallback_assessment,VERSION
from proworksim.software_organization_api_v223_2 import Ledger,Backend,DirectHTTPS,NEW
from proworksim.software_organization_api_v204 import PrefixComplete
from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_organization_planning_v223 import parse
from proworksim.software_organization_generator_v217 import compile_target
from proworksim.software_organization_generator_v216 import target_id
from proworksim.software_organization_opportunity_v218 import distinct_structure,structure
from proworksim.work_interface import _schema_errors
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v223-2/protocol-r1';OUT=R/'runs/software-benchmark-v223-2/recovery-r1/task-03/REPAIR-W0';L=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def main():
 OUT.mkdir(parents=True,exist_ok=False);slot=NEW+'REPAIR-W0';ledger=Ledger(L);admitted=False;result={'status':'preparing','started':time.time(),'slot':slot}
 try:
  for ref in read(P/'deployment-freeze.json')['files']:checked(ref)
  plan=read(P/'recovery-plan.json')
  for ref in plan['old_sources'].values():checked(ref)
  state=read(checked(plan['old_sources']['state']));graph=read(checked(plan['old_sources']['graph']));old=plan['old_accounting'];limit=plan['remaining_generator_tokens'];ledger.admit(slot,limit);admitted=True
  tok=R/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';counter=OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256']);wire=read(checked(plan['repair_wire_before_allocation']));wire,quote=prepare_dispatch(wire,counter,ledger.stage_remaining(slot));save(OUT/'allocation.json',quote)
  assert quote==read(P/'allocation.json') and wire==read(checked(plan['repair_wire']))
  errors=[];valid={};assessment=None;fallback=None;body=None
  if quote['dispatch']:
   backend=Backend(OUT/'physical-api',ledger,slot,counter,DirectHTTPS(load_api_key(R/'.env'),timeout_seconds=1800),{'propose_organization'})
   try:body=backend.post('/chat/completions',{'team_slot_id':slot,'member_id':'member_001','usage_id':'agent','logical_role':'unused_proposal_correction','wire':wire})
   except PrefixComplete as e:fallback={'kind':'pre_dispatch_stage_boundary','error':str(e),'new_model_request_issued':backend.requests>0}
   if body is not None:
    save(OUT/'response.json',body)
    try:
     calls=body['choices'][0]['message'].get('tool_calls') or []
     if len(calls)!=1 or calls[0]['function']['name']!='propose_organization':raise ValueError('Exactly one proposal payload required')
     args,proof=parse(calls[0]['function']['arguments'],state);save(OUT/'normalization.json',proof);assessment=args['assessment']
     for n,proposal in enumerate(args['candidates']):
      try:
       c=compile_target(state,proposal)
       if not distinct_structure(state,c):raise ValueError('Setup-only candidate is KEEP')
       for action in c['actions']:
        params=action.get('arguments',{'offer_id':'actual-receipt-placeholder-for-schema-only'});bad=_schema_errors(state['proposal_tool_schemas'][action['tool']],params)
        if bad:raise ValueError('; '.join(bad))
       valid.setdefault(digest(json_bytes(structure(c['target']))),c)
      except (ValueError,KeyError,TypeError) as e:errors.append({'candidate':n,'error':str(e)})
    except (ValueError,KeyError,TypeError) as e:errors.append({'response_error':str(e)})
  else:fallback={'kind':quote['reason'],'new_model_request_issued':False}
  if assessment is None or (assessment['decision']=='propose' and not valid):
   fallback=fallback or {'kind':'bounded_invalid_proposal','errors':errors,'no_additional_retry':True};assessment=fallback_assessment(fallback['kind'])
  with ledger.db() as c:new_tokens,new_cost=c.execute('SELECT COALESCE(sum(tokens),0),COALESCE(sum(cost),0) FROM requests WHERE slot=? AND status="settled"',(slot,)).fetchone()
  total_gen=old['GEN-W0']['tokens']+new_tokens;assert total_gen<=200_000
  keep={'candidate_id':'KEEP-'+target_id(state['graph']),'keep':True,'reason':assessment['reason'] if assessment['decision'] in ('keep','defer') else 'Keep current structure if no adjustment is chosen.','actions':[],'target':state['graph'],'host_execution':False,'source_project_graph':state['project_relations']['graph_id']}
  candidates={'KEEP':keep,**{'C'+str(i+1):v for i,v in enumerate(list(valid.values())[:2])}}
  for v in candidates.values():v['decision_assessment']=assessment
  bank={'version':VERSION,'decision_assessment':assessment,'candidates':candidates,'selected':'C1' if valid else 'KEEP','source_state':plan['old_sources']['prefix'],'checkpoint':plan['old_sources']['checkpoint'],'actual_generator_tokens':total_gen,'actual_generator_cost_CNY_upper':(old['GEN-W0']['cost_nanoyuan']+new_cost)/1e9,'shared_graph_tokens':old['GRAPH']['tokens'],'shared_graph_state':graph['state'],'prefix_tokens':old['PREFIX']['tokens'],'remaining_branch_token_limit':5_000_000-old['PREFIX']['tokens']-old['GRAPH']['tokens']-total_gen,'recovery_sources':plan['old_sources'],'new_repair_tokens':new_tokens,'system_fallback':fallback,'information_condition':'W0','selection_rule':'first valid structural candidate, else KEEP; unchanged from bounded generation','old_calls_and_costs_retained':True}
  save(OUT/'candidate-bank.json',bank);save(OUT/'diagnostics.json',{'errors':errors,'fallback':fallback,'old_parse_errors':plan['old_parse_errors'],'no_model_resampling':True,'new_logical_corrections':int(body is not None)})
  result.update(status='candidate_bank_ready',bank=reference(OUT/'candidate-bank.json'),selected=bank['selected'],new_repair_tokens=new_tokens,total_generator_tokens=total_gen,fallback=fallback)
 except BaseException as e:result.update(status='technical_unknown',error={'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
 finally:
  if admitted:ledger.close(slot)
  result['finished']=time.time();save(OUT/'result.json',result)
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
