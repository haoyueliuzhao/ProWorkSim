"""Recover the three proven closed children whose owner died before its result.

Only existing artifacts are read. No model, container, test suite or grader is
started, and no original result/status is overwritten.
"""
from contextlib import closing
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tarfile
from types import SimpleNamespace

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new as original_write_new
from proworksim.software_benchmark_managed_recovery_v095 import (
    ROOT, EPISODES, archive_evidence, _relative,
)
from proworksim import software_benchmark_candidates_v054 as candidates
from proworksim.software_benchmark_archive_storage_v064 import open_verified_archive
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.software_benchmark_native_artifact_v054 import native_tree_manifest, PROTOCOL
from proworksim.software_benchmark_project_closure_v064 import validate_delivery_evidence
from proworksim.software_benchmark_snapshot_recovery_v061 import export_utf8_patch
from proworksim.software_benchmark_episode_v066 import archive_bundle
from proworksim.storage import json_bytes

VERSION = 'v095-original-closed-child-owner-result-recovery-r1'
ALLOWED = frozenset({3171, 3459, 3514})
OUTPUT = ROOT/'runs/software-benchmark-v095/closed-owner-recovery-r1'


def write_new(path, value):
    path = Path(path)
    if path.is_file():
        data = value if isinstance(value, bytes) else json_bytes(value)
        if path.read_bytes() != data:
            raise ValueError('Refuse to overwrite different administrative recovery evidence')
        return reference(path)
    return original_write_new(path, value)


def read(ref):
    return json.loads(checked(ref).read_bytes())


def cash_proof(slot_id, ledger):
    path = ROOT/'runs/software-benchmark-v064/full-verified-r1/api-budget/ledger.sqlite3'
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        rows = [dict(row) for row in db.execute(
            'SELECT request_id,slot_id,condition,status,usage_json,response_id,settled_nanoyuan FROM requests WHERE slot_id=? ORDER BY request_id', (slot_id,))]
    calls = ledger['calls']
    indexed = {row['request_id']: row for row in rows}
    if (len(rows) != ledger['attempts'] or len(calls) != len(rows)
            or ledger.get('complete_actual_tokens') != ledger.get('known_actual_tokens')
            or ledger.get('complete_actual_tokens') is None or ledger.get('inflight') is not None
            or ledger.get('uncertain_reserved_tokens') != 0):
        raise ValueError('Closed child and authoritative cash request count differ')
    total = 0
    for call in calls:
        row = indexed[call['request_id']]
        usage = json.loads(row['usage_json']) if row['usage_json'] is not None else None
        if (row['status'] != 'settled' or row['response_id'] != call['response_id']
                or row['settled_nanoyuan'] is None or usage != call['usage']):
            raise ValueError('A controller response lacks its identical settled provider receipt')
        total += usage['total_tokens']
    if total != ledger['known_actual_tokens']:
        raise ValueError('Authoritative actual token total differs')
    return {'ledger_path': str(path), 'read_only': True, 'requests': len(rows), 'known_actual_tokens': total,
            'settled_rows_sha256': hashlib.sha256(json_bytes(rows)).hexdigest(),
            'uncertain_requests': 0, 'ledger_rows_changed': False}


