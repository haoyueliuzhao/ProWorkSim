"""Separate structural explanation of frozen query results, no outcome data."""
import sys,json
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,OUT,read,save,frame_for,graph_from_snapshot
from proworksim.software_dependency_query_v197 import typed_routes,state

def main():
    points=read(OUT/'private-map-r1/manifest.json')['points'];rows=[]
    for p in points:
        frame,indices,s,pool,cutoff=frame_for(p);g=graph_from_snapshot(s);phase=state(frame)
        roots,routes,_=typed_routes(g,phase,inferred=False)
        reached={nid:r for nid,r in routes.items() if r['edges']}
        candidates_reached=[];additional=[]
        for e in pool:
            endpoints={e['entity_node']}|{g._file_nodes[path] for path in e['paths'] if path in g._file_nodes}
            if endpoints.intersection(reached):
                candidates_reached.append(p['event_map'][e['event_id']])
                if not roots.intersection(e['paths']):additional.append(p['event_map'][e['event_id']])
        rows.append({'point':p['point'],'phase':phase,'reachable_nonroot_nodes':len(reached),
            'reachable_entity_types':dict(Counter(g.nodes[n]['attrs'].get('entity_kind',g.nodes[n]['type']) for n in reached)),
            'new_file_paths_reached':sorted({g.nodes[n]['attrs']['path'] for n in reached if g.nodes[n]['type']=='Code' and g.nodes[n]['attrs'].get('entity_kind')=='file' and g.nodes[n]['attrs']['path'] not in roots}),
            'candidate_events_reached':candidates_reached,'candidate_events_beyond_direct_path':additional,
            'candidate_endpoint_types':dict(Counter(g.nodes[e['entity_node']]['type'] for e in pool))})
    counts=Counter();crossfile=[];tasks=set()
    for p in points:
        if p['slot_id'] in tasks:continue
        tasks.add(p['slot_id'])
        s=read(ROOT/'runs/software-benchmark-v196/offline-graph-r4'/str(p['slot_index'])/'final-graph.json.gz')
        for e in s['edges'].values():
            counts[(e['type'],e['status'])]+=1
            a,b=s['nodes'][e['source']],s['nodes'][e['target']]
            if e['status']=='Confirmed' and a['attrs'].get('path') and b['attrs'].get('path') and a['attrs']['path']!=b['attrs']['path']:
                crossfile.append({'instance_id':p['instance_id'],'type':e['type'],'proof':e['proof'],'from':a['attrs']['path'],'to':b['attrs']['path']})
    save(OUT/'graph-structure-r1/summary.json',{'rows':rows,
        'edges_final12':[{'type':t,'status':s,'count':n} for (t,s),n in sorted(counts.items())],
        'confirmed_edges_with_distinct_observed_path_endpoints':crossfile,
        'points_with_confirmed_additional_candidate':sum(bool(r['candidate_events_beyond_direct_path']) for r in rows),
        'points_with_new_confirmed_file_path':sum(bool(r['new_file_paths_reached']) for r in rows),
        'root_cause_scope':'current representation and typed query only, not proof graphs cannot help coding',
        'no_API_or_model_calls':True})
    print('confirmed extra-candidate points',sum(bool(r['candidate_events_beyond_direct_path']) for r in rows))
if __name__=='__main__':main()
