"""Evaluate frozen views, with reference truth never supplied to the selector."""
import sys,json,re,copy
from pathlib import Path
from collections import Counter,defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref,frame_for
from proworksim.software_fact_metrics_v199 import covers
from proworksim.software_context_compression_v175 import digest,canonical
BASE=ROOT/'artifacts/software-benchmark-v200'

def union_length(ranges):
    end=None;length=0
    for a,z in sorted(ranges):
        if end is None or a>end:length+=z-a;end=z
        elif z>end:length+=z-end;end=z
    return length

def witnessed(target,fields):
    spans=[]
    for field in fields:
        for origin in field.get('origins',[field['origin']]):
            if covers(field['value'],origin,target):return True
            if not target.get('span') or origin.get('channel')!='body' or not origin.get('span'):continue
            if (origin['source_id'],origin['message_sha256'],origin['pointer'])!=(target['source_id'],target['message_sha256'],target['pointer']):continue
            a,z=origin['span'];x,y=target['span'];lo,hi=max(a,x),min(z,y)
            if lo<hi and field['value'][lo-a:hi-a]==target['value'][lo-x:hi-x]:spans.append((lo,hi))
    return bool(target.get('span')) and union_length(spans)==target['span'][1]-target['span'][0]

def unit_present(unit,fields):
    return any(witnessed({'source_id':o['source_id'],'message_sha256':o['message_sha256'],'pointer':o['pointer'],'span':o.get('span'),'value':unit['value']},fields) for o in unit['origins'] if o['channel']=='body')

def repeated_chars(fields,inv,groups):
    ranges=defaultdict(list)
    for field in fields:
        o=field['origin'];span=o.get('span')
        if not span:continue
        f=inv['facts'][field['fact_id']];sem=f.get('semantic_location') or {};gid=f['event_id']
        if sem.get('chars'):
            original=next(x for x in f['origins'] if x['source_id']==o['source_id'] and x['pointer']==o['pointer'])
            shift=sem['chars'][0]-original.get('span',[0])[0];span=[x+shift for x in span]
            key=canonical([groups[gid]['scope'],gid,{k:v for k,v in sem.items() if k!='chars'}])
        else:key=canonical([gid,o['source_id'],o['channel'],o['pointer'],o.get('call_index')])
        ranges[key].append(span)
    total=sum(z-a for spans in ranges.values() for a,z in spans);unique=sum(union_length(spans) for spans in ranges.values())
    return total-unique,total

