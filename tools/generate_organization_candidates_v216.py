"""Paid fixed-generator service on frozen public decision state; no live tool execution."""
import argparse,json,time,traceback
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.work_interface import _schema_errors
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_organization_api_v216 import Ledger,Backend,DirectHTTPS
from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_organization_generator_v216 import VERSION,GENERATOR_INSTRUCTION,TOOL,validate,target_id
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v216/protocol-r1'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);slot='v216:'+out.parent.name+':'+out.name;ledger=Ledger(a.ledger);result={'status':'preparing','slot':slot,'started':time.time()};save(out/'result.json',result);admitted=False
 try:
  for ref in json.loads((P/'deployment-freeze.json').read_text())['files']:checked(ref)
  state=json.loads((a.prefix/'decision-state.json').read_text());assert state['eligible'];graph=state['graph'];row=next(r for r in json.loads((P/'candidate-tasks.json').read_text())['rows'] if r['index']==a.index)
  cfg=json.loads(checked(row['configuration']).read_text());public={'problem_statement':cfg['public_task']['problem_statement'],'public_requirement_anchors':row['requirements'],'actual_decision_state':state}
  tok=R/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';counter=OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256']);backend=Backend(out/'physical-api',ledger,slot,counter,DirectHTTPS(load_api_key(R/'.env'),timeout_seconds=1800),{'propose_organization'})
  ledger.admit(slot,200_000);admitted=True;messages=[{'role':'system','content':GENERATOR_INSTRUCTION},{'role':'user','content':json.dumps(public,ensure_ascii=False)}];valid={};failures=[]
  for attempt in range(2):
   wire={'model':'deepseek-flash','thinking':{'type':'disabled'},'temperature':1.0,'top_p':1.0,'stream':False,'max_tokens':8192,'tools':[TOOL],'tool_choice':'auto','messages':messages}
   body=backend.post('/chat/completions',{'team_slot_id':slot,'member_id':'member_001','usage_id':'agent','wire':wire});save(out/f'generated-{attempt}.json',body)
   errors=[]
   try:
    calls=body['choices'][0]['message'].get('tool_calls') or []
    if len(calls)!=1 or calls[0]['function']['name']!='propose_organization':raise ValueError('Exactly one proposal tool payload required')
    args=json.loads(calls[0]['function']['arguments'])
    if set(args)!={'candidates'} or not 1<=len(args['candidates'])<=2:raise ValueError('Expected candidate array')
    for i,proposal in enumerate(args['candidates']):
     try:
      candidate=validate(graph,proposal)
      for action in candidate['actions']:
       arguments=action.get('arguments',{'offer_id':'actual-receipt-placeholder-for-schema-only'})
       schema_errors=_schema_errors(state['proposal_tool_schemas'][action['tool']],arguments)
       if schema_errors:raise ValueError('Actual tool schema: '+'; '.join(schema_errors))
      if not any(o['op']=='JOINT_ASSIGN' for o in candidate['operations']):raise ValueError('Mechanism admission candidate must include actual bidirectional owner arrangement')
      valid[candidate['candidate_id']]=candidate
     except (ValueError,KeyError,TypeError) as e:errors.append({'candidate_position':i,'reason':str(e)})
   except (ValueError,KeyError,TypeError) as e:errors.append({'response_error':str(e)})
   failures.append({'attempt':attempt,'errors':errors})
   if len(valid)>=a.required:break
   # One bounded repair of generator FORMAT/LEGALITY, never performance-selected resampling.
   messages.append({'role':'user','content':'The previous output did not provide the required valid distinct plans. Validation errors: '+json.dumps(errors,ensure_ascii=False)+'. Return two complete legal alternatives using propose_organization. No world state has changed.'})
  with ledger.db() as c:
   actual=c.execute('SELECT COALESCE(sum(tokens),0),COALESCE(sum(cost),0) FROM requests WHERE slot=? AND status="settled"',(slot,)).fetchone()
  save(out/'generator-diagnostics.json',{'failures':failures,'valid_candidates':list(valid.values()),'generator_version':VERSION,'failed_candidates_and_repairs_charged':True})
  if len(valid)<a.required:result.update(status='no_valid_complete_candidate_panel',valid_count=len(valid))
  else:
   chosen=sorted(valid.values(),key=lambda x:x['candidate_id']);keep={'candidate_id':'KEEP-'+target_id(graph),'keep':True,'reason':'Keep the actual current organization at the same frozen checkpoint','actions':[],'target':graph,'host_execution':False}
   bank={'version':VERSION,'source_state':reference(a.prefix/'decision-state.json'),'checkpoint':reference(a.prefix/'checkpoint/manifest.json'),'selected':{'KEEP':keep,'ADAPT':chosen[0]},'valid_candidates':chosen,'required_count':a.required,'selection_rule':'lexicographic canonical effective target ID, before branch outcomes','actual_generator_tokens':actual[0],'actual_generator_cost_CNY_upper':actual[1]/1e9,'prefix_tokens':state['prefix_tokens'],'native_branch_task_limit':5_000_000-actual[0],'remaining_branch_token_limit':5_000_000-state['prefix_tokens']-actual[0],'no_reference_patch_or_hidden_test':True,'generator_prompt_sha256':__import__('hashlib').sha256(GENERATOR_INSTRUCTION.encode()).hexdigest()}
   assert bank['remaining_branch_token_limit']>0;save(out/'candidate-bank.json',bank);result.update(status='candidate_bank_ready',bank=reference(out/'candidate-bank.json'),actual_tokens=actual[0],actual_cost_CNY_upper=actual[1]/1e9)
 except BaseException as e:result.update(status='technical_unknown',error={'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
 finally:
  if admitted:ledger.close(slot)
  result['finished']=time.time();save(out/'result.json',result)
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--index',type=int,required=True);p.add_argument('--prefix',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--required',type=int,choices=[1,2],default=1);main(p.parse_args())
