"""Measure preserved recent test headers from the stopped SDK archives, offline."""
import copy,gzip,json,os
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_collaboration_observation_v141 import load_official_content_counter
from proworksim.software_collaboration_runtime_observer_v167 import root_sessions
from proworksim.software_public_test_view_v192 import VERSION
from proworksim.storage import digest,json_bytes

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v191/capacity-audit-r1'

def main():
    os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-2:]))
    manifest=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,meta=load_official_content_counter(manifest,manifest_sha256=reference(manifest)['sha256'])
    rows=[]
    for index in (18111,18138,18108,18141):
        root=ROOT/f'runs/software-benchmark-v191/capacity-audit-r1/{index}/retained'
        events=[json.loads(gzip.decompress(p.read_bytes())) for p in sorted(root.rglob('event-*.json.gz'))]
        forgotten={ident for e in events if e['kind']=='Condensation' for ident in e['forgotten_event_ids']}
        visible=[e for e in events if e['id'] not in forgotten and e['kind']=='ObservationEvent']
        measured=[]
        for event in visible[-10:]:
            text=''.join(c.get('text','') for c in event['observation']['content']);body=json.loads(text)
            result=body.get('result',{});full=result.get('test_evidence')
            if not isinstance(full,dict):continue
            compact=copy.deepcopy(body)
            compact['result']['test_evidence']={'version':VERSION,'full_evidence_version':full.get('version'),
                'framework':full.get('framework'),'report_count':full.get('report_count'),
                'nested_report_count':full.get('nested_report_count'),'partial':full.get('partial'),
                'parse_error_present':full.get('error') is not None,'root_sessions':root_sessions(full),
                'total_sessions':len(full.get('sessions',[])),'root_counts_only':True,
                'full_evidence_sha256':digest(json_bytes(full)),
                'full_details':{'tool':'read_test_result','report_id':result['report_id'],
                    'cursor':result['page']['cursor'],'body_sha256':result['body_sha256'],
                    'same_immutable_report':True,
                    'instruction':'Read this exact page and follow next_cursor for the complete framework evidence; no test reruns.'},
                'full_test_records_omitted_from_repeated_header':True,'full_test_records_remain_in_exact_body_pages':True}
            measured.append({'tool_call_id':event['tool_call_id'],'tool':event['tool_name'],
                'source_reference':result.get('source_reference'),'report_id':result['report_id'],
                'original_characters':len(text),'full_evidence_characters':len(json.dumps(full,ensure_ascii=False)),
                'original_observation_tokens_estimate':count(text),
                'bounded_header_observation_tokens_estimate':count(json.dumps(compact,ensure_ascii=False)),
                'navigation_cursor_is_already_seen_page_not_recomputed_evidence_cursor':True,
                'passed_unchanged':compact['result']['passed']==result['passed'],
                'counts_unchanged':compact['result']['counts']==result['counts']})
        rows.append({'slot_index':index,'remaining_original_observation_events':len(visible),
            'summary_events':sum(e['kind']=='Condensation' for e in events),
            'recent10_test_observations':measured,
            'input_pressure_not_normal31_cycle_trigger':index in (18108,18141),
            'local_content_estimates_not_full_API_request_count':True,
            'fresh_provider_or_task_success_not_measured':True})
    value={'rows':rows,'tokenizer':meta,'common_interface_revision':VERSION,
        'basis':'original saved SDK observation events; only the repeated evidence header is projected offline',
        'new_API_calls':0,'old_candidate_or_world_mutations':0}
    (OUT/'header-measurements.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('slot_index','remaining_original_observation_events','summary_events')}|
        {'old_tokens':sum(v['original_observation_tokens_estimate'] for v in r['recent10_test_observations']),
         'bounded_tokens':sum(v['bounded_header_observation_tokens_estimate'] for v in r['recent10_test_observations'])} for r in rows]))

if __name__=='__main__':main()
