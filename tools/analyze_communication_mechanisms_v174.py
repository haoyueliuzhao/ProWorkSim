"""Small evidence cases: the sole structured representation and Flask public tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import tarfile

from proworksim.software_benchmark_candidates_v054 import checked,reference,write_new
from proworksim.software_benchmark_archive_storage_v064 import CODEC_BINARY
from proworksim.software_collaboration_observation_v141 import load_official_content_counter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v174/final-report-r1'


def read(path):return json.loads(Path(path).read_bytes())
def load(ref):return json.loads(checked(ref).read_bytes())


def main():
    data=read(OUT/'summary.json');audit=read(OUT/'evidence-audit.json')
    accepted=[c for c in audit['compressor_calls'] if c['representation']!='raw']
    assert len(accepted)==1
    item=accepted[0];row=next(r for r in data['rows'] if r['slot_id']==item['slot_id'])
    ep=Path(row['episode_directory']);proof=row['communication_extraction']
    transfer=load(proof['source_transfer'])
    filename=hashlib.sha256(item['source_id'].encode()).hexdigest()+'-'+item['version_hash']+'.json'
    target='output/managed-runtime/communication/sources/'+filename
    cached=OUT/'sole-structured-source.json'
    raw=cached.read_bytes() if cached.exists() else None
    if raw is None:
        p=subprocess.Popen([str(CODEC_BINARY),'-d','--long=27','-q','-c',transfer['archive_storage']['blob']['path']],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try:
            with tarfile.open(fileobj=p.stdout,mode='r|*') as archive:
                for member in archive:
                    if member.name.removeprefix('./')==target:
                        assert member.isfile() and member.size<1024**2
                        raw=archive.extractfile(member).read();break
        finally:
            p.stdout.close()
            if p.poll() is None:p.terminate()
            p.wait(timeout=10)
    assert raw and hashlib.sha256(raw).hexdigest()==item['version_hash']
    source=json.loads(raw)
    source_ref=reference(cached) if cached.exists() else write_new(cached,raw)
    events=[json.loads(x) for x in (OUT/'communications'/str(row['slot_index'])/'events.jsonl').read_bytes().splitlines()]
    prepared=next(e for e in events if e['kind']=='representation_prepared' and e['L0']['source_id']==item['source_id'])
    manifest=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,meta=load_official_content_counter(manifest,manifest_sha256=reference(manifest)['sha256'])
    presentations=[]
    for path in (ep/'physical-http-capture/requests').glob('*/physical-receipt.json'):
        receipt=read(path)
        record=receipt['ledger_record']
        if record.get('member_id')!=prepared['recipient'] or record.get('usage_id')!='agent':continue
        mapping=load(receipt['request_capture']['manifest']);facts=set();total_bytes=0
        payload=checked(receipt['request_capture']['payload']).read_bytes()
        for span in mapping['spans']:
            origin=span.get('source') or {}
            if (span.get('semantic_input') and origin.get('transformation')=='compressed'
                and origin.get('source_id','').startswith(item['source_id']+':fact:')
                and origin.get('origin_event_id')==source['metadata']['published_event_id']
                and origin.get('parent_source_ids')==[item['source_id']]):
                assert hashlib.sha256(payload[span['payload_start']:span['payload_end']]).hexdigest()==span['payload_slice_sha256']
                facts.add(origin['source_id'].split(':fact:')[-1]);total_bytes+=span['payload_end']-span['payload_start']
        if facts:presentations.append({'request_id':receipt['request_id'],'fact_ids':sorted(facts),
            'tagged_payload_bytes':total_bytes,'manifest':receipt['request_capture']['manifest']})
    one={'source':source_ref,'source_archive':proof['compressed_source'],'member':target,
        'raw_characters':len(source['raw_text']),'raw_preview_characters':len(source['raw_text'][:500]),
        'structured_characters':len(prepared['L1']), 'raw_tokens_local_estimate':count(source['raw_text']),
        'raw_preview_tokens_local_estimate':count(source['raw_text'][:500]),
        'structured_tokens_local_estimate':count(prepared['L1']),'tokenizer':meta,
        'source_fact_count':len(source['facts']),'source_critical_facts':sum(f['critical'] for f in source['facts']),
        'selected_fact_ids':sorted(fid for values in prepared['selection']['fields'].values() for fid in values),
        'actual_direct_tagged_agent_requests':len(presentations),'actual_presentations':presentations,
        'provider_token_saving_claimed':False,'understanding_or_use_inferred':False}
    flask=[]
    for r in data['rows']:
        if r['instance_id']!='pallets__flask-5014':continue
        rows=[]
        for path in sorted((Path(r['episode_directory'])/'controller-output/public-test-rpc').glob('*/response.json')):
            v=read(path);g=next(iter(v['groups'].values()));output=g.get('output','')
            marker='pytest.PytestAssertRewriteWarning: Module already imported so cannot be rewritten: pws_public_test_evidence_v141'
            rows.append({'response':reference(path),'command_executed':v['execution'].get('command_executed'),
                'returncode':v['execution']['returncode'],'framework_sessions':len(v['test_evidence']['sessions']),
                'actual_observer_import_warning':marker in output,'actual_error_line':marker if marker in output else None})
        assert rows and all(x['actual_observer_import_warning'] and x['framework_sessions']==0 for x in rows)
        flask.append({'slot_id':r['slot_id'],'group_id':r['group_id'],'R_code':r['R_code'],
            'R_delivery':r['delivery']['R_delivery'],'budget_exhausted':r['budget_exhausted'],
            'actual_tokens':r['actual_tokens'],'public_attempts':rows})
    write_new(OUT/'mechanism-cases-r2.json',{'sole_structured_representation':one,
        'flask_public_entry_failure':flask,'new_model_calls':0,'new_test_calls':0,
        'original_results_changed':False})
    print(json.dumps({'sole_representation':{k:v for k,v in one.items() if k not in ['actual_presentations','tokenizer']},
        'flask_attempts':{r['group_id']:len(r['public_attempts']) for r in flask}},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT,
        help='Directory containing the corresponding summary and evidence audit')
    OUT=parser.parse_args().output.resolve()
    os.nice(10);os.environ.update(TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[-2:])
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    main()
