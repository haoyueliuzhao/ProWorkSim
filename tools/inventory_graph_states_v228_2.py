"""Locate predecision evidence in the original eight prefixes, without consulting scores."""
from pathlib import Path
from collections import Counter
from proworksim.software_anomaly_graph_v226 import AnomalyGraph
from proworksim.software_anomaly_pilot_v226 import stable_control_node
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import atomic_write,json_bytes,read_json

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'artifacts/software-benchmark-v228/control-r2/panel.json'
OUT=ROOT/'artifacts/software-benchmark-v228/diagnosis-supplement-r1'


def inspect(row):
    prefix=Path(row.get('archived_prefix') or ROOT/f"runs/software-benchmark-v228/control-r1/task-{row['index']:02d}/PREFIX")
    source=prefix/'observations.json'
    if source.is_file():
        events=read_json(source)
    else:
        source=prefix/'boundary.json'
        events=[{'ordinal':i,'outcome':outcome} for i,outcome in enumerate(read_json(source)['outcomes'],1)]
    observer=row['observer']
    graph=AnomalyGraph(observer)
    seen={};history=[]
    for item in events:
        n,outcome=item['ordinal'],item['outcome']
        if outcome.get('worker_id')!=observer:continue
        graph.observe(n,outcome);history.append((n,outcome))
        for node in graph.nodes.values():
            if node['affected_work'] and node['status'] in ('OPEN','ACTIVE','REOPENED'):
                seen.setdefault(node['anomaly_type'],{'ordinal':n,'subject':node['subject'],'evidence_count':len(node['evidence_refs'])})
        if graph.current_work and 'STABLE' not in seen:
            try:stable=stable_control_node(graph,history,affected_work=[graph.current_work])
            except ValueError:continue
            seen['STABLE']={'ordinal':n,'subject':stable['subject'],'evidence_count':len(stable['evidence_refs'])}
    checkpoint=prefix/'checkpoint/manifest.json'
    assigned=row['target_scene']
    return {'instance_id':row['instance_id'],'observer':observer,'assigned':assigned,'seen':seen,'original_source':reference(source),
            'original_checkpoint':reference(checkpoint) if checkpoint.is_file() else None}


if __name__=='__main__':
    cases=[inspect(r) for r in read_json(PLAN)['rows']]
    counts=Counter(kind for case in cases for kind in case['seen'])
    result={'method':'causal replay through end of saved common prefix; fixed original observer; no hidden scores or model calls; diagnostic sightings, not new restartable states or independent samples',
            'cases':cases,'tasks_by_observed_type':dict(counts),'new_provider_calls':0}
    atomic_write(OUT/'recruitment.json',json_bytes(result))
    print(counts,[(c['instance_id'],list(c['seen']),bool(c['original_checkpoint'])) for c in cases])
