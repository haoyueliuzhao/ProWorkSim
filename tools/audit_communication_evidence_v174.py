"""Bounded read-only audit of final request receipts and communication treatments."""
from collections import Counter, defaultdict
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sqlite3

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_communication_execution_v157 import source_facts

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'artifacts/software-benchmark-v174/final-report-r1'


def read(path):
    return json.loads(Path(path).read_bytes())


def load(ref):
    return json.loads(checked(ref).read_bytes())


def audit():
    summary=read(OUTPUT/'summary.json')
    ledger=ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/ledgers/pilot.sqlite'
    slots={r['slot_id'] for r in summary['rows']}
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN')
        requests={r['request_id']:dict(r) for r in db.execute('SELECT * FROM requests') if r['slot_id'] in slots}
    seen=set();source_counts=Counter();provider_models=Counter();fingerprints=Counter()
    comp=[];logical_requests=defaultdict(set);capture_counts=Counter();physical_refs=[]
    representations={};fallback_rules=defaultdict(Counter);reused=[]
    for row in summary['rows']:
        episode=Path(row['episode_directory']);group=row['group_id']
        journal=OUTPUT/'communications'/str(row['slot_index'])/'events.jsonl'
        for e in [json.loads(x) for x in journal.read_bytes().splitlines()]:
            if e['kind']=='representation_prepared':
                representations[e['L0']['source_id']]=e
                if e.get('fallback_reason')=='source_semantics_not_structured_and_complete':
                    _,complete,why=source_facts(e['raw_text'])
                    assert not complete
                    fallback_rules[group][why]+=1
        if row['delivery']['method']=='offline_same_tree_official_reuse':
            delivery=row['delivery'];receipt=load(delivery['score_receipt']);identity=load(receipt['identity'])
            batch=episode.parents[1]
            administrative=reference(batch/'grading-coordinator/scorer-manifest.json')
            actual=identity['scorer_manifest']
            a,b=checked(actual).read_bytes(),checked(administrative).read_bytes()
            av,bv=json.loads(a),json.loads(b)
            differences={k:{'actual':av.get(k),'coordinator':bv.get(k)}
                for k in av.keys()|bv.keys() if av.get(k)!=bv.get(k)}
            if (actual['path']==administrative['path']
                or set(differences)-{'guard','scoring_policy_scope','new_resource_scope'}
                or any(v['actual']['path']!=v['coordinator']['path']
                    or not v['actual']['path'].endswith('software_benchmark_scope_v161.py')
                    for v in differences.values())):
                raise ValueError('Manifest difference extends beyond administrative reference metadata')
            reused.append({'slot_id':row['slot_id'],'R_delivery':delivery['R_delivery'],
                'actual_scoring_manifest':actual,'coordinator_manifest':administrative,
                'exact_content_equal':a==b,'path_equal':False,'candidate_tree_content_verified':True,
                'administrative_field_differences':differences,
                'all_other_manifest_fields_equal':True,
                'legal_delivery_evidence':delivery['evidence'],'code_receipt':delivery['score_receipt'],
                'new_grading_calls':0,'original_raw_error':delivery['raw_reuse_error']})
        for path in sorted((episode/'physical-http-capture/requests').glob('*/physical-receipt.json')):
            receipt=read(path);rid=receipt['request_id']
            if rid not in requests or rid in seen:
                raise ValueError('Extra, missing or duplicated physical request capture')
            record=requests[rid];capture=receipt['request_capture']
            payload_raw=checked(capture['payload']).read_bytes()
            if hashlib.sha256(payload_raw).hexdigest()!=record['request_sha256']:
                raise ValueError('Captured HTTP payload differs from charged request')
            response=load(receipt['response_metadata_ref'])
            body=load(receipt['response_original_ref'])
            charged=json.loads(record['usage_json'])
            usage_equal=all(response['usage'][key]==charged[provider] for key,provider in (
                ('input_tokens','prompt_tokens'),('output_tokens','completion_tokens'),
                ('total_tokens','total_tokens'),('cached_input_tokens','prompt_cache_hit_tokens'),
                ('cache_miss_input_tokens','prompt_cache_miss_tokens')))
            if (response!=receipt['response_metadata'] or not usage_equal
                or response['request_payload_sha256']!=capture['payload_sha256']
                or response['outcome']!='success' or receipt.get('observer_errors')):
                raise ValueError('Captured response/usage is not complete')
            # Full provenance manifests are preserved but not re-tokenized here.
            if not Path(capture['manifest']['path']).is_file():
                raise ValueError('Source manifest is missing')
            for key,counter in [('provider_model',provider_models),('provider_fingerprint',fingerprints)]:
                counter[json.dumps(response.get(key),sort_keys=True)]+=1
            capture_counts[group]+=1;seen.add(rid);logical_requests[row['slot_id']].add(record['logical_id'])
            physical_refs.append({'request_id':rid,'receipt':reference(path),'purpose':record['usage_id']})
            if record['usage_id']=='compressor':
                payload=json.loads(payload_raw);data=json.loads(payload['messages'][1]['content'])
                selection=json.loads(body['choices'][0]['message']['content'])
                source={f['fact_id']:f for f in data['facts']};mismatches=[];chosen=[]
                for field,ids in selection['fields'].items():
                    for fid in ids:
                        if fid not in source or fid in chosen or source[fid]['field']!=field:
                            mismatches.append({'fact_id':fid,'selected_field':field,
                                'declared_field':source.get(fid,{}).get('field'),'duplicate':fid in chosen})
                        chosen.append(fid)
                rendered=representations.get(data['source_id'])
                comp.append({'slot_id':row['slot_id'],'group_id':group,'request_id':rid,
                    'source_id':data['source_id'],'version_hash':data['version_hash'],
                    'source_fact_count':len(source),'selected_fact_count':len(chosen),
                    'dropped_fact_ids':sorted(set(source)-set(chosen)),
                    'field_or_reference_rejections':mismatches,
                    'raw_request':capture['payload'],'raw_response':receipt['response_original_ref'],
                    'provider_usage':response['usage'],'representation':rendered['representation'],
                    'fallback_reason':rendered.get('fallback_reason'),
                    'L1_characters':len(rendered.get('L1','')),
                    'L1_local_estimated_tokens':rendered.get('L1_tokens_estimated')})
    if seen!=set(requests):raise ValueError('Some canonical physical calls are not captured')
    result={'version':'v174-actual-request-and-rendering-audit-r1',
        'canonical_physical_requests':len(requests),'actual_request_response_capture_pairs':len(seen),
        'capture_counts_by_group':dict(capture_counts),'source_manifest_present_count':len(seen),
        'provider_usage_matches_ledger':True,'provider_model_receipts':dict(provider_models),
        'provider_fingerprint_receipts':dict(fingerprints),'source_token_attribution_reestimated':False,
        'source_token_98_percent_gate_claimed_for_full_final_panel':False,
        'fallback_rule_reasons':{k:dict(v) for k,v in fallback_rules.items()},
        'compressor_calls':comp,'offline_delivery_reuse_count':len(reused),'delivery_reuse':reused,
        'physical_capture_index':physical_refs,'model_calls':0,'Docker_operations':0,
        'old_observation_flags_unchanged':True,'two_person_blind_fidelity_review_claimed':False}
    write_new(OUTPUT/'evidence-audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['physical_capture_index','delivery_reuse']},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT,
        help='Directory containing the corresponding final analysis summary')
    OUTPUT=parser.parse_args().output.resolve()
    os.nice(10)
    os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[-2:])
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    audit()
