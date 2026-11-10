"""Compare48 fixed historical inputs without invoking any model or World."""
import copy,gzip,json,os
from collections import Counter
from functools import lru_cache
from pathlib import Path
from proworksim.software_context_critical_v191 import project,inventory,RULES,METHODS
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_runtime_v181 import CONTEXT_TOOL
from proworksim.software_benchmark_candidates_v054 import checked,reference
from proworksim.software_collaboration_observation_v141 import load_official_content_counter
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v191/offline-views-r1'
RUN=ROOT/'runs/software-benchmark-v191/offline-views-r1'
PLAN=ROOT/'runs/software-benchmark-v175/context-replay-r1/plan.json'

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    if path.suffix=='.gz':raw=gzip.compress(raw,mtime=0)
    path.write_bytes(raw);return reference(path)
def pointer(body,path):
    value=body
    for key in path.strip('/').split('/'):value=value[key]
    return value

def main():
    os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-2:]))
    plan=json.loads(PLAN.read_bytes());assert len(plan['rows'])==48
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'summary.json').exists():raise ValueError('Preserve completed offline comparison')
    token=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,meta=load_official_content_counter(token,manifest_sha256=reference(token)['sha256'])
    count=lru_cache(maxsize=4096)(count)
    counter=OfficialDeepSeekCounter(token,manifest_sha256=reference(token)['sha256'])
    rule_ref=write(OUT/'rules.json',RULES);rows=[]
    for point in plan['rows']:
        source=json.loads(checked(point['source_capture']['payload']).read_bytes())
        source=copy.deepcopy(source)
        if not any(t['function']['name']=='context_read' for t in source.get('tools',[])):
            source.setdefault('tools',[]).append(copy.deepcopy(CONTEXT_TOOL))
        events,current=inventory(source);latest=[e for e in events if e['superseded_by_message_index'] is None]
        tools=[i for i,m in enumerate(source['messages']) if m.get('role')=='tool']
        cutoff=tools[-5] if len(tools)>5 else 0
        target=[e for e in latest if e['message_index']<cutoff]
        raw_measure=counter.measure(source)
        for method in METHODS:
            store=SourceLabeledHistoryReader(point['point_id'],point['slot_id'],point['member_id'])
            value,proof=project(source,method,store,count=count)
            measured=counter.measure(value);card_by_index={c['index']:c for c in proof['critical_cards']}
            restored=0
            for item in proof['masked']:
                original=source['messages'][item['index']]['content'];start=0;pieces=[]
                while True:
                    page=store.read({'reference':item['reference'],'start':start},point_id=store.point_id,slot_id=store.slot_id,member_id=store.member_id)
                    pieces.append(page['text'])
                    if page['next_start'] is None:break
                    start=page['next_start']
                assert ''.join(pieces)==original
                restored+=1
            correct_fields=0
            for card in proof['critical_cards']:
                original=json.loads(source['messages'][card['index']]['content'])
                for field in card['fields']:
                    source_value=pointer(original,field['pointer'])
                    assert (source_value[field['start']:field['end']]==field['value'] if field.get('excerpt') else source_value==field['value'])
                    correct_fields+=1
            retained=0;expected=0;retained_events=0
            for event in target:
                i=event['message_index'];expected+=len(event['fields'])
                if value['messages'][i]==source['messages'][i]:retained+=len(event['fields']);retained_events+=1
                elif i in card_by_index:
                    assert card_by_index[i]['fields']==event['fields'];retained+=len(event['fields']);retained_events+=1
            baseline_action=[(m.get('role'),m.get('tool_call_id'),m.get('tool_calls')) for m in source['messages']]
            assert baseline_action==[(m.get('role'),m.get('tool_call_id'),m.get('tool_calls')) for m in value['messages']]
            folder=RUN/point['point_id']/method
            payload_ref=write(folder/'payload.json.gz',value)
            store_ref=write(folder/'original-evidence.json.gz',{'point_id':store.point_id,'slot_id':store.slot_id,'member_id':store.member_id,'entries':store.entries})
            rows.append({'point_id':point['point_id'],'instance_id':point['instance_id'],'partition':point['partition'],
                'method':method,'source_payload':point['source_capture']['payload'],'payload':payload_ref,'evidence_store':store_ref,
                'original_with_common_reader_prompt_tokens_estimate':raw_measure['prompt_tokens'],
                'prompt_tokens_estimate':measured['prompt_tokens'],'input_cap_fits':measured['prompt_tokens']<=98304,
                'projection':proof,'old_latest_critical_events':len(target),'retained_old_critical_events':retained_events,
                'old_critical_field_count':expected,'retained_old_critical_field_count':retained,
                'emitted_fields_source_verified':correct_fields,'exact_recovered_original_observations':restored,
                'critical_retention_is_rule_defined_not_full_semantic_ground_truth':True,
                'actual_provider_usage_available':False,'new_model_calls':0})
        print(point['point_id'],'done',flush=True)
    groups={}
    for method in METHODS:
        selected=[r for r in rows if r['method']==method]
        groups[method]={'points':len(selected),'input_tokens_estimate_sum':sum(r['prompt_tokens_estimate'] for r in selected),
            'over_input_cap':sum(not r['input_cap_fits'] for r in selected),
            'old_critical_fields':sum(r['old_critical_field_count'] for r in selected),
            'retained_old_critical_fields':sum(r['retained_old_critical_field_count'] for r in selected),
            'retained_old_critical_events':sum(r['retained_old_critical_events'] for r in selected),
            'critical_cards':sum(len(r['projection']['critical_cards']) for r in selected),
            'critical_card_token_estimate_sum':sum(r['projection']['critical_card_tokens_estimate'] for r in selected),
            'exact_restored_observations':sum(r['exact_recovered_original_observations'] for r in selected),
            'budget_fallback_cards':sum(len(r['projection']['critical_fallbacks']) for r in selected)}
    result={'version':'v191-critical-event-offline-prototype-r1','plan':reference(PLAN),'rules':rule_ref,
        'source_final_outcomes_consulted_by_projection':False,'groups':groups,'rows':rows,'tokenizer':meta,
        'provider_usage_not_measured':True,'new_API_calls':0,'new_world_actions':0,'new_GPU_use':0,
        'all_emitted_fields_bind_observed_source':True,'all_raw_recovery_roundtrips_passed':True,
        'formal_task_success_not_measured':True,'P1_admission_not_implied':True}
    write(OUT/'summary.json',result);print(json.dumps(groups,ensure_ascii=False))

if __name__=='__main__':main()
