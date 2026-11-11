"""Event -> literal Fact -> source Span, with no learned summarizer or I/O."""
from __future__ import annotations
import copy,json,math,re
from collections import Counter,defaultdict
from .software_context_compression_v175 import canonical,digest,is_observation
from .software_context_graph_v196 import obj,GraphIntegrityError,GraphScopeError
from .software_context_selection_v196 import baseline
from .software_global_evidence_v198 import query_text,terms,mandatory_events

VERSION='v199-fact-grounded-context-r3'
CONDITIONS={'E0':(False,False,False),'E1':(True,False,False),'E2':(False,True,False),'E3':(True,True,False),'E4':(True,True,True)}
DOMAIN=('workspace_reference','current_version_test_coverage','delivery_status','tasks','messages','handoffs','personal_workbench')
PRIORITY={'explicit_assert_false':95,'exception':90,'diagnostic_output':85,'assertion_context':80,
 'code_function':75,'code_control':72,'code_dispatch':70,'code_statement':40,'failed_test':60,
 'observed_excerpt':25,'state_value':20,'declared_selection':15,'metadata':10,'counts':100,'passed':99}


def normalize(graph):
    groups={};aliases={};last_state={};transitions=[]
    for e in sorted(graph.events.values(),key=lambda e:(e['first_index'],e['id'])):
        ref=graph.nodes[e['version']]['attrs']['source_reference'] if e.get('version') else None
        if e['kind']=='state':
            sid=e['sources'][-1];state=obj(graph.sources[sid]['message'].get('content')).get('observation',{})
            projected=copy.deepcopy({k:state[k] for k in DOMAIN if k in state})
            if isinstance(projected.get('personal_workbench'),dict):
                projected['personal_workbench'].pop('observed_history_entries',None)
            domain_key=canonical([graph.episode,graph.member,'workspace_state'])
            identity=canonical([ref,projected]);previous=last_state.get(domain_key)
            if previous and previous[0]==identity:key=previous[1]
            else:
                key='group:'+digest([domain_key,ref,identity,e['first_index']])[:24]
                if previous:
                    transitions.append({'from':previous[1],'to':key,'at_message_index':e['first_index'],'same_version':previous[2]==ref})
                    if previous[1] in groups:groups[previous[1]]['superseded_by_state']=key
                last_state[domain_key]=(identity,key,ref)
        elif e['kind']=='code' and e.get('version') and e['paths']:
            key='group:'+digest([graph.episode,graph.member,'code_read',sorted(e['paths']),ref])[:24]
        elif e['kind']=='diff' and e.get('version'):
            texts=[obj(graph.sources[sid]['message'].get('content')).get('result',{}).get('text') for sid in e['sources']]
            key='group:'+digest([graph.episode,graph.member,'exact_observed_diff',ref,texts])[:24]
        else:key='group:'+digest([graph.episode,graph.member,e['id']])[:24]
        if key not in groups:groups[key]={'id':key,'kind':e['kind'],'version':e.get('version'),'source_reference':ref,
            'scope':[graph.episode,graph.member],'members':[],'sources':[],'anchors':[],'paths':[],'last_index':e['last_index'],
            'superseded_by_state':None,'raw_occurrences':[]}
        g=groups[key];g['members'].append(e['id']);aliases[e['id']]=key
        for prop in ('sources','anchors','paths'):g[prop]=sorted(set(g[prop])|set(e[prop]))
        g['last_index']=max(g['last_index'],e['last_index'])
        g['raw_occurrences'].append({'event_id':e['id'],'message_indices':e['anchors'],'source_ids':e['sources']})
    return groups,aliases,transitions


def real_lines(text):
    offsets=[];pos=0
    for line in text.splitlines(keepends=True):offsets.append((pos,pos+len(line),line));pos+=len(line)
    if not offsets and text:offsets=[(0,len(text),text)]
    return offsets


