"""One paid proposal plus at most one legality repair; never outcome-selected."""
import argparse,json,time,traceback
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.work_interface import _schema_errors
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_organization_api_v217 import Ledger,Backend,DirectHTTPS
from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_organization_generator_v217 import VERSION,GENERATOR_INSTRUCTION,TOOL,compile_target
from proworksim.software_organization_generator_v216 import target_id
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v217/protocol-r1'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);slot='v217:'+out.parent.name+':'+out.name;ledger=Ledger(a.ledger);result={'status':'preparing','slot':slot,'started':time.time()};save(out/'result.json',result);admitted=False
 try:
  for ref in json.loads((P/'deployment-freeze.json').read_text())['files']:checked(ref)
  state=json.loads((a.prefix/'decision-state.json').read_text());assert state['eligible'];graph=state['graph'];row=next(r for r in json.loads((P/'candidate-tasks.json').read_text())['rows'] if r['index']==a.index)
  cfg=json.loads(checked(row['configuration']).read_text());public={'problem_statement':cfg['public_task']['problem_statement'],'public_requirement_anchors':row['requirements'],'actual_decision_state':state}
  save(out/'generator-visible-input.json',public)
  tok=R/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';counter=OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256']);backend=Backend(out/'physical-api',ledger,slot,counter,DirectHTTPS(load_api_key(R/'.env'),timeout_seconds=1800),{'propose_organization'})
  ledger.admit(slot,200_000);admitted=True;messages=[{'role':'system','content':GENERATOR_INSTRUCTION},{'role':'user','content':json.dumps(public,ensure_ascii=False)}];valid={};failures=[]
  for attempt in range(2):
   wire={'model':'deepseek-flash','thinking':{'type':'disabled'},'temperature':1.0,'top_p':1.0,'stream':False,'max_tokens':8192,'tools':[TOOL],'tool_choice':'auto','messages':messages}
   body=backend.post('/chat/completions',{'team_slot_id':slot,'member_id':'member_001','usage_id':'agent','wire':wire});save(out/f'generated-{attempt}.json',body);errors=[]
   try:
    calls=body['choices'][0]['message'].get('tool_calls') or []
    if len(calls)!=1 or calls[0]['function']['name']!='propose_organization':raise ValueError('Exactly one proposal tool payload required')
    args=json.loads(calls[0]['function']['arguments']);err=_schema_errors(TOOL['function']['parameters'],args)
    if err:raise ValueError('; '.join(err))
    for i,proposal in enumerate(args['candidates']):
     try:
      candidate=compile_target(state,proposal)
      for action in candidate['actions']:
       arguments=action.get('arguments',{'offer_id':'actual-receipt-placeholder-for-schema-only'})
       errors_schema=_schema_errors(state['proposal_tool_schemas'][action['tool']],arguments)
       if errors_schema:raise ValueError('; '.join(errors_schema))
      valid[candidate['candidate_id']]=candidate
     except (ValueError,KeyError,TypeError) as e:errors.append({'candidate_position':i,'reason':str(e)})
   except (ValueError,KeyError,TypeError) as e:errors.append({'response_error':str(e)})
   failures.append({'attempt':attempt,'errors':errors})
   if not errors or len(valid)>=2:break
   messages.append({'role':'user','content':'One permitted format/legality correction only. Errors: '+json.dumps(errors,ensure_ascii=False)+'. Return up to two valid alternatives, or fewer if none other can be grounded. Do not invent transfers, relations or outcomes.'})
  with ledger.db() as c:actual=c.execute('SELECT COALESCE(sum(tokens),0),COALESCE(sum(cost),0) FROM requests WHERE slot=? AND status="settled"',(slot,)).fetchone()
  save(out/'generator-diagnostics.json',{'failures':failures,'valid_candidates':list(valid.values()),'generator_version':VERSION,'invalid_does_not_mean_infeasible':True})
  keep={'candidate_id':'KEEP-'+target_id(graph),'keep':True,'reason':'Keep current scope/owners/dependencies; fill missing required setup without changing owners','actions':[],'target':graph,'host_execution':False,'source_project_graph':state['project_relations']['graph_id']}
  candidates={'KEEP':keep,**{'C'+str(i+1):c for i,c in enumerate(sorted(valid.values(),key=lambda c:c['candidate_id'])[:2])}}
  bank={'version':VERSION,'source_state':reference(a.prefix/'decision-state.json'),'checkpoint':reference(a.prefix/'checkpoint/manifest.json'),'candidates':candidates,'actual_generator_tokens':actual[0],'actual_generator_cost_CNY_upper':actual[1]/1e9,'prefix_tokens':state['prefix_tokens'],'remaining_branch_token_limit':5_000_000-state['prefix_tokens']-actual[0],'selection_rule':'computed by frozen shared P_CN before any branch outcome, not by target hash','coverage_limited':len(candidates)<3,'generator_received_graph_id':state['project_relations']['graph_id'],'generator_visible_input':reference(out/'generator-visible-input.json')}
  assert bank['remaining_branch_token_limit']>0;save(out/'candidate-bank.json',bank);result.update(status='candidate_bank_ready',candidate_count=len(candidates),bank=reference(out/'candidate-bank.json'),actual_tokens=actual[0],actual_cost_CNY_upper=actual[1]/1e9)
 except BaseException as e:result.update(status='technical_unknown',error={'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
 finally:
  if admitted:ledger.close(slot)
  result['finished']=time.time();save(out/'result.json',result)
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--index',type=int,required=True);p.add_argument('--prefix',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);main(p.parse_args())
