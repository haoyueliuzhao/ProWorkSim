"""32 authored structural controls, not an independent semantic gold standard."""
import copy

def base():
    return {'step':10,'members':{m:{'live':True,'available':True,'tools':['replace_file','run_tests']} for m in ['member_001','member_002']},
        'tasks':{t:{'owner':m,'required':True,'ownership_record_complete':True,'ready':True,'required_tools':['replace_file'],'last_reassignment':0} for t,m in [('T1','member_001'),('T2','member_002')]},
        'regions':[],'dependencies':[],'initial_dependencies':[],'handoffs':[],'evidence':['controlled-receipt'],'focus':'T1',
        'policy':{'hold_steps':2,'switch_limit':2,'max_proxy_cost_units':4,'candidate_limit':4}}
def dependency(active=True,status='Confirmed Structural',blocked=True):
    return {'upstream':'T1','downstream':'T2','active':active,'status':status,'evidence':['dependency-receipt'],'blocked_due_to_missing_handoff':blocked}
def bottleneck():
    s=base();s['tasks']['T3']={**s['tasks']['T2']};s['dependencies']=[dependency(),{**dependency(),'downstream':'T3'}];s['handoffs']=[['T1','T2'],['T1','T3']]
    s['tasks']['T1'].update(blocked_reason='ownership_capacity',blocked_observations=3,available_alternative=True);s['blocked_event_count']=3;return s
def cases():
    result=[]
    def add(name,s,ops=(),mismatches=()):
        result.append({'id':name,'state':copy.deepcopy(s),'expected_valid_interventions':[{'operation':op,'tasks':list(tasks)} for op,tasks in ops],
            'expected_mismatch_types':list(mismatches),'reference_kind':'authored_development_control_not_independent_human_gold'})
    s=base();s['dependencies']=[dependency()];add('S1a-new-confirmed-dependency',s,[('AddHandoff',['T1','T2'])],['DependencyMisalignment'])
    s=base();s['dependencies']=[dependency(blocked=False)];add('S1b-no-execution-failure',s,mismatches=['DependencyMisalignment'])
    s=base();s['dependencies']=[dependency(status='Inferred')];add('S1c-inferred-only',s)
    s=base();s['dependencies']=[dependency()];s['handoffs']=[['T1','T2']];add('S1d-existing-contract',s)
    s=base();s['tasks']['T1']['owner']=None;add('S2a-explicit-gap',s,[('Reassign',['T1'])],['ResponsibilityGap'])
    s=base();s['same_path_writers']=2;s['regions']=[{'id':'R','owners':['member_001','member_002'],'tasks':['T1','T2'],'exclusive':False,'ownership_evidence':['joint'],'observed_conflict':False}];add('S2b-joint-ownership',s)
    s['regions'][0].update(exclusive=True,observed_conflict=True);add('S2c-exclusive-conflict',s,[('Split',['T1','T2'])],['OwnershipConflict'])
    s=base();s['same_path_writers']=2;add('S2d-editing-not-ownership',s)
    s=base();s['artifact']={'author':'member_001','task':'T1','independent_review_required':True,'adopted':True,'review_accepted':False,'source_bound':True};add('S3a-adopted-unreviewed',s,[('AddReviewer',['T1'])])
    s['artifact']['adopted']=False;add('S3b-published-not-adopted',s)
    s['artifact'].update(adopted=True,review_accepted=True);add('S3c-reviewed',s)
    s['artifact'].update(review_accepted=False,source_bound=False);add('S3d-unbound-artifact',s)
    for label,cause in [('old-pass','environment'),('new-failure','code'),('not-executed','environment'),('same-version-reread','running')]:
        s=base();s['test_state']=label;s['blocked_event_count']=3;s['tasks']['T1']['blocked_reason']=cause;add('S4-'+label,s)
    s=bottleneck();add('S5a-capacity-bottleneck',s,[('Reassign',['T1'])],['CoordinationBottleneck'])
    for label,cause in [('environment','environment'),('waiting-upstream','upstream_wait'),('legitimate-operation','running')]:
        s=bottleneck();s['tasks']['T1']['blocked_reason']=cause;s['ongoing_critical_operation']=label=='legitimate-operation';add('S5-'+label,s)
    for label,status,active,blocked in [('removed','Confirmed Structural',False,True),('stale-revision','Confirmed Structural',False,True),('unknown','Unknown',True,True),('not-yet-blocked','Confirmed Dynamic',True,False)]:
        s=base();s['dependencies']=[dependency(active,status,blocked)];s['initial_dependencies']=[{**dependency(),'owners_differ':True}]
        add('S6-'+label,s,mismatches=['DependencyMisalignment'] if active and status=='Confirmed Dynamic' else [])
    s=base();s.update(merge_evidence=['actual-rework'],regions_coupled=True,observed_handoff_loop=True,predicted_saved_steps=4,merge_cost=1);add('S7a-confirmed-coupling',s,[('Merge',['T1','T2'])])
    s=base();s['same_path_writers']=2;add('S7b-legitimate-coediting',s)
    s=base();s.update(merge_evidence=['actual-rework'],regions_coupled=True,observed_handoff_loop=True,predicted_saved_steps=2,merge_cost=10);add('S7c-expensive-merge',s)
    s=base();s.update(merge_evidence=['actual-rework'],regions_coupled=True,observed_handoff_loop=True,predicted_saved_steps=4,merge_cost=1,independent_reviewers=[{'task':'T2','member':'member_001'}]);add('S7d-preserve-independent-review',s)
    s=bottleneck();s['members']['member_002']['tools']=[];add('S8a-permission-gap',s,mismatches=['CoordinationBottleneck'])
    s=bottleneck();s['tasks']['T1']['last_reassignment']=9;add('S8b-hold-window',s,mismatches=['CoordinationBottleneck'])
    s=bottleneck();s['tasks']['T1']['recent_owner_switches']=2;add('S8c-oscillation',s,mismatches=['CoordinationBottleneck'])
    s=bottleneck();s['tasks']['T1']['blocked_observations']=2;s['blocked_event_count']=2;add('S8d-observation-window',s,[('Reassign',['T1'])],['CoordinationBottleneck'])
    assert len(result)==32
    return result