def recover(index, *, resume_existing_evidence=False):
    if index not in ALLOWED:
        raise ValueError('Only the three independently identified closed-owner cases are in scope')
    episode = EPISODES/str(index)
    owner = ROOT/'runs/software-benchmark-v080/dead-api-owner-r1/episodes'/str(index)
    completed_ref = reference(owner/'completed.json')
    completed = read(completed_ref)
    retained = read(completed['evidence'])
    row = retained['row']
    config = read(row['configuration'])
    writers_record = read(retained['writer_boundary'])
    writers, quiet = writers_record['writers'], completed['cleanup']
    if (completed.get('original_result') is not None or completed.get('new_model_calls') != 0
            or completed.get('generation_status') != 'technical_unknown'
            or completed.get('slot_id') != row['slot_id'] or row['slot_index'] != index
            or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or quiet.get('create_result_unknown') is not False or quiet.get('retained_objects') != []
            or writers.get('all_quiet') is not True or writers.get('errors') != []
            or {item['role'] for item in writers['writers']} != {'actor','controller'}
            or any(item['state'].get('Running') is not False or item['state'].get('Pid') != 0
                   or item['state'].get('ExitCode') != 0 for item in writers['writers'])):
        raise ValueError('The actual closed children and exact dead-owner cleanup are not proven')
    for item in writers['writers']:
        claim = read(item['claim'])
        if item['claim'] != retained['claims'][item['role']] or claim['spec']['slot_id'] != row['slot_id']:
            raise ValueError('Writer identity differs from the original task')
    output = OUTPUT/str(index)
    if output.exists():
        if (not resume_existing_evidence or not (output/'archive-verification.json').is_file()
                or (output/'recovered-result.json').exists()):
            raise ValueError('Existing recovery directory is not an explicitly resumable incomplete artifact preparation')
    else:
        output.mkdir(parents=True, exist_ok=False)
    transfer = read(retained['archives']['controller'])
    storage = transfer['storage']
    archive_name = 'archive-verification-r2.json' if resume_existing_evidence else 'archive-verification.json'
    archive = archive_evidence(storage, episode/'controller-output', output, extract_large=True,
                               receipt_name=archive_name)
    refs = archive['selected_evidence']
    child = read(refs['controller-result.json'])
    if (child.get('status') != 'closed' or child.get('slot_id') != row['slot_id']
            or child.get('condition_id') != row['condition_id'] or child.get('preparation_only') is not False
            or child.get('hidden_feedback_received') is not False or child.get('automatic_retry') is not False):
        raise ValueError('Original controller did not actually close this one task')
    usage = cash_proof(row['slot_id'], child['ledger'])
    writer_ref = write_new(output/'writers.json', {**writers, 'original_owner_evidence': retained['writer_boundary']})
    quiet_ref = write_new(output/'quiescence.json', {**quiet, 'original_owner_evidence': completed_ref})
    baseline_ref = reference(episode/'baseline-snapshot.json')
    baseline = read(baseline_ref)
    base_tree = native_tree_manifest(baseline['files'], baseline['entry_metadata'])['tree_sha256']
    slot = {key: config[key] for key in ('slot_id','slot_index','instance_id','condition_id','seed','arm')}

    def resolved(ref):
        value = refs.get(_relative(ref).as_posix())
        if value is None or any(value[k] != ref[k] for k in ('sha256','bytes')):
            raise ValueError('Original managed reference is not in the verified archive')
        return checked(value)

    def native_lock(endpoint, bundle_ref, tree, patch, *, original_lock=None):
        return write_new(output/(endpoint+'-lock.json'), {
            'version':'software-benchmark-native-closure-v054','implementation':VERSION,
            'slot':slot,'source_slot_id':row['source_slot_id'],'measurement_kind':'full_verified_comparison',
            'endpoint':endpoint,'quiescence':writer_ref,'baseline':baseline_ref,'candidate':bundle_ref,
            'patch_receipt':patch,'tree_sha256':tree,'delivery':None,'lock_before_grading':True,
            'model_calls':0,'grading_calls':0,'original_managed_lock':original_lock})

    delivery_lock, delivery_ref, delivery_snapshot_ref = None, None, None
    if row['arm']=='PROJECT':
        root_lock = read(refs['project-candidates/lock.json'])
        original_root = {'path':'/pws/output/project-candidates/lock.json',
                         **{k:refs['project-candidates/lock.json'][k] for k in ('sha256','bytes')}}
        pair = private_function(candidates.read_episode_candidates, checked=resolved,
            read_locked_candidate=private_function(candidates.read_locked_candidate,checked=resolved))(original_root)
        boundary = read(refs['managed-boundary.json'])
        if boundary.get('status')!='bounded_work_closed' or boundary.get('execution_integrity_failure') is not None:
            raise ValueError('Managed child has no trusted model-work boundary')
        evidence, delivery = read(refs['delivery-evidence.json']), read(refs['project-delivery-snapshot.json'])
        delivery_proof = validate_delivery_evidence(evidence, delivery, baseline)
        delivery_ref, delivery_snapshot_ref = refs['delivery-evidence.json'],refs['project-delivery-snapshot.json']
        def endpoint_lock(endpoint, original, bundle):
            lock = json.loads(resolved(original).read_bytes())
            patch = json.loads(resolved(lock['patch_receipt']).read_bytes())
            resolved(patch['patch']).read_bytes().decode('utf-8','strict')
            tree = native_tree_manifest(bundle['files'],bundle['entry_metadata'])['tree_sha256']
            if patch['base_tree_sha256']!=base_tree or patch['candidate_tree_sha256']!=tree or not patch['round_trip_verified']:
                raise ValueError('Original patch and complete native source trees differ')
            return native_lock(endpoint,refs[_relative(lock['candidate']).as_posix()],tree,
                {**patch,'patch':refs[_relative(patch['patch']).as_posix()],'utf8_strict':True,
                 'candidate_content_changed':False,'native_artifact_protocol':PROTOCOL,'patch_regenerated':False},
                original_lock=refs[_relative(original).as_posix()])
        code_lock = endpoint_lock('terminal_code',root_lock['terminal_code'],pair['terminal_code'])
        if pair['last_legal_delivery'] is not None:
            delivery_lock = endpoint_lock('last_legal_delivery',root_lock['last_legal_delivery'],pair['last_legal_delivery'])
    else:
        if child.get('native_finished') is not True or child.get('normal_completion') is not True:
            raise ValueError('This narrow REF repair requires the original native normal finish')
        claim = read(reference(episode/'candidate-claim.json'))
        if claim.get('slot_id')!=row['slot_id'] or claim.get('selection')!='single_final_worktree_after_generation':
            raise ValueError('No original unique terminal-worktree selection claim')
        original_quiet = read(claim['writer_quiescence'])
        if (original_quiet.get('all_quiet') is not True or original_quiet.get('errors')!=[]
                or {item['container_id'] for item in original_quiet['writers']} != {item['container_id'] for item in writers['writers']}):
            raise ValueError('Original candidate selection preceded another writer boundary')
        worktree = read(retained['archives']['worktree'])
        actor = next(item for item in writers['writers'] if item['role']=='actor')
        if worktree.get('container_id')!=actor['container_id'] or worktree.get('container_path')!='/testbed':
            raise ValueError('Retained final worktree is not from the stopped original actor')
        with open_verified_archive(worktree['storage']) as raw:
            terminal = private_function(archive_bundle,tarfile=SimpleNamespace(
                open=lambda *_args,**_kwargs: tarfile.open(fileobj=raw,mode='r|')))(None,gitlinks=baseline.get('gitlinks',[]))
        terminal_ref = write_new(output/'terminal-snapshot.json',terminal)
        patch = export_utf8_patch(baseline,terminal,output/'candidate.patch',policy=terminal['file_policy'])
        code_lock = native_lock('terminal_code',terminal_ref,patch['candidate_tree_sha256'],patch)
        delivery_proof = {'submitted':None,'scope':'REF has no project delivery contract'}
    audit = write_new(output/'administrative-closure-audit.json',{
        'version':VERSION,'original_owner_recovery':completed_ref,'original_retained_evidence':completed['evidence'],
        'original_controller':refs['controller-result.json'],'original_controller_status':'closed',
        'actual_cash_reconciliation':usage,'archive_verification':reference(output/archive_name),
        'writer_quiescence':writer_ref,'cleanup':quiet_ref,'original_result_absent':True,
        'new_model_calls':0,'new_container_operations':0,'scoring_performed':False,
        'candidate_lock':code_lock,'delivery_candidate_lock':delivery_lock})
    result = {**row,'version':VERSION,'status':'closed','original_status':'technical_unknown',
        'original_result':None,'original_administrative_owner_recovery':completed_ref,
        'administrative_closure_audit':audit,'recovery_kind':'original_closed_child_owner_result_missing',
        'candidate_lock':code_lock,'delivery_candidate_lock':delivery_lock,'quiescence':quiet_ref,
        'writer_quiescence':writer_ref,'controller_result':refs['controller-result.json'],
        'controller_status':'closed','controller_exit_code':0,'model_calls':child['ledger']['attempts'],
        'ledger':child['ledger'],'known_actual_tokens':child['ledger']['known_actual_tokens'],
        'model_calls_added':0,'old_result_written':False,'delivery_validation':delivery_proof,
        'delivery_evidence':delivery_ref,'delivery_snapshot':delivery_snapshot_ref,
        'project_baseline_snapshot':baseline_ref if row['arm']=='PROJECT' else None}
    return write_new(output/'recovered-result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=int,required=True)
    parser.add_argument('--resume-existing-evidence',action='store_true')
    args=parser.parse_args()
    print(json.dumps(recover(args.index,resume_existing_evidence=args.resume_existing_evidence)))
