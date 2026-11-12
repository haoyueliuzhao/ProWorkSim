"""Task-clustered source-bound metrics on sealed AI prefix references."""
import sys,json,re,copy
from pathlib import Path
from collections import Counter,defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref
from score_fact_budget_v200 import witnessed
from proworksim.software_context_compression_v175 import canonical,digest
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_graph_check_v196 import recover_field
BASE=ROOT/'artifacts/software-benchmark-v201'

def main():
    output=BASE/'metrics-r1/summary.json'
    if output.exists():raise ValueError('Preserve completed evaluation')
    data=read(BASE/'offline-r1/summary.json');assert not data['errors'] and len(data['rows'])==207
    details=[];rows=[];retrieval_checks=[];availability=[]
    relationships=read(BASE/'annotations-r1/relationships.json')['links']
    for p in data['points']:
        annotation=read(BASE/'annotations-r1'/f"{p['point']}.json");g=read(p['graph']['path']);inv=read(p['inventory']['path']);cat=read(p['catalogue']['path'])
        frame=read(p['frame']['path']);positions=dict(zip(p['indices'],range(len(p['indices']))));tools=[i for i,m in enumerate(frame['messages']) if m.get('role')=='tool'];cut=tools[-5] if len(tools)>5 else 0
        verified={};unit_fields=[{'value':u['value'],'origin':u['origin'],'origins':u['origins']} for u in cat['units'].values()]
        for f in annotation['reference_facts']:
            for o in f['origins']:recover_field({'value':f['value'],'origin':o},g['sources'])
            candidate=any(witnessed({**o,'value':f['value']},unit_fields) for o in f['origins'])
            availability.append({'point':p['point'],'reference':f['id'],'label':f['relevance'],'in_selectable_old_fact_catalogue':candidate})
        for r in p['rows']:
            proof=read(r['proof']['path']);view=read(r['payload']['path']);entries=read(r['reader_entries']['path']);fields=[f for c in proof['selected'] for f in c['selected_facts']]
            if r['condition']=='A':fields=[{**f,'origins':inv['facts'][f['fact_id']]['origins']} for f in fields]
            visible=set(re.findall(r'ctx:[0-9a-f]{24}',canonical(view)));facts=[]
            for f in annotation['reference_facts']:
                from_card=any(witnessed({**o,'value':f['value']},fields) for o in f['origins']);original=False;recent=False;action=False;other=False;references=[]
                for o in f['origins']:
                    source=g['sources'][o['source_id']];pos=positions.get(o['message_index'])
                    same=pos is not None and view['messages'][pos]==source['message']
                    original |= same;recent |= same and pos>=cut;action |= same and source['message'].get('role')=='assistant';other |= same and pos<cut and source['message'].get('role')!='assistant'
                    for key,entry in entries.items():
                        if key not in visible or entry.get('message_index')!=o['message_index'] or entry['text']!=source['message'].get('content'):continue
                        references.append(key)
                        if key not in verified:
                            reader=SourceLabeledHistoryReader(p['point'],p['slot_id'],'member_001');reader.entries={key:entry};pages=[];start=0;calls=0
                            while True:
                                response=reader.read({'reference':key,'start':start,'characters':8192},point_id=p['point'],slot_id=p['slot_id'],member_id='member_001');pages.append(response['text']);calls+=1
                                if response['next_start'] is None:break
                                start=response['next_start']
                            assert ''.join(pages)==source['message']['content'];verified[key]=True
                            retrieval_checks.append({'point':p['point'],'reference':key,'source_id':o['source_id'],'bounded_CPU_reads':calls,'characters':len(entry['text']),'Agent_call':False})
                facts.append({'reference':f['id'],'label':f['relevance'],'added_history':from_card,'recent_original':recent,'retained_action':action,
                    'other_original':other,'direct_union':from_card or original,'recoverable':original or bool(references),'visible_references':references,
                    'source_version':f['source_version'],'version_validity':f['version_validity']})
            byid={f['reference']:f for f in facts};pairs=[l for l in relationships if l['point']==p['point']]
            hits={label:sum(f['direct_union'] for f in facts if f['label']==label) for label in ['necessary','useful','irrelevant']}
            totals=Counter(f['label'] for f in facts)
            row={**r,'necessary_direct':hits['necessary'],'necessary_total':totals['necessary'],'necessary_recoverable':sum(f['recoverable'] for f in facts if f['label']=='necessary'),
                'useful_direct':hits['useful'],'useful_total':totals['useful'],'irrelevant_direct':hits['irrelevant'],'irrelevant_total':totals['irrelevant'],
                'added_irrelevant_occurrences':sum(f['label']=='irrelevant' and f['added_history'] for f in facts),
                'recent_necessary':sum(f['label']=='necessary' and f['recent_original'] for f in facts),'action_necessary':sum(f['label']=='necessary' and f['retained_action'] for f in facts),
                'other_original_necessary':sum(f['label']=='necessary' and f['other_original'] for f in facts),'added_necessary':sum(f['label']=='necessary' and f['added_history'] for f in facts),
                'reference_pairs':len(pairs),'complete_reference_pairs':sum(all(byid[i]['direct_union'] for i in l['members']) for l in pairs),
                'all_reference_facts_recoverable':sum(f['recoverable'] for f in facts),'all_reference_facts':len(facts),
                'sample_labels_are_not_population_precision':True}
            rows.append(row);details.append({'point':p['point'],'condition':r['condition'],'budget':r['budget'],'facts':facts})
    groups=[];paired=[]
    for budget in [1024,2048,4096]:
        task_stats={}
        for c in ['A','B','C']:
            rs=[r for r in rows if r['condition']==c and r['budget']==budget];tasks=defaultdict(list)
            for r in rs:tasks[r['instance_id']].append(r)
            per_task=[]
            for task,items in tasks.items():
                den=sum(x['necessary_total'] for x in items);num=sum(x['necessary_direct'] for x in items)
                per_task.append({'instance_id':task,'points':len(items),'necessary_direct':num,'necessary_total':den,'recall':num/den if den else None,
                    'input_tokens_estimate':sum(x['input_tokens_estimate'] for x in items)})
            task_stats[c]={x['instance_id']:x for x in per_task}
            group={'condition':c,'budget':budget,'tasks':len(tasks),'points':len(rs),'per_task':per_task}
            for k in ['necessary_direct','necessary_total','necessary_recoverable','useful_direct','useful_total','irrelevant_direct','irrelevant_total','added_irrelevant_occurrences','recent_necessary','action_necessary','other_original_necessary','added_necessary','reference_pairs','complete_reference_pairs','all_reference_facts_recoverable','all_reference_facts','input_tokens_estimate','added_tokens_estimate','cards']:
                group[k]=sum(r[k] for r in rs)
            group['task_balanced_necessary_recall']=sum(t['recall'] for t in per_task if t['recall'] is not None)/sum(t['recall'] is not None for t in per_task)
            group['full_fact_precision']=None;group['source_fields_checked']=sum(r['checks']['source_fragment_presentations_checked'] for r in rs)
            groups.append(group)
        for a,b in [('A','B'),('C','B')]:
            deltas=[task_stats[b][t]['recall']-task_stats[a][t]['recall'] for t in task_stats[a]]
            paired.append({'budget':budget,'comparison':b+'-'+a,'tasks':len(deltas),'better':sum(v>0 for v in deltas),'equal':sum(v==0 for v in deltas),'worse':sum(v<0 for v in deltas),'mean_task_delta':sum(deltas)/len(deltas)})
    save(output,{'version':'v201-historical-task-holdout-metrics-r1','groups':groups,'rows':rows,'details':details,'task_paired':paired,
        'candidate_availability':availability,'bounded_reader_verification':retrieval_checks,'CPU_reader_calls':sum(x['bounded_CPU_reads'] for x in retrieval_checks),
        'annotation_scope':'62 primary-AI references in23 points of12 previously calibrated tasks; not human gold or all-history independent confirmation',
        'new_API_calls':0,'actual_Agent_reads':0,'actual_fact_use_measured':False,'real_task_success_measured':False})
    for g in groups:
        if g['budget']==2048:print({k:v for k,v in g.items() if k!='per_task'})
    print('paired',paired)
if __name__=='__main__':main()
