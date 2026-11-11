"""Evaluation-only literal evidence coverage, separate from selection policy."""
from .software_context_graph_check_v196 import at

def covers(value,origin,reference):
    if origin.get('channel')!='body' or origin.get('source_id')!=reference['source_id'] or origin.get('message_sha256')!=reference['message_sha256']:return False
    pointer=origin['pointer'];target=reference['pointer'];span=origin.get('span');wanted=reference.get('span')
    try:
        if pointer==target:
            if wanted:
                a,z=span if span is not None else (0,len(value))
                return a<=wanted[0]<=wanted[1]<=z and value[wanted[0]-a:wanted[1]-a]==reference['value']
            return span is None and value==reference['value']
        if span is None and target.startswith(pointer+'/'):
            child=at(value,target[len(pointer):])
            if wanted:child=child[wanted[0]:wanted[1]]
            return child==reference['value']
    except (KeyError,TypeError,IndexError):return False
    return False

def fact_covers(fact,reference):
    return any(covers(fact['value'],o,reference) for o in fact['origins'])
