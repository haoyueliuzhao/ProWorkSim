"""Synthetic graph examples; no repository task, SDK, model, Docker or host action."""
from pathlib import Path
import json
from proworksim.software_organization_space_v210 import proposal,CAPABILITIES,update_bank,structured_reference
R=Path(__file__).resolve().parents[1];O=R/'artifacts/software-benchmark-v210/protocol-r2'
s={'members':{'member_001':{'status':'live'},'member_002':{'status':'live'}},'delivery_member':'member_001','requirements':['public-parser-contract','public-serializer-contract'],'roles':{'member_001':['implement'],'member_002':['review']},'work':{'whole':{'scope':['public-parser-contract','public-serializer-contract'],'owner':'member_001','contributors':[],'authors':[],'status':'open'}},'dependencies':[],'collaboration':[['member_001','member_002'],['member_002','member_001']],'execution_order':['whole'],'verification':{},'subteams':{}}
def op(name,actor,**args):return {'op':name,'actor':actor,'args':args}
examples=[proposal(s,[]),proposal(s,[op('CREATE_ROLE','member_002',member='member_002',roles=['implement','review']),op('SPLIT_WORK','member_001',task='whole',children={'parser':{'scope':['public-parser-contract']},'serializer':{'scope':['public-serializer-contract']}}),op('ASSIGN_WORK','member_001',task='parser',member='member_001'),op('ASSIGN_WORK','member_002',task='serializer',member='member_002')]),proposal(s,[op('CREATE_ROLE','member_001',member='member_001',roles=['coordinate','review','integrate']),op('TRANSFER_OWNERSHIP','member_001',task='whole',member='member_002'),op('ASSIGN_VERIFICATION','member_001',task='whole',member='member_001')])]
for x in examples:x['coverage_family']='+'.join(x['coverage_signature'])
r=structured_reference(examples,{x['coverage_family']:1 for x in examples})
result={'synthetic_only':True,'not_three_fixed_experimental_candidates':True,'not_runtime_admitted':True,'examples':examples,'capabilities':CAPABILITIES,'illustrative_bank_reference':r,'illustrative_zero_quality_update':update_bank(r,r,{k:0 for k in r}),'new_real_model_calls':0}
(O/'synthetic-examples.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('3 synthetic proposals; 12 operator mappings; 0 API / 0 Docker')
