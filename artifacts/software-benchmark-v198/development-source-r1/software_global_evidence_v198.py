"""Global evidence inventory, lexical discovery, and explicit coverage budget."""
from __future__ import annotations
import copy,json,math,re
from collections import Counter,defaultdict
from .software_context_compression_v175 import canonical,digest,is_observation
from .software_context_graph_v196 import obj,source_ref,safe_path,GraphScopeError
from .software_context_selection_v196 import baseline,candidates,render,PRIORITY

VERSION='v198-global-observed-evidence-discovery-r1'
CONDITIONS=('G0','G1','G2','G3','G4')
POLICY={'budgets':[1024,2048,4096],'primary_budget':4096,'maximum_input':98304,'maximum_card_tokens':768,
 'hard_card_count_cap':None,'k1':1.2,'b':.75,'path_bonus':2,'current_bonus':1,'failure_bonus':2,
 'coverage':'latest unsuccessful report per exact selector, unresolved by later same-selector success',
 'scope':'development_only','no_annotation_features':True}
STOP=set('the a an to of in on is are for as and or with by be at from this that it not if when should have has was were true false none self return def class import'.split())
PRIORITIES={**PRIORITY,'task':55,'search':45,'environment':50,'state':30,'note':20,'raw':15}

def terms(text):return [x for x in re.findall(r'[A-Za-z_][A-Za-z_0-9]{2,}',text.lower()) if x not in STOP]

def query_text(payload,graph):
    issue=''
    for s in sorted(graph.sources.values(),key=lambda s:s['first_seen_step']):
        b=obj(s['message'].get('content'));goal=b.get('observation',{}).get('root_goal',{})
        if isinstance(goal,dict) and goal.get('description'):issue=goal['description'];break
    actions=[c for m in payload['messages'] for c in m.get('tool_calls',[])]
    return issue+'\n'+'\n'.join(canonical(c['function']) for c in actions[-3:])

def excerpt(text,query,maximum=512):
    hits=[text.lower().find(t) for t in set(terms(query)) if len(t)>=4 and text.lower().find(t)>=0]
    start=max(0,min(hits)-100) if hits else 0
    return start,min(len(text),start+maximum)

