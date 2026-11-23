"""Select validated issue identities without reading solver outcomes or official patches."""
import hashlib
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import checked,reference
from proworksim.software_graph_policy_v229 import FEATURES,Q0,SPEC
from proworksim.storage import read_json,atomic_write,json_bytes

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v229/design-r1'
SALT='v229-controlled-graph-window-20261123'
def rank(key):
    return hashlib.sha256((SALT+'|'+key).encode()).hexdigest()


def main():
    excluded={r['instance_id'] for r in read_json(ROOT/'artifacts/software-benchmark-v228/control-r2/panel.json')['rows']}
    pool={}
    for v,env,scorer in [('217','environment-r2','score_project_relations_v217_1.py'),
                         ('223-1','environment-r1','score_organization_demand_v223_1.py'),
                         ('224-2','environment-r1','score_mapping_v224_2.py')]:
        path=ROOT/f'artifacts/software-benchmark-v{v}/protocol-r1/candidate-tasks.json'
        for row in read_json(path)['rows']:
            iid=row['instance_id'];i=row['index']
            if iid in excluded or iid in pool:continue
            q=ROOT/f'runs/software-benchmark-v{v}/{env}/task-{i:02d}/qualification.json'
            if not q.is_file():continue
            proof=read_json(q)
            if proof['instance_id']!=iid or not proof['qualified']:continue
            if not all(read_json(checked(proof['proof'][k]))['resolved'] is val for k,val in [('gold',True),('empty',False)]):continue
            pool[iid]={**row,'source_index':i,'scorer_script':scorer,'environment':reference(q),
                       'source_panel':reference(path)}
    rows=[];used={}
    for phase,size in [('dev1',4),('dev2',4),('confirm',8)]:
        counts={}
        for _ in range(size):
            def order(iid):
                repo=pool[iid]['repo']
                return counts.get(repo,0),used.get(repo,0),rank(phase+'|'+iid)
            iid=min(pool,key=order);row=pool.pop(iid);repo=row['repo']
            counts[repo]=counts.get(repo,0)+1;used[repo]=used.get(repo,0)+1
            rows.append({**row,'phase':phase,'index':len(rows)})
    plan={'selection':'fixed SHA-256 order balanced by repo within split then across splits; no score-based replacements',
          'salt':SALT,'excluded_v228':sorted(excluded),'historical_exposure':'disjoint from v228, not necessarily unseen in older experiments',
          'rows':rows,'Q0':Q0,'features':FEATURES,'spec':SPEC,'provider_calls':0}
    atomic_write(OUT/'panel.json',json_bytes(plan))
    print([(r['phase'],r['instance_id']) for r in rows])
if __name__=='__main__':main()
