"""Register one supplemental development cohort using public work receipts, never solver scores."""
from collections import Counter,defaultdict
from pathlib import Path

from proworksim.software_anomaly_graph_v226 import AnomalyGraph,MEMBERS
from proworksim.software_benchmark_candidates_v054 import checked,reference
from proworksim.storage import atomic_write,json_bytes,read_json
from prepare_graph_learning_v229 import ROOT,rank

BASE=ROOT/'artifacts/software-benchmark-v229/design-r1'
EXT=ROOT/'artifacts/software-benchmark-v229/dev1-extension-r1'
VERSIONS=('216','217','218','219','222','223','223-1','223-2','224','224-1','224-2')


def candidate_pool():
    plan=read_json(BASE/'panel.json')
    excluded=set(plan['excluded_v228'])|{r['instance_id'] for r in plan['rows']}
    pool={}
    for v,env,scorer in [('217','environment-r2','score_project_relations_v217_1.py'),
                         ('223-1','environment-r1','score_organization_demand_v223_1.py'),
                         ('224-2','environment-r1','score_mapping_v224_2.py')]:
        source=ROOT/f'artifacts/software-benchmark-v{v}/protocol-r1/candidate-tasks.json'
        for row in read_json(source)['rows']:
            iid=row['instance_id'];i=row['index']
            if iid in pool or iid in excluded:continue
            q=ROOT/f'runs/software-benchmark-v{v}/{env}/task-{i:02d}/qualification.json'
            if not q.exists():continue
            proof=read_json(q)
            if not proof['qualified'] or proof['instance_id']!=iid:continue
            if not all(read_json(checked(proof['proof'][k]))['resolved'] is b for k,b in [('gold',True),('empty',False)]):continue
            pool[iid]={**row,'source_index':i,'environment':reference(q),'source_panel':reference(source),'scorer_script':scorer}
    return pool


def prior_sightings(pool):
    sightings=defaultdict(dict);counts=Counter()
    for v in VERSIONS:
        source=ROOT/f'runs/software-benchmark-v{v}'
        for path in sorted(source.glob('*/task-*/*/boundary.json')):
            meta=path.parent/'result.json'
            if not meta.exists():continue
            header=read_json(meta)
            iid=header.get('instance_id')
            if iid not in pool:continue
            counts[iid]+=1
            graphs={m:AnomalyGraph(m) for m in MEMBERS}
            cp=header.get('checkpoint_parent')
            if cp:
                d=Path(cp).parent/'dynamic-final.json'
                if d.is_file():
                    active=read_json(d).get('active_work',{})
                    for m,g in graphs.items():g.current_work=active.get(m)
            for ordinal,outcome in enumerate(read_json(path)['outcomes'],1):
                observer=outcome.get('worker_id')
                if observer not in graphs:continue
                g=graphs[observer];g.observe(ordinal,outcome)
                for n in g.nodes.values():
                    kind=n['anomaly_type']
                    if kind in sightings[iid] or not n['affected_work'] or n['status'] not in ('OPEN','REOPENED','ACTIVE'):continue
                    sightings[iid][kind]={'source':reference(path),'ordinal':ordinal,'observer':observer,
                                          'subject':n['subject'],'work':n['affected_work'],
                                          'note':'historic trigger only; checkpoint and legal alternative not implied'}
    return sightings,counts


def main():
    pool=candidate_pool();evidence,counts=prior_sightings(pool)
    rows=[];repos=Counter();kinds=set()
    for index in range(min(4,len(pool))):
        def priority(iid):
            observed=set(evidence[iid]);return (not bool(observed),not bool(observed-kinds),
                                               repos[pool[iid]['repo']],rank('dev1-extra1|'+iid))
        iid=min(pool,key=priority);row=pool.pop(iid)
        rows.append({**row,'index':len(read_json(BASE/'panel.json')['rows'])+index,'phase':'dev1','historical_trigger_types':sorted(evidence[iid])})
        repos[row['repo']]+=1;kinds.update(evidence[iid])
    atomic_write(EXT/'recruitment.json',json_bytes({'archive_versions':VERSIONS,'trace_counts':dict(counts),
        'observations':dict(evidence),'rank_order':'historically observed anomaly, unrepresented anomaly class, within-batch repository count, fixed issue hash',
        'conditioning':'development enrichment; no prior solver scores or hidden patches used; no substitution after launch'}))
    p=read_json(BASE/'panel.json')
    p.update(rows=[*p['rows'],*rows],supplement_indices=[r['index'] for r in rows],source_design=reference(BASE/'panel.json'),excluded_original_ids=[r['instance_id'] for r in p['rows']],
             purpose='separate prospective supplement to dev1 under Q0; original four remain reported; dev2 and confirmation untouched')
    atomic_write(EXT/'panel.json',json_bytes(p))
    print([(r['instance_id'],r['historical_trigger_types']) for r in rows])
if __name__=='__main__':main()
