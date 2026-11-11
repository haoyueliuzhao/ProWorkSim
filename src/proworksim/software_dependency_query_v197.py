"""Factorized, typed queries over the unchanged v196 observed work graph."""
from __future__ import annotations
import copy,json,re
from collections import defaultdict
from .software_context_compression_v175 import canonical,digest
from .software_context_selection_v196 import baseline,candidates,render,PRIORITY
from .software_context_graph_v196 import GraphIntegrityError,GraphScopeError

VERSION='v197-typed-observed-dependency-query-r1'
CONDITIONS=('G0','G1','G2','G3','G4')
# Types are directed semantic descriptions; traversal may follow an edge
# backwards to locate the evidence of a code entity, never reverse its claim.
PATHS={
 'code':[(('contains','calls'),26),(('imports','depends_on'),18),(('contains','calls','depends_on'),20),(('contains','calls','depends_on','calls'),14)],
 'test':[(('tests',),32),(('tests','contains'),24),(('tests','contains','calls'),16),(('contains',),8),(('imports','depends_on'),18)],
 'version':[(('modifies',),32),(('derived_from',),20),(('tests',),24)],
 'locate':[(('contains',),12),(('imports','depends_on'),20),(('contains','calls'),20)]}
POLICY={'version':VERSION,'paths':PATHS,'budgets':[1024,2048,4096],'primary_budget':4096,
 'maximum_cards':8,'maximum_card_tokens':768,'maximum_input':98304,
 'direct_score':40,'current_bonus':8,'critical_bonus':6,'other_bonus':2,'inferred_multiplier':.5,
 'same_candidates_renderer_scope_and_version_guards':True,'primary_task_roots':False,
 'missing_or_invalid_graph_fallback':'G0','graph_is_not_added_whole_to_prompt':True}


def state(payload):
    for m in reversed(payload['messages']):
        for call in reversed(m.get('tool_calls',[])):
            name=call.get('function',{}).get('name')
            if name in {'run_tests','read_test_result'}:return 'test'
            if name in {'fix_patch','submit_integration','integrate_patch','delivery_status','diff_workspace'}:return 'version'
            if name in {'write_file','replace_file','create_file','delete_file','rename_file','read_file'}:return 'code'
            if name in {'search_repository','search_file','list_files','read_task'}:return 'locate'
    return 'locate'


def task_roots(graph):
    """Literal issue/diagnostic lookup in ALREADY seen entities, not root cause."""
    issue=''
    for s in sorted(graph.sources.values(),key=lambda z:(z['first_seen_step'],z['message_index'])):
        try:b=json.loads(s['message'].get('content',''))
        except (ValueError,TypeError):continue
        if isinstance(b,dict):
            goal=b.get('observation',{}).get('root_goal',{})
            if isinstance(goal,dict) and isinstance(goal.get('description'),str):issue=goal['description'];break
    found={}
    for n in graph.nodes.values():
        if n['type']!='Code':continue
        attr=n['attrs'];path=attr.get('path');symbol=attr.get('symbol')
        if not path:continue
        if path in issue:found[path]='literal_path_in_original_issue'
        elif symbol and len(symbol)>=4 and re.search(r'(?<![\w])'+re.escape(symbol)+r'(?![\w])',issue):
            found[path]='literal_symbol_in_original_issue_not_causal_proof'
    return found


def typed_routes(graph,phase,*,inferred=False,extra_roots=False):
    roots=set(graph.focus()['paths']);lexical=task_roots(graph) if extra_roots else {}
    roots.update(lexical);root_nodes={graph._file_nodes[p] for p in roots if p in graph._file_nodes}
    adj=defaultdict(list);excluded=0
    for e in graph.edges.values():
        if e['status']=='Inferred' and not inferred:continue
        if e.get('attrs',{}).get('version') not in (None,graph.current_version):excluded+=1;continue
        if e['type'] in {'observed_in','validates','supersedes'}:continue
        adj[e['source']].append((e['target'],e));adj[e['target']].append((e['source'],e))
    best={n:{'weight':0,'edges':[],'root':n,'types':[],'inferred_edges':0} for n in root_nodes}
    for sequence,weight in PATHS[phase]:
        frontier=[(n,n,[],[n],0) for n in sorted(root_nodes)]
        for kind in sequence:
            following=[]
            for node,origin,path,visited,uncertain in frontier:
                for nxt,edge in sorted(adj[node],key=lambda a:a[1]['id']):
                    if edge['type']!=kind or nxt in visited:continue
                    following.append((nxt,origin,path+[edge['id']],visited+[nxt],uncertain+int(edge['status']=='Inferred')))
            frontier=following
        for end,origin,path,visited,uncertain in frontier:
            proposal={'weight':weight*(.5**uncertain),'edges':path,'root':origin,'types':list(sequence),'inferred_edges':uncertain}
            old=best.get(end)
            if old is None or (proposal['weight'],-len(path),path)>(old['weight'],-len(old['edges']),old['edges']):best[end]=proposal
    return roots,best,{'phase':phase,'roots':sorted(roots),'literal_task_roots':lexical,'stale_edges_excluded':excluded}


