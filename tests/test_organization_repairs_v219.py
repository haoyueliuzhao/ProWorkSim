import json,copy
from pathlib import Path
from types import SimpleNamespace as S
import pytest
from proworksim.software_organization_generator_v219 import parse_proposal,validated_candidates
from proworksim.software_organization_runtime_v219 import rejection_proof

def test_five_historical_generators_have_grounded_alternatives_without_api():
 root=Path('runs/software-benchmark-v218/pilot8-r1')
 for i in (1,4,5,6,7):
  g=root/f'task-{i:02d}/GENERATOR';state=json.loads((g/'generator-visible-input.json').read_text())['actual_decision_state'];found={}
  before=copy.deepcopy(state)
  for a in (0,1):
   raw=json.loads((g/f'generated-{a}.json').read_text())['choices'][0]['message']['tool_calls'][0]['function']['arguments']
   try:v,errors,proof=validated_candidates(raw,state);found.update(v)
   except ValueError:continue
  assert found and state==before
@pytest.mark.parametrize('raw',['{"candidates":[]} {"owner":"evil"}','{"candidates":[],"candidates":[]}','{"candidates":[]} null'])
def test_ambiguous_or_semantic_json_rejected(raw):
 with pytest.raises(ValueError):parse_proposal(raw,{'graph':{'work':{}}})
def test_input_error_proof_does_not_relax_execution_integrity():
 c={'id':'c1','type':'function','function':{'name':'offer_joint_arrangement','arguments':'{"action":"wait"}'}}
 w=S(_executions=0,_pending=None,_result=None,_last_body={'id':'r1','choices':[{'message':{'role':'assistant','tool_calls':[c]}}]},_association={'call_id':'m1'},_assistant_messages={},schemas={'offer_joint_arrangement':{}})
 assert rejection_proof(w)['record']['arguments_stripped'] is False
 w._executions=1;assert rejection_proof(w) is None
 w._executions=0;w._pending={};assert rejection_proof(w) is None
 w._pending=None;w._assistant_messages={'c1':{}};assert rejection_proof(w) is None
 w._assistant_messages={};c['function']['name']='forbidden_admin_tool';assert rejection_proof(w) is None

def test_immutable_owner_change_cannot_be_repaired_away():
 g=Path('runs/software-benchmark-v218/pilot8-r1/task-01/GENERATOR')
 state=json.loads((g/'generator-visible-input.json').read_text())['actual_decision_state']
 data=json.loads(json.loads((g/'generated-0.json').read_text())['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
 work=data['candidates'][0]['remaining_work'][0];tid=work['source_task_id'];assert state['graph']['work'][tid]['authors']
 work['parts'][0]['owner']='member_002'
 with pytest.raises(ValueError,match='immutable'):parse_proposal(json.dumps(data),state)
