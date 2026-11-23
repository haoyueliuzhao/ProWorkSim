"""Replay causal prefixes to independently supplied window boundaries, without model calls."""
import hashlib
import json
from pathlib import Path

from proworksim.software_anomaly_graph_v226 import AnomalyGraph, MEMBERS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v226/preparation-r1'

def read(path):
    return json.loads(path.read_bytes())

def windows():
    for row in read(OUT/'independent-review.json')['windows']:
        yield row['id'], row['source'], row['source_sha256'], row['window_start_opportunity'],row['window_end_opportunity'],row['supported'],row['negative_for'],row['classification']
    for row in read(OUT/'older-independent-review.json')['windows']:
        label=row['review_label']
        yield row['id'],row['source']['path'],row['source']['sha256'],row['start_ordinal'],row['end_ordinal'],[label] if label in ('A1','A2','A3','A4','A5') else [],['A5'] if label=='STABLE' else ['A1'] if label=='UNKNOWN' else [],label

def main():
    results=[]
    for key,source,sha,start,end,expected,negative,label in windows():
        path=ROOT/source
        data=path.read_bytes()
        assert hashlib.sha256(data).hexdigest()==sha
        events=json.loads(data)['outcomes']
        graphs={a:AnomalyGraph(a) for a in MEMBERS}
        saved=read(path.parent/'result.json').get('checkpoint_parent')
        initial=Path(saved).parent/'dynamic-final.json' if saved else None
        if initial and initial.exists():
            active=read(initial).get('active_work',{})
            for actor,graph in graphs.items():graph.current_work=active.get(actor)
        for i,o in enumerate(events[:end],1):
            for g in graphs.values():g.observe(i,o)
        def selected(graph):
            return [n for n in graph.view()['anomalies'] if any(start<=r['opportunity']<=end for r in n['evidence_refs'])]
        views={a:selected(g) for a,g in graphs.items()}
        found={n['anomaly_type'] for v in views.values() for n in v}
        results.append({'id':key,'source':source,'window':[start,end],'reference':label,'expected':expected,'negative_for':negative,
            'detected_in_separately_authorized_views':sorted(found),'missing':sorted(set(expected)-found),
            'contradicted_negative':sorted(set(negative)&found),'by_observer':views,
            'not_shared_between_observers':True})
    (OUT/'replay.json').write_text(json.dumps({'windows':results,'api_calls':0,'C_N_updates':0,
        'scope':'selected historical controls; cumulative prefix ending at the window end; display only window-linked nodes; UNKNOWN does not imply wrong prediction'},ensure_ascii=False,indent=2)+'\n')
    for r in results:print(r['id'],r['expected'],r['detected_in_separately_authorized_views'],r['missing'],r['contradicted_negative'])
if __name__=='__main__': main()
