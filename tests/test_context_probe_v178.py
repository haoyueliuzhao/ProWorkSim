import copy
from proworksim.software_context_probe_v178 import evaluate,input_payload


def fixture():
    case={'expected':{'status':'recovered','scope':'historical','facts':{'test_passed':False},
        'decision_checks':{'can_validate_current':False}},
        'citation_inventory':{'ctx:a':{'kind':'original_closed_private_history','message_offsets':[
            {'message_index':17,'start':10,'end':9000}]}},
        'fact_evidence_ranges':{'test_passed':[{'reference':'ctx:a','message_index':17,'start':100,'end':120}]}}
    answer={**copy.deepcopy(case['expected']),'evidence':[{'reference':'ctx:a','message_index':17}]}
    reads=[{'ok':True,'result':{'reference':'ctx:a','start':80,'text':'x'*60}}]
    return case,answer,reads


def test_needed_partial_evidence_is_sufficient_and_unread_fact_is_not():
    c,a,r=fixture();assert evaluate(c,a,r)['passed']
    r[0]['result']['start']=0;assert not evaluate(c,a,r)['passed']


def test_fabricated_extra_citation_fails_even_when_answer_is_correct():
    c,a,r=fixture();a['evidence'].append({'reference':'ctx:a','message_index':0})
    result=evaluate(c,a,r);assert not result['passed'] and result['invalid_citations']


def test_boolean_count_and_unknown_remain_distinct():
    c,a,r=fixture();a['facts']['test_passed']=0;assert not evaluate(c,a,r)['passed']
    c['expected']['facts']['test_passed']=None;a['facts']['test_passed']='unknown'
    assert not evaluate(c,a,r)['passed']


def test_unknown_value_is_not_leaked_through_model_schema():
    c={'case_id':'r10','question':'Recover tests_run','summary':'summary','current_snapshot':{},
       'expected':{'facts':{'tests_run':None},'decision_checks':{'count_known':False}}}
    first=input_payload(c)['messages'][-1]['content']
    c['expected']['facts']['tests_run']=3;c['expected']['decision_checks']['count_known']=True
    assert input_payload(c)['messages'][-1]['content']==first
