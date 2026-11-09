"""Apply the forward archive fix to retained summaries without calling a model."""
import json
from pathlib import Path
import statistics

from proworksim.software_benchmark_candidates_v054 import reference,checked,write_new
from proworksim.software_collaboration_observation_v141 import load_official_content_counter
from proworksim.software_context_compression_v175 import summary_prefix,canonical
from proworksim.software_context_recovery_v176 import HistoryEvidenceStore,apply_recoverable_summary

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'runs/software-benchmark-v175/context-replay-r1'
RUN=ROOT/'runs/software-benchmark-v176/summary-recovery-controls-r2'
OUT=ROOT/'artifacts/software-benchmark-v176/summary-recovery-controls-r2'


def read(path):return json.loads(Path(path).read_bytes())


def main():
    RUN.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    log=Path('/tmp/proworksim-v176-recovery-tests-r2.log').read_text()
    if '4 passed' not in log:raise ValueError('Targeted recovery controls must pass')
    results=read(ROOT/'artifacts/software-benchmark-v175/replay-results-r3/summary.json')
    views=read(ROOT/'artifacts/software-benchmark-v175/offline-comparison-r2/summary.json')
    lookup={(r['point_id'],r['method']):r for r in views['rows']}
    manifest=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,meta=load_official_content_counter(manifest,manifest_sha256=reference(manifest)['sha256'])
    rows=[]
    for case in results['summary_cases']:
        pid=case['point_id'];view=lookup[pid,'M3']
        original=read(checked(lookup[pid,'M0']['payload']))
        masked=read(checked(view['payload']));saved=read(checked(view['evidence_store']))
        store=HistoryEvidenceStore(saved['point_id'],saved['slot_id'],saved['member_id']);store.entries=saved['entries']
        prefix=summary_prefix(masked)
        output,proof=apply_recoverable_summary(masked,prefix,case['summary'],
            original_payload=original,store=store,count=count)
        pages=[];start=0
        while True:
            page=store.read({'reference':proof['original_prefix_reference'],'start':start},
                point_id=store.point_id,slot_id=store.slot_id,member_id=store.member_id)
            pages.append(page['text'])
            if page['next_start'] is None:break
            start=page['next_start']
        decoded=json.loads(''.join(pages))
        if decoded['messages']!=original['messages'][prefix['start']:prefix['end']]:
            raise ValueError('Original complete prefix did not survive an actual paged restore')
        indexed=store.read({'reference':proof['original_prefix_reference'],'characters':1},
            point_id=store.point_id,slot_id=store.slot_id,member_id=store.member_id)['message_offsets']
        for entry,message in zip(indexed,decoded['messages']):
            if ''.join(pages)[entry['start']:entry['end']]!=canonical(message):
                raise ValueError('An indexed history offset differs from its actual original message')
        folder=RUN/case['job_id'];folder.mkdir(exist_ok=True)
        store_ref=write_new(folder/'store.json',{'point_id':store.point_id,'slot_id':store.slot_id,
            'member_id':store.member_id,'entries':store.entries})
        payload_ref=write_new(folder/'payload.json',output)
        actual=read(OLD/'jobs'/case['job_id']/'effective-payload.json')
        rows.append({'job_id':case['job_id'],'original_summary_unchanged':True,'proof':proof,
            'payload':payload_ref,'store':store_ref,'exact_original_prefix_restored':True,
            'full_restore_pages_at_8192_characters':len(pages),
            'indexed_original_messages':len(indexed),'indexed_offset_roundtrip_passed':True,
            'local_input_delta_vs_frozen_v175':count(canonical(output))-count(canonical(actual))})
    value={'version':'v176-addressable-original-prefix-controls-r1','CPU_tests_passed':4,'retained_summaries_checked':len(rows),
        'adopted':sum(r['proof']['adopted'] for r in rows),'exact_prefix_restore_passed':len(rows),
        'visible_protected_reference':sum(r['proof'].get('protected_reference_visible',False) for r in rows),
        'additional_local_tokens':sum(r['local_input_delta_vs_frozen_v175'] for r in rows),
        'full_restore_page_min':min(r['full_restore_pages_at_8192_characters'] for r in rows),
        'full_restore_page_median':statistics.median(r['full_restore_pages_at_8192_characters'] for r in rows),
        'full_restore_page_max':max(r['full_restore_pages_at_8192_characters'] for r in rows),
        'new_API_calls':0,'old_paid_replay_changed':False,'new_model_behavior_or_task_accuracy_measured':False,
        'original_message_offsets_allow_direct_bounded_seek':True,
        'actual_replay_two_read_limit_does_not_imply_full_archive_can_be_read':True,
        'tokenizer':meta,'test_log':reference('/tmp/proworksim-v176-recovery-tests-r2.log'),
        'source_files':[reference(ROOT/'src/proworksim/software_context_recovery_v176.py'),
            reference(ROOT/'tests/test_context_recovery_v176.py'),reference(Path(__file__))],
        'paid_evidence':reference(ROOT/'artifacts/software-benchmark-v175/replay-results-r3/summary.json'),'rows':rows}
    write_new(OUT/'summary.json',value)
    print(json.dumps({k:v for k,v in value.items() if k not in ('rows','tokenizer','source_files')},ensure_ascii=False))


if __name__=='__main__':main()