def code_spans(text):
    """Whole visible blocks when bounded; no partial snippet gains a symbol ID."""
    lines=real_lines(text);items=[]
    for i,(a,b,line) in enumerate(lines):
        stripped=line.strip()
        if not stripped or stripped.startswith('#'):continue
        indent=len(line.expandtabs(8))-len(line.expandtabs(8).lstrip())
        function=bool(re.match(r'(?:async\s+)?def\s+\w+',stripped))
        control=bool(re.match(r'(if|elif|else|try|except|for|while|with)\b',stripped))
        if function or control:
            j=i+1
            while j<len(lines):
                t=lines[j][2];s=t.strip();n=len(t.expandtabs(8))-len(t.expandtabs(8).lstrip())
                if s and not s.startswith('#') and n<=indent:
                    if control and n==indent and re.match(r'(elif|else|except|finally)\b',s):j+=1;continue
                    break
                j+=1
            end=lines[j][0] if j<len(lines) else len(text)
            if end-a<=2400:items.append(('code_function' if function else 'code_control',a,end))
        if re.match(r'[A-Za-z_]\w*\s*=\s*\{',stripped):
            end=b
            # This is a literal bounded table, not inferred dispatch behavior.
            for j in range(i,min(len(lines),i+12)):
                end=lines[j][1]
                if '}' in lines[j][2]:break
            if end-a<=1200:items.append(('code_dispatch',a,end))
        if re.match(r'(return|raise|assert)\b|assert_\w+\(|[A-Za-z_]\w*\s*=',stripped):
            if b-a<=600:items.append(('code_statement',a,b))
    if not items and text:items=[('observed_excerpt',0,min(len(text),512))]
    return list(dict.fromkeys(items))


def diagnostic_spans(text):
    # Split both real and JSON-escaped newlines while preserving raw offsets.
    starts=[0]+[m.end() for m in re.finditer(r'\\n|\n',text)];ends=[m.start() for m in re.finditer(r'\\n|\n',text)]+[len(text)]
    out=[]
    for a,z in zip(starts,ends):
        line=text[a:z];kind=None
        if re.search(r'\bassert\s+False\b',line):kind='explicit_assert_false'
        elif re.search(r'\b\w*(?:Error|Exception|Warning)\b',line):kind='exception'
        elif re.match(r'\s*[A-Z][A-Z0-9_ ]{1,30}(?::|=|\s)\s*.+',line) and not re.match(r'\s*(FAILED|ERROR|INFO|WARNING)\b',line):kind='diagnostic_output'
        elif re.match(r'\s*(?:>|E)\s+.*(?:assert|AssertionError|\[)',line):kind='assertion_context'
        if kind:
            stripped_start=a+len(line)-len(line.lstrip());out.append((kind,stripped_start,min(z,stripped_start+360)))
    return list(dict.fromkeys(out))


