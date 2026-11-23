"""Retain lone-KEEP observations; fork only at the first live scoped anomaly with a legal alternative."""
from .software_graph_controller_v228 import menu
from .software_graph_policy_v229 import TYPES

def has_alternative(frozen):
    return any(option['op']!='keep' for option in frozen['options'].values())



def inspect_opportunity(world, observer, graph, ordinal, singletons):
    for node in graph.nodes.values():
        if (node['anomaly_type'] not in TYPES or node['status'] not in ('OPEN','ACTIVE','REOPENED')
                or not node['affected_work']):
            continue
        # Old graph nodes remain in the timeline when work has disappeared.
        if not all(t in world.dynamic()['work'] for t in node['affected_work']):
            continue
        frozen=menu(world,node,observer)
        if has_alternative(frozen):
            return node
        key=(observer,node['anomaly_id'],frozen['base_sha256'])
        if key not in singletons:
            singletons[key]={'observer':observer,'anomaly_id':node['anomaly_id'],'kind':node['anomaly_type'],
                             'subject':node['subject'],'work':list(node['affected_work']),'first':ordinal,
                             'graph_sha256':frozen['base_sha256'],'evidence':frozen['evidence'],'visits':0}
        singletons[key].update(last=ordinal,visits=singletons[key]['visits']+1)
    return None
