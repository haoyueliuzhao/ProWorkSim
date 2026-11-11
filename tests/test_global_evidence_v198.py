import copy,json
import pytest
from test_context_graph_v196 import start,call,public_result,version,build,old_failed_prefix
from proworksim.software_evidence_entities_v198 import EvidenceEntities
from proworksim.software_global_evidence_v198 import enrich,project,mandatory_events
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_selection_v196 import baseline,candidates

def entities(g):return EvidenceEntities(g.snapshot(),repo='example/repo',base_commit='a'*40,issue_id='issue-1')
def read_piece(ms,path,text,a,z,total,ver=1):
    call(ms,'read_file',{'path':path},{'path':path,'source_reference':version(ver),'text':text,'start_character':a,'end_character':z,'total_characters':total})
def project_fixture(p,condition='G2',budget=4096):
    g=build(p);enrich(g,p,list(range(len(p['messages']))));en=entities(g);store=SourceLabeledHistoryReader('point','episode','member_001')
    value,proof,pool=project(p,condition,g,en,store,count=lambda s:(len(s)+3)//4,measure=lambda v:(len(json.dumps(v))+3)//4,indices=list(range(len(p['messages']))),budget=budget)
    return value,proof,pool

def test_partial_class_body_cannot_be_a_fully_qualified_symbol():
    ms=start();text='    def method(self):\n        return 1\n';read_piece(ms,'a.py',text,50,50+len(text),1000)
    en=entities(build({'messages':ms}));assert not any(e['kind']=='Symbol' for e in en.entities.values())
    assert any(e['kind']=='Reference' and e['attrs']['qualified_name'] is None for e in en.entities.values())

def test_complete_same_version_pieces_resolve_exact_qualified_names_and_signature():
    ms=start();text='class A:\n    def f(self, x):\n        return x\nclass B:\n    def f(self):\n        return 1\n';split=30
    read_piece(ms,'a.py',text[:split],0,split,len(text));read_piece(ms,'a.py',text[split:],split,len(text),len(text))
    en=entities(build({'messages':ms}));syms=[e for e in en.entities.values() if e['kind']=='Symbol']
    assert {'A','A.f','B','B.f'}=={e['identity']['qualified_name'] for e in syms}
    assert all(e['identity']['revision']['base_commit']=='a'*40 for e in syms)
    assert len({e['id'] for e in syms})==4

def test_fragments_of_different_versions_are_never_stitched():
    ms=start();text='def f(x):\n    return x\n';read_piece(ms,'a.py',text[:10],0,10,len(text),1);read_piece(ms,'a.py',text[10:],10,len(text),len(text),2)
    en=entities(build({'messages':ms}));assert not en.full_files

def test_conflicting_overlap_is_recorded_not_chosen_silently():
    ms=start();read_piece(ms,'a.py','def f():\n',0,9,15);read_piece(ms,'a.py','WRONG',4,9,15)
    en=entities(build({'messages':ms}));assert en.fragments[0]['conflict'] and not en.full_files

def test_cross_file_resolution_remains_inferred_even_with_complete_text():
    ms=start();a='from pkg.b import f\ndef g():\n    return f()\n';b='def f():\n    return 1\n'
    read_piece(ms,'pkg/a.py',a,0,len(a),len(a));read_piece(ms,'pkg/b.py',b,0,len(b),len(b))
    en=entities(build({'messages':ms}));links=[e for e in en.edges.values() if e['relation_type']=='resolves_to']
    assert links and all(e['verification_status']=='Inferred' and not e['runtime_dispatch_verified'] for e in links)
    assert all(e['evidence_source_ids'] for e in en.edges.values())

def test_test_definition_is_not_an_execution_and_reruns_are_distinct():
    ms=start();call(ms,'run_tests',{'selection':{'kind':'pytest','targets':['test_a.py::test_x']}},public_result('r1',text='FAILED test_a.py::test_x'))
    call(ms,'run_tests',{'selection':{'kind':'pytest','targets':['test_a.py::test_x']}},public_result('r2',text='FAILED test_a.py::test_x'))
    en=entities(build({'messages':ms}));assert sum(e['kind']=='TestRun' for e in en.entities.values())==2
    assert sum(e['kind']=='TestDefinition' for e in en.entities.values())==1

def test_open_world_inventory_adds_previously_unmodeled_search_feedback():
    p=old_failed_prefix();call(p['messages'],'search_repository',{'text':'global evidence'}, {'matches':[{'path':'other.py','line':7,'text':'evidence outside current paths'}]})
    g=build(p);info=enrich(g,p,list(range(len(p['messages']))))
    assert any(x['kind']=='search' for x in info['new_observations'])
    assert any(f['name']=='matches_text' for e in g.events.values() for f in e['fields'])

def test_global_candidate_pool_is_identical_for_all_five_conditions():
    p=old_failed_prefix();proofs=[project_fixture(p,c)[1] for c in ['G0','G1','G2','G3','G4']]
    assert len({r['candidate_pool_sha256'] for r in proofs})==1
    assert all(r['hard_path_eligibility'] is False and r['hard_card_cap'] is None for r in proofs)

def many_failed_tests():
    p={'messages':start(),'tools':[]}
    p['messages'].append({'role':'user','content':json.dumps({'observation':{'workspace_reference':version(1)}})})
    for i in range(10):call(p['messages'],'run_tests',{'selection':{'kind':'pytest','targets':[f'test_{i}.py']}},public_result(f'r{i}'))
    for i in range(6):read_piece(p['messages'],'unrelated.py','# new observation\n'*80,0,len('# new observation\n'*80),len('# new observation\n'*80))
    return p

def test_more_than_eight_real_failed_reports_can_be_covered_without_path_gate():
    _,proof,_=project_fixture(many_failed_tests())
    assert len(proof['mandatory'])==10
    assert len(proof['selected'])>8 and proof['coverage_constraint_satisfied']

def test_infeasible_coverage_is_reported_instead_of_silent_success():
    _,proof,_=project_fixture(many_failed_tests(),budget=1024)
    assert proof['unmet_mandatory'] and not proof['coverage_constraint_satisfied']
    assert proof['added_tokens_estimate']<=1024

def test_later_success_only_supersedes_same_exact_selector():
    p=many_failed_tests();call(p['messages'],'run_tests',{'selection':{'kind':'pytest','targets':['test_0.py']}},public_result('pass',2,True))
    for _ in range(6):read_piece(p['messages'],'unrelated.py','# filler\n'*80,0,720,720,2)
    _,proof,_=project_fixture(p)
    assert len(proof['mandatory'])==9

def test_registry_export_does_not_mutate_old_snapshot():
    g=build(old_failed_prefix());en=entities(g);first=en.as_json();before=json.dumps(first,sort_keys=True)
    en.entities.clear();assert json.dumps(first,sort_keys=True)==before
    assert not first['runtime_resolution_claimed']

def test_foreign_or_future_source_cannot_become_a_private_entity():
    from proworksim.software_context_graph_v196 import GraphScopeError,GraphIntegrityError
    s=build(old_failed_prefix()).snapshot();source=next(iter(s['sources'].values()));source['scope']=['foreign','member_001']
    with pytest.raises(GraphScopeError):EvidenceEntities(s,repo='example/repo',base_commit='a'*40,issue_id='x')
    source['scope']=s['scope'];source['first_seen_step']=s['step']+1
    with pytest.raises(GraphIntegrityError):EvidenceEntities(s,repo='example/repo',base_commit='a'*40,issue_id='x')

def test_same_file_name_in_different_commits_cannot_alias():
    s=build(old_failed_prefix()).snapshot();a=EvidenceEntities(s,repo='example/repo',base_commit='a'*40,issue_id='x');b=EvidenceEntities(s,repo='example/repo',base_commit='b'*40,issue_id='x')
    assert a.file('a.py',version(1))!=b.file('a.py',version(1))

def test_unexecuted_report_is_not_validation_or_mandatory_actual_failure():
    p={'messages':start(),'tools':[]};r=public_result('not-started');r['executed']=False
    call(p['messages'],'run_tests',{'selection':{'kind':'full'}},r)
    g=build(p);en=entities(g)
    assert not any(e['relation_type']=='validates' for e in en.edges.values())
    eid=next(e['id'] for e in g.events.values() if e['kind']=='test')
    assert not mandatory_events(g,[{'event_id':eid}])