class FactInventory:
    def __init__(self,graph,payload,indices,masked,cutoff):
        self.graph=graph;self.indices=indices;self.masked=masked;self.cutoff=cutoff
        self.groups,self.aliases,self.state_transitions=normalize(graph);self.facts={};self.group_facts=defaultdict(list)
        self.frame={i:m for i,m in zip(indices,payload['messages'])}
        self.old_positions={m['original_index']:m['index'] for m in masked}
        self.visible_indices=set(indices)-set(self.old_positions)
        self.actions={c['id']:(sid,j,c) for sid,s in graph.sources.items() for j,c in enumerate(s['message'].get('tool_calls',[]))}
        self._build()

    def add(self,gid,kind,field,name=None):
        origin=copy.deepcopy(field['origin']);s=self.graph.sources[origin['source_id']]
        if s['scope']!=self.groups[gid]['scope'] or s['first_seen_step']>self.graph.step:raise GraphScopeError('Fact outside private prefix')
        origin.update(message_index=s['message_index'],message_sha256=s['message_sha256'])
        m=s['message'];body=obj(m.get('content'));r=body.get('result',{});r=r if isinstance(r,dict) else {}
        location=None
        if origin['channel']=='body' and origin['pointer']=='/result/text' and r.get('path') and origin.get('span') and type(r.get('start_character'))is int:
            location={'path':r['path'],'reference':r.get('source_reference'),'chars':[r['start_character']+x for x in origin['span']]}
        elif origin['channel']=='body' and origin['pointer']=='/result/page/text' and origin.get('span'):
            page=r.get('page',{})
            if type(page.get('start'))is int:location={'report_id':r.get('report_id'),'body_sha256':r.get('body_sha256'),'chars':[page['start']+x for x in origin['span']]}
        name=name or kind;identity=[self.groups[gid]['scope'],gid,kind,name,field['value'],location]
        fid='fact:'+digest(identity)[:24]
        if fid not in self.facts:
            self.facts[fid]={'id':fid,'event_id':gid,'kind':kind,'name':name,'value':copy.deepcopy(field['value']),'origins':[],
                'version':self.groups[gid]['source_reference'],'semantic_location':location,'status':'literal_observed_not_generated',
                'presentation_role':'occurrence_counter' if name=='personal_workbench_observed_history_entries' else 'evidence'}
            self.group_facts[gid].append(fid)
        if origin not in self.facts[fid]['origins']:self.facts[fid]['origins'].append(origin)

    def _build(self):
        g=self.graph
        for gid,group in self.groups.items():
            for old_id in group['members']:
                e=g.events[old_id]
                for f in e['fields']:
                    if f['name'] in {'code_excerpt','observed_excerpt','observed_raw_excerpt'}:continue
                    kind=f['name'] if f['name'] in {'counts','passed','failed_test','declared_selection'} else 'state_value' if group['kind']=='state' else 'metadata'
                    self.add(gid,kind,{'value':f['value'],'origin':f['origin']},name=f['name'])
                    for o in f.get('supporting_origins',[]):self.add(gid,kind,{'value':f['value'],'origin':o},name=f['name'])
            for sid in group['sources']:
                s=g.sources[sid];m=s['message'];body=obj(m.get('content'));r=body.get('result',{});r=r if isinstance(r,dict) else {}
                for pointer in ['/result/text','/result/page/text','/error/message']:
                    try:text=g.field(sid,'body',pointer)['value']
                    except (KeyError,IndexError,TypeError):continue
                    if not isinstance(text,str) or not text:continue
                    is_code=group['kind']=='code' and pointer=='/result/text'
                    parts=code_spans(text) if is_code else diagnostic_spans(text) if group['kind'] in {'test','error'} else [('observed_excerpt',0,min(len(text),512))]
                    for kind,a,z in parts:self.add(gid,kind,g.field(sid,'body',pointer,span=(a,z)))
        for f in self.facts.values():
            # Facts repeated in a recent complete observation need no extra card.
            f['already_direct']=any(self.frame.get(o['message_index'])==self.graph.sources[o['source_id']]['message'] and (o['message_index'] in self.visible_indices or self.graph.sources[o['source_id']]['message'].get('role')=='assistant') for o in f['origins'])
        self.pool=[]
        for gid,group in self.groups.items():
            anchors=[a for a in group['anchors'] if a in self.old_positions]
            facts=[self.facts[f] for f in self.group_facts[gid] if not self.facts[f]['already_direct'] and self.facts[f]['presentation_role']!='occurrence_counter']
            if anchors and facts:
                self.pool.append({**group,'anchor':self.old_positions[max(anchors)],'fact_ids':[f['id'] for f in facts],
                    'version_status':'unknown' if group['version'] is None else 'current_observed_version' if group['version']==g.current_version else 'historical_version'})
        self.pool.sort(key=lambda e:e['id'])

    def snapshot(self):
        return copy.deepcopy({'version':VERSION,'scope':[self.graph.episode,self.graph.member],'groups':self.groups,'facts':self.facts,
            'aliases':self.aliases,'state_transitions':self.state_transitions,'pool':self.pool,
            'raw_source_occurrences_preserved':True,'same_request_cost_counted_each_time':True})


