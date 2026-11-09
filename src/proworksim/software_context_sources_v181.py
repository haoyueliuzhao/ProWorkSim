"""Position-bound source accounting for masked and retrieved private history."""
import copy
from types import FunctionType
from . import software_sdk_input_sources_v159 as base


def annotate_agent_wire(wire,origins,*,member,projection=None,**kwargs):
    output,template,evidence=base.annotate_agent_wire(wire,origins,member=member,projection=projection,**kwargs)
    projection=projection or {}
    masked=projection.get('observation_history_projection',{}).get('context_treatment',{}).get('masked',[])
    indices=evidence.get('selected_indices',[])
    for item in masked:
        i=item['index']
        if i>=len(indices):raise ValueError('Masked observation lost its original SDK position')
        origin=origins[indices[i]];event='sdk:'+'+'.join(origin['event_ids'])
        output['messages'][i]=base.annotate_tree(wire['messages'][i],base.source('Artifact',event,member,
            value=wire['messages'][i],transformation='index',source_id=item['reference'],
            parent_source_ids=tuple(origin['event_ids'])))
    for i,index in enumerate(indices):
        message=wire['messages'][i];origin=origins[index]
        events=origin.get('events') or []
        if message.get('role')=='tool' and events and events[0].get('tool_name')=='context_read':
            event='sdk:'+'+'.join(origin['event_ids'])
            output['messages'][i]=base.annotate_tree(message,base.source('Retrieved',event,member,
                transformation='excerpt',parent_source_ids=(message['tool_call_id'],)))
    return output,template,evidence


class SDKRequestCapture(base.SDKRequestCapture):
    request=FunctionType(base.SDKRequestCapture.request.__code__,
        {**base.SDKRequestCapture.request.__globals__,'annotate_agent_wire':annotate_agent_wire})
