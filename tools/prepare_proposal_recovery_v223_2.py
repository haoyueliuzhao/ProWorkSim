"""Seal the unused second proposal request from original pre-score inputs; no API."""
import json,sqlite3
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_organization_proposal_budget_v223_2 import correction_request,prepare_dispatch
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v223-2/protocol-r1';OLD=R/'runs/software-benchmark-v223-1/paired4-r1/task-03';LEDGER=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def main():
 P.mkdir(parents=True,exist_ok=False);g=OLD/'GEN-W0';assert not (OLD/'W0').exists();result=read(g/'result.json');assert result['error']['type']=='PrefixComplete'
 requests=list((g/'physical-api').glob('*/request.json'));assert len(requests)==1;p=requests[0];first=read(p);response=read(p.parent/'response.json');state=read(g/'condition-state.json');wire,errors=correction_request(first,response,state)
 with sqlite3.connect('file:'+str(LEDGER)+'?mode=ro',uri=True) as c:
  assert c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()==('1100000000000',)
  assert not c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone()
  assert not c.execute('SELECT 1 FROM block_slots WHERE status="pending"').fetchone()
  assert not c.execute('SELECT 1 FROM slots WHERE id="v223.1:task-03:W0"').fetchone()
  values={}
  for stage in ('PREFIX','GRAPH','GEN-W0'):
   slot='v223.1:task-03:'+stage;assert c.execute('SELECT status FROM slots WHERE id=?',(slot,)).fetchone()==('closed',)
   rows=c.execute('SELECT status,tokens,cost FROM requests WHERE slot=?',(slot,)).fetchall();assert all(x[0]=='settled' for x in rows)
   values[stage]={'tokens':sum(x[1] for x in rows),'cost_nanoyuan':sum(x[2] for x in rows)}
  assert values['GEN-W0']['tokens']==response['usage']['total_tokens']==96778
  settled=c.execute('SELECT sum(cost) FROM requests WHERE status="settled"').fetchone()[0]
 D=R/'runs/software-benchmark-v223-2/prepared-request-r1';D.mkdir(parents=True,exist_ok=False)
 remain=200_000-values['GEN-W0']['tokens'];tok=R/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';counter=OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256']);adjusted,quote=prepare_dispatch(wire,counter,remain)
 assert quote['dispatch'] and quote['max_tokens']<8192
 save(D/'repair-wire-before-allocation.json',wire);save(D/'repair-wire.json',adjusted);save(P/'allocation.json',quote)
 plan=read(R/'artifacts/software-benchmark-v223-1/protocol-r1/candidate-tasks.json');plan['rows']=[r for r in plan['rows'] if r['index']==3];plan.update(version='v223.2-unused-W0-continuation-recovery-r1',main_states=1,max_main_continuations=1,main_conditions=['W0'],prefix_limit=0,new_prefix_calls=0,new_graph_calls=0,new_logical_repair_calls=1,new_budget=0);save(P/'candidate-tasks.json',plan)
 allowance=5_000_000-sum(v['tokens'] for v in values.values())
 save(P/'recovery-plan.json',{'version':'v223.2-one-unused-correction-and-continuation-r1','index':3,'condition':'W0','old_sources':{'prefix':reference(OLD/'PREFIX/decision-state.json'),'checkpoint':reference(OLD/'PREFIX/checkpoint/manifest.json'),'graph':reference(OLD/'GRAPH/result.json'),'state':reference(g/'condition-state.json'),'first_request':reference(p),'first_response':reference(p.parent/'response.json'),'old_result':reference(g/'result.json')},'old_accounting':values,'old_parse_errors':errors,'remaining_generator_tokens':remain,'maximum_additional_input_output_tokens':allowance,'maximum_additional_CNY':allowance*.000008,'current_remaining_CNY':1100-settled/1e9,'repair_wire':reference(D/'repair-wire.json'),'repair_wire_before_allocation':reference(D/'repair-wire-before-allocation.json'),'quote':reference(P/'allocation.json'),'no_hidden_score_used':True,'old_native_W0_never_admitted':True,'old_calls_not_replayed':True,'old_result_not_overwritten':True,'generation_model':'deepseek-flash','thinking':False})
 print(json.dumps({'quote':quote,'additional_tokens_max':allowance,'additional_CNY_max':allowance*.000008,'API_calls':0}))
if __name__=='__main__':main()
