"""Three equal-permission views over one observed, canonical event pool."""
from __future__ import annotations
import copy
from collections import defaultdict, deque
from .software_context_compression_v175 import canonical, digest, is_observation
from .software_context_graph_v196 import GraphIntegrityError, GraphScopeError

VERSION='v196-equal-budget-event-and-graph-context-views-r1'
METHODS=('M1-5','M1-5K-v2','M1-5G')
RULES={'recent_tool_cycles':5,'added_content_tokens':4096,'maximum_event_tokens':768,
       'maximum_default_events':8,'maximum_request_input_tokens':98304,
       'graph_hops':2,'direct_focus':40,'dependency_1hop':25,'dependency_2hop':12,
       'current_version':8,'critical_failure':6,'other_evidence':2,
       'inferred_relation_multiplier':.5,'fallback':'M1-5'}
PRIORITY={'failed_test':100,'error':90,'change':80,'diff':75,'test':70,'artifact':60,'code':40}
FIELD_ORDER={'failed_test':0,'error_type':1,'error_excerpt':2,'reported_location':3,'path':4,
    'observed_command':5,'observed_command_json':5,'declared_selection':6,'observed_selection':6,
    'change_before':7,'change_after':8,'diff_excerpt':9,'written_text':10,'counts':11,
    'passed':12,'validation_status':13,'report_id':14}
PREFIX='[Retained observed evidence. Historical records do not verify a newer code version.]\n'
TRAVERSABLE={'contains','calls','imports','tests','modifies','depends_on','derived_from'}


def marker(reference):
    return '[Earlier private observation retained at '+reference+'. Use context_read for the exact original; it is historical evidence.]'


def baseline(payload,store,count,indices):
    result=copy.deepcopy(payload);messages=result['messages']
    tools=[i for i,m in enumerate(messages) if m.get('role')=='tool']
    observed=[i for i,m in enumerate(messages) if is_observation(m)]
    masked=[];cutoff=tools[-5] if len(tools)>5 else 0
    for i in observed:
        if not cutoff or i>=cutoff or i==observed[0] or i==len(messages)-1:continue
        ref=store.put(messages[i],indices[i]);text=marker(ref)
        if count(text)>=count(messages[i]['content']):continue
        messages[i]['content']=text;masked.append({'index':i,'original_index':indices[i],'reference':ref,'source_sha256':digest(payload['messages'][i])})
    return result,masked,cutoff


def candidates(graph,masked,indices,cutoff):
    available={m['original_index']:m['index'] for m in masked};current=set(indices[cutoff:]) if cutoff else set(indices)
    pool=[]
    for event in graph.events.values():
        anchors=[x for x in event['anchors'] if x in available]
        if not anchors:continue
        fields=[]
        for field in event['fields']:
            origins=[field['origin'],*field.get('supporting_origins',[])]
            # A recent observation already contains this exact fact.
            if any(graph.sources[o['source_id']]['message_index'] in current and
                   is_observation(graph.sources[o['source_id']]['message']) for o in origins):continue
            fields.append(field)
        if not fields:continue
        kind='failed_test' if event.get('critical_failure') else event['kind']
        pool.append({'event_id':event['id'],'entity_node':event['node'],'kind':kind,
            'anchor':available[max(anchors)],'last_index':event['last_index'],
            'version_status':graph.version_status(event),'version':event['version'],
            'fields':copy.deepcopy(fields),'paths':sorted(event['paths']),
            'sources':list(event['sources'])})
    return sorted(pool,key=lambda e:e['event_id'])


def distances(graph,*,dependency_edges=True):
    focus=graph.focus();roots={graph._file_nodes[p] for p in focus['paths'] if p in graph._file_nodes}
    adjacency=defaultdict(list)
    if dependency_edges:
        for edge in graph.edges.values():
            if edge['type'] not in TRAVERSABLE:continue
            # An old static/execution relation remains in the audit graph, but
            # cannot justify current dependency traversal after code changes.
            # Without observed per-file continuity, invalidate conservatively
            # at the workspace-version boundary.
            if edge.get('attrs',{}).get('version') not in (None,graph.current_version):continue
            confidence=1.0 if edge['status']=='Confirmed' else RULES['inferred_relation_multiplier']
            adjacency[edge['source']].append((edge['target'],confidence,edge['id']))
            adjacency[edge['target']].append((edge['source'],confidence,edge['id']))
    found={n:(0,1.0,[]) for n in roots};queue=deque(sorted(roots))
    while queue:
        node=queue.popleft();hops,confidence,path=found[node]
        if hops>=RULES['graph_hops']:continue
        for other,weight,eid in sorted(adjacency[node]):
            proposal=(hops+1,confidence*weight,path+[eid]);old=found.get(other)
            if old is None or proposal[0]<old[0] or (proposal[0]==old[0] and proposal[1]>old[1]):
                found[other]=proposal;queue.append(other)
    return focus,found


