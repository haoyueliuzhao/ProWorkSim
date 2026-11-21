"""Preselect four new task IDs before using the second-window outcomes."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SALT = 'v225-preselection-window2-r1'
REPOS = ('django/django', 'sympy/sympy', 'astropy/astropy', 'scikit-learn/scikit-learn')

def strings(value):
    if isinstance(value,str):
        yield value
    elif isinstance(value,list):
        for item in value:
            yield from strings(item)
    elif isinstance(value,dict):
        for item in value.values():
            yield from strings(item)

def main():
    pool={}
    for cfg in sorted((R/'runs/software-benchmark-v064/full-verified-r1/configs').glob('*.json')):
        data=json.loads(cfg.read_bytes())
        pool.setdefault(data['instance_id'],data['public_task'])
    excluded=set()
    sources=[]
    manifests = [path for path in (R/'artifacts').glob('software-benchmark-v2*/**/*.json')
                 if path.name in ('candidate-tasks.json','plan.json','approved-panel.json')]
    for path in sorted(manifests):
        listed=set(strings(json.loads(path.read_bytes()))) & pool.keys()
        excluded.update(listed)
        sources.append({'path':str(path.relative_to(R)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    picks=[]
    for repo in REPOS:
        ids=[iid for iid,task in pool.items() if task['repo']==repo and iid not in excluded]
        iid=min(ids,key=lambda s:hashlib.sha256((SALT+':'+s).encode()).digest())
        picks.append({'repo':repo,'instance':iid,'public_text_sha256':hashlib.sha256(pool[iid]['problem_statement'].encode()).hexdigest(),'eligible_pool':len(ids)})
    out=R/'artifacts/software-benchmark-v224-4/window2-r1/confirmation-task-ids-r2.json'
    with out.open('x') as stream:
        json.dump({'salt':SALT,'selection':'first salted hash per repo outside archived candidate, plan and approved panel manifests','sources':sources,
                   'excluded_ids':sorted(excluded),'rows':picks,'prior_general_benchmark_exposure_possible':True,
                   'no_environment_or_model_admission':True},stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(picks)

if __name__=='__main__':
    main()
