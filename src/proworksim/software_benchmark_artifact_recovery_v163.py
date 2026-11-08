"""Read-only verification of15703's pre-existing unique code/delivery candidates.

The absent controller-result.json is not fabricated. A new administrative
record binds the original lock, settled usage and stopped actor export. No
model, test, scorer, container, network call or old-file mutation occurs here.
"""
from __future__ import annotations
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path,PurePosixPath
import sqlite3
import tarfile

from . import software_benchmark_candidates_v054 as c
from .software_benchmark_archive_storage_v064 import open_verified_archive,stream_reference
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_native_artifact_v054 import native_tree_manifest,PROTOCOL
from .software_benchmark_project_closure_v157 import validate_delivery_evidence
from .storage import digest,json_bytes

VERSION='v163-original-15703-locked-candidate-administrative-recovery-r1'
ROOT=Path(__file__).resolve().parents[2]
EPISODE=ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/episodes/15703'
OUTPUT=ROOT/'artifacts/software-benchmark-v163/locked-candidate-recovery-r2'
LEDGER=ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/ledgers/pilot.sqlite'


def read(path):return json.loads(Path(path).read_bytes())


def rel(ref):
    p=PurePosixPath(ref['path'])
    if p.parts[:3]!=('/','pws','output') or '..' in p.parts:raise ValueError('Original reference escaped controller output')
    return '/'.join(p.parts[3:])


def archive_evidence(storage,controller,output):
    wanted={'managed-boundary.json','delivery-evidence.json','project-delivery-snapshot.json',
        'project-terminal-snapshot.json','project-baseline-snapshot.json','project-candidates/lock.json',
        'managed-world/world/control/v141-candidate-close.json',
        'model-ledger/collaboration-observation/summary.json'}
    selected={};headers={};communication=[]
    with open_verified_archive(storage) as raw:
        with tarfile.open(fileobj=raw,mode='r|') as archive:
            for entry in archive:
                p=PurePosixPath(entry.name.removeprefix('./'))
                if not p.parts or p.parts[0]!='output' or p.is_absolute() or '..' in p.parts:continue
                name='/'.join(p.parts[1:])
                comm='/communication/' in name and name.endswith(('.json','.jsonl'))
                keep=(name in wanted or name.startswith('project-candidates/')
                    or name.startswith('managed-actor-rpc/') and name.endswith(('-request.json','-response.json')) or comm)
                if not keep or not entry.isfile():continue
                if name in headers:raise ValueError('Duplicate locked evidence in original archive')
                target=controller/name
                if not target.is_file():
                    target=output/'archive-evidence'/name;target.parent.mkdir(parents=True,exist_ok=True)
                    handle=target.open('xb')
                else:handle=None
                hasher=hashlib.sha256();size=0
                try:
                    stream=archive.extractfile(entry)
                    for chunk in iter(lambda:stream.read(1024*1024),b''):
                        hasher.update(chunk);size+=len(chunk)
                        if handle is not None:handle.write(chunk)
                finally:
                    if handle is not None:handle.close()
                bound=stream_reference(target)
                if size!=entry.size or bound['bytes']!=size or bound['sha256']!=hasher.hexdigest():
                    raise ValueError('Extracted evidence changed relative to original archive')
                selected[name]=bound;headers[name]={'mtime':entry.mtime,'size':entry.size}
                if comm and entry.size<=1024*1024:
                    if name.endswith('.json'):
                        value=read(target)
                    else:
                        events=[json.loads(line) for line in target.read_text().splitlines() if line.strip()]
                        published=[r for r in events if r.get('kind')=='published']
                        rendered=[r for r in events if r.get('kind')=='representation_prepared']
                        value={'jsonl_event_count':len(events),'published':len(published),
                            'facts_complete_publications':sum(r.get('facts_complete') is True for r in published),
                            'representations_prepared':len(rendered),
                            'structured_representations':sum(r.get('representation') in {'structured_summary','L0_L1'} for r in rendered),
                            'raw_fallbacks':sum(bool(r.get('fallback_reason')) for r in rendered),
                            'fallback_reasons':sorted({r.get('fallback_reason') for r in rendered if r.get('fallback_reason')}),
                            'compressor_attempts':sum(len(r.get('compressor_attempts',[])) if isinstance(r.get('compressor_attempts'),list) else r.get('compressor_attempts',0) for r in rendered),
                            'presentation_not_inferred_from_preparation':True}
                    communication.append({'path':name,'reference':bound,'keys':list(value) if isinstance(value,dict) else None,
                        'condition':value.get('condition') if isinstance(value,dict) else None,
                        'fallback_reason':value.get('fallback_reason') if isinstance(value,dict) else None,
                        'status':value.get('status') if isinstance(value,dict) else None,
                        'event_summary':value if name.endswith('.jsonl') else None})
    proof={'version':VERSION,'storage':storage,'full_archive_verified':True,'selected':selected,
        'archive_headers':headers,'communication_index':communication,'new_model_calls':0,
        'raw_archive_extracted':False,'candidate_reselected':False}
    c.write_new(output/'archive-verification.json',proof)
    return proof


