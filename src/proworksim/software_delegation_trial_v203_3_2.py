"""Preassigned delegation study: eligibility, ITT denominators and prefix costs.

This validates supplied evidence records, not the semantic truth of diagnosis.
No positive mismatch label or expected winning branch is required.
"""
from collections import defaultdict
from decimal import Decimal

def eligible_state(record):
    if record.get('source') not in {'natural','common_preparation'}:
        return {'admitted':False,'reason':'unregistered_state_source'}
    if record.get('diagnosis_status')=='completed':
        return {'admitted':False,'reason':'no_unfinished_diagnostic_object'}
    if record.get('diagnosis_status')!='unfinished' or not record.get('prefix_evidence'):
        return {'admitted':False,'reason':'unfinished_work_not_established'}
    if record.get('permanent_environment_failure') is not False:
        return {'admitted':False,'reason':'environment_not_ready'}
    if not all(record.get(k) is True for k in ('KEEP_legal','REASSIGN_legal','SDK_resume_qualified')):
        return {'admitted':False,'reason':'branch_legality_or_restore_missing'}
    if record['source']=='common_preparation' and record.get('prepared_before_split') is not True:
        return {'admitted':False,'reason':'one_sided_preparation'}
    return {'admitted':True,'semantic_evidence_requires_review':True,'positive_effect_required':False}

def endpoint(row):
    # Declining the transfer is not itself a missing observation or an exclusion.
    if row.get('technical_unknown') or type(row.get('legal_delivery')) is not bool:
        return None
    if not row['legal_delivery']:return 0
    if (type(row.get('delivery_official_resolved')) is not bool
            or row.get('score_bound_to_submitted_version') is not True):return None
    return int(row['delivery_official_resolved'])

def summarize(prefixes,assignments):
    if len({p['candidate_id'] for p in prefixes})!=len(prefixes):raise ValueError('Prefix charged twice')
    if len({r['run_id'] for r in assignments})!=len(assignments):raise ValueError('Duplicate branch identity')
    prefix={p['candidate_id']:p for p in prefixes}
    actual=sum((Decimal(str(p['cost_CNY'])) for p in prefixes if p.get('cost_CNY') is not None),Decimal(0))
    unknown_costs=sum(p.get('cost_CNY') is None for p in prefixes)
    arms=defaultdict(list);full_costs=[]
    for row in assignments:
        if row['candidate_id'] not in prefix:raise ValueError('Missing prefix cost')
        if row.get('cost_CNY') is None:unknown_costs+=1
        else:actual+=Decimal(str(row['cost_CNY']))
        arms[row['assigned_arm']].append(row)
        p_cost=prefix[row['candidate_id']].get('cost_CNY');b_cost=row.get('cost_CNY')
        full_costs.append({'run_id':row['run_id'],'full_task_cost_CNY':
            str(Decimal(str(p_cost))+Decimal(str(b_cost))) if p_cost is not None and b_cost is not None else None})
    report={}
    for arm,rows in arms.items():
        values=[endpoint(r) for r in rows]
        report[arm]={'planned':len(rows),'success':values.count(1),'failure':values.count(0),'unknown':values.count(None),
            'success_rate':sum(values)/len(values) if None not in values else None,
            'accepted_transfers':sum(r.get('transfer_accepted') is True for r in rows),
            'protocol_deviations':sum(r.get('protocol_deviation') is True for r in rows),
            'noncompliant_branches_excluded':0}
    return {'actual_experiment_cost_CNY':str(actual) if unknown_costs==0 else None,
        'known_cost_CNY':str(actual),'unresolved_cost_records':unknown_costs,'prefix_cost_counted_once':True,
        'per_branch_full_task_costs':full_costs,'ITT':report,
        'effect_generalization':'frozen states only; repeated branches are not new independent tasks'}
