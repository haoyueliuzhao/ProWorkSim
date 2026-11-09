"""Offline final analysis of the fixed24 REVIEW2 communication pilot.

Reads the canonical recovery mapping, exact provider usage, stored final trees,
official receipts and immutable communication journals. No API/Docker/training.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import sqlite3
import statistics
import subprocess
import tarfile

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_archive_storage_v064 import CODEC_BINARY, stream_reference

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'artifacts/software-benchmark-v174/final-report-r1'
STATUS = ROOT/'artifacts/software-benchmark-v172/completion-status-r1/summary.json'
BATCHES = [(170,'completion-recovery13-r1'),(169,'communication-wave2-r2'),
    (161,'independent-technical-recovery-r1'),(159,'communication-pilot-recovery-r1'),
    (157,'communication-pilot24-r1')]


def read(path):
    return json.loads(Path(path).read_bytes())


def load(ref):
    return json.loads(checked(ref).read_bytes())


def catalog():
    entries = {}
    for version, folder in BATCHES:
        batch = ROOT/f'runs/software-benchmark-v{version}'/folder
        plan = read(batch/('execution-plan-r2.json' if version == 157 else 'execution-plan.json'))
        for row in plan['rows']:
            episode = batch/'episodes'/str(row['slot_index'])
            if row['slot_id'] not in entries and (episode/'controller-output/managed-boundary.json').exists():
                entries[row['slot_id']] = (version, batch, episode, row)
    return entries


def extract_events(entry):
    version, batch, episode, row = entry
    out = OUTPUT/'communications'/str(row['slot_index'])
    proof_path = out/'extraction.json'
    if proof_path.exists():
        proof = read(proof_path)
        return proof, [json.loads(line) for line in checked(proof['events']).read_bytes().splitlines()]
    transfer_ref = reference(episode/'controller-output-transfer.json')
    storage = load(transfer_ref)['archive_storage']
    if storage['round_trip_verified'] is not True or stream_reference(storage['blob']['path']) != storage['blob']:
        raise ValueError('Original verified communication archive identity changed')
    target = 'output/managed-runtime/communication/events.jsonl'
    process = subprocess.Popen([str(CODEC_BINARY), '-d', '--long=27', '-q', '-c', storage['blob']['path']],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    raw = None
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|*') as archive:
            for member in archive:
                if member.name.removeprefix('./') == target:
                    if not member.isfile() or member.size > 16*1024**2:
                        raise ValueError('Communication journal is not a bounded regular file')
                    raw = archive.extractfile(member).read()
                    break
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)
    if raw is None:
        raise ValueError('Original complete archive has no communication journal')
    events = [json.loads(line) for line in raw.splitlines()]
    if [e['ordinal'] for e in events] != list(range(1,len(events)+1)):
        raise ValueError('Communication journal sequence is incomplete')
    out.mkdir(parents=True, exist_ok=True)
    (out/'events.jsonl').write_bytes(raw)
    proof = {'episode': row['slot_id'], 'source_transfer': transfer_ref,
        'compressed_source': storage['blob'], 'original_full_roundtrip_verified': True,
        'current_compressed_digest_verified': True, 'member': target,
        'events': reference(out/'events.jsonl'), 'raw_tar_materialized': False,
        'full_archive_reverification_claimed': False, 'model_calls': 0, 'Docker_operations': 0}
    write_new(proof_path, proof)
    return proof, events


def delivery(row, entry):
    version, batch, episode, planned = entry
    if planned['slot_index'] in (15703,17002):
        rv = 163 if planned['slot_index']==15703 else 173
        folder = f'original-{planned["slot_index"]}-rescore-r1'
        path = ROOT/f'runs/software-benchmark-v{rv}'/folder/'coordinator/result.json'
        result = read(path)
        return {'R_delivery': result['R_delivery'], 'submitted': True, 'same_tree': True,
            'method': 'prior_audited_same_tree_recovery', 'evidence': reference(path), 'raw_reuse_error': None}
    result_ref = reference(episode/'result.json')
    result = load(result_ref)
    closure = result['project_closure']
    validator = importlib.import_module('proworksim.software_benchmark_project_closure_v'+str(
        170 if version == 170 else 161 if version == 161 else 157))
    evidence = load(result['delivery_evidence'])
    snapshot = load(result['delivery_snapshot'])
    baseline = load(result['project_baseline_snapshot'])
    verdict = validator.validate_delivery_evidence(evidence, snapshot, baseline)
    if verdict != closure['delivery_validation']:
        raise ValueError('Original legal-delivery proof changed')
    terminal = read(batch/'api-coordinator/run-summary.json')['delivery_endpoints'].get(row['slot_id'], {})
    raw_error = terminal.get('error')
    common = {'submitted': verdict['submitted'], 'same_tree': verdict['same_tree'],
        'legal_delivery_proof': verdict, 'raw_reuse_error': raw_error,
        'evidence': result['delivery_evidence'], 'original_raw_status': terminal.get('status')}
    if not verdict['submitted']:
        return {**common, 'R_delivery': False, 'method': 'no_legal_delivery'}
    grade = batch/'grading'/('delivery-score-'+str(planned['slot_index']))/'receipt.json'
    if grade.exists():
        receipt = read(grade)
        request = read(grade.with_name('request.json'))
        quiet = read(grade.with_name('quiescence.json'))
        if (receipt['slot_id'] != row['slot_id'] or request['candidate_lock'] != result['delivery_candidate_lock']
            or receipt['status'] != 'official_report' or type(receipt['resolved']) is not bool
            or not quiet['quiescent'] or quiet['cleanup_errors']):
            raise ValueError('Separate delivery score is not an exact known official result')
        return {**common, 'R_delivery': receipt['resolved'], 'method': 'separate_official_delivery_score',
            'score_receipt': reference(grade)}
    if verdict['same_tree'] is not True:
        raise ValueError('A different last delivery has no official score')
    code_lock, delivery_lock = load(result['candidate_lock']), load(result['delivery_candidate_lock'])
    code_candidate, delivery_candidate = load(code_lock['candidate']), load(delivery_lock['candidate'])
    if (code_lock['tree_sha256'] != delivery_lock['tree_sha256']
        or code_lock['patch_receipt']['base_tree_sha256'] != delivery_lock['patch_receipt']['base_tree_sha256']
        or code_candidate['files'] != delivery_candidate['files']
        or code_candidate['entry_metadata'] != delivery_candidate['entry_metadata']):
        raise ValueError('Never infer delivery from a different final tree')
    score = batch/'grading'/('score-'+str(planned['slot_index']))
    receipt = read(score/'receipt.json'); request_ref = reference(score/'request.json')
    request = load(request_ref); identity = load(receipt['identity'])
    quiet = read(score/'quiescence.json'); completion = read(score/'completion.json')
    if (receipt['status'] != 'official_report' or receipt['resolved'] != row['R_code']
        or request['generation_result'] != result_ref or request['slot_id'] != row['slot_id']
        or request['candidate_lock'] != result['candidate_lock'] or identity['request'] != request_ref
        or identity['configuration'] != planned['configuration'] or identity['candidate_lock'] != result['candidate_lock']
        or identity['plan'] != request['plan'] or identity['scorer_manifest'] != request['scorer_manifest']
        or identity['endpoint'] != 'code' or completion['returncode'] != 0
        or not quiet['quiescent'] or quiet['cleanup_errors'] or quiet['create_result_unknown']):
        raise ValueError('Same-tree reuse lacks exact original scoring and cleanup evidence')
    return {**common, 'R_delivery': receipt['resolved'], 'method': 'offline_same_tree_official_reuse',
        'score_receipt': reference(score/'receipt.json'), 'exact_files_and_entry_metadata_equal': True,
        'code_candidate_lock': result['candidate_lock'], 'delivery_candidate_lock': result['delivery_candidate_lock'],
        'candidate_content_changed': False, 'new_model_calls': 0, 'new_grading_calls': 0}


def journal_metrics(events):
    published = {e['sequence']: e for e in events if e['kind']=='published'}
    prepared = [e for e in events if e['kind']=='representation_prepared']
    pulls = [e for e in events if e['kind']=='retrieved']
    return {'published': len(published), 'prepared': len(prepared),
        'facts_complete': sum(e['facts_complete'] for e in published.values()),
        'representations': dict(Counter(e['representation'] for e in prepared)),
        'fallbacks': dict(Counter(e['fallback_reason'] for e in prepared if e.get('fallback_reason'))),
        'compressor_attempts': sum(len(e['compressor_attempts']) for e in prepared),
        'successful_summary_preparations': sum(e['representation']!='raw' for e in prepared),
        'raw_preview_truncated': sum(e['representation']=='raw' and len(e['raw_text'])>500 for e in prepared),
        'L2_pulls': sum(e['level']=='L2' for e in pulls), 'L3_pulls': sum(e['level']=='L3' for e in pulls),
        'pulled_characters': sum(e['returned_characters'] for e in pulls),
        'prepared_is_presented': False}


def describe(values):
    values=sorted(values)
    return {'n':len(values), 'sum':sum(values), 'mean':statistics.fmean(values),
        'median':statistics.median(values), 'min':min(values), 'max':max(values)}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    status = read(STATUS); entries = catalog()
    selection = status['canonical_results']
    with sqlite3.connect(Path(status['ledger']).resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN')
        records=[dict(r) for r in db.execute('SELECT * FROM requests ORDER BY request_id')]
    assert all(r['status']=='settled' for r in records)
    usage_by_slot=defaultdict(list)
    for r in records:
        r['usage']=json.loads(r['usage_json']);usage_by_slot[r['slot_id']].append(r)
    with ThreadPoolExecutor(max_workers=2) as pool:
        extracted=list(pool.map(extract_events,[entries[r['slot_id']] for r in selection]))
    rows=[]
    for index,(base,(proof,events)) in enumerate(zip(selection,extracted)):
        entry=entries[base['slot_id']];version,batch,episode,planned=entry
        boundary=read(episode/'controller-output/managed-boundary.json')
        observed=read(episode/'controller-output/model-ledger/collaboration-observation/summary.json')
        calls=usage_by_slot[base['slot_id']]
        totals={key:sum(r['usage'].get(key,0) for r in calls) for key in
            ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')}
        assert totals['total_tokens']==base['actual_tokens']
        purposes={purpose:{key:sum(r['usage'].get(key,0) for r in calls if r['usage_id']==purpose)
            for key in ('prompt_tokens','completion_tokens','total_tokens')}
            | {'requests':sum(r['usage_id']==purpose for r in calls)} for purpose in ('agent','condenser','compressor')}
        members={member:sum(r['usage']['total_tokens'] for r in calls if r['member_id']==member)
            for member in planned['fixed_members']}
        actions=observed.get('actions',{}).get('whole_request_attribution',{})
        d=delivery(base,entry)
        row={**base,'repo':planned['repo'],'wave':planned['wave'],'source_version':version,
            'slot_index':planned['slot_index'],'episode_directory':str(episode),
            'delivery':d,'usage':totals,'purposes':purposes,'members':members,'physical_requests':len(calls),
            'budget_exhausted':any(v=='team_budget_exhausted' for v in boundary.get('role_stops',{}).values()),
            'role_stops':boundary.get('role_stops',{}),'cash_censored':boundary.get('cash_censored'),
            'administrative_censoring':boundary.get('administrative_censoring'),
            'closure_reason':boundary.get('closure_reason'),'communication':journal_metrics(events),
            'communication_extraction':proof,'observation_status':observed.get('completion_status'),
            'observation_errors':observed.get('runtime_measurement_errors',[]),
            'observation_partial_channels':observed.get('runtime_partial_channels',[]),
            'source_presentations':observed.get('source_presentations'),
            'action_counts':{k:v['requests'] for k,v in actions.items()},
            'public_tests':observed.get('public_tests'),
            'same_member_reread_characters_known':observed.get('information',{}).get('same_member_reread_characters'),
            'observed_direct_message_content_tokens':observed.get('messages',{}).get('direct_content_tokens_known'),
            'boundary_evidence':reference(episode/'controller-output/managed-boundary.json'),
            'observation_evidence':reference(episode/'controller-output/model-ledger/collaboration-observation/summary.json')}
        rows.append(row)
        if (index+1)%12==0:print(json.dumps({'analyzed':index+1,'model_calls':0}),flush=True)
    groups={}
    for group in ('C0','C1','C2'):
        selected=[r for r in rows if r['group_id']==group]
        communication=Counter();representations=Counter();fallbacks=Counter();actions=Counter()
        for r in selected:
            communication.update({k:v for k,v in r['communication'].items() if type(v) is int})
            representations.update(r['communication']['representations']);fallbacks.update(r['communication']['fallbacks'])
            actions.update(r['action_counts'])
        groups[group]={'n':len(selected),'code_correct':sum(r['R_code'] for r in selected),
            'delivery_correct':sum(r['delivery']['R_delivery'] for r in selected),
            'code_pass_delivery_fail':sum(r['R_code'] and not r['delivery']['R_delivery'] for r in selected),
            'code_fail_delivery_pass':sum(not r['R_code'] and r['delivery']['R_delivery'] for r in selected),
            'budget_exhausted':sum(r['budget_exhausted'] for r in selected),
            'budget_exhausted_code_fail':sum(r['budget_exhausted'] and not r['R_code'] for r in selected),
            'submitted':sum(r['delivery']['submitted'] for r in selected),
            'total_tokens':describe([r['usage']['total_tokens'] for r in selected]),
            'prompt_tokens':describe([r['usage']['prompt_tokens'] for r in selected]),
            'completion_tokens':describe([r['usage']['completion_tokens'] for r in selected]),
            'cache_hit_tokens':sum(r['usage']['prompt_cache_hit_tokens'] for r in selected),
            'cash_upper_nanoyuan':sum(r['cash_nanoyuan'] for r in selected),
            'physical_requests':sum(r['physical_requests'] for r in selected),
            'purposes':{purpose:{k:sum(r['purposes'][purpose][k] for r in selected)
                for k in ('requests','prompt_tokens','completion_tokens','total_tokens')}
                for purpose in ('agent','condenser','compressor')},
            'member_tokens':{member:sum(r['members'][member] for r in selected) for member in ('member_001','member_002')},
            'communication':dict(communication),'representations':dict(representations),'fallbacks':dict(fallbacks),
            'teams_with_compressor_calls':sum(r['purposes']['compressor']['requests']>0 for r in selected),
            'teams_with_nonraw_representation':sum(r['communication']['successful_summary_preparations']>0 for r in selected),
            'action_counts':dict(actions), 'delivery_methods':dict(Counter(r['delivery']['method'] for r in selected)),
            'raw_delivery_reuse_errors':sum(bool(r['delivery']['raw_reuse_error']) for r in selected)}
    paired={}
    for a,b in [('C2','C0'),('C2','C1'),('C1','C0')]:
        by_a={r['instance_id']:r for r in rows if r['group_id']==a}
        by_b={r['instance_id']:r for r in rows if r['group_id']==b}
        assert set(by_a)==set(by_b)
        pairs=[{'instance_id':t,'repo':by_a[t]['repo'],'a_code':by_a[t]['R_code'],'b_code':by_b[t]['R_code'],
            'a_delivery':by_a[t]['delivery']['R_delivery'],'b_delivery':by_b[t]['delivery']['R_delivery'],
            'token_delta':by_a[t]['usage']['total_tokens']-by_b[t]['usage']['total_tokens']}
            for t in sorted(by_a)]
        paired[a+'-'+b]={'a':a,'b':b,'both_pass':sum(p['a_code'] and p['b_code'] for p in pairs),
            'a_only_pass':sum(p['a_code'] and not p['b_code'] for p in pairs),
            'b_only_pass':sum(p['b_code'] and not p['a_code'] for p in pairs),
            'both_fail':sum(not p['a_code'] and not p['b_code'] for p in pairs),
            'token_delta':describe([p['token_delta'] for p in pairs]),
            'token_lower_tasks':sum(p['token_delta']<0 for p in pairs),'rows':pairs}
    chosen={r['slot_id'] for r in rows};all_tokens=sum(r['usage']['total_tokens'] for r in records)
    extras=[r for r in records if r['slot_id'] not in chosen]
    summary={'version':'v174-communication-pilot-final-analysis-r1','canonical_mapping':reference(STATUS),
        'groups':groups,'paired':paired,'rows':rows,'physical_requests_all_attempts':len(records),
        'all_actual_tokens':all_tokens,'all_cash_upper_nanoyuan':sum(r['settled_nanoyuan'] for r in records),
        'superseded_attempts':len({r['slot_id'] for r in extras}),'superseded_requests':len(extras),
        'superseded_actual_tokens':sum(r['usage']['total_tokens'] for r in extras),
        'superseded_cash_upper_nanoyuan':sum(r['settled_nanoyuan'] for r in extras),
        'new_model_calls':0,'new_grading_calls':0,'complete_source_token_attribution_claimed':False,
        'observation_statuses':dict(Counter(r['observation_status'] for r in rows)),
        'runtime_observation_error_episodes':sum(bool(r['observation_errors']) for r in rows),
        'measurement_categories_are_not_provider_token_split':True}
    write_new(OUTPUT/'summary.json',summary)
    fields=['instance_id','repo','group_id','slot_id','R_code','R_delivery','input_tokens','output_tokens',
        'total_tokens','cost_upper_CNY','budget_exhausted','compression_calls','prepared_summaries','fallback_count']
    with (OUTPUT/'task-results.csv').open('x',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for r in rows:writer.writerow({k:r.get(k) for k in fields[:5]} | {'R_delivery':r['delivery']['R_delivery'],
            'input_tokens':r['usage']['prompt_tokens'],'output_tokens':r['usage']['completion_tokens'],
            'total_tokens':r['usage']['total_tokens'],'cost_upper_CNY':r['cash_nanoyuan']/1e9,
            'budget_exhausted':r['budget_exhausted'],'compression_calls':r['purposes']['compressor']['requests'],
            'prepared_summaries':r['communication']['successful_summary_preparations'],
            'fallback_count':sum(r['communication']['fallbacks'].values())})
    print(json.dumps({'groups':groups,'superseded_tokens':summary['superseded_actual_tokens'],
        'superseded_cost_CNY':summary['superseded_cash_upper_nanoyuan']/1e9},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT,
        help='New report directory; existing result files are never replaced')
    OUTPUT=parser.parse_args().output.resolve()
    os.nice(10)
    os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[-2:])
    resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
    main()