def rank(pool,graph,condition,phase,*,extra_roots=False,no_path=False,no_version_bonus=False):
    if condition=='G1':
        return [(e,{'type_priority':PRIORITY[e['kind']]}) for e in sorted(pool,key=lambda e:(-PRIORITY[e['kind']],-e['last_index'],e['event_id']))],{}
    if condition in {'G3','G4'}:
        roots,routes,query=typed_routes(graph,phase,inferred=condition=='G4',extra_roots=extra_roots)
    else:
        roots=set(graph.focus()['paths']);lexical=task_roots(graph) if extra_roots else {};roots.update(lexical)
        routes={};query={'phase':phase,'roots':sorted(roots),'literal_task_roots':lexical,'stale_edges_excluded':0}
    ranked=[]
    for e in pool:
        direct=bool(roots.intersection(e['paths']))
        endpoints=[graph._file_nodes[p] for p in e['paths'] if p in graph._file_nodes]+[e['entity_node']]
        options=[routes[n] for n in endpoints if n in routes and routes[n]['edges']]
        route=max(options,key=lambda r:(r['weight'],-len(r['edges']),r['edges'])) if options else None
        unlocalized=e['kind']=='failed_test' and e['version_status']=='current_observed_version' and not e['paths']
        if not (direct or route or unlocalized or no_path):continue
        score=(40 if direct and not no_path else 0)+(route['weight'] if route and not direct else 0)
        if not no_version_bonus and e['version_status']=='current_observed_version':score+=8
        score+=6 if e['kind']=='failed_test' else 2
        ranked.append((e,{'score':score,'direct':direct,'phase':phase,
            'typed_route':route if not direct else None,'unlocalized_current_failure':unlocalized}))
    return sorted(ranked,key=lambda a:(-a[1]['score'],-a[0]['last_index'],a[0]['event_id'])),query


def project(payload,condition,graph,store,*,count,measure,indices,budget=4096,extra_roots=False,no_path=False,no_version_bonus=False):
    if condition not in CONDITIONS:raise ValueError('Unknown condition')
    if budget not in POLICY['budgets']:raise ValueError('Unfrozen budget')
    if [graph.episode,graph.member]!=[store.slot_id,store.member_id]:raise GraphScopeError('Private source boundary')
    base,masked,cutoff=baseline(payload,store,count,indices);phase=state(payload)
    proof={'version':VERSION,'condition':condition,'budget':budget,'masked':masked,'selected':[],
        'added_content_tokens_local_estimate':0,'omitted_events':[],'fallback':None,'phase':phase,
        'diagnostics':{'extra_roots':extra_roots,'no_path':no_path,'no_version_bonus':no_version_bonus}}
    base_tokens=measure(base);proof['base_input_tokens_local_estimate']=base_tokens
    try:
        pool=candidates(graph,masked,indices,cutoff);proof['candidate_pool_sha256']=digest(pool);proof['candidate_pool_size']=len(pool)
        ranked,query=rank(pool,graph,condition,phase,extra_roots=extra_roots,no_path=no_path,no_version_bonus=no_version_bonus) if condition!='G0' else ([],{})
        proof['query']=query;result=copy.deepcopy(base);occupied=set()
        for event,reason in ranked:
            if len(proof['selected'])==8:proof['omitted_events'].append({'event':event['event_id'],'reason':'card_count'});continue
            if event['anchor'] in occupied:proof['omitted_events'].append({'event':event['event_id'],'reason':'same_position'});continue
            text,info=render(event,graph,store,count,indices,payload)
            if text is None:continue
            cost=count(text)
            if cost+proof['added_content_tokens_local_estimate']>budget:proof['omitted_events'].append({'event':event['event_id'],'reason':'token_budget'});continue
            value=copy.deepcopy(result);value['messages'][event['anchor']]['content']=text
            if measure(value)>98304:proof['omitted_events'].append({'event':event['event_id'],'reason':'capacity'});continue
            result=value;occupied.add(event['anchor']);proof['added_content_tokens_local_estimate']+=cost
            proof['selected'].append({'event_id':event['event_id'],'anchor':event['anchor'],'rank_reason':reason,**info})
        proof['input_tokens_local_estimate']=measure(result);return result,proof
    except GraphScopeError:raise
    except (GraphIntegrityError,KeyError,TypeError,ValueError,IndexError) as error:
        proof.update(selected=[],added_content_tokens_local_estimate=0,input_tokens_local_estimate=base_tokens,
            fallback={'condition':'G0','error':type(error).__name__+': '+str(error)})
        return base,proof
