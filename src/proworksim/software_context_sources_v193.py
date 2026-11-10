"""Trace critical-card payload to its original tool observation and SDK event."""
from types import FunctionType
from . import software_context_sources_v181 as original
from . import software_sdk_input_sources_v159 as base


def annotate_agent_wire(wire,origins,*,member,projection=None,**kwargs):
    output,template,evidence=original.annotate_agent_wire(wire,origins,member=member,projection=projection,**kwargs)
    projection=projection or {}
    cards=projection.get('observation_history_projection',{}).get('context_treatment',{}).get('critical_cards',[])
    indices=evidence.get('selected_indices',[])
    for card in cards:
        i=card['index']
        if i>=len(indices):raise ValueError('Critical event lost its original SDK source position')
        origin=origins[indices[i]];event='sdk:'+'+'.join(origin['event_ids'])
        output['messages'][i]=base.annotate_tree(wire['messages'][i],base.source('Tool-feedback',event,member,
            value=wire['messages'][i],transformation='structured',source_id='critical-event:'+card['reference'],
            parent_source_ids=tuple(origin['event_ids'])))
    return output,template,evidence


class SDKRequestCapture(original.SDKRequestCapture):
    request=FunctionType(original.SDKRequestCapture.request.__code__,
        {**original.SDKRequestCapture.request.__globals__,'annotate_agent_wire':annotate_agent_wire})
