import copy,pytest
from test_organization_space_v210 import state,op
from proworksim.software_organization_space_v210 import proposal
from proworksim.software_organization_equivalence_v210_1 import normalize,deduplicate,novelty

def split():return proposal(state(),[op('SPLIT_WORK',task='root',children={'x':{'scope':['parser']},'y':{'scope':['serializer']}})])['target']
def test_task_rename_and_edge_permutation_same_semantics():
 s=split();t=copy.deepcopy(s);t['work']={'foo':t['work'].pop('x'),'bar':t['work'].pop('y')};t['execution_order']=['foo','bar'];t['collaboration'].reverse()
 assert normalize(s)['sha256']==normalize(t)['sha256']
 assert len(deduplicate([{'target':s},{'target':t}]))==1
 t['execution_order'].reverse();assert normalize(s)['sha256']!=normalize(t)['sha256']
def test_do_not_erase_owner_or_public_scope_to_claim_equivalence():
 s=split();t=copy.deepcopy(s);t['work']['x']['owner']='b';assert normalize(s)['sha256']!=normalize(t)['sha256']
 t=copy.deepcopy(s);t['work']['x']['scope'],t['work']['y']['scope']=t['work']['y']['scope'],t['work']['x']['scope'];assert normalize(s)['sha256']!=normalize(t)['sha256']
def test_novelty_aggregates_equivalent_structure_mass_not_id_count():
 q={'x':.1,'y':.4,'z':.5};r={'x':.25,'y':.25,'z':.5};f={'x':{'struct':'A','combo':'split'},'y':{'struct':'A','combo':'split'},'z':{'struct':'B','combo':'transfer'}}
 assert all(v['combined']==0 for v in novelty(q,r,f).values())