def rank(pool,graph,method,*,dependency_edges=True):
    if method=='M1-5K-v2':
        return sorted([(e,{'type_priority':PRIORITY[e['kind']]}) for e in pool],
            key=lambda item:(-PRIORITY[item[0]['kind']],-item[0]['last_index'],item[0]['event_id']))
    focus,reachable=distances(graph,dependency_edges=dependency_edges);focus_set=set(focus['paths']);ranked=[]
    for e in pool:
        direct=bool(focus_set.intersection(e['paths']))
        targets=[graph._file_nodes[p] for p in e['paths'] if p in graph._file_nodes]
        if e['entity_node']:targets.append(e['entity_node'])
        routes=[reachable[t] for t in targets if t in reachable]
        route=min(routes,key=lambda x:(x[0],-x[1],x[2])) if routes else None
        current_failure=(e['kind']=='failed_test' and e['version_status']=='current_observed_version' and not e['paths'])
        if not direct and route is None and not current_failure:continue
        score=RULES['direct_focus'] if direct else 0
        if route and route[0]>0:score+=RULES['dependency_'+str(route[0])+'hop']*route[1]
        if e['version_status']=='current_observed_version':score+=RULES['current_version']
        score+=RULES['critical_failure'] if e['kind']=='failed_test' else RULES['other_evidence']
        ranked.append((e,{'score':score,'direct_focus':direct,'dependency_path':route[2] if route else [],
            'dependency_confidence':route[1] if route else None,'unlocalized_current_failure':current_failure,
            'focus':focus['paths']}))
    return sorted(ranked,key=lambda item:(-item[1]['score'],-item[0]['last_index'],item[0]['event_id']))


def render(event,graph,store,count,indices,payload):
    reference=graph.nodes[event['version']]['attrs']['source_reference'] if event['version'] else None
    card={'event':event['event_id'],'kind':event['kind'],'version_status':event['version_status'],
        'source_version':reference,'text_is_not_new_validation':True,'facts':[],'originals':[],'retained_action_ids':[]}
    if event['kind'] in {'test','failed_test'}:card['validation_scope']='selected_public_tests_only'
    selected=[];omitted=[]
    actual={index:digest(message) for index,message in zip(indices,payload['messages'])}
    for field in sorted(event['fields'],key=lambda f:(FIELD_ORDER.get(f['name'],20),f['key'])):
        origin=field['origin'];source=graph.sources[origin['source_id']]
        if source['scope']!=[store.slot_id,store.member_id] or source['first_seen_step']>graph.step:
            raise GraphScopeError('A fact is outside the current private prefix')
        recovered=graph.field(origin['source_id'],origin['channel'],origin['pointer'],
            call_index=origin.get('call_index'),span=origin.get('span'))
        if recovered['value']!=field['value']:raise GraphIntegrityError('A selected fact differs from its source')
        proposal=copy.deepcopy(card);message=source['message']
        fact={'name':field['name'],'value':field['value']}
        if origin.get('span') is not None:fact['exact_excerpt']=True
        if is_observation(message):
            ref=store.put(message,source['message_index'])
            if ref not in proposal['originals']:proposal['originals'].append(ref)
        elif message.get('role')=='assistant' and actual.get(source['message_index'])==source['message_sha256']:
            cid=message['tool_calls'][origin['call_index']]['id']
            if cid not in proposal['retained_action_ids']:proposal['retained_action_ids'].append(cid)
        else:
            omitted.append({'field':field['key'],'reason':'source_not_recoverable_in_same_private_view'});continue
        proposal['facts'].append(fact)
        if count(PREFIX+canonical(proposal))>RULES['maximum_event_tokens']:
            omitted.append({'field':field['key'],'reason':'event_text_budget'});continue
        card=proposal;selected.append(field)
    if not selected:return None,{'omitted_fields':omitted}
    text=PREFIX+canonical(card)
    return text,{'selected_fields':selected,'omitted_fields':omitted,'card':card,
        'content_tokens_local_estimate':count(text)}


