"""One bounded, shared Graph Agent review; E3 claims never become permissions."""
import argparse,json,time,traceback
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_organization_api_v223 import Ledger,Backend,DirectHTTPS
from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_organization_planning_v223 import GRAPH_TOOL,GRAPH_INSTRUCTION,add_hypotheses
from proworksim.software_project_information_v222 import prepare_context
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v223/protocol-r1'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def main(a):
 out=a.output;out.mkdir(parents=True,exist_ok=False);slot='v223:'+out.parent.name+':GRAPH';ledger=Ledger(a.ledger);admitted=False;result={'status':'preparing','started':time.time()}
 try:
  for ref in json.loads((P/'deployment-freeze.json').read_text())['files']:checked(ref)
  raw=json.loads((a.prefix/'decision-state.json').read_text());assert raw['eligible']
  source=json.loads(checked(raw['authorized_generator_source']).read_text());assert source['actor']=='member_001'
  row=next(r for r in json.loads((P/'candidate-tasks.json').read_text())['rows'] if r['index']==a.index)
  state,information=prepare_context(raw,'G',files=source['files'],source_reference=source['source_reference'],entry_metadata=source['entry_metadata'],public_query=row['public_problem'][:4000])
  save(out/'information-audit.json',information);save(out/'base-state.json',state)
  tok=R/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';counter=OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256'])
  backend=Backend(out/'physical-api',ledger,slot,counter,DirectHTTPS(load_api_key(R/'.env'),timeout_seconds=1800),{'annotate_project_graph'})
  wire={'model':'deepseek-flash','thinking':{'type':'disabled'},'temperature':1.0,'top_p':1.0,'stream':False,'max_tokens':4096,'tools':[GRAPH_TOOL],'tool_choice':'auto','messages':[{'role':'system','content':GRAPH_INSTRUCTION},{'role':'user','content':json.dumps({'public_problem':row['public_problem'],'state':state},ensure_ascii=False)}]}
  # One request fits the shared Graph allocation; never silently truncate evidence.
  if counter.measure(wire)['prompt_tokens']+wire['max_tokens']>80_000:raise ValueError('Graph context does not fit frozen review allocation')
  ledger.admit(slot,80_000);admitted=True
  body=backend.post('/chat/completions',{'team_slot_id':slot,'member_id':'member_001','usage_id':'agent','logical_role':'graph_reviewer','wire':wire});save(out/'response.json',body)
  fallback=None
  try:
   calls=body['choices'][0]['message'].get('tool_calls') or []
   if len(calls)!=1 or calls[0]['function']['name']!='annotate_project_graph':raise ValueError('Exactly one Graph review payload required')
   state=add_hypotheses(state,json.loads(calls[0]['function']['arguments']))
  except (ValueError,TypeError,KeyError) as e:fallback={'reason':str(e),'preserved_deterministic_graph':True,'no_retry':True}
  with ledger.db() as c:tokens,cost=c.execute('SELECT COALESCE(sum(tokens),0),COALESCE(sum(cost),0) FROM requests WHERE slot=? AND status="settled"',(slot,)).fetchone()
  save(out/'shared-state.json',state);result.update(status='graph_context_ready',shared_graph_tokens=tokens,shared_graph_cost_CNY_upper=cost/1e9,fallback=fallback,graph_id=state['project_relations']['graph_id'],state=reference(out/'shared-state.json'),physical_paid_once=True,charged_to_each_logical_branch=True,world_actions=0)
 except BaseException as e:result.update(status='technical_unknown',error={'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
 finally:
  if admitted:ledger.close(slot)
  result['finished']=time.time();save(out/'result.json',result)
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--index',type=int,required=True);p.add_argument('--prefix',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);main(p.parse_args())
