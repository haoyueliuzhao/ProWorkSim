"""Bounded, fixed-initial-topology baseline preparation; never a paper reproduction."""
import itertools

def partition(tasks,members,dependencies,facts,*,assignment_limit=256):
    """Task regions, typed task dependencies, role/tool constraints and visibility."""
    ids=sorted(tasks);actors=sorted(members)
    if len(actors)!=2:raise ValueError('This pilot fixes two members')
    if 2**len(ids)>assignment_limit:raise ValueError('Declared topology search budget insufficient')
    edges=[d for d in dependencies if d['relation_type']=='task_depends_on' and d['status']=='confirmed']
    best=None;checked=0
    for values in itertools.product(actors,repeat=len(ids)):
        checked+=1;owners=dict(zip(ids,values));valid=True
        for t,a in owners.items():
            row=tasks[t]
            if not members[a].get('live') or not set(row.get('required_tools',[]))<=set(members[a].get('tools',[])):valid=False
            if row.get('locked_owner') and row['locked_owner']!=a:valid=False
            if row.get('review_of') and owners[row['review_of']]==a:valid=False
        if not valid:continue
        load={a:sum(tasks[t].get('work_units',1) for t in ids if owners[t]==a) for a in actors}
        crossing=[d for d in edges if owners[d['source_entity']]!=owners[d['target_entity']]]
        # Keep balance primary; do not "optimize" communication by giving one member everything.
        key=(max(load.values()),len(crossing),values)
        if best is None or key<best[0]:best=(key,owners,load,crossing)
    if best is None:return {'status':'infeasible','assignments_checked':checked,'world_actions':0}
    _,owners,load,crossing=best
    routes=[{'upstream':d['target_entity'],'downstream':d['source_entity'],'sender':owners[d['target_entity']],'recipient':owners[d['source_entity']],
        'relation_id':d['relation_id'],'source_version':d['source_version'],'evidence_source':d['evidence_source']} for d in crossing]
    visible={a:[f['id'] for f in facts if f['owner']==a or (a in f.get('granted_to',[]) and f.get('publication_receipt'))] for a in actors}
    return {'status':'prepared','regions':{a:[t for t in ids if owners[t]==a] for a in actors},'owners':owners,'workload_units':load,'handoffs':routes,
        'memory_visibility':visible,'assignments_checked':checked,'confirmed_task_edges_only':True,'initial_topology_frozen':True,
        'unpublished_private_memory_not_migrated':True,'world_actions':0,'not_full_ToCoMAS_reproduction':True}
