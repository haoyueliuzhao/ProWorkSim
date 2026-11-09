"""Run the frozen four-view offline comparison before any new paid replay."""
import json
from pathlib import Path
from functools import lru_cache

from proworksim.software_benchmark_candidates_v054 import checked,reference,write_new
from proworksim.software_collaboration_observation_v141 import load_official_content_counter
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_context_compression_v175 import EvidenceStore,apply,METHODS,summary_prefix

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v175/context-replay-r1'
OUT=ROOT/'artifacts/software-benchmark-v175/offline-comparison-r2'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plan=json.loads((RUN/'plan.json').read_bytes())
    scores=json.loads((ROOT/'artifacts/software-benchmark-v175/llmlingua-unit-scores-r2/summary.json').read_bytes())
    if scores['plan']!=reference(RUN/'plan.json'):raise ValueError('Encoder scores belong to another fixed panel')
    manifest=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,meta=load_official_content_counter(manifest,manifest_sha256=reference(manifest)['sha256'])
    count=lru_cache(maxsize=4096)(count)
    counter=OfficialDeepSeekCounter(manifest,manifest_sha256=reference(manifest)['sha256'])
    rows=[]
    for point in plan['rows']:
        source=json.loads(checked(point['source_capture']['payload']).read_bytes())
        directory=RUN/'points-r2'/point['point_id'];directory.mkdir(parents=True,exist_ok=True)
        for method in METHODS:
            store=EvidenceStore(point['point_id'],point['slot_id'],point['member_id'])
            value,measurement=apply(source,method,store,count=count,neural_scores=scores['point_scores'][point['point_id']])
            # New independent cache identity; no provider conversation continuation.
            from proworksim.software_context_compression_v175 import digest
            value['user_id']='pws_v175_'+digest({'point':point['point_id'],'method':method})[:32]
            value['max_tokens']=32768
            receipt=counter.measure(value)
            if receipt['prompt_tokens']>98304:raise ValueError('The fixed replay decision exceeds the shared input cap')
            payload=write_new(directory/(method+'-payload.json'),value)
            evidence=write_new(directory/(method+'-evidence.json'),{'point_id':store.point_id,'slot_id':store.slot_id,
                'member_id':store.member_id,'entries':store.entries})
            restored=0
            for changed in measurement['replaced']:
                original=source['messages'][changed['message_index']]['content']
                start=0;pieces=[]
                while True:
                    page=store.read({'reference':changed['reference'],'start':start},point_id=store.point_id,
                        slot_id=store.slot_id,member_id=store.member_id)
                    pieces.append(page['text'])
                    if page['next_start'] is None:break
                    start=page['next_start']
                if ''.join(pieces)!=original:raise ValueError('Exact recall roundtrip failed')
                restored+=1
            prefix=summary_prefix(value) if measurement['hybrid_summary_needed'] else None
            rows.append({'point_id':point['point_id'],'instance_id':point['instance_id'],'partition':point['partition'],
                'method':method,'payload':payload,'evidence_store':evidence,'measurement':measurement,
                'local_prompt_measurement':receipt,'restored_observations':restored,
                'summary_prefix_available':prefix is not None,'source_action_or_score_used':False})
    aggregates={}
    for method in METHODS:
        selected=[r for r in rows if r['method']==method]
        aggregates[method]={'points':len(selected),'changed_points':sum(bool(r['measurement']['replaced']) for r in selected),
            'baseline_local_tokens':sum(r['measurement']['baseline_local_tokens'] for r in selected),
            'transformed_local_tokens':sum(r['measurement']['transformed_local_tokens'] for r in selected),
            'replaced_observations':sum(len(r['measurement']['replaced']) for r in selected),
            'restored_observations':sum(r['restored_observations'] for r in selected),
            'pending_Hybrid_summary_points':sum(r['summary_prefix_available'] for r in selected)}
    result={'plan':reference(RUN/'plan.json'),'rows':rows,'groups':aggregates,'tokenizer':meta,
        'M3_values_are_masking_stage_only_until_paid_summary':True,'local_estimates_are_not_API_usage':True,
        'exact_recall_controls_passed':True,'new_model_calls':0,'new_world_actions':0,
        'research_control_scope':'same historical member-private decision points, not complete single-agent tasks'}
    write_new(OUT/'summary.json',result)
    print(json.dumps(aggregates,ensure_ascii=False))


if __name__=='__main__':main()