def actor_tree_proof(archive_ref,expected):
    path=c.checked(archive_ref);wanted={r['path']:r for r in expected['entries']};seen=set();ignored_git=0
    with tarfile.open(path,mode='r|') as archive:
        for entry in archive:
            p=PurePosixPath(entry.name.removeprefix('./'))
            if not p.parts or p.parts[0]!='testbed' or p.is_absolute() or '..' in p.parts:
                raise ValueError('Unexpected stopped actor archive path')
            parts=p.parts[1:]
            if not parts or entry.isdir():continue
            if '.git' in parts:ignored_git+=1;continue
            name='/'.join(parts)
            if name not in wanted or name in seen:raise ValueError('Stopped actor has an unexpected or duplicate source entry: '+name)
            row=wanted[name]
            if entry.issym():raw=entry.linkname.encode();mode='120000';kind='symlink'
            elif entry.isfile():raw=archive.extractfile(entry).read();mode='100755' if entry.mode&0o111 else '100644';kind='file'
            else:raise ValueError('Unexpected special file in stopped actor')
            if (len(raw)!=row['size_bytes'] or digest(raw)!=row['sha256'] or mode!=row['mode'] or kind!=row['kind']):
                raise ValueError('Stopped actor differs from locked candidate at '+name)
            seen.add(name)
    if seen!=set(wanted):raise ValueError('Stopped actor lacks locked source files')
    return {'archive':archive_ref,'source_entries_verified':len(seen),'git_control_entries_ignored':ignored_git,
        'same_locked_candidate_tree':True,'actor_worktree_selected_as_new_candidate':False}