def project(payload,method,graph,store,*,count,source_indices=None,measure=None,decision_step=None,dependency_edges=True):
    if method not in METHODS:raise ValueError('Unknown context method')
    if [graph.episode,graph.member]!=[store.slot_id,store.member_id]:raise GraphScopeError('Private graph/store scope differs')
    indices=list(range(len(payload['messages']))) if source_indices is None else list(source_indices)
    base,masked,cutoff=baseline(payload,store,count,indices)
    proof={'version':VERSION,'method':method,'rules':copy.deepcopy(RULES),'masked':masked,
        'selected':[],'omitted_events':[],'fallback':None,'added_content_tokens_local_estimate':0,
        'same_original_evidence_permissions':True,'dependency_edges_enabled':dependency_edges,
        'provider_exact_tokens_claimed':False,'original_actions_and_recent_window_unchanged':True}
    def token_measure(wire):
        value=measure(wire) if measure else count(canonical({k:wire[k] for k in ('messages','tools') if k in wire}))
        return value['prompt_tokens'] if isinstance(value,dict) else value
    base_tokens=token_measure(base);proof['baseline_input_tokens_local_estimate']=base_tokens
    if method=='M1-5':
        proof['input_tokens_local_estimate']=base_tokens;proof['input_capacity_fits']=base_tokens<=RULES['maximum_request_input_tokens'];return base,proof
    try:
        if decision_step is not None and graph.step!=decision_step:raise GraphIntegrityError('Graph temporal cutoff differs')
        if any(n['first_seen_step']>graph.step for n in graph.nodes.values()):raise GraphIntegrityError('Future node')
        if any(e['source'] not in graph.nodes or e['target'] not in graph.nodes for e in graph.edges.values()):raise GraphIntegrityError('Broken graph edge')
        pool=candidates(graph,masked,indices,cutoff)
        proof['candidate_pool_sha256']=digest(pool);proof['candidate_pool_size']=len(pool)
        result=copy.deepcopy(base);occupied=set()
        for event,reason in rank(pool,graph,method,dependency_edges=dependency_edges):
            if len(proof['selected'])>=RULES['maximum_default_events']:
                proof['omitted_events'].append({'event_id':event['event_id'],'reason':'event_count_budget'});continue
            if event['anchor'] in occupied:
                proof['omitted_events'].append({'event_id':event['event_id'],'reason':'original_message_position_already_used'});continue
            text,view=render(event,graph,store,count,indices,payload)
            if text is None:
                proof['omitted_events'].append({'event_id':event['event_id'],'reason':'no_recoverable_bounded_fact'});continue
            cost=view['content_tokens_local_estimate']
            if proof['added_content_tokens_local_estimate']+cost>RULES['added_content_tokens']:
                proof['omitted_events'].append({'event_id':event['event_id'],'reason':'added_text_budget'});continue
            proposed=copy.deepcopy(result);proposed['messages'][event['anchor']]['content']=text
            if token_measure(proposed)>RULES['maximum_request_input_tokens']:
                proof['omitted_events'].append({'event_id':event['event_id'],'reason':'whole_request_capacity'});continue
            result=proposed;occupied.add(event['anchor']);proof['added_content_tokens_local_estimate']+=cost
            proof['selected'].append({'event_id':event['event_id'],'anchor':event['anchor'],'rank_reason':reason,**view})
        proof['input_tokens_local_estimate']=token_measure(result)
        proof['input_capacity_fits']=proof['input_tokens_local_estimate']<=RULES['maximum_request_input_tokens']
        return result,proof
    except GraphScopeError:
        raise
    except (GraphIntegrityError,KeyError,TypeError,ValueError,IndexError) as error:
        proof.update(selected=[],added_content_tokens_local_estimate=0,
            fallback={'method':'M1-5','error_type':type(error).__name__,'message':str(error)},
            input_tokens_local_estimate=base_tokens,input_capacity_fits=base_tokens<=RULES['maximum_request_input_tokens'])
        return base,proof


def update_and_project(payload,method,graph,store,*,step,count,source_indices=None,measure=None):
    """Integration entry point: graph maintenance failure cannot stop an Agent.

    A failed index is disabled for this private conversation; the exact raw
    observations remain available via the same reader. Cross-scope requests
    are rejected, never served from another member's fallback history.
    """
    if method not in METHODS:raise ValueError('Unknown context method')
    if [graph.episode,graph.member]!=[store.slot_id,store.member_id]:raise GraphScopeError('Private graph/store scope differs')
    fault=getattr(graph,'disabled_after_integrity_error',None)
    if fault is None:
        try:graph.ingest(payload,step=step,source_indices=source_indices)
        except GraphScopeError:raise
        except (GraphIntegrityError,KeyError,TypeError,ValueError,IndexError,RecursionError) as error:
            fault={'method':'M1-5','phase':'graph_update','error_type':type(error).__name__,'message':str(error)}
            graph.disabled_after_integrity_error=fault
    value,proof=project(payload,'M1-5' if fault else method,graph,store,count=count,
        source_indices=source_indices,measure=measure,decision_step=step)
    if fault:proof.update(method=method,fallback=copy.deepcopy(fault))
    return value,proof
