"""Identity-only feasibility and a non-runnable future passive-pilot proposal."""
import collections
from inventory_multimember_v203 import ROOT,read,ref,save,sha
ART=ROOT/'artifacts/software-benchmark-v203-2/pilot-preparation-r1'
def main():
    source=ROOT/'artifacts/software-benchmark-v054/source/public-tasks.json';pool=read(source)
    prior=read(ROOT/'artifacts/software-benchmark-v201/prospective-identities-r1/manifest.json');excluded=set(prior['excluded_instance_ids'])
    previous50=read(ROOT/'runs/software-benchmark-v131/fixed-organization-50-r1/execution-plan.json')['rows'];excluded.update(r['instance_id'] for r in previous50)
    excluded.update(r['instance_id'] for r in read(ROOT/'artifacts/software-benchmark-v203-1/panel-r1/plan.json')['rows'])
    excluded.update(r['instance_id'] for r in read(ROOT/'artifacts/software-benchmark-v203/material-admission-r1/selection.json'))
    groups=collections.defaultdict(list)
    for row in pool:
        if row['instance_id'] not in excluded:groups[row['repo']].append({k:row[k] for k in ['instance_id','repo','base_commit']})
    rank=lambda x:sha(('v203.2-passive-identity-only-20261112'+x).encode())
    for rows in groups.values():rows.sort(key=lambda r:rank(r['instance_id']))
    chosen=[]
    while len(chosen)<12:
        changed=False
        for repo in sorted(groups,key=rank):
            if groups[repo]:chosen.append(groups[repo].pop(0));changed=True
            if len(chosen)==12:break
        if not changed:break
    plan={'status':'identity_reservation_only_not_a_ready_or_authorized_experiment','runnable':False,'tasks':chosen,'task_count':len(chosen),
        'repository_count':len({r['repo'] for r in chosen}),'goal_at_least10_repositories_met':len({r['repo'] for r in chosen})>=10,
        'all_study_history_unseen_repositories':0,'scope':'existing SWE-bench Verified; no silent dataset substitution',
        'recent_development_exclusions':sorted(excluded),'source':ref(source),'source_script':ref(__file__),
        'problem_statements_or_old_trajectories_presented_to_model_or_reviewer':False,'environment_readiness_verified':False,
        'organization':'fixed REVIEW2, two actual members','condition':'passive observation only; no policy intervention or compression',
        'tools_or_prompts_changed':False,'candidate_team_token_limit':5000000,'candidate_total_token_upper_bound':len(chosen)*5000000,
        'new_API_cash_authorized':False,'ledger':None,'new_runtime_started':False,
        'requirements_before_real_launch':['explicit new budget and model-run authorization','task and repository-scope decision','frozen model/SDK/source version','current environment qualification and resource limits','actual provider input/usage capture admission'],
        'different_future_stages':{'pilot':12,'development':24,'task_holdout':12,'pilot_reused_in_development_is_not_independent':True}}
    save(ART/'plan.json',plan);print({k:plan[k] for k in ['task_count','repository_count','goal_at_least10_repositories_met','runnable','all_study_history_unseen_repositories']})
if __name__=='__main__':main()