def enrich(graph,payload,indices):
    """Mutate only the new caller-owned graph copy, never frozen v196 records."""
    query=query_text(payload,graph);covered={sid for e in graph.events.values() for sid in e['sources']}
    lookup={(s['message_index'],s['message_sha256']):sid for sid,s in graph.sources.items()}
    additions=[];enriched=[]
    for event in list(graph.events.values()):
        if event['kind']!='code':continue
        for sid in event['sources']:
            b=obj(graph.sources[sid]['message'].get('content'));text=b.get('result',{}).get('text')
            if isinstance(text,str):
                graph._add(event,'code_excerpt',graph.field(sid,'body','/result/text',span=excerpt(text,query)))
                enriched.append(event['id']);break
    action_map={c['id']:c for m in payload['messages'] for c in m.get('tool_calls',[])}
    for index,m in zip(indices,payload['messages']):
        if not is_observation(m):continue
        sid=lookup.get((index,digest(m)))
        if not sid or sid in covered:continue
        b=obj(m.get('content'));is_state=m.get('role')=='user';r=b.get('observation' if is_state else 'result');r=r if isinstance(r,dict) else {}
        base_pointer='/observation' if is_state else '/result'
        tool=m.get('name') or action_map.get(m.get('tool_call_id'),{}).get('function',{}).get('name','unknown')
        kind='state' if is_state else 'search' if tool in {'search_file','search_repository','list_files'} else 'task' if tool=='read_task' else 'note' if tool.startswith('work_') else 'raw'
        reference=r.get('workspace_reference') if is_state else source_ref(r)
        ver=next((nid for nid,n in graph.nodes.items() if n['type']=='Version' and n['attrs'].get('source_reference')==reference),None)
        node=next((nid for nid,n in graph.nodes.items() if n['type']=='Observation' and n['attrs'].get('source_id')==sid),None)
        if node is None:continue
        e=graph._event(['v198-open-observation',index,digest(m)],kind,sid,index,node=node,version=ver)
        for pointer in ['/result/text','/result/page/text','/error/message']:
            try:value=graph.field(sid,'body',pointer)['value']
            except (KeyError,TypeError):continue
            if isinstance(value,str):graph._add(e,'observed_excerpt',graph.field(sid,'body',pointer,span=excerpt(value,query)))
        # Structured search/list responses may expose paths and matched lines.
        state_keys=['workspace_reference','current_version_test_coverage','delivery_status','tasks','messages','handoffs','personal_workbench']
        items=[(k,r[k]) for k in state_keys if k in r] if is_state else list(r.items())[:16]
        for key,value in items:
            if key in {'text','page'}:continue
            if isinstance(value,(str,int,bool)):
                graph._try(e,key,sid,'body',base_pointer+'/'+key,**({'span':(0,min(256,len(value)))} if isinstance(value,str) else {}))
            elif is_state and isinstance(value,dict):
                for sub,v in list(value.items())[:6]:
                    if isinstance(v,(str,int,bool)) or v is None:
                        graph._try(e,key+'_'+sub,sid,'body',base_pointer+'/'+key+'/'+sub,**({'span':(0,min(256,len(v)))} if isinstance(v,str) else {}))
            elif isinstance(value,list):
                for j,item in enumerate(value[:4]):
                    if isinstance(item,(str,int,bool)):
                        graph._try(e,key,sid,'body',f'{base_pointer}/{key}/{j}',**({'span':(0,min(256,len(item)))} if isinstance(item,str) else {}))
                    elif isinstance(item,dict):
                        for sub in ('path','line','line_number','text','name'):
                            if sub in item and isinstance(item[sub],(str,int)):
                                v=item[sub];graph._try(e,key+'_'+sub,sid,'body',f'{base_pointer}/{key}/{j}/{sub}',**({'span':(0,min(256,len(v)))} if isinstance(v,str) else {}))
        if not e['fields']:
            # An exact observation excerpt is a source record, not an inferred fact.
            graph._add(e,'observed_raw_excerpt',graph.field(sid,'message','/content',span=excerpt(m['content'],query)))
        for field in e['fields']:
            if field['name'].endswith('path') and safe_path(field['value']):e['paths'].append(safe_path(field['value']))
        additions.append({'event_id':e['id'],'kind':kind,'tool':tool,'source_id':sid,'message_index':index})
    return {'new_observations':additions,'code_excerpt_events':sorted(set(enriched))}

def mandatory_events(graph,pool):
    latest={};candidate_ids={e['event_id'] for e in pool};proof={}
    for e in sorted(graph.events.values(),key=lambda e:e['first_index']):
        if e['kind']!='test':continue
        selector=next((f['value'] for f in e['fields'] if f['name']=='declared_selection'),None)
        key=digest(selector) if selector is not None else e['id']
        latest[key]=e
    for key,e in latest.items():
        if e.get('passed') is False and e['id'] in candidate_ids:
            proof[e['id']]={'constraint':'latest_observed_unsuccessful_actual_test_for_exact_selector',
                'selector_identity':key,'source_version':e.get('version'),'does_not_prove_current_code_failure':True,
                'source_ids':e['sources']}
    return proof

def bm25(pool,query):
    docs={e['event_id']:terms(' '.join(e['paths'])+' '+canonical([f['value'] for f in e['fields']])) for e in pool}
    q=set(terms(query));n=len(docs);avg=sum(map(len,docs.values()))/n if n else 1;df=Counter(t for doc in docs.values() for t in set(doc));scores={}
    for eid,doc in docs.items():
        freq=Counter(doc);score=0
        for t in q:
            f=freq[t]
            if f:score+=math.log(1+(n-df[t]+.5)/(df[t]+.5))*f*2.2/(f+1.2*(.25+.75*len(doc)/max(avg,1)))
        scores[eid]=score
    return scores