def lexical_scores(documents,query):
    docs={k:terms(v) for k,v in documents.items()};df=Counter(t for d in docs.values() for t in set(d));n=len(docs);avg=sum(map(len,docs.values()))/n if n else 1;q=set(terms(query));scores={}
    for key,doc in docs.items():
        tf=Counter(doc);scores[key]=sum(math.log(1+(n-df[t]+.5)/(df[t]+.5))*tf[t]*2.2/(tf[t]+1.2*(.25+.75*len(doc)/max(avg,1))) for t in q if tf[t])
    return scores


def confirmed_bonus(pool,entities,seeds):
    roots=set().union(*(set(entities.event_bindings.get(old,[])) for e in pool if e['id'] in seeds for old in e['members'])) if seeds else set()
    reached=set(roots);edges=[]
    for edge in entities.edges.values():
        if edge['verification_status']!='Confirmed' or not edge.get('effective_for_current_workspace',True):continue
        if edge['relation_type'] not in {'declares','references','reports_test'}:continue
        if edge['source_entity_id'] in roots or edge['target_entity_id'] in roots:
            reached.update((edge['source_entity_id'],edge['target_entity_id']));edges.append(edge)
    bonus={}
    for e in pool:
        targets=set().union(*(set(entities.event_bindings.get(old,[])) for old in e['members']))
        selected=[x['edge_id'] for x in edges if x['source_entity_id'] in targets or x['target_entity_id'] in targets]
        if targets&reached:bonus[e['id']]={'bonus':1,'edge_ids':selected,'matching_entities':sorted(targets&reached)}
    return bonus


def render_card(group,inventory,store,count,query):
    facts=[inventory.facts[f] for f in group['fact_ids']];scores=lexical_scores({f['id']:canonical(f['value']) for f in facts},query)
    ranked=sorted(facts,key=lambda f:(-PRIORITY.get(f['kind'],10),-scores[f['id']],f['id']))
    anchor_index=inventory.indices[group['anchor']]
    original_reference=store.put(inventory.frame[anchor_index],anchor_index)
    card={'card_type':'state' if group['kind']=='state' else 'evidence','event':group['id'],
        'source_version':group['source_reference'],'version_status':group['version_status'],
        'state_superseded':bool(group.get('superseded_by_state')),'text_is_not_new_validation':True,
        'facts':[],'originals':[original_reference]}
    selected=[];omitted=[]
    for f in ranked:
        possible=[o for o in f['origins'] if inventory.frame.get(o['message_index'])==inventory.graph.sources[o['source_id']]['message']]
        if not possible:omitted.append({'fact':f['id'],'reason':'no_current_private_source_identity'});continue
        origin=max(possible,key=lambda o:o['message_index']);source=inventory.graph.sources[origin['source_id']]
        covered=False
        for previous in selected:
            old=previous['origin']
            if origin.get('span') and old.get('span') and (origin['source_id'],origin['channel'],origin['pointer'])==(old['source_id'],old['channel'],old['pointer']):
                covered |= old['span'][0]<=origin['span'][0] and origin['span'][1]<=old['span'][1]
        if covered:omitted.append({'fact':f['id'],'reason':'already_quoted_source_span'});continue
        actual=inventory.graph.field(origin['source_id'],origin['channel'],origin['pointer'],call_index=origin.get('call_index'),span=origin.get('span'))
        if actual['value']!=f['value']:raise GraphIntegrityError('Fact changed from original source')
        proposal=copy.deepcopy(card)
        if not is_observation(source['message']):continue # actions remain complete, never re-presented as new evidence
        reference=store.put(source['message'],origin['message_index'])
        if reference not in proposal['originals']:proposal['originals'].append(reference)
        shown={'id':f['id'],'kind':f['kind'],'name':f['name'],'value':f['value'],'source':reference}
        proposal['facts'].append(shown);text='[Observed historical evidence; quoted source facts, not a new test or model summary.]\n'+canonical(proposal)
        if count(text)>768:omitted.append({'fact':f['id'],'reason':'card_budget'});continue
        card=proposal;selected.append({'fact_id':f['id'],'origin':origin,'value':f['value'],'source_reference':reference})
    if not selected:return None,{'omitted_facts':omitted}
    text='[Observed historical evidence; quoted source facts, not a new test or model summary.]\n'+canonical(card)
    return text,{'card':card,'selected_facts':selected,'omitted_facts':omitted,'tokens':count(text)}


