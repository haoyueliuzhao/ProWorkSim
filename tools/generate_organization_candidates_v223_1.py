"""One paid proposal plus at most one legality repair; never outcome-selected."""
import argparse,json,time,traceback
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.work_interface import _schema_errors
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_organization_api_v223_1 import Ledger,Backend,DirectHTTPS
from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_organization_generator_v219 import GENERATOR_INSTRUCTION,mutable_tasks
from proworksim.software_organization_planning_v223 import VERSION,tool as contextual_tool,parse as parse_proposal
from proworksim.software_organization_generator_v217 import compile_target
from proworksim.software_organization_generator_v216 import target_id
from proworksim.software_organization_opportunity_v218 import distinct_structure,structure
from proworksim.storage import digest
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v223-1/protocol-r1'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);slot='v223.1:'+out.parent.name+':'+out.name;ledger=Ledger(a.ledger);result={'status':'preparing','slot':slot,'started':time.time()};save(out/'result.json',result);admitted=False
 try:
  for ref in json.loads((P/'deployment-freeze.json').read_text())['files']:checked(ref)
  state=json.loads((a.prefix/'decision-state.json').read_text());assert state['eligible']
  shared=a.prefix.parent/'GRAPH';review=json.loads((shared/'result.json').read_text());assert review['status']=='graph_context_ready'
  state=json.loads(checked(review['state']).read_text());graph_tokens=review['shared_graph_tokens']
  row=next(r for r in json.loads((P/'candidate-tasks.json').read_text())['rows'] if r['index']==a.index)
  cfg=json.loads(checked(row['configuration']).read_text());save(out/'condition-state.json',state)
  graph=state['graph'];TOOL=contextual_tool(state);public={'problem_statement':cfg['public_task']['problem_statement'],'public_requirement_anchors':row['requirements'],'actual_decision_state':state}
  public['allowed_mutable_work']={k:{'scope':w['scope'],'owner':w['owner'],'mode':w.get('mode','implementation')} for k,w in mutable_tasks(state).items()};public['immutable_work_ids']=sorted(set(state['graph']['work'])-set(mutable_tasks(state)));save(out/'generator-visible-input.json',public)
  tok=R/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';counter=OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256']);backend=Backend(out/'physical-api',ledger,slot,counter,DirectHTTPS(load_api_key(R/'.env'),timeout_seconds=1800),{'propose_organization'})
  ledger.admit(slot,200_000);admitted=True;messages=[{'role':'system','content':GENERATOR_INSTRUCTION+' This pilot seeks only grounded differences in scope, owner, implementation/evidence mode or dependency. Filling missing verifier/collaboration setup alone is already permitted under KEEP and is not a separate structural alternative. Return fewer or zero alternatives when evidence does not justify change. Never invent a transfer or dependency just to qualify. Evidence levels: E1 records an actual receipt or ledger state, not proven semantic coverage; E2 is static syntax/reference, not runtime dependency; E3 is an unverified hypothesis. Historical version evidence must not be used as current verification. Proposals do not execute; current actors may decline. Prefer KEEP if changes lack support.'},{'role':'user','content':json.dumps(public,ensure_ascii=False)}];valid={};failures=[];candidate_counts=[];component_counts=[];assessment=None
  messages[0]['content'] += ' Return assessment={decision:propose|keep|defer,demand_types:[supported kind],reason:...} together with candidates. An organization demand is not proof of an executable beneficial intervention. Both arms share the identical graph and grammar; never execute a world tool here.'
  worker_history=None
  if a.condition=='W0':
   worker_history=json.loads((a.prefix/'worker-seen-context.json').read_text());checked(worker_history['source'])
   messages[0]['content'] += ' You are the existing worker member_001 reflecting on your actual prior context. This is a bounded proposal readout, not a new autonomous member.'
   messages.insert(1,{'role':'user','content':'Your actual previously submitted model-input history (quoted evidence, not current tool calls):\n'+json.dumps(worker_history['messages'],ensure_ascii=False)})
  else:messages[0]['content'] += ' You are an independent Organizational Architect, a read-only logical role. You receive no worker-private conversation history. Judge the supplied common state and propose or retain the arrangement.'
  save(out/'proposer-context-boundary.json',{'condition':a.condition,'worker_seen_context':reference(a.prefix/'worker-seen-context.json') if worker_history else None,'common_graph':review['state'],'same_graph':True,'role_and_history_bundle':True,'no_third_world_member':True})
  for attempt in range(2):
   wire={'model':'deepseek-flash','thinking':{'type':'disabled'},'temperature':1.0,'top_p':1.0,'stream':False,'max_tokens':8192,'tools':[TOOL],'tool_choice':'auto','messages':messages}
   measurement={}
   for label,content in [('project_relations',state['project_relations']),('navigation',state['navigation']),('proposal_tool_schema',TOOL)]:
    measured=counter.measure({'model':'deepseek-flash','thinking':{'type':'disabled'},'messages':[{'role':'user','content':json.dumps(content,ensure_ascii=False)}]})
    measurement[label]={'local_encoded_tokens_including_separate_message_frame':measured['local_encoded_prompt_tokens'],'exact_provider_component_tokens':False}
   component_counts.append({'attempt':attempt,'components':measurement,'repeated_presentations_counted':True,'not_additive_to_authoritative_usage':True})
   save(out/'input-component-estimates.json',component_counts)
   body=backend.post('/chat/completions',{'team_slot_id':slot,'member_id':'member_001','usage_id':'agent','wire':wire});save(out/f'generated-{attempt}.json',body);errors=[];candidate_count=None
   try:
    calls=body['choices'][0]['message'].get('tool_calls') or []
    if len(calls)!=1 or calls[0]['function']['name']!='propose_organization':raise ValueError('Exactly one proposal tool payload required')
    args,proof=parse_proposal(calls[0]['function']['arguments'],state);save(out/f'normalization-{attempt}.json',proof);save(out/f'assessment-{attempt}.json',args['assessment']);assessment=args['assessment'];err=_schema_errors(TOOL['function']['parameters'],args)
    if err:raise ValueError('; '.join(err))
    candidate_count=len(args['candidates'])
    for i,proposal in enumerate(args['candidates']):
     try:
      candidate=compile_target(state,proposal)
      from proworksim.software_organization_demand_v223 import inspect_state
      if any(op['tool']=='offer_joint_arrangement' for op in candidate['actions']) and not inspect_state(state)['joint_action_preconditions_present']:raise ValueError('No actual joint-arrangement execution window')
      if not distinct_structure(state,candidate):raise ValueError('Setup-only alternative is not structurally distinct from KEEP')
      for action in candidate['actions']:
       arguments=action.get('arguments',{'offer_id':'actual-receipt-placeholder-for-schema-only'})
       errors_schema=_schema_errors(state['proposal_tool_schemas'][action['tool']],arguments)
       if errors_schema:raise ValueError('; '.join(errors_schema))
      valid.setdefault(digest(json_bytes(structure(candidate['target']))),candidate)
     except (ValueError,KeyError,TypeError) as e:errors.append({'candidate_position':i,'reason':str(e)})
   except (ValueError,KeyError,TypeError) as e:errors.append({'response_error':str(e)})
   candidate_counts.append(candidate_count);failures.append({'attempt':attempt,'errors':errors,'parsed_candidate_count':candidate_count})
   if not errors or valid:break
   messages.append(body['choices'][0]['message'])
   for call in body['choices'][0]['message'].get('tool_calls',[]):messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps({'errors':errors,'exact_mutable_ids':sorted(mutable_tasks(state))})})
   messages.append({'role':'user','content':'One permitted format/legality correction only. Errors: '+json.dumps(errors,ensure_ascii=False)+'. Return up to two valid alternatives, or fewer if none other can be grounded. Do not invent transfers, relations or outcomes.'})
  with ledger.db() as c:actual=c.execute('SELECT COALESCE(sum(tokens),0),COALESCE(sum(cost),0) FROM requests WHERE slot=? AND status="settled"',(slot,)).fetchone()
  save(out/'generator-diagnostics.json',{'format_and_compile_failures':failures,'live_execution_validity':'unknown_until_actual_receipts','generated_candidate_count':sum(n for n in candidate_counts if n is not None),'unparseable_response_count':sum(n is None for n in candidate_counts),'unknown_candidate_count_not_zero':True,'valid_candidates':list(valid.values()),'generator_version':VERSION,'invalid_does_not_mean_infeasible':True})
  if assessment is None:assessment={'decision':'keep','demand_types':[],'reason':'No valid decision payload after the bounded repair; fallback preserves structure, not a substantive OA endorsement.'}
  keep={'candidate_id':'KEEP-'+target_id(graph),'keep':True,'reason':assessment['reason'] if assessment['decision'] in ('keep','defer') else 'No eligible structural alternative retained; keep current owners and perform ordinary setup.','actions':[],'target':graph,'host_execution':False,'source_project_graph':state['project_relations']['graph_id']}
  candidates={'KEEP':keep,**{'C'+str(i+1):c for i,c in enumerate(list(valid.values())[:2])}}
  for candidate in candidates.values():candidate['decision_assessment']=assessment
  bank={'decision_assessment':assessment,'version':VERSION,'source_state':reference(a.prefix/'decision-state.json'),'checkpoint':reference(a.prefix/'checkpoint/manifest.json'),'candidates':candidates,'actual_generator_tokens':actual[0],'actual_generator_cost_CNY_upper':actual[1]/1e9,'prefix_tokens':state['prefix_tokens'],'shared_graph_tokens':graph_tokens,'shared_graph_state':review['state'],'remaining_branch_token_limit':5_000_000-state['prefix_tokens']-graph_tokens-actual[0],'selection_rule':'first compiler-valid structural alternative in model order, else KEEP; no outcome-conditioned choice','selected':'C1' if len(candidates)>1 else 'KEEP','information_condition':a.condition,'static_valid_does_not_prove_live_action_enabled':True,'coverage_limited':len(candidates)<3,'generator_received_graph_id':state['project_relations']['graph_id'],'generator_visible_input':reference(out/'generator-visible-input.json')}
  assert bank['remaining_branch_token_limit']>0;save(out/'candidate-bank.json',bank);result.update(status='candidate_bank_ready',candidate_count=len(candidates),bank=reference(out/'candidate-bank.json'),actual_tokens=actual[0],actual_cost_CNY_upper=actual[1]/1e9)
 except BaseException as e:result.update(status='technical_unknown',error={'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
 finally:
  if admitted:ledger.close(slot)
  result['finished']=time.time();save(out/'result.json',result)
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--index',type=int,required=True);p.add_argument('--condition',choices=['W0','W1'],required=True);p.add_argument('--prefix',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);main(p.parse_args())