def graph_boost(pool,entities,seeds,*,inferred=False):
    """Evidence is linked through exact entities; no global Version hub walk."""
    seed_entities=set().union(*(set(entities.event_bindings.get(e,[])) for e in seeds)) if seeds else set()
    allowed={'declares','references','reports_test'}|({'resolves_to'} if inferred else set())
    reached=set(seed_entities);used=[]
    for edge in entities.edges.values():
        if edge['relation_type'] not in allowed or not edge.get('effective_for_current_workspace',True):continue
        if edge['verification_status']=='Inferred' and not inferred:continue
        if edge['source_entity_id'] in seed_entities or edge['target_entity_id'] in seed_entities:
            reached.update((edge['source_entity_id'],edge['target_entity_id']));used.append(edge['edge_id'])
    boosts={}
    for e in pool:
        matches=set(entities.event_bindings.get(e['event_id'],[]))&reached
        if matches:boosts[e['event_id']]={'bonus':1.0,'entities':sorted(matches),'edge_ids':[eid for eid in used if entities.edges[eid]['source_entity_id'] in matches or entities.edges[eid]['target_entity_id'] in matches]}
    return boosts

def project(payload,condition,graph,entities,store,*,count,measure,indices,budget):
    if condition not in CONDITIONS or budget not in POLICY['budgets']:raise ValueError('Unfrozen condition or budget')
    if [graph.episode,graph.member]!=[store.slot_id,store.member_id] or entities.scope!=[graph.episode,graph.member]:raise GraphScopeError('Private scope mismatch')
    base,masked,cutoff=baseline(payload,store,count,indices);pool=candidates(graph,masked,indices,cutoff)
    query=query_text(payload,graph);scores=bm25(pool,query);focus=set(graph.focus()['paths']);must=mandatory_events(graph,pool) if condition in {'G2','G3','G4'} else {}
    rank_scores={e['event_id']:scores[e['event_id']]+2*bool(focus&set(e['paths']))+int(e['version_status']=='current_observed_version')+2*(e['kind']=='failed_test') for e in pool}
    seed_ids=sorted(rank_scores,key=lambda k:(-rank_scores[k],k))[:8]
    boosts=graph_boost(pool,entities,seed_ids,inferred=condition=='G4') if condition in {'G3','G4'} else {}
    if condition=='G1':ranked=sorted(pool,key=lambda e:(-PRIORITIES[e['kind']],-e['last_index'],e['event_id']))
    else:ranked=sorted(pool,key=lambda e:(e['event_id'] not in must,-rank_scores[e['event_id']]-boosts.get(e['event_id'],{}).get('bonus',0),-e['last_index'],e['event_id']))
    proof={'version':VERSION,'condition':condition,'budget':budget,'masked':masked,'candidate_pool_sha256':digest(pool),
        'candidate_count':len(pool),'selected':[],'omitted':[],'mandatory':must,'added_tokens_estimate':0,'graph_boosts':boosts,
        'hard_path_eligibility':False,'hard_card_cap':None,'baseline_input_tokens_estimate':measure(base)}
    result=copy.deepcopy(base);occupied=set()
    for event in ranked if condition!='G0' else []:
        if event['anchor'] in occupied:proof['omitted'].append({'event':event['event_id'],'reason':'same_position'});continue
        text,info=render(event,graph,store,count,indices,payload)
        if text is None:proof['omitted'].append({'event':event['event_id'],'reason':'no_bounded_fact'});continue
        if count(text)+proof['added_tokens_estimate']>budget:
            proof['omitted'].append({'event':event['event_id'],'reason':'token_budget','mandatory':event['event_id'] in must});continue
        proposed=copy.deepcopy(result);proposed['messages'][event['anchor']]['content']=text
        if measure(proposed)>98304:proof['omitted'].append({'event':event['event_id'],'reason':'whole_capacity'});continue
        result=proposed;occupied.add(event['anchor']);proof['added_tokens_estimate']+=count(text)
        proof['selected'].append({'event_id':event['event_id'],'anchor':event['anchor'],'mandatory':event['event_id'] in must,
            'retrieval_score':rank_scores[event['event_id']],'graph_bonus':boosts.get(event['event_id']),**info})
    chosen={e['event_id'] for e in proof['selected']};proof['unmet_mandatory']=sorted(set(must)-chosen)
    proof['coverage_constraint_satisfied']=not proof['unmet_mandatory'];proof['input_tokens_estimate']=measure(result)
    return result,proof,pool
