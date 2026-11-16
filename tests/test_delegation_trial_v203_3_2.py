from proworksim.software_delegation_trial_v203_3_2 import eligible_state,summarize,endpoint

def test_completed_diagnosis_is_a_no_intervention_control_not_an_extra_pair():
    row={'source':'natural','diagnosis_status':'unfinished','prefix_evidence':['event'],
        'permanent_environment_failure':False,'KEEP_legal':True,'REASSIGN_legal':True,'SDK_resume_qualified':True}
    assert eligible_state(row)['admitted']
    assert not eligible_state({**row,'diagnosis_status':'completed','next_work':['nonempty']})['admitted']
    assert not eligible_state({**row,'source':'common_preparation','prepared_before_split':False})['admitted']

def test_ITT_keeps_declines_deviations_unknowns_and_prefix_failures_in_the_accounts():
    prefixes=[{'candidate_id':'s1','cost_CNY':'2'},{'candidate_id':'rejected','cost_CNY':'1'}]
    base={'candidate_id':'s1','cost_CNY':'3','legal_delivery':True,'delivery_official_resolved':True,'score_bound_to_submitted_version':True}
    rows=[{**base,'run_id':'keep','assigned_arm':'KEEP'},
          {**base,'run_id':'declined','assigned_arm':'REASSIGN','transfer_accepted':False},
          {**base,'run_id':'deviation','assigned_arm':'REASSIGN','protocol_deviation':True,'delivery_official_resolved':False},
          {**base,'run_id':'unknown','assigned_arm':'REASSIGN','technical_unknown':True}]
    r=summarize(prefixes,rows)
    assert r['actual_experiment_cost_CNY']=='15'
    assert all(v['full_task_cost_CNY']=='5' for v in r['per_branch_full_task_costs'])
    assert r['ITT']['REASSIGN']['planned']==3
    assert r['ITT']['REASSIGN']['success']==1 and r['ITT']['REASSIGN']['failure']==1
    assert r['ITT']['REASSIGN']['unknown']==1 and r['ITT']['REASSIGN']['success_rate'] is None
    assert r['ITT']['REASSIGN']['noncompliant_branches_excluded']==0

def test_final_worktree_pass_does_not_grade_another_submitted_version():
    assert endpoint({'legal_delivery':True,'official_code_resolved':True}) is None
    assert endpoint({'legal_delivery':False,'official_code_resolved':True})==0
    assert endpoint({'legal_delivery':True,'official_code_resolved':True,
        'delivery_official_resolved':False,'score_bound_to_submitted_version':True})==0

def test_unsettled_cost_is_reported_without_zero_fill_or_stopping_other_results():
    r=summarize([{'candidate_id':'s','cost_CNY':'2'}],
        [{'candidate_id':'s','run_id':'pending','assigned_arm':'KEEP','cost_CNY':None,'technical_unknown':True}])
    assert r['actual_experiment_cost_CNY'] is None and r['known_cost_CNY']=='2'
    assert r['unresolved_cost_records']==1 and r['ITT']['KEEP']['unknown']==1
