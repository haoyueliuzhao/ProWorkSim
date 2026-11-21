import copy,json,sqlite3
from pathlib import Path
import pytest
from proworksim.software_organization_proposal_budget_v223_2 import output_allocation,prepare_dispatch,correction_request,fallback_assessment
from proworksim.software_organization_api_v223_2 import Ledger,NEW,OLD
R=Path(__file__).resolve().parents[1]

def test_actual_failing_request_fits_by_lowering_only_output_cap():
 p=R/'artifacts/software-benchmark-v223-2/protocol-r1';plan=json.loads((p/'recovery-plan.json').read_text());raw=json.loads(Path(plan['repair_wire_before_allocation']['path']).read_text());adjusted=json.loads(Path(plan['repair_wire']['path']).read_text());q=json.loads((p/'allocation.json').read_text())
 assert q['prompt_upper_including_existing_margin']==97006 and q['remaining_stage_tokens']==103222
 assert q['max_tokens']==6216 and q['dispatch'];assert 96778+97006+6216==200000
 before=copy.deepcopy(raw);expected=copy.deepcopy(raw);expected['max_tokens']=6216
 class Counter:
  def measure(self,value):return {'prompt_tokens':97006}
 new,quote=prepare_dispatch(raw,Counter(),103222)
 assert new==adjusted==expected and raw==before and quote==q

def test_zero_remaining_input_limit_and_small_output_are_explicit():
 assert not output_allocation(97006,97006)['dispatch']
 assert not output_allocation(98305,200000)['dispatch']
 assert output_allocation(97006,97007)['max_tokens']==1
 assert output_allocation(1000,20000)['max_tokens']==8192
 a=fallback_assessment('no_output_allowance');assert a['decision']=='keep' and 'not a valid model endorsement' in a['reason']
 with pytest.raises(ValueError):output_allocation(-1,10)

def test_saved_invalid_first_response_is_not_silently_relabelled_valid():
 p=R/'runs/software-benchmark-v223-1/paired4-r1/task-03/GEN-W0';reqs=list((p/'physical-api').glob('*/request.json'));assert len(reqs)==1
 request=json.loads(reqs[0].read_text());response=json.loads((p/'generated-0.json').read_text());state=json.loads((p/'condition-state.json').read_text());old=copy.deepcopy(request)
 wire,errors=correction_request(request,response,state)
 assert request==old and errors==[{'response_error':'KEEP/DEFER must not simultaneously propose changes'}]
 assert wire['messages'][:len(request['payload']['wire']['messages'])]==request['payload']['wire']['messages']
 valid=copy.deepcopy(response);valid['choices'][0]['message']['tool_calls'][0]['function']['arguments']=json.dumps({'candidates':[],'assessment':{'decision':'keep','demand_types':[],'reason':'Valid original KEEP'}})
 with pytest.raises(ValueError,match='already valid'):correction_request(request,valid,state)

def ledger(tmp_path):
 p=tmp_path/'ledger';c=sqlite3.connect(p);c.executescript('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE slots(id TEXT PRIMARY KEY,token_limit INTEGER,status TEXT,hold INTEGER);CREATE TABLE requests(id TEXT PRIMARY KEY,slot TEXT,status TEXT,cost INTEGER,tokens INTEGER,body TEXT,provider_id TEXT UNIQUE);CREATE TABLE block_slots(slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT);INSERT INTO meta VALUES("cap","1100000000000");')
 for stage,n in [('PREFIX',1137344),('GRAPH',12355),('GEN-W0',96778)]:
  s=OLD+stage;c.execute('INSERT INTO slots VALUES(?,2000000,"closed",0)',(s,));c.execute('INSERT INTO requests VALUES(?,?,"settled",?,?,NULL,?)',(s,s,n*1000,n,s))
 c.commit();c.close();return Ledger(p)

def test_recovery_retains_all_old_spend_and_never_reissues_old_stage(tmp_path):
 l=ledger(tmp_path);before=l.snapshot()['settled_total_CNY_upper'];assert l.reserve_recovery()==3753523
 with pytest.raises(ValueError):l.reserve_recovery()
 s=NEW+'REPAIR-W0';n=l.reserve_stage(s);assert n==103222;l.admit(s,n)
 with l.db() as c:c.execute('INSERT INTO requests VALUES("repair",?,"settled",100000000,98000,NULL,"repair")',(s,))
 l.close(s);native=NEW+'W0';n=l.reserve_stage(native);assert n==3655523 and n+98000+96778+12355+1137344==5000000
 l.admit(native,n)
 with l.db() as c:c.execute('INSERT INTO requests VALUES("native",?,"settled",1000000000,1000000,NULL,"native")',(native,))
 l.close(native);assert l.finish();assert l.snapshot()['settled_total_CNY_upper']==pytest.approx(before+1.1)
 with pytest.raises(ValueError):l.reserve_stage(OLD+'W0')

def test_uncertain_request_keeps_hold_and_prevents_dispatch(tmp_path):
 l=ledger(tmp_path);l.reserve_recovery();s=NEW+'REPAIR-W0';n=l.reserve_stage(s);l.admit(s,n);l.reserve(s,'uncertain',1000)
 with pytest.raises(ValueError,match='Uncertain'):l.stage_remaining(s)
 l.close(s);assert not l.finish()
 with pytest.raises(ValueError):l.reserve_stage(NEW+'W0')