def main():
    out=BASE/'metrics-r1/summary.json'
    if out.exists():raise ValueError('Preserve completed metrics')
    data=read(BASE/'development-r1/summary.json');assert not data['failures'] and len(data['rows'])==720
    refs=read(ROOT/'artifacts/software-benchmark-v199/fact-reference-r1/facts.json')['facts'];byref=defaultdict(list)
    for r in refs:byref[r['point']].append(r)
    points={p['point']:p for p in read(ROOT/'artifacts/software-benchmark-v197/private-map-r1/manifest.json')['points']}
    old=read(ROOT/'artifacts/software-benchmark-v199/development-score-r4/summary.json')
    recovery={f['reference']:f['legal_visible_recovery_reference'] for r in old['reference_details'] if r['condition']=='E3' and r['budget']==4096 for f in r['facts']}
    review=read(BASE/'review-r1/assessment.json');review_map={(r['point'],r['fact_id']):r for r in review['rows']}
    rows=[];details=[];pool=[];review_exposure=[];dependency_rows=[]
    for p in data['points']:
        name=p['point'];meta=points[name];inv=read(p['inventory']['path']);cat=read(p['catalogue']['path']);sources=read(p['sources']['path'])
        frame,indices,_,_,_=frame_for(meta);positions={i:j for j,i in enumerate(indices)}
        tool_positions=[i for i,m in enumerate(frame['messages']) if m.get('role')=='tool']
        cutoff=tool_positions[-5] if len(tool_positions)>5 else 0
        targets=byref[name];unit_fields=[{'value':u['value'],'origin':u['origin'],'origins':u['origins']} for u in cat['units'].values()]
        for t in targets:pool.append({'reference':t['id'],'found':witnessed(t,unit_fields),'text_span':t['span'] is not None})
        for row in p['rows']:
            proof=read(row['proof']['path']);view=read(row['payload']['path']);fields=[f for c in proof['selected'] for f in c['selected_facts']]
            if row['condition']=='F0':
                # The unchanged F0 card quotes full facts with their multiple legitimate origins.
                fields=[{**f,'origins':inv['facts'][f['fact_id']]['origins']} for f in fields]
            presented_refs=set(re.findall(r'ctx:[0-9a-f]{24}',canonical(view)));part=[]
            for t in targets:
                card=witnessed(t,fields);index=positions[t['message_index']]
                exact=frame['messages'][index]==sources[t['source_id']]['message'] and view['messages'][index]==frame['messages'][index]
                recent=exact and index>=cutoff;action=exact and frame['messages'][index].get('role')=='assistant';other=exact and not recent and not action
                lexical=[]
                if isinstance(t['value'],str) and len(t['value'])>=6:
                    for m in frame['messages']:
                        if m.get('role')=='assistant' and t['value'] in canonical(m):lexical.append('action_text_literal_only')
                    # A lexical mention has no source/version equivalence proof and earns no coverage.
                legal=recovery[t['id']] in presented_refs
                part.append({'reference':t['id'],'added_history':card,'recent_exact_source':recent,'action_exact_source':action,
                    'other_unchanged_exact_source':other,'direct_union':card or exact,'recoverable':legal or exact,
                    'unproven_action_literal_reoccurrence':bool(lexical)})
            selected_ids={f['fact_id'] for f in fields};sample_rows=[]
            for fid in selected_ids:
                if (name,fid) in review_map:
                    sample_rows.append(review_map[name,fid]);review_exposure.append({'point':name,'condition':row['condition'],'budget':row['budget'],'fact_id':fid,'relevance':review_map[name,fid]['relevance']})
            # Required qualification coverage is assessed only for selected trigger units.
            dep_selected=dep_closed=0;present_cache={}
            def present(uid):
                if uid not in present_cache:present_cache[uid]=unit_present(cat['units'][uid],fields)
                return present_cache[uid]
            for uid,links in cat['dependencies'].items():
                if not present(uid):continue
                for link in links:
                    dep_selected+=1;closed=present(link['target']);dep_closed+=closed
                    dependency_rows.append({'point':name,'condition':row['condition'],'budget':row['budget'],'trigger':uid,'support':link['target'],'edge':link['edge_id'],'closed':closed})
            duplicate,total=repeated_chars(fields,inv,inv['groups'])
            details.append({'point':name,'condition':row['condition'],'budget':row['budget'],'facts':part})
            rows.append({**row,'direct_facts':sum(x['direct_union'] for x in part),'reference_facts':len(part),
                'added_history_reference_facts':sum(x['added_history'] for x in part),'recent_reference_facts':sum(x['recent_exact_source'] for x in part),
                'action_reference_facts':sum(x['action_exact_source'] for x in part),'other_unchanged_reference_facts':sum(x['other_unchanged_exact_source'] for x in part),
                'recoverable_facts':sum(x['recoverable'] for x in part),'dependency_triggers':dep_selected,'dependency_closed':dep_closed,
                'exact_redundant_characters':duplicate,'exact_source_characters':total,'selected_fact_ids':sorted(selected_ids),
                'sample_relevant':sum(x['relevance']=='relevant' for x in sample_rows),'sample_irrelevant':sum(x['relevance']=='irrelevant' for x in sample_rows),
                'sample_unknown':sum(x['relevance']=='unknown' for x in sample_rows),'unreviewed_selected_fact_ids':len(selected_ids)-len(sample_rows)})
    groups=[]
    for b in [1024,2048,4096]:
        for c in ['F0','F1','F2','F3','F4']:
            rs=[r for r in rows if r['budget']==b and r['condition']==c];g={'condition':c,'budget':b,'points':len(rs)}
            for key in ['direct_facts','reference_facts','added_history_reference_facts','recent_reference_facts','action_reference_facts','other_unchanged_reference_facts','recoverable_facts','input_tokens_estimate','added_tokens_estimate','cards','dependency_triggers','dependency_closed','exact_redundant_characters','exact_source_characters','sample_relevant','sample_irrelevant','sample_unknown','unreviewed_selected_fact_ids']:
                g[key]=sum(r[key] for r in rs)
            g.update(unmet_protection_groups=sum(len(r['unmet_mandatory_groups']) for r in rs),unmet_required_units=sum(len(r['unmet_required_units']) for r in rs),
                source_fields_checked=sum(r['checks']['source_fragment_presentations_checked'] for r in rs),
                exact_character_redundancy=g['exact_redundant_characters']/g['exact_source_characters'] if g['exact_source_characters'] else None,
                fact_precision_population=None,fact_precision_reason='24 AI-reviewed facts are a stratified diagnostic sample; all remaining facts unlabelled')
            groups.append(g)
    changed={}
    for a,b in [('F0','F1'),('F1','F2'),('F2','F3'),('F3','F4')]:
        for budget in [1024,2048,4096]:
            left={r['point']:r for r in rows if r['condition']==a and r['budget']==budget};right={r['point']:r for r in rows if r['condition']==b and r['budget']==budget}
            changed[f'{a}:{b}:{budget}']=sum(left[p]['payload']['sha256']!=right[p]['payload']['sha256'] for p in left)
    save(out,{'version':'v200-fact-budget-metrics-r1','groups':groups,'rows':rows,'reference_details':details,'candidate_reference_coverage':pool,
        'dependency_details':dependency_rows,'review_sample_exposure':review_exposure,'input_changes':changed,
        'reference_review':ref(BASE/'review-r1/assessment.json'),'new_API_calls':0,'Agent_actual_reads':0,'Agent_actual_use_measured':False,
        'recovery_validation':'reuse identical v199 r4 bounded-reader source receipts; newly verify visible references in720 views, no fabricated Agent read',
        'dependency_coverage_scope':'typed source qualification only; not complete semantic software Path Recall',
        'redundancy_scope':'overlapping exact source characters in same run/version; not semantic or token redundancy',
        'token_scope':'local official tokenizer hypothetical input estimates; not provider usage or full rollout cost'})
    for g in groups:
        if g['budget']==4096:print(g)
    print('changes',changed)
if __name__=='__main__':main()
