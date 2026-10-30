"""Offline recovery of an already locked managed terminal code candidate.

An interrupted actor worktree is never selected. Old records remain unchanged;
the new result explicitly records administrative artifact closure, not a normal
controller exit, successful delivery, new generation, or successful grading.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

from . import software_benchmark_candidates_v054 as candidates
from .software_benchmark_archive_storage_v064 import open_verified_archive, stream_reference
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_native_artifact_v054 import native_tree_manifest, PROTOCOL
from .software_benchmark_project_closure_v064 import validate_delivery_evidence

VERSION = 'v095-original-managed-terminal-administrative-recovery-r1'
ROOT = Path(__file__).resolve().parents[2]
EPISODES = ROOT/'runs/software-benchmark-v066/v064-continuation-r3/episodes'
OUTPUT = ROOT/'runs/software-benchmark-v095/managed-terminal-recovery-r1'
META_NAMES = ('controller-result.json', 'managed-boundary.json', 'delivery-evidence.json',
              'project-delivery-snapshot.json', 'project-candidates/lock.json',
              'managed-world/world/control/v054-candidate-close.json')


def read(path):
    return json.loads(Path(path).read_bytes())


def validate_boundary(result, child, boundary, quiet, writers, bridge, lock):
    """Only frozen post-SDK-close managed locks can repair export administration."""
    if (result.get('arm') != 'PROJECT' or child.get('arm') != 'PROJECT'
            or child.get('slot_id') != result.get('slot_id')
            or child.get('hidden_feedback_received') is not False
            or child.get('automatic_retry') is not False
            or child.get('preparation_only') is not False
            or boundary.get('status') != 'bounded_work_closed'
            or boundary.get('execution_integrity_failure') is not None
            or boundary.get('continuation') is not False
            or boundary.get('closure_reason') != child.get('closure_reason')):
        raise ValueError('Managed generation has no trusted fixed terminal boundary')
    trace = child.get('traceback', '')
    if child.get('status') != 'closed' and not (
            child.get('error', {}).get('type') in {'ManagedTransferError', 'ManagedInterfaceLimit', 'RuntimeError', 'ValueError'}
            and ('synced = rpc.request("sync_terminal"' in trace
                 or 'Stopped actor code does not equal the uniquely locked managed terminal tree' in trace)):
        raise ValueError('Failure is not proven to follow SDK close and managed candidate locking')
    ledger = child.get('ledger', {})
    calls = ledger.get('calls', [])
    if (type(ledger.get('complete_actual_tokens')) is not int
            or ledger['complete_actual_tokens'] != ledger.get('known_actual_tokens')
            or ledger.get('inflight') is not None or ledger.get('uncertain_reserved_tokens') != 0
            or not isinstance(calls, list) or len(calls) != ledger.get('attempts')
            or sum(call['usage']['total_tokens'] for call in calls) != ledger['known_actual_tokens']
            or any(call['usage']['prompt_tokens']+call['usage']['completion_tokens'] != call['usage']['total_tokens']
                   for call in calls)):
        raise ValueError('Original model accounting is incomplete or inconsistent')
    if (quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or quiet.get('create_result_unknown') is not False or quiet.get('retained_objects') != []
            or writers.get('all_quiet') is not True or writers.get('errors') != []
            or {item.get('role') for item in writers.get('writers', [])} != {'actor', 'controller'}
            or any(item.get('state', {}).get('Running') is not False or item['state'].get('Pid') != 0
                   for item in writers['writers'])):
        raise ValueError('Original writer or cleanup closure is not proven')
    if (bridge.get('ready') is not True or bridge.get('status') not in {'channel_closed', 'stopped_after_controller'}
            or bridge.get('generation_requests') != ledger['attempts']
            or bridge.get('failed_requests') != 0 or bridge.get('automatic_retries') != 0):
        raise ValueError('Original model bridge does not reconcile with terminal usage')
    if (lock.get('version') != candidates.EPISODE_VERSION or lock.get('locked_before_grading') is not True
            or lock.get('same_world_transaction') is not True
            or not isinstance(lock.get('terminal_code'), dict)
            or lock.get('current_working_tree_substituted_for_delivery') is not False
            or any(lock.get(key) != 0 for key in ('model_calls', 'public_test_calls', 'grading_calls'))):
        raise ValueError('Only the original pre-grading terminal lock may be selected')
    return {'administrative_artifact_recovery_eligible': True,
            'original_controller_normal_exit': child.get('status') == 'closed',
            'original_model_calls': ledger['attempts'], 'original_tokens': ledger['known_actual_tokens'],
            'actor_interrupted_tree_used': False, 'model_rerun': False}


def _relative(ref):
    path = PurePosixPath(ref['path'])
    if path.parts[:3] != ('/', 'pws', 'output') or '..' in path.parts:
        raise ValueError('Managed reference escapes original controller output')
    return Path(*path.parts[3:])


def archive_evidence(storage, controller, output, *, extract_large=False, receipt_name='archive-verification.json'):
    """One verified stream pass; retain only endpoint evidence, never an actor tree."""
    saved, indexed, selected = {}, {}, {}
    large = {'project-terminal-snapshot.json', 'project-baseline-snapshot.json', 'project-delivery-snapshot.json',
             'project-candidates/terminal-code/candidate-bundle.json',
             'project-candidates/last-legal-delivery/candidate-bundle.json'}
    with open_verified_archive(storage) as raw:
        with tarfile.open(fileobj=raw, mode='r|') as archive:
            for item in archive:
                name = PurePosixPath(item.name.removeprefix('./'))
                if not name.parts or name.parts[0] != 'output' or name.is_absolute() or '..' in name.parts:
                    continue
                relative = '/'.join(name.parts[1:])
                wanted = relative in META_NAMES or relative.startswith('project-candidates/')
                wanted |= relative in large
                if not wanted or not item.isfile():
                    continue
                if relative in indexed:
                    raise ValueError('Duplicate endpoint evidence in original archive')
                target = controller/relative
                cached = output/'archive-evidence'/relative
                if not target.is_file() and cached.is_file():
                    target = cached
                destination = None
                if not target.is_file() and (item.size <= 4*1024**2 or extract_large and relative in large):
                    destination = output/'archive-evidence'/relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(item)
                hasher, total = hashlib.sha256(), 0
                handle = destination.open('xb') if destination is not None else None
                try:
                    for chunk in iter(lambda: stream.read(1024**2), b''):
                        hasher.update(chunk)
                        total += len(chunk)
                        if handle is not None:
                            handle.write(chunk)
                finally:
                    if handle is not None:
                        handle.close()
                identity = {'sha256': hasher.hexdigest(), 'bytes': total}
                if total != item.size:
                    raise ValueError('Truncated endpoint archive member')
                indexed[relative] = identity
                if target.is_file():
                    reference = stream_reference(target)
                    if any(reference[key] != identity[key] for key in identity):
                        raise ValueError('Extracted endpoint differs from its trusted original archive')
                    selected[relative] = reference
                elif destination is not None:
                    saved[relative] = selected[relative] = stream_reference(destination)
    receipt = {'version': VERSION, 'storage': storage, 'full_archive_verified': True,
               'endpoint_members': indexed, 'selected_evidence': selected, 'newly_extracted': saved,
               'raw_archive_extracted': False, 'actor_worktree_selected': False}
    candidates.write_new(output/receipt_name, receipt)
    return receipt


def recover(index, *, episode_root=EPISODES, output_root=OUTPUT):
    """Create one independent administrative result, never overwrite old output."""
    episode = Path(episode_root)/str(index)
    output = Path(output_root)/str(index)
    controller = episode/'controller-output'
    result = read(episode/'result.json')
    child = read(controller/'controller-result.json')
    boundary = read(controller/'managed-boundary.json')
    quiet = read(episode/'quiescence.json')
    writers = read(episode/'writer-quiescence.json')
    bridge = read(episode/'model-transport.json')
    original_lock = read(controller/'project-candidates/lock.json')
    eligibility = validate_boundary(result, child, boundary, quiet, writers, bridge, original_lock)
    config = read(candidates.checked(result['configuration']))
    transfer = read(episode/'controller-output-transfer.json')
    copied = transfer['transfer']
    owner = next(item for item in writers['writers'] if item['role'] == 'controller')
    if (copied.get('role') != 'controller' or copied.get('container_path') != '/pws/output'
            or copied.get('container_id') != owner['container_id'] or copied.get('container_claim') != owner['claim']
            or transfer['relocation'].get('host_prefix') != str(controller)
            or transfer['archive_storage']['decompressed_sha256'] != copied['stream_sha256']):
        raise ValueError('Controller archive is not bound to the original stopped writer')
    for role in ('actor', 'controller'):
        claim = read(candidates.checked(quiet['claims'][role]))
        if claim['spec'].get('slot_id') != result['slot_id'] or claim['spec'].get('instance_id') != result['instance_id']:
            raise ValueError('Quiet resource claim belongs to another task')
    output.mkdir(parents=True, exist_ok=False)
    archive = archive_evidence(transfer['archive_storage'], controller, output)
    resolved = archive['selected_evidence']

    def checked(ref):
        relative = _relative(ref).as_posix()
        bound = resolved.get(relative)
        if bound is None or any(ref.get(key) != bound.get(key) for key in ('sha256', 'bytes')):
            raise ValueError('Locked reference has no identical verified archive member: '+relative)
        return candidates.checked(bound)

    original_ref = {'path': '/pws/output/project-candidates/lock.json',
                    **{k: archive['endpoint_members']['project-candidates/lock.json'][k] for k in ('sha256', 'bytes')}}
    read_locked = private_function(candidates.read_locked_candidate, checked=checked)
    pair = private_function(candidates.read_episode_candidates, checked=checked,
                            read_locked_candidate=read_locked)(original_ref)
    baseline_ref = resolved['project-baseline-snapshot.json']
    baseline = read(candidates.checked(baseline_ref))
    base_tree = native_tree_manifest(baseline['files'], baseline['entry_metadata'])['tree_sha256']
    evidence = read(checked({'path': '/pws/output/delivery-evidence.json',
                            **archive['endpoint_members']['delivery-evidence.json']}))
    delivery = read(checked({'path': '/pws/output/project-delivery-snapshot.json',
                            **archive['endpoint_members']['project-delivery-snapshot.json']}))
    delivery_proof = validate_delivery_evidence(evidence, delivery, baseline)
    slot = {key: config[key] for key in ('slot_id', 'slot_index', 'instance_id', 'condition_id', 'seed', 'arm')}

    def host_lock(kind, original_endpoint, bundle):
        locked = read(checked(original_endpoint))
        patch = read(checked(locked['patch_receipt']))
        patch_path = checked(patch['patch'])
        patch_path.read_bytes().decode('utf-8', 'strict')
        tree = native_tree_manifest(bundle['files'], bundle['entry_metadata'])['tree_sha256']
        if (tree != locked['tree_sha256'] or patch.get('round_trip_verified') is not True
                or patch.get('base_tree_sha256') != base_tree or patch.get('candidate_tree_sha256') != tree):
            raise ValueError('Original verified patch is not bound to the exact native endpoint')
        receipt = {**patch, 'patch': resolved[_relative(patch['patch']).as_posix()],
            'utf8_strict': True, 'candidate_content_changed': False, 'native_artifact_protocol': PROTOCOL,
            'original_round_trip_receipt': resolved[_relative(locked['patch_receipt']).as_posix()],
            'patch_regenerated': False}
        return candidates.write_new(output/(kind+'-lock.json'), {
            'version': 'software-benchmark-native-closure-v054', 'implementation': VERSION,
            'slot': slot, 'source_slot_id': result['source_slot_id'],
            'measurement_kind': result['measurement_kind'], 'endpoint': kind,
            'quiescence': stream_reference(episode/'writer-quiescence.json'),
            'baseline': baseline_ref, 'candidate': resolved[_relative(locked['candidate']).as_posix()],
            'patch_receipt': receipt, 'tree_sha256': tree, 'lock_before_grading': True,
            'original_managed_lock': resolved[_relative(original_endpoint).as_posix()],
            'administrative_relocation_only': True, 'actor_terminal_sync_completed': child.get('status') == 'closed',
            'model_calls': 0, 'grading_calls': 0})

    code_lock = host_lock('terminal_code', pair['lock']['terminal_code'], pair['terminal_code'])
    delivery_lock = (host_lock('last_legal_delivery', pair['lock']['last_legal_delivery'], pair['last_legal_delivery'])
                     if pair['last_legal_delivery'] is not None else None)
    audit = candidates.write_new(output/'administrative-closure-audit.json', {
        'version': VERSION, **eligibility, 'original_result': stream_reference(episode/'result.json'),
        'original_controller': stream_reference(controller/'controller-result.json'),
        'managed_boundary': stream_reference(controller/'managed-boundary.json'),
        'archive_verification': stream_reference(output/'archive-verification.json'),
        'original_controller_status': child['status'], 'original_controller_exit_code': result.get('controller_exit_code'),
        'unique_original_candidate_preserved': True, 'candidate_lock': code_lock,
        'delivery_candidate_lock': delivery_lock, 'submitted': delivery_proof['submitted'],
        'original_generation_status_changed': False, 'model_calls_added': 0,
        'candidate_content_changed': False, 'official_scoring_performed': False})
    recovered = {**copy.deepcopy(result), 'status': 'closed', 'candidate_lock': code_lock,
        'recovery_version': VERSION, 'recovery_kind': 'administrative_original_managed_code_artifact_closure',
        'original_result': stream_reference(episode/'result.json'), 'original_status': result['status'],
        'administrative_closure_audit': audit, 'controller_normal_exit_repaired': False,
        'actor_terminal_sync_repaired': False, 'model_calls_added': 0,
        'model_calls': child['ledger']['attempts'], 'ledger': child['ledger'],
        'known_actual_tokens': child['ledger']['known_actual_tokens'],
        'delivery_candidate_lock': delivery_lock, 'delivery_validation': delivery_proof,
        'delivery_evidence': resolved['delivery-evidence.json'],
        'delivery_snapshot': resolved['project-delivery-snapshot.json'],
        'project_baseline_snapshot': baseline_ref,
        'assessment_performed': False, 'original_first_attempt_or_recovery_identity_preserved': True}
    return candidates.write_new(output/'recovered-result.json', recovered)
