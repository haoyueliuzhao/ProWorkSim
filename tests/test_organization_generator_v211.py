from proworksim.software_organization_generator_v211 import generate

def test_generated_scope_and_cross_review_for_every_configuration():
 x=generate(['a','b','c'],seed=211)
 assert len(x['candidate_bank'])>3
 for p in x['candidate_bank']:
  scope=[s for t in p['target']['tasks'] for s in t['scope']]
  assert sorted(scope)==['a','b','c']
  assert all(t['owner']!=t['reviewer'] for t in p['target']['tasks'])
 assert x==generate(['c','b','a'],seed=211)
 assert x['selected']['O1']['candidate_id']!=x['selected']['O2']['candidate_id']
 assert x['selected']['O1']['distinct_owners']==2

def test_dependencies_bind_generated_work_and_receipt_refs_remain_explicit():
 x=generate(['api','render'],seed=1,dependencies=[('render','api')])
 for p in x['candidate_bank']:
  tasks={t['task_id'] for t in p['target']['tasks']}
  assert all(a in tasks and b in tasks for a,b in p['target']['dependencies'])
  for a in p['actions']:
   if a['tool']=='accept_transfer':assert 'arguments_from_real_receipt' in a and 'arguments' not in a


def test_all_immediate_generated_arguments_match_real_harness_schema():
 from proworksim.software_organization_world_v211 import NEW_TOOLS
 from proworksim.work_interface import _schema_errors
 definitions={t['name']:t for t in NEW_TOOLS}
 x=generate(['a','b','c'],seed=2,dependencies=[('b','a')])
 for p in list(x['candidate_bank'])+[x['selected']['O0']]:
  for a in p['actions']:
   if 'arguments' in a:
    assert not _schema_errors(definitions[a['tool']]['parameters'],a['arguments']),a