def recover():
    episode=EPISODE;controller=episode/'controller-output';out=OUTPUT
    if out.exists():raise ValueError('Administrative recovery evidence must not be overwritten')
    result=read(episode/'result.json');boundary=read(controller/'managed-boundary.json')
    observer=read(controller/'model-ledger/collaboration-observation/summary.json')
    quiet=read(episode/'quiescence.json');writers=read(episode/'writer-quiescence.json')
    if (controller/'controller-result.json').exists():raise ValueError('This recovery addresses only absent top-level result')
    if (result.get('status')!='technical_unknown' or result.get('instance_id')!='sympy__sympy-17318'
        or result.get('group_id')!='C1' or boundary.get('status')!='bounded_work_closed'
        or boundary.get('execution_integrity_failure') is not None or boundary.get('continuation') is not False
        or observer.get('completion_status')!='normal' or observer.get('runtime_measurement_errors')!=[]
        or observer.get('coverage',{}).get('presentations') is not True):
        raise ValueError('The original managed/observer closure is not trustworthy')
    if (quiet.get('quiescent') is not True or quiet.get('cleanup_errors')!=[]
        or quiet.get('create_result_unknown') is not False or quiet.get('retained_objects')!=[]
        or writers.get('all_quiet') is not True or writers.get('errors')!=[]
        or {r['role'] for r in writers['writers']}!={'actor','controller'}
        or any(r['state'].get('Running') is not False or r['state'].get('Pid')!=0 for r in writers['writers'])):
        raise ValueError('Original writers and cleanup have not closed')
    with sqlite3.connect(LEDGER.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        rows=[dict(r) for r in db.execute('SELECT * FROM requests WHERE slot_id=? ORDER BY reserved_utc,request_id',(result['slot_id'],))]
        global_count=db.execute('SELECT COUNT(*),COUNT(DISTINCT slot_id) FROM requests').fetchone()
    if not rows or any(r['status']!='settled' or not r['usage_json'] for r in rows):
        raise ValueError('Original physical usage is not wholly settled')
    transfer=read(episode/'controller-output-transfer.json');copied=transfer['transfer']
    controller_owner=next(r for r in writers['writers'] if r['role']=='controller')
    if (copied['container_id']!=controller_owner['container_id'] or copied['container_claim']!=controller_owner['claim']
        or copied['container_path']!='/pws/output' or copied['stream_sha256']!=transfer['archive_storage']['decompressed_sha256']):
        raise ValueError('Controller export lost its original stopped writer binding')
    out.mkdir(parents=True,exist_ok=False)
    archive=archive_evidence(transfer['archive_storage'],controller,out)
    selected=archive['selected']
    def checked(ref):
        name=rel(ref);bound=selected.get(name)
        if bound is None or any(ref.get(k)!=bound[k] for k in ('sha256','bytes')):
            raise ValueError('Locked reference has no identical original archived member: '+name)
        return c.checked(bound)
    lock_ref={'path':'/pws/output/project-candidates/lock.json',**{k:selected['project-candidates/lock.json'][k] for k in ('sha256','bytes')}}
    pair=private_function(c.read_episode_candidates,checked=checked,
        read_locked_candidate=private_function(c.read_locked_candidate,checked=checked))(lock_ref)
    original_lock=pair['lock']
    if (original_lock.get('locked_before_grading') is not True or original_lock.get('same_world_transaction') is not True
        or original_lock.get('same_tree') is not True or original_lock.get('submitted') is not True):
        raise ValueError('This case needs its original identical code/delivery endpoint locks')
    baseline=read(c.checked(selected['project-baseline-snapshot.json']))
    delivery=read(c.checked(selected['project-delivery-snapshot.json']))
    evidence=read(c.checked(selected['delivery-evidence.json']))
    verdict=validate_delivery_evidence(evidence,delivery,baseline)
    if verdict['submitted'] is not True or verdict.get('organization_submission_verified') is not True:
        raise ValueError('Original lawful REVIEW2 delivery chain failed verification')
    bundle=pair['terminal_code'];tree=native_tree_manifest(bundle['files'],bundle['entry_metadata'])
    base_tree=native_tree_manifest(baseline['files'],baseline['entry_metadata'])['tree_sha256']
    sync=[(name,read(c.checked(ref))) for name,ref in selected.items() if name.startswith('managed-actor-rpc/') and name.endswith('-response.json')]
    synced=[(name,v) for name,v in sync if v.get('tool')=='sync_terminal']
    if len(synced)!=1:raise ValueError('Need exactly one original terminal actor synchronization')
    sync_name,sync_reply=synced[0];sync_result=sync_reply['result']
    if (sync_result.get('tree_sha256')!=tree['tree_sha256'] or sync_result.get('exact_complete_tree') is not True
        or sync_result.get('terminal_locked') is not True or sync_result.get('model_can_resume') is not False
        or sync_reply.get('upload_receipt',{}).get('complete_payload_verified') is not True
        or sync_reply.get('upload_receipt',{}).get('operation_executed') is not True):
        raise ValueError('Original actor did not synchronize the unique terminal candidate')
    actor=read(episode/'interrupted-worktree.json');actor_owner=next(r for r in writers['writers'] if r['role']=='actor')
    if actor['archive']['container_id']!=actor_owner['container_id'] or actor['archive']['container_claim']!=actor_owner['claim']:
        raise ValueError('Stopped actor export belongs to another original writer')
    actor_proof=actor_tree_proof(actor['archive']['archive'],tree)
    code_locked=read(checked(original_lock['terminal_code']))
    if sync_result.get('source_reference')!=code_locked['source_reference']:
        raise ValueError('Terminal synchronization changed managed version identity')
    lock_time=archive['archive_headers']['project-candidates/lock.json']['mtime']
    if any(datetime.fromisoformat(r['finished_utc']).timestamp()>lock_time+1 for r in rows):
        raise ValueError('A physical model request completed after final candidate locking')
    config=read(c.checked(result['configuration']));slot={k:config[k] for k in ('slot_id','slot_index','instance_id','condition_id','seed','arm')}
    def host_lock(endpoint,source_ref,bundle):
        original=read(checked(source_ref));receipt=read(checked(original['patch_receipt']))
        patch=checked(receipt['patch']);patch.read_bytes().decode('utf-8','strict')
        native=native_tree_manifest(bundle['files'],bundle['entry_metadata'])['tree_sha256']
        if (native!=original['tree_sha256'] or receipt.get('candidate_tree_sha256')!=native
            or receipt.get('base_tree_sha256')!=base_tree or receipt.get('round_trip_verified') is not True):
            raise ValueError('Original patch is not a lossless representation of its locked endpoint')
        return c.write_new(out/(endpoint+'-lock.json'),{'version':'software-benchmark-native-closure-v054',
            'implementation':VERSION,'slot':slot,'source_slot_id':result['source_slot_id'],
            'measurement_kind':result['measurement_kind'],'endpoint':endpoint,'quiescence':reference(episode/'writer-quiescence.json'),
            'baseline':selected['project-baseline-snapshot.json'],'candidate':selected[rel(original['candidate'])],
            'patch_receipt':{**receipt,'patch':selected[rel(receipt['patch'])],'utf8_strict':True,
                'candidate_content_changed':False,'native_artifact_protocol':PROTOCOL,'patch_regenerated':False},
            'tree_sha256':native,'original_managed_lock':selected[rel(source_ref)],'lock_before_grading':True,
            'administrative_relocation_only':True,'actor_terminal_sync_completed':True,'model_calls':0,'grading_calls':0})
    code=host_lock('terminal_code',original_lock['terminal_code'],pair['terminal_code'])
    submitted=host_lock('last_legal_delivery',original_lock['last_legal_delivery'],pair['last_legal_delivery'])
    usage={'physical_requests':len(rows),'actual_input_tokens':sum(json.loads(r['usage_json'])['prompt_tokens'] for r in rows),
        'actual_output_tokens':sum(json.loads(r['usage_json'])['completion_tokens'] for r in rows),
        'actual_total_tokens':sum(json.loads(r['usage_json'])['total_tokens'] for r in rows),
        'all_settled':True,'known_cash_upper_nanoyuan':sum(r['settled_nanoyuan'] for r in rows),'source_ledger':str(LEDGER)}
    audit=c.write_new(out/'administrative-closure-audit.json',{'version':VERSION,
        'original_result':reference(episode/'result.json'),'original_result_missing_controller_summary_retained':True,
        'managed_boundary':selected['managed-boundary.json'],'observer':selected['model-ledger/collaboration-observation/summary.json'],
        'observer_original_coverage':observer['coverage'],'coverage_reconstructed_or_invented':False,
        'archive_verification':reference(out/'archive-verification.json'),'actor_sync_response':selected[sync_name],
        'actor_export_same_tree':actor_proof,'unique_original_candidate_preserved':True,
        'candidate_lock':code,'delivery_candidate_lock':submitted,'submitted':True,'same_tree':True,
        'delivery_validation':verdict,'usage':usage,'global_ledger_rows_observed':global_count[0],
        'original_used_slots_observed':global_count[1],'model_calls_added':0,'candidate_content_changed':False,
        'actor_interrupted_tree_selected_as_candidate':False,'original_generation_status_changed':False,
        'official_scoring_performed':False})
    value={**copy.deepcopy(result),'status':'closed','recovery_version':VERSION,
        'recovery_kind':'administrative_recovery_of_original_prelocked_dual_endpoint',
        'original_result':reference(episode/'result.json'),'original_status':result['status'],
        'administrative_closure_audit':audit,'controller_result_reconstructed':False,
        'candidate_lock':code,'delivery_candidate_lock':submitted,'delivery_validation':verdict,
        'delivery_evidence':selected['delivery-evidence.json'],'delivery_snapshot':selected['project-delivery-snapshot.json'],
        'project_baseline_snapshot':selected['project-baseline-snapshot.json'],
        'controller_output_transfer':reference(episode/'controller-output-transfer.json'),
        'model_calls':len(rows),'model_calls_added':0,'known_actual_tokens':usage['actual_total_tokens'],
        'same_tree':True,'assessment_performed':False,'observer_coverage_preserved':observer['coverage']}
    return c.write_new(out/'recovered-result.json',value)


reference=c.reference
