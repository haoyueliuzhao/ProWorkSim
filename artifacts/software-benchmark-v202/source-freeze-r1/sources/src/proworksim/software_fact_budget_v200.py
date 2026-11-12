"""Deterministic fact budgeting over previously visible private evidence.

No reference labels, repository reads, model calls or generated summaries.
Graph closure is evidence qualification, not inferred runtime causality.
"""
from __future__ import annotations
import copy,math
from collections import defaultdict
from .software_context_compression_v175 import canonical,digest
from .software_context_graph_v196 import GraphIntegrityError,GraphScopeError
from .software_context_selection_v196 import baseline
from .software_global_evidence_v198 import query_text,mandatory_events
from .software_fact_context_v199 import PRIORITY,lexical_scores,project as event_project

VERSION='v200-fact-budget-r1'
CONDITIONS=('F0','F1','F2','F3','F4')
PREFIX='[Observed historical evidence; quoted source facts, not a new test or model summary.]\n'

def slices(text,count,limit=360):
    """Lossless consecutive source slices; no word/line deletion."""
    start=0;parts=[]
    while start<len(text):
        lo=start+1;hi=len(text);end=lo
        while lo<=hi:
            mid=(lo+hi)//2
            if count(text[start:mid])<=limit:end=mid;lo=mid+1
            else:hi=mid-1
        if end<len(text):
            line=text.rfind('\n',start+(end-start)//2,end)
            if line>=0:end=line+1
        if end<=start:raise ValueError('Cannot create a bounded source fragment')
        parts.append((start,end));start=end
    return parts or [(0,0)]

class FactCatalogue:
    def __init__(self,inventory,entities,count):
        self.inventory=inventory;self.entities=entities;self.groups={e['id']:e for e in inventory.pool}
        self.units={};self.by_fact=defaultdict(list);self.by_group=defaultdict(list);self.dependencies=defaultdict(list)
        self.excluded=[];self.query=query_text({'messages':list(inventory.frame.values())},inventory.graph)
        for group in inventory.pool:
            for fid in group['fact_ids']:
                fact=inventory.facts[fid]
                origins=[o for o in fact['origins'] if inventory.frame.get(o['message_index'])==inventory.graph.sources[o['source_id']]['message']]
                if not origins:self.excluded.append({'fact_id':fid,'reason':'no_actual_private_source_in_request'});continue
                origin=max(origins,key=lambda o:o['message_index']);value=fact['value']
                source=inventory.graph.field(origin['source_id'],origin['channel'],origin['pointer'],call_index=origin.get('call_index'),span=origin.get('span'))
                if source['value']!=value:raise GraphIntegrityError('Changed source fact')
                parts=slices(value,count) if isinstance(value,str) else [(None,None)]
                for n,(a,z) in enumerate(parts):
                    part=value[a:z] if a is not None else copy.deepcopy(value);adjusted=[]
                    for o in origins:
                        new=copy.deepcopy(o)
                        if a is not None:
                            offset=o.get('span',[0])[0];new['span']=[offset+a,offset+z]
                        adjusted.append(new)
                    chosen=next(o for o in adjusted if o['source_id']==origin['source_id'] and o['pointer']==origin['pointer'])
                    uid='factpart:'+digest([fid,n,a,z])[:24]
                    self.units[uid]={'id':uid,'fact_id':fid,'group_id':group['id'],'kind':fact['kind'],'name':fact['name'],
                        'value':part,'origin':copy.deepcopy(chosen),'origins':adjusted,'part_index':n,'part_count':len(parts),
                        'version':fact['version'],'partial_fact':len(parts)>1,'status':'literal_observed_fragment'}
                    self.by_fact[fid].append(uid);self.by_group[group['id']].append(uid)
        # Source-backed test identity requires the status of that same execution.
        # This is not an assertion that every test in the repository depends on it.
        for edge in entities.edges.values():
            if edge['verification_status']!='Confirmed' or not edge.get('effective_for_current_workspace',True):continue
            left=entities.entities[edge['source_entity_id']];right=entities.entities[edge['target_entity_id']]
            if edge['relation_type']=='reports_test' and left['kind']=='TestRun' and right['kind']=='TestDefinition':
                run_sources=set(left['attrs'].get('source_ids',[]));node=right['identity'].get('node_id')
                triggers=[u for u in self.units.values() if u['kind']=='failed_test' and u['value']==node and any(o['source_id'] in run_sources for o in u['origins'])]
                for u in triggers:
                    supports=[v['id'] for v in self.units.values() if v['group_id']==u['group_id'] and v['kind'] in {'counts','passed'}]
                    for target in supports:self.dependencies[u['id']].append({'target':target,'edge_id':edge['edge_id'],'semantics':'reported_test_identity_qualified_by_same_run_status'})
            if edge['relation_type']=='declares' and left['kind']=='File' and right['kind']=='Symbol':
                path=left['identity']['path'];reference=left['identity']['revision']['workspace_reference']
                complete=entities.full_files.get((path,digest(reference)))
                if not complete:continue
                lines=complete['text'].splitlines(keepends=True);line=right['attrs'].get('lines')
                if not line:continue
                begin=sum(map(len,lines[:line[0]-1]));end=sum(map(len,lines[:line[1]]))
                for u in self.units.values():
                    f=inventory.facts[u['fact_id']];location=f.get('semantic_location') or {}
                    if u['kind']!='code_function' or location.get('path')!=path or u['version']!=reference:continue
                    interval=location.get('chars',[])
                    if interval!=[begin,end]:continue # no fuzzy partial-function qualification
                    supports=[v['id'] for v in self.units.values() if v['group_id']==u['group_id'] and v['name']=='path' and v['value']==path]
                    for target in supports:self.dependencies[u['id']].append({'target':target,'edge_id':edge['edge_id'],'semantics':'complete_symbol_excerpt_qualified_by_observed_file_identity'})

    def snapshot(self):
        return {'version':VERSION,'units':self.units,'by_fact':dict(self.by_fact),'by_group':dict(self.by_group),
            'dependencies':dict(self.dependencies),'excluded':self.excluded,'scope':[self.inventory.graph.episode,self.inventory.graph.member],
            'reference_labels_loaded':False,'source_facts_sha256':digest(self.inventory.facts)}

def location(unit,catalogue):
    """An exact address, not a text similarity key; retains run/version/scope."""
    o=unit['origin'];span=o.get('span')
    if span is None:return None
    f=catalogue.inventory.facts[unit['fact_id']];semantic=f.get('semantic_location') or {}
    if 'chars' in semantic:
        original=next(x for x in f['origins'] if x['source_id']==o['source_id'] and x['pointer']==o['pointer'])
        shift=semantic['chars'][0]-original.get('span',[0])[0]
        address={k:v for k,v in semantic.items() if k!='chars'}
        return canonical([catalogue.groups[unit['group_id']]['scope'],unit['group_id'],address]),(span[0]+shift,span[1]+shift)
    return canonical([unit['group_id'],o['source_id'],o['channel'],o['pointer'],o.get('call_index')]),tuple(span)

def subtract(span,covered):
    pieces=[span]
    for a,z in sorted(covered):
        pieces=[part for x,y in pieces for part in [(x,min(y,a)),(max(x,z),y)] if part[0]<part[1]]
    return pieces

def fragments_for(unit,catalogue,selected,merge=False):
    current=location(unit,catalogue)
    if current is None:return [unit]
    key,(a,z)=current;covered=[]
    for v in selected:
        old=location(v,catalogue)
        if old and old[0]==key:
            x,y=old[1];lo,hi=max(a,x),min(z,y)
            if lo<hi and unit['value'][lo-a:hi-a]!=v['value'][lo-x:hi-x]:
                raise GraphIntegrityError('Conflicting literal bytes at one claimed source/version interval')
            covered.append(old[1])
    if any(x<=a and z<=y for x,y in covered):return []
    if not merge:return [unit]
    out=[]
    for start,end in subtract((a,z),covered):
        v=copy.deepcopy(unit);x,y=start-a,end-a
        v['value']=unit['value'][x:y];v['partial_fact']=True
        for o in [v['origin'],*v['origins']]:
            offset=o['span'][0];o['span']=[offset+x,offset+y]
        v['presentation_id']=unit['id']+':'+str(x)+'-'+str(y);out.append(v)
    return out

class Presentation:
    def __init__(self,base,catalogue,store,count,budget):
        self.base=base;self.catalogue=catalogue;self.store=store;self.count=count;self.budget=budget
        self.cards=[];self.units=[];self.tokens=0

    def propose(self,units):
        cards=copy.deepcopy(self.cards)
        for unit in units:
            group=self.catalogue.groups[unit['group_id']];inv=self.catalogue.inventory;o=unit['origin']
            value=inv.graph.field(o['source_id'],o['channel'],o['pointer'],call_index=o.get('call_index'),span=o.get('span'))['value']
            if value!=unit['value']:raise GraphIntegrityError('Rendered fragment lost source identity')
            source=inv.graph.sources[o['source_id']];reference=self.store.put(source['message'],o['message_index'])
            anchor_index=inv.indices[group['anchor']];anchor_ref=self.store.put(inv.frame[anchor_index],anchor_index)
            shown={'id':unit.get('presentation_id',unit['id']),'kind':unit['kind'],'name':unit['name'],'value':unit['value'],'source':reference}
            if unit['partial_fact']:shown['fragment_of']=unit['fact_id']
            header={'card_type':'state' if group['kind']=='state' else 'evidence','event':group['id'],
                'source_version':group['source_reference'],'version_status':group['version_status'],
                'state_superseded':bool(group.get('superseded_by_state')),'text_is_not_new_validation':True,
                'facts':[],'originals':[anchor_ref]}
            position=next((i for i in range(len(cards)-1,-1,-1) if cards[i]['group_id']==group['id']),None)
            previous=cards[position] if position is not None else None
            def append(card):
                p=copy.deepcopy(card);p['facts'].append(shown)
                if reference not in p['originals']:p['originals'].append(reference)
                return p,PREFIX+canonical(p)
            card,text=append(previous['card'] if previous else header)
            if self.count(text)>768 and previous:previous=None;card,text=append(header)
            if self.count(text)>768:return None,'single_fragment_capacity'
            proof={'fact_id':unit['fact_id'],'unit_id':unit['id'],'presentation_id':unit.get('presentation_id',unit['id']),
                'origin':copy.deepcopy(o),'origins':copy.deepcopy(unit['origins']),'value':copy.deepcopy(unit['value']),
                'source_reference':reference,'kind':unit['kind'],'partial_fact':unit['partial_fact']}
            if previous:
                cards[position]={**previous,'card':card,'content':text,'tokens':self.count(text),'selected_facts':previous['selected_facts']+[proof]}
            else:cards.append({'group_id':group['id'],'anchor':group['anchor'],'members':group['members'],'card':card,'content':text,
                'tokens':self.count(text),'selected_facts':[proof]})
        anchors=defaultdict(list)
        for c in cards:anchors[c['anchor']].append(c['content'])
        total=sum(self.count('\n\n'.join(texts)) for texts in anchors.values())
        if total>self.budget:return None,'total_budget'
        view=copy.deepcopy(self.base)
        for anchor,texts in anchors.items():view['messages'][anchor]['content']='\n\n'.join(texts)
        return (cards,total,view),None

def project(payload,condition,graph,entities,inventory,catalogue,store,*,count,measure,indices,budget):
    if condition not in CONDITIONS or budget not in {1024,2048,4096}:raise ValueError('Unfrozen condition')
    if [graph.episode,graph.member]!=[store.slot_id,store.member_id] or catalogue.inventory is not inventory:raise GraphScopeError('Foreign evidence catalogue')
    base,masked,cutoff=baseline(payload,store,count,indices)
    if condition=='F0':
        view,proof=event_project(payload,'E3',graph,entities,inventory,store,count=count,measure=measure,indices=indices,budget=budget)
        proof.update(condition='F0',baseline_version=proof['version'],version=VERSION,catalogue_sha256=digest(catalogue.snapshot()),
            original_event_proof=True,base_input_tokens_estimate=measure(base))
        return view,proof
    query=query_text(payload,graph);units=catalogue.units;pool=inventory.pool
    group_scores=lexical_scores({e['id']:' '.join(e['paths'])+' '+canonical([inventory.facts[f]['value'] for f in e['fact_ids']]) for e in pool},query)
    focus=set(graph.focus()['paths'])
    group_scores={e['id']:group_scores[e['id']]+2*bool(focus&set(e['paths']))+int(e['version_status']=='current_observed_version') for e in pool}
    raw_must=mandatory_events(graph,[{'event_id':old} for e in pool for old in e['members']]);must={inventory.aliases[k] for k in raw_must}
    required={u['id'] for u in units.values() if u['group_id'] in must and u['kind'] in {'counts','passed','declared_selection'}}
    scores=lexical_scores({uid:' '.join(catalogue.groups[u['group_id']]['paths'])+' '+u['name']+' '+canonical(u['value']) for uid,u in units.items()},query)
    presentation=Presentation(base,catalogue,store,count,budget);cost=getattr(catalogue,'unit_cost_cache',{})
    if condition!='F1' and not cost:
        for uid,u in units.items():
            proposal,_=presentation.propose([u]);cost[uid]=proposal[1] if proposal else 769
        catalogue.unit_cost_cache=cost
    def fact_priority(uid):
        u=units[uid];g=catalogue.groups[u['group_id']]
        tier=0 if uid in required else 1 if scores[uid]>0 and g['kind'] in {'test','error'} else 2 if scores[uid]>0 and g['kind']!='state' else 4 if g.get('superseded_by_state') else 3
        return (tier,-scores[uid]/math.sqrt(max(1,cost[uid])),-PRIORITY.get(u['kind'],10),-g['last_index'],uid)
    if condition=='F1':
        order=[]
        for g in sorted(pool,key=lambda e:(e['id'] not in must,-group_scores[e['id']],-e['last_index'],e['id'])):
            local=lexical_scores({fid:canonical(inventory.facts[fid]['value']) for fid in g['fact_ids']},query)
            for fid in sorted(g['fact_ids'],key=lambda f:(-PRIORITY.get(inventory.facts[f]['kind'],10),-local[f],f)):
                order+=catalogue.by_fact.get(fid,[])
    else:order=sorted(units,key=fact_priority)
    chosen=set();omitted=[];closures=[];view=base
    def dependencies(uid):
        found=[];proofs=[];pending=[uid];seen=set()
        while pending:
            item=pending.pop(0)
            if item in seen:continue
            seen.add(item)
            if item not in chosen:found.append(item)
            if condition in {'F3','F4'}:
                for d in catalogue.dependencies.get(item,[]):proofs.append({'from':item,**d});pending.append(d['target'])
        if condition=='F4':
            group=catalogue.groups[units[uid]['group_id']]
            if group['kind']=='test':
                candidates=catalogue.by_group[group['id']]
                status=[v for v in candidates if units[v]['kind'] in {'counts','passed','declared_selection'}]
                diagnostic=[v for v in candidates if units[v]['kind'] in {'exception','diagnostic_output','assertion_context','explicit_assert_false','failed_test'}]
                if diagnostic:status.append(min(diagnostic,key=fact_priority))
                for other in status:
                    if other not in chosen and other not in found:found.append(other)
                    proofs.append({'from':uid,'target':other,'same_execution_bundle':group['id'],'semantics':'same_report_joint_presentation_not_causal_dependency'})
        return found,proofs
    for uid in order:
        if uid in chosen:continue
        if condition!='F1' and uid not in required and scores[uid]<=0:
            omitted.append({'unit':uid,'reason':'no_query_term_overlap'});continue
        package,evidence=dependencies(uid);fragments=[]
        for item in package:fragments+=fragments_for(units[item],catalogue,presentation.units+fragments,merge=condition=='F4')
        if not fragments:
            chosen.update(package);omitted.append({'unit':uid,'reason':'already_present_source_span'});continue
        proposal,reason=presentation.propose(fragments)
        if proposal is not None and measure(proposal[2])>98304:proposal=None;reason='input_capacity'
        if proposal is None:omitted.append({'unit':uid,'required_package':package,'reason':reason});continue
        presentation.cards,presentation.tokens,view=proposal;presentation.units+=fragments;chosen.update(package)
        if evidence:closures.append({'root_unit':uid,'requirements':evidence})
    proof={'version':VERSION,'condition':condition,'budget':budget,'masked':masked,'selected':presentation.cards,'omitted':omitted,
        'pool_sha256':digest(inventory.pool),'fact_pool_sha256':digest(inventory.facts),'catalogue_sha256':digest(catalogue.snapshot()),
        'mandatory_groups':sorted(must),'required_status_units':sorted(required),'unmet_required_units':sorted(required-chosen),
        'unmet_mandatory':sorted(must-{c['group_id'] for c in presentation.cards}),
        'added_tokens_estimate':presentation.tokens,'input_tokens_estimate':measure(view),'base_input_tokens_estimate':measure(base),
        'dependency_closures':closures,'graph_semantics':'evidence qualification only','agent_actual_read_calls':0,
        'selection_order':order,'selected_unit_ids':sorted(chosen),'original_event_proof':False}
    return view,proof
