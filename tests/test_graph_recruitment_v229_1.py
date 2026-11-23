from copy import deepcopy
from types import SimpleNamespace
from proworksim.software_graph_recruitment_v229_1 import inspect_opportunity
from test_graph_controller_v228 import scene,M1
from test_organization_world_v211 import split


def test_single_support_does_not_hide_another_live_node(tmp_path):
    w,call,original=scene(tmp_path)
    split(call)
    node={**original,'status':'OPEN'}
    g=SimpleNamespace(nodes={'first':node})
    seen={}
    assert inspect_opportunity(w,M1,g,1,seen) is None
    assert inspect_opportunity(w,M1,g,2,seen) is None
    recorded,=seen.values()
    assert (recorded['first'],recorded['last'],recorded['visits'])==(1,2,2)
    next_node={**deepcopy(node),'anomaly_id':'second','affected_work':['behavior']}
    g.nodes['second']=next_node
    assert inspect_opportunity(w,M1,g,3,seen) is next_node


def test_resolved_or_unbound_nodes_do_not_trigger(tmp_path):
    w,_,node=scene(tmp_path)
    g=SimpleNamespace(nodes={'a':{**node,'status':'RESOLVED'},'b':{**node,'affected_work':['retired-work'],'status':'OPEN'}})
    seen={};assert inspect_opportunity(w,M1,g,1,seen) is None and not seen
