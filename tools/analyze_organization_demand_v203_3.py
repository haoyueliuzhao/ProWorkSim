"""Read-only historical demand/capability alignment and first-fault censoring."""
from __future__ import annotations
from collections import Counter
import hashlib,json,sqlite3,statistics
from pathlib import Path
from proworksim.software_organization_demand_v203_3 import observed_interval

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v203-3/natural-demand-r1'
OLD=ROOT/'artifacts/software-benchmark-v203-2-2'
COLLAB={'send_message','handoff_patch','fix_patch','integrate_patch','org_review_patch',
        'create_task','claim_task','offer_transfer','accept_transfer','decline_transfer',
        'org_declare_role','submit_integration','revise_task','declare_dependency','resolve_dependency'}

def ref(path):
    raw=path.read_bytes();return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def save(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def lines(path):return [json.loads(line) for line in path.read_text().splitlines() if line]

def source(item):return (item or {}).get('source')

def history():
    path=OLD/'natural-audit-r1/collaboration_chains.jsonl'
    chains=lines(path);rows=[]
    for chain in chains:
        kind=chain['chain_type'];start=end=None;capability=None;need=None
        if kind=='A_handoff_information_adoption':
            need='published_candidate_adoption';capability='existing_recipient_integrate_patch'
            start=source(chain.get('publication'))
            recipient=chain['anchor']['arguments']['to_member']
            matches=[r['receipt'] for r in chain['integrations']
                     if r['receipt'].get('actor')==recipient and r['receipt'].get('ok')]
            if matches:end=source(min(matches,key=lambda r:r['source']['sequence']))
        elif kind=='B_conflict_handling_recovery':
            need='restore_exact_published_content_after_conflict';capability='existing_private_edit_and_test'
            start=source(chain['anchor']);end=source(chain.get('first_restored_published_content'))
        elif kind=='C_review_rework_delivery':
            need='independent_same_version_review';capability='existing_member_002_review_role'
            start=source(chain.get('publication'))
            if chain.get('reviewed_content_matches_publication') is True and chain.get('test_content_matches_publication') is True:
                end=source(chain['anchor'])
        else:continue
        rows.append({'id':chain['chain_id'],'task':chain['task_id'],'kind':kind,
            'work_demand':need,'existing_capability':capability,
            'demand_interval':observed_interval(start,end),
            'mismatch':'NOT_INFERRED','mismatch_duration_seconds':None,
            'organization_change_required':'UNKNOWN',
            'successful_normal_operation_observed':bool(end),
            'cohort':'v203.2.1_historical_with_known_environment_defects',
            'source':{'file':str(path),'chain_id':chain['chain_id']},
            'not_a_normal_environment_effect_sample':True})
    labels_by_id={r['window_id']:r for r in lines(OLD/'independent-review-r1/reviewer-a.jsonl')}
    labels_by_id.update({r['window_id']:r for r in lines(OLD/'independent-review-r1/adjudication.jsonl')})
    labels=list(labels_by_id.values())
    assert len(labels)==108
    # These are old AI auxiliary judgments, not fresh independent validation.
    label_counts=Counter(r['misalignment'] for r in labels)
    aggregates={}
    for kind in sorted({r['kind'] for r in rows}):
        selected=[r for r in rows if r['kind']==kind]
        values=[r['demand_interval']['seconds'] for r in selected if r['demand_interval']['status']=='observed']
        aggregates[kind]={'n':len(selected),'tasks':len({r['task'] for r in selected}),
            'interval_statuses':dict(Counter(r['demand_interval']['status'] for r in selected)),
            'observed_seconds_median':statistics.median(values) if values else None,
            'observed_seconds_range':[min(values),max(values)] if values else None}
    save('demand-capability-intervals.json',{'rows':rows,'aggregates':aggregates,
        'selection':'all existing handoff, conflict and review chains; no final-score filtering',
        'source':ref(path),'prior_auxiliary_references':[ref(OLD/'independent-review-r1'/name)
            for name in ('reviewer-a.jsonl','adjudication.jsonl')],
        'prior_auxiliary_mismatch_counts':dict(label_counts),'new_independent_reviews':0,
        'natural_mismatch_rate':None,'mismatch_duration_distribution':None,
        'reason':'No confirmed positive mismatch; correlated historical windows are not a prevalence denominator.'})
    return aggregates,dict(label_counts)

def contaminated_prefixes():
    base=ROOT/'runs/software-benchmark-v203-2-3/role-context-recovery12-r3/episodes'
    cohorts=[];retained=[]
    for folder in sorted(base.iterdir()):
        dbpath=folder/'controller-output/model-ledger/passive-observer/events.sqlite'
        if not dbpath.is_file():continue
        receipts=[];usage=[];initial=None;first_fault=None
        with sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            count=db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
            query="SELECT sequence,record_json,record_sha256,chain_sha256 FROM observations WHERE json_extract(record_json,'$.kind') IN ('INITIAL','RECEIPT','MODEL_RESPONSE') ORDER BY sequence"
            for seq,raw,record_sha,chain_sha in db.execute(query):
                event=json.loads(raw);payload=event['payload']
                pointer={'journal':str(dbpath),'sequence':seq,'event_key':event['key'],
                    'record_sha256':record_sha,'chain_sha256':chain_sha,
                    'capture_time':event.get('source',{}).get('capture_time')}
                if event['kind']=='INITIAL':initial=payload;continue
                if event['kind']=='MODEL_RESPONSE':
                    usage.append((seq,payload.get('body',{}).get('usage',{})));continue
                error=payload.get('response',{}).get('error',{}) or {}
                if first_fault is None and 'FileNotFoundError' in error.get('message','') and 'public_test_execution_v175.py' in error.get('message',''):
                    first_fault={'source':pointer,'error':error}
                receipts.append((pointer,payload,raw))
        if not first_fault:raise ValueError('Missing independently traceable original first fault: '+str(folder))
        cutoff=first_fault['source']['sequence']
        selected=[]
        for pointer,payload,raw in receipts:
            if pointer['sequence']>=cutoff or payload.get('tool') not in COLLAB:continue
            if payload.get('response',{}).get('ok') is not True:continue
            if hashlib.sha256(raw.encode()).hexdigest()!=pointer['record_sha256']:
                raise ValueError('Selected original receipt checksum changed')
            selected.append({'episode_id':initial['episode_id'],'task':initial['case_id'],
                'actor':payload['actor'],'tool':payload['tool'],'arguments':payload.get('arguments'),
                'response':payload['response'],'source':pointer,
                'boundary':'strictly_before_first_actor_script_failure',
                'allowed_use':'process_evidence_only','policy_effect_sample':False})
        retained.extend(selected)
        cohorts.append({'episode_id':initial['episode_id'],'task':initial['case_id'],
            'journal':str(dbpath),'total_observation_count':count,'first_fault':first_fault,
            'prefix_end_exclusive':cutoff,'selected_collaboration_receipts':len(selected),
            'selected_tools':dict(Counter(r['tool'] for r in selected)),
            'reported_response_count':len(usage),
            'observed_response_tokens':sum(u.get('total_tokens',0) for _,u in usage),
            'post_fault_reported_tokens':sum(u.get('total_tokens',0) for seq,u in usage if seq>cutoff),
            'post_fault_tokens_not_causal_savings':True,
            'normal_execution_or_organization_effect_sample':False})
    save('fault-boundaries.json',{'rows':cohorts,'all_original_generation_states_preserved':True})
    save('pre-fault-process-evidence.json',{'rows':retained,'API_calls':0,'no_intervention_or_new_label':True})
    return cohorts,retained

def main():
    aggregates,labels=history();cohorts,retained=contaminated_prefixes()
    summary={'version':'v203.3-A-natural-demand-alignment-r1','API_calls':0,
        'source_cohorts_separated':True,'historical_task_count':12,'historical_window_count':108,
        'historical_reference_type':'previous_AI_auxiliary_not_human_gold_or_new_independent_review',
        'prior_auxiliary_mismatch_counts':labels,'demand_interval_aggregates':aggregates,
        'damaged_episodes':len(cohorts),'damaged_distinct_tasks':len({r['task'] for r in cohorts}),
        'pre_fault_collaboration_receipts':len(retained),'pre_fault_tools':dict(Counter(r['tool'] for r in retained)),
        'observed_response_tokens':sum(r['observed_response_tokens'] for r in cohorts),
        'post_fault_reported_tokens':sum(r['post_fault_reported_tokens'] for r in cohorts),
        'natural_mismatch_rate':None,'mismatch_duration':None,'v204_effect_run_admitted':False,
        'pending':['independent demand/capability annotations','supported positive mismatch evidence',
                   'full deployed FIFO chain gate','new API budget and frozen task/policy protocol']}
    save('summary.json',summary);print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