def project(payload,condition,graph,entities,inventory,store,*,count,measure,indices,budget):
    if condition not in CONDITIONS or budget not in {1024,2048,4096}:raise ValueError('Unfrozen condition')
    if [graph.episode,graph.member]!=[store.slot_id,store.member_id] or inventory.graph is not graph:raise GraphScopeError('Private scope mismatch')
    retrieval,protection,use_graph=CONDITIONS[condition];base,masked,cutoff=baseline(payload,store,count,indices);pool=inventory.pool
    query=query_text(payload,graph);scores=lexical_scores({e['id']:' '.join(e['paths'])+' '+canonical([inventory.facts[f]['value'] for f in e['fact_ids']]) for e in pool},query)
    focus=set(graph.focus()['paths'])
    values={e['id']:scores[e['id']]+2*bool(focus&set(e['paths']))+int(e['version_status']=='current_observed_version') for e in pool}
    raw_pool=[{'event_id':old} for e in pool for old in e['members']]
    raw_must=mandatory_events(graph,raw_pool) if protection else {};must={inventory.aliases[k] for k in raw_must}
    seeds=set(sorted(values,key=lambda k:(-values[k],k))[:8])
    bonuses=confirmed_bonus(pool,entities,seeds) if use_graph else {}
    ranked=sorted((e for e in pool if retrieval or e['id'] in must),key=lambda e:(e['id'] not in must,-values[e['id']]-bonuses.get(e['id'],{}).get('bonus',0),-e['last_index'],e['id']))
    if condition=='E0':ranked=[]
    proof={'version':VERSION,'condition':condition,'bits':CONDITIONS[condition],'budget':budget,'masked':masked,
        'pool_sha256':digest(pool),'fact_pool_sha256':digest(inventory.facts),'selected':[],'omitted':[],
        'mandatory_groups':sorted(must),'graph_bonus':bonuses,'added_tokens_estimate':0,'input_tokens_estimate':measure(base)}
    result=copy.deepcopy(base);occupied=set()
    for group in ranked:
        if group['anchor'] in occupied:proof['omitted'].append({'group':group['id'],'reason':'occupied_anchor'});continue
        text,info=render_card(group,inventory,store,count,query)
        if text is None:proof['omitted'].append({'group':group['id'],'reason':'no_bounded_fact'});continue
        if proof['added_tokens_estimate']+info['tokens']>budget:proof['omitted'].append({'group':group['id'],'reason':'token_budget'});continue
        new=copy.deepcopy(result);new['messages'][group['anchor']]['content']=text
        if measure(new)>98304:proof['omitted'].append({'group':group['id'],'reason':'input_capacity'});continue
        result=new;occupied.add(group['anchor']);proof['added_tokens_estimate']+=info['tokens']
        proof['selected'].append({'group_id':group['id'],'anchor':group['anchor'],'members':group['members'],**info})
    proof['unmet_mandatory']=sorted(must-{s['group_id'] for s in proof['selected']});proof['input_tokens_estimate']=measure(result)
    return result,proof
