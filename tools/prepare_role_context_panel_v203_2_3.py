"""Score-blind four-repository development panel; no environment or API work."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/software-benchmark-v203-2-3/panel-r1'
SEED = 'v203.2.3-role-context-20261113'

def main():
    source = ROOT/'artifacts/software-benchmark-v054/source/public-tasks.json'
    pool = json.loads(source.read_bytes())
    previous = json.loads((ROOT/'artifacts/software-benchmark-v203-2-1/final-report-r1/summary.json').read_bytes())
    excluded = {x['instance_id'] for x in previous['records']}
    rank = lambda x: hashlib.sha256((SEED+'|'+x).encode()).hexdigest()
    groups = {}
    for row in pool:
        if row['instance_id'] not in excluded:
            groups.setdefault(row['repo'], []).append(row)
    tasks = []
    for repo in sorted(groups, key=rank)[:4]:
        selected = min(groups[repo], key=lambda r: rank(r['instance_id']))
        tasks.append({k:selected[k] for k in ('instance_id','repo','base_commit','image')})
    rows=[]
    for i,t in enumerate(tasks):
        seed=int(rank(t['instance_id'])[:8],16)
        for j in range(3):
            condition=['K0','K1','K2'][(i+j)%3]
            rows.append({**t,'condition':condition,'seed':seed,'slot_index':2032300+i*3+j,
                         'slot_id':f"v203.2.3:{t['instance_id']}:{condition}:{seed}"})
    result={'version':SEED,'tasks':tasks,'rows':rows,'task_count':4,'repository_count':4,
            'planned_rounds':12,'conditions':['K0','K1','K2'],'model':'deepseek-flash',
            'thinking':False,'organization':'REVIEW2','members':2,'team_token_limit':5000000,
            'total_token_upper_bound':60000000,'cash_authorized_CNY':130,
            'ledger_policy':'new independent ledger; no use of old balance',
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'selection':'fixed SHA rank by repository then task; no performance/environment outcome inputs',
            'excluded_recent_task_ids':sorted(excluded),'whole_study_unseen':False,
            'purpose':'development mechanism pilot, not independent confirmation',
            'environment_ready':False,'runtime_started':False}
    OUT.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
    target=OUT/'plan.json'
    if target.exists() and target.read_bytes()!=raw:raise ValueError('Do not change frozen selection')
    target.write_bytes(raw)
    print(json.dumps({'tasks':[t['instance_id'] for t in tasks],'rounds':12,'budget':130}))

if __name__=='__main__':main()
