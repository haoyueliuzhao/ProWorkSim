"""Explicit one-task CPU recovery of an interrupted, never-qualified image export.

freeze is read-only except for its new plan. register requires a stopped DeepSeek
coordinator and registers a normal reserved preparation worker. run preserves the
original truncated tar and failure reference and never enters a formal episode.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from proworksim import software_benchmark_disk_volumes_v055_r2 as volumes
from proworksim import software_benchmark_native_lazy_v054 as lazy
from proworksim import software_benchmark_queue_v055 as queue
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_network_v055 import direct_environment_command, host_capacity
from proworksim.software_benchmark_native_rootfs_v054 import canonical, digest
from proworksim.storage import atomic_write, json_bytes

ROOT = queue.ROOT
VERSION = 'v055-one-task-truncated-export-recovery-r1'
INSTANCE = 'matplotlib__matplotlib-25122'
CACHE = ROOT / 'runs/software-benchmark-v054/native-lazy-cache'
MAPPING = ROOT / 'runs/software-benchmark-v054/images/actor-admission-r3/instances' / (INSTANCE + '.json')
MAPPING_SHA = 'b770350da573155d40a3455740b95205fb868897cd63156e80d21deb8d3a9dc4'
IMAGE_ID = 'sha256:620e603424132a9f94e0e262abfc980e3c981395feeab85d07ebfe3eb0e791e6'
FAILURE_SHA = 'f39babc6bb10f3c9fc720c7eab920e59fc4aa90a56e149e2cc421fe20cc65cd9'
ENTRY = CACHE / INSTANCE / MAPPING_SHA[:16]
STAGING = ENTRY.parent / (ENTRY.name + '-export-recovery-r1')
OUT = ROOT / 'runs/software-benchmark-v055/partial-export-recovery-r1'
QROOT = ROOT / 'runs/software-benchmark-v055/queue-r1'
QSTATE = QROOT / 'state.json'
OLDSTATE = ROOT / 'runs/software-benchmark-v054/formal-queue-r1/state.json'
HOST = ROOT / 'runs/software-benchmark-v055/native-host-revision-r9/revision.json'
CONTROLLER = 'proworksim-v055-deepseek-six-conditions-native-host-r9.service'
TOOL = ROOT / 'tools/repair_partial_export_v055_r1.py'
CONTROL = ROOT / 'tools/check_partial_export_v055_r1.py'
IDENTITY = hashlib.sha256((INSTANCE + ':' + VERSION).encode()).hexdigest()[:24]
WORKER = QROOT / 'workers' / ('preparation-export-recovery-' + IDENTITY)
UNIT = 'proworksim-v055-preparation-export-recovery-' + IDENTITY + '.service'
LIMITS = {'cpu.max': '400000 100000', 'memory.max': '17179869184', 'pids.max': '16384'}


def read(path):
    return json.loads(Path(path).read_bytes())


def archive_identity(path):
    value = Path(path).lstat()
    if not stat.S_ISREG(value.st_mode):
        raise ValueError('Retained interrupted archive must remain a regular file')
    return {key: getattr(value, 'st_' + key) for key in ('dev', 'ino', 'size', 'mtime_ns')}


def verify_unentered(old, new, slots):
    selected = {}
    for family, state, count in (('v054', old, 3), ('v055', new, 6)):
        rows = [row for row in state['rows'] if row['slot']['instance_id'] == INSTANCE]
        if len(rows) != count:
            raise ValueError('Exact nine original slots are required')
        for row in rows:
            slot = row['slot']
            name = slot['slot_id']
            if (row['generation'].get('status') != 'pending'
                    or set(row['generation']) - {'status', 'attempts'}
                    or row['generation'].get('attempts') or row.get('scores')):
                raise ValueError('An entered or scored slot cannot receive environment recovery')
            claim = ROOT / f'runs/software-benchmark-{family}/episode-claims' / hashlib.sha256(name.encode()).hexdigest()
            if claim.exists() or claim.is_symlink():
                raise ValueError('A formal claim exists; never replay')
            if family == 'v055':
                suffix = digest((name + '-generation').encode())[:24]
                for root in (QROOT, volumes.SECONDARY_ROOT, volumes.TERTIARY_ROOT):
                    candidate = root / 'workers' / ('generation-' + suffix)
                    if candidate.exists() or candidate.is_symlink():
                        raise ValueError('An existing generation directory is not an unentered slot')
            selected[name] = slot
    if slots is not None and selected != slots:
        raise ValueError('Frozen original task/seed/condition identity changed')
    return selected


def validate_original(plan, *, initial_layout=True):
    if (reference(MAPPING) != plan['baseline_mapping'] or plan['baseline_mapping']['sha256'] != MAPPING_SHA
            or read(MAPPING)['actor_image_id'] != IMAGE_ID
            or reference(ENTRY / 'preparation-failure.json') != plan['original_failure']
            or plan['original_failure']['sha256'] != FAILURE_SHA
            or archive_identity(ENTRY / 'rootfs.tar') != plan['original_partial_archive']):
        raise ValueError('Original task/image/failure/retained archive identity changed')
    if initial_layout and {p.name for p in ENTRY.iterdir()} != {'rootfs.tar', 'preparation-failure.json'}:
        raise ValueError('Recovery requires exactly the original interrupted export, never another partial retry')
    if initial_layout and (STAGING.exists() or STAGING.is_symlink()):
        raise ValueError('A previous recovery staging directory exists; no automatic retry')


def load_plan(ref):
    plan = queue.load(ref)
    if (plan.get('version') != VERSION or plan.get('instance_id') != INSTANCE
            or plan.get('cache_entry') != str(ENTRY) or plan.get('staging_directory') != str(STAGING)
            or plan.get('worker_directory') != str(WORKER) or plan.get('controller_unit') != CONTROLLER
            or plan.get('worker_unit') != UNIT or plan.get('actor_image_id') != IMAGE_ID
            or plan.get('kernel_limits') != LIMITS or plan.get('model_calls_authorized') != 0
            or plan.get('formal_claims_authorized') != 0 or plan.get('original_failure_preserved') is not True):
        raise ValueError('Unknown one-task recovery plan')
    for item in plan['sources']:
        checked(item)
    for key in ('host_revision', 'public_tasks', 'baseline_mapping', 'original_failure', 'original_prewarm_failure'):
        checked(plan[key])
    return plan


def freeze():
    old, new = read(OLDSTATE), read(QSTATE)
    host = reference(HOST)
    if new['active_host_revision'] != host:
        raise ValueError('The reviewed r9 host is not the active configuration')
    policy = read(ROOT / 'runs/software-benchmark-v054/native-prewarm-r4/policy.json')
    value = {'version': VERSION, 'created_utc': queue.now(), 'instance_id': INSTANCE,
        'cache_entry': str(ENTRY), 'staging_directory': str(STAGING), 'worker_directory': str(WORKER),
        'controller_unit': CONTROLLER, 'worker_unit': UNIT, 'host_revision': host,
        'baseline_mapping': reference(MAPPING), 'actor_image_id': IMAGE_ID,
        'original_failure': reference(ENTRY / 'preparation-failure.json'),
        'original_partial_archive': archive_identity(ENTRY / 'rootfs.tar'),
        'original_prewarm_failure': reference(ROOT / 'runs/software-benchmark-v054/native-prewarm-r4/events/00000299.json'),
        'original_partial_archive_hashed': False, 'original_partial_archive_reused_as_complete': False,
        'slots': verify_unentered(old, new, None), 'original_deepseek_preparation': new['preparation'][INSTANCE],
        'public_tasks': policy['public_tasks'], 'stdlib': policy['stdlib'], 'docker_socket': policy['docker_socket'],
        'queue_plan': new['plan'], 'kernel_limits': LIMITS, 'runtime_max_seconds': 3660,
        'model_calls_authorized': 0, 'formal_claims_authorized': 0, 'hidden_grader_calls_authorized': 0,
        'original_failure_preserved': True, 'original_queue_exceptions_preserved': True,
        'additional_export_count': 1, 'source_image_downloads': 0, 'automatic_retry': False,
        'disk_reservation_bytes': volumes.POLICY['cold_preparation_reservation_bytes'],
        'sources': [reference(p) for p in (TOOL, CONTROL, Path(lazy.__file__),
            ROOT / 'src/proworksim/software_benchmark_native_rootfs_v054.py',
            Path(volumes.__file__), Path(queue.__file__))]}
    validate_original(value)
    OUT.mkdir(parents=True, exist_ok=False)
    result = write_new(OUT / 'plan.json', value)
    load_plan(result)
    return result


def stopped_controller():
    result = subprocess.run(['systemctl', '--user', 'show', CONTROLLER, '--property=ActiveState,MainPID,KillMode'],
        check=True, capture_output=True, text=True, timeout=15)
    value = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if value.get('ActiveState') not in {'inactive', 'failed'} or value.get('MainPID') != '0' or value.get('KillMode') != 'process':
        raise ValueError('Only the stopped process-only coordinator may be adopted; workers stay running')
    return value


def recovery_state(state, plan, plan_ref, job_ref, gate, proof_ref):
    """Pure, narrow state adoption; keep every row, exception and financial gate."""
    if state.get('dispatch_stopped') or state.get('budget', {}).get('halted'):
        raise ValueError('Environment recovery cannot bypass a financial or dispatch stop')
    if state.get('status') not in {'running', 'primary_finished_with_deferred_environment'}:
        raise ValueError('Only running or fully evidenced deferred-environment completion can resume')
    if state.get('active_host_revision') != plan['host_revision'] or state['plan'] != plan['queue_plan']:
        raise ValueError('Host or experiment plan changed')
    if state['preparation'][INSTANCE] != plan['original_deepseek_preparation']:
        raise ValueError('Failed environment record changed before explicit adoption')
    if state.get('status') == 'primary_finished_with_deferred_environment':
        pending = [row for row in state['rows'] if row['generation']['status'] == 'pending']
        active = any(row['generation']['status'] in {'running', 'intent'} or any(
            x['status'] in {'pending', 'running', 'intent'} for x in row['scores']) for row in state['rows'])
        if (len(pending) != 6 or any(row['slot']['instance_id'] != INSTANCE or row.get('environment_status') != 'failed'
                for row in pending) or active or any(r.get('worker', {}).get('status') == 'running'
                    for r in state['preparation'].values())):
            raise ValueError('Terminal state is not exactly the six never-entered environment slots')
    result = deepcopy(state)
    record = result['preparation'][INSTANCE]
    record['readiness'] = {'status': 'preparing', 'instance_id': INSTANCE,
        'reason': 'explicit_zero_model_partial_export_recovery', 'recovery_plan': plan_ref}
    record['worker'] = {'status': 'running', 'job': job_ref, 'unit': UNIT, 'directory': str(WORKER), 'dispatched_utc': queue.now()}
    record['disk_reservation'] = {'host_revision': plan['host_revision'], **gate, 'recovery_plan': plan_ref}
    record['explicit_recovery'] = proof_ref
    result.setdefault('explicit_environment_recoveries', []).append(proof_ref)
    if result['status'] == 'primary_finished_with_deferred_environment':
        result['status'] = 'running'
        result.pop('ended_utc', None)  # Exact former value is retained in immutable registration receipt.
    result['updated_utc'] = queue.now()
    assert result['rows'] == state['rows'] and result['exceptions'] == state['exceptions']
    assert result.get('budget') == state.get('budget') and result['dispatch_stopped'] == state['dispatch_stopped']
    return result


def register(plan_ref):
    plan = load_plan(plan_ref)
    stopped = stopped_controller()
    with (QROOT / 'coordinator.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        volumes.configure(queue.load(plan['host_revision'])['volume_manifest'])
        with volumes.disk_dispatch_lock():
            old, state = read(OLDSTATE), read(QSTATE)
            verify_unentered(old, state, plan['slots'])
            validate_original(plan)
            if WORKER.exists() or (OUT / 'registration.json').exists():
                raise ValueError('Registration already has an intent; never automatically repeat')
            capacity = host_capacity()
            if not capacity['admit'] or sum(r.get('worker', {}).get('status') == 'running'
                    for r in state['preparation'].values()) >= 2:
                raise ValueError('CPU/RAM or existing two-preparer bound does not admit recovery')
            snapshot = volumes.shared_disk_snapshot(v055_state=state, v054_state=old, target_volume='primary')
            if snapshot.get('metadata_error'):
                raise ValueError('Shared disk snapshot is not trustworthy')
            gate = volumes.admission(snapshot['free_bytes'], snapshot['active_peak_reserved_bytes'],
                plan['disk_reservation_bytes'], kind='preparation')
            if not gate['admitted']:
                raise ValueError('Original shared 128GiB preparation reservation/floor rejects recovery')
            # Validate the pure adoption before creating any durable execution intent.
            recovery_state(state, plan, plan_ref, {}, gate, {})
            WORKER.mkdir(parents=False, exist_ok=False)
            request = write_new(WORKER / 'request.json', {'instance_id': INSTANCE, 'baseline_mapping': plan['baseline_mapping'],
                'cache_root': str(CACHE), 'stdlib': plan['stdlib'], 'public_tasks': plan['public_tasks'],
                'docker_socket': plan['docker_socket'], 'output': str(WORKER), 'recovery_plan': plan_ref,
                'model_calls_authorized': 0, 'formal_claims_authorized': 0})
            argv = [str(ROOT / '.venv/bin/python'), '-B', str(TOOL), 'run', '--request', request['path'], '--sha256', request['sha256']]
            job = write_new(WORKER / 'job.json', {'version': queue.VERSION, 'kind': 'preparation',
                'instance_id': INSTANCE, 'plan': plan['queue_plan'], 'directory': str(WORKER), 'unit': UNIT,
                'argv': direct_environment_command(argv), 'timeout_seconds': 3600})
            before = write_new(OUT / 'state-before-registration.json', QSTATE.read_bytes())
            proof = write_new(OUT / 'registration.json', {'version': VERSION, 'utc': queue.now(),
                'plan': plan_ref, 'state_before': before, 'controller': stopped, 'job': job,
                'disk_admission': gate, 'host_capacity': capacity, 'previous_status': state['status'],
                'previous_ended_utc': state.get('ended_utc'), 'prior_preparation': state['preparation'][INSTANCE],
                'original_rows_sha256': digest(canonical(state['rows'])),
                'original_exceptions_sha256': digest(canonical(state['exceptions'])),
                'model_calls': 0, 'formal_claims': 0, 'worker_processes_signalled': False,
                'financial_gate_changed': False, 'original_failure_preserved': True})
            updated = recovery_state(state, plan, plan_ref, job, gate, proof)
            atomic_write(QSTATE, json_bytes(updated))
            command = ['systemd-run', '--user', '--quiet', '--unit=' + UNIT,
                '--property=Restart=no', '--property=KillMode=control-group', '--property=CPUQuota=400%',
                '--property=MemoryMax=17179869184', '--property=TasksMax=16384',
                '--property=TimeoutStopSec=40', '--property=RuntimeMaxSec=3660',
                '--property=WorkingDirectory=' + str(ROOT), '--setenv=PYTHONPATH=' + str(ROOT / 'src'),
                '--', str(ROOT / '.venv/bin/python'), '-B', '-m', 'proworksim.software_benchmark_queue_v055',
                'worker', '--job', job['path'], '--sha256', job['sha256']]
            try:
                result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
                launch = {'returncode': result.returncode, 'launch_confirmed': True}
            except Exception as error:
                launch = {'launch_confirmed': False, 'error_type': type(error).__name__, 'error': str(error),
                    'automatic_retry': False, 'reason': 'durable_worker_intent_retained_for_normal_collection'}
            return write_new(OUT / 'launch.json', {'version': VERSION, 'utc': queue.now(), 'job': job, **launch})


def kernel_limits():
    entry = next(line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))
    if Path(entry).name != UNIT:
        raise ValueError('Recovery must run in its exact bounded preparation unit')
    root = Path('/sys/fs/cgroup') / entry.lstrip('/')
    observed = {key: (root / key).read_text().strip() for key in LIMITS}
    if observed != LIMITS:
        raise ValueError('Preparation CPU/memory/PID hard limits are absent')
    return {'path': str(root), 'observed': observed}


def publish_export(environment, mapping, stage, destination):
    """Publish same bytes with canonical metadata; qualified receipt comes last."""
    stage, destination = Path(stage), Path(destination)
    manifest_path = stage / 'rootfs-manifest.json'
    manifest = read(manifest_path)
    if (manifest['prepared_root'] != str(stage / 'rootfs') or manifest['image_id'] != IMAGE_ID
            or manifest['instance_id'] != INSTANCE or manifest['baseline_mapping'] != mapping
            or manifest['source_environment_sha256'] != digest(canonical(environment))
            or manifest.get('numeric_ownership_equivalence_admitted') is not True
            or manifest.get('native_real_task_control_passed') is not False):
        raise ValueError('Staged export lacks exact image/mapping/environment/ownership evidence')
    for name in ('rootfs', 'rootfs-manifest.json', 'public-environment.json', 'environment.json', 'lazy-preparation.json'):
        if (destination / name).exists() or (destination / name).is_symlink():
            raise ValueError('Canonical target already exists; no overwrite or automatic retry')
    original = reference(manifest_path)
    (stage / 'rootfs').rename(destination / 'rootfs')
    manifest['prepared_root'] = str(destination / 'rootfs')
    manifest['explicit_export_publication'] = {'staging_manifest': original,
        'new_payload_export': True, 'payload_bytes_changed_on_publication': False,
        'publication_version': VERSION}
    target_manifest = write_new(destination / 'rootfs-manifest.json', canonical(manifest))
    public = read(stage / 'public-environment.json')
    public.update(rootfs_manifest=target_manifest['path'], rootfs_manifest_sha256=target_manifest['sha256'])
    write_new(destination / 'public-environment.json', canonical(public))
    write_new(destination / 'environment.json', canonical(environment))
    return {'staging_manifest': original, 'canonical_manifest_path': target_manifest['path'],
        'initial_publication_sha256': target_manifest['sha256'],
        'canonical_manifest_will_be_finalized_after_initialization': True}


def qualify_and_publish(environment, plan, inherited):
    qualification = lazy.qualify_instance(environment, ENTRY, plan['stdlib'], inherited)
    manifest_path = ENTRY / 'rootfs-manifest.json'
    manifest = read(manifest_path)
    write_new(ENTRY / 'rootfs-manifest-before-initialization.json', manifest_path.read_bytes())
    manifest.update(native_real_task_control_passed=True, native_control_receipt=qualification,
        qualification_scope='per_instance_public_runtime_plus_shared_mechanism')
    atomic_write(manifest_path, canonical(manifest))
    public_path = ENTRY / 'public-environment.json'
    public = read(public_path)
    public['rootfs_manifest_sha256'] = reference(manifest_path)['sha256']
    atomic_write(public_path, canonical(public))
    receipt = {'version': 'v054-lazy-native-preparation-v1', 'status': 'qualified',
        'baseline_mapping': plan['baseline_mapping'], 'slot_claimed': False, 'model_calls': 0,
        'rootfs_environment': reference(public_path), 'rootfs_manifest': reference(manifest_path),
        'environment': reference(ENTRY / 'environment.json'), 'qualification': qualification}
    return receipt


def run(request_ref):
    request = queue.load(request_ref)
    plan_ref = request['recovery_plan']
    plan = load_plan(plan_ref)
    if (request_ref != reference(WORKER / 'request.json') or request['instance_id'] != INSTANCE
            or request['cache_root'] != str(CACHE) or request['baseline_mapping'] != plan['baseline_mapping']):
        raise ValueError('Worker request differs from the sole explicit recovery')
    result = {'version': VERSION, 'instance_id': INSTANCE, 'request': request_ref, 'recovery_plan': plan_ref,
        'started_utc': queue.now(), 'model_calls': 0, 'formal_claims': 0, 'grader_calls': 0,
        'original_failure_preserved': True, 'automatic_retry': False}
    try:
        result['kernel_limits'] = kernel_limits()
        registration = read(OUT / 'registration.json')
        if registration['plan'] != plan_ref or registration['job'] != reference(WORKER / 'job.json'):
            raise ValueError('Worker lacks its immutable explicit registration')
        with (CACHE / 'locks' / (INSTANCE + '.lock')).open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            old, state = read(OLDSTATE), read(QSTATE)
            verify_unentered(old, state, plan['slots'])
            if state['preparation'][INSTANCE]['worker']['job'] != registration['job']:
                raise ValueError('Shared queue does not reserve this exact CPU worker')
            validate_original(plan)
            volumes.configure(queue.load(plan['host_revision'])['volume_manifest'])
            with volumes.disk_dispatch_lock():
                snapshot = volumes.shared_disk_snapshot(target_volume='primary')
                gate = volumes.admission(snapshot['free_bytes'], snapshot['active_peak_reserved_bytes'], 0, kind='preparation')
                if snapshot.get('metadata_error') or not gate['admitted']:
                    raise ValueError('Reserved CPU worker no longer meets the shared disk floor')
                result['reserved_disk_recheck'] = gate
            rows = queue.load(plan['public_tasks'])
            task = next(row for row in rows if row['instance_id'] == INSTANCE)
            environment, mapping = lazy.environment_from_mapping(task, plan['baseline_mapping'])
            inherited = lazy._mechanism()
            # Fresh, full local export. The old truncated tar is neither read nor removed.
            lazy.prepare_rootfs(environment=environment, controller=lazy.ActorDocker(plan['docker_socket']),
                config_blob=mapping['actor_config_blob'], destination=STAGING, preserve_numeric_ownership=True)
            result['published_export'] = publish_export(environment, plan['baseline_mapping'], STAGING, ENTRY)
            receipt = qualify_and_publish(environment, plan, inherited)
            validate_original(plan, initial_layout=False)
            result['qualification'] = receipt['qualification']
            result['lazy_preparation'] = write_new(ENTRY / 'lazy-preparation.json', canonical(receipt))
            result.update(status='qualified', reused=False, additional_exports=1,
                prepared={key: receipt[key]['path'] for key in lazy_reference_fields()})
    except Exception as error:
        result.update(status='deferred_environment_failure', error={'type': type(error).__name__, 'message': str(error)})
    result['finished_utc'] = queue.now()
    return write_new(WORKER / 'preparation-result.json', result)


def lazy_reference_fields():
    return ('rootfs_environment', 'rootfs_manifest', 'environment', 'qualification')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    sub.add_parser('freeze')
    command = sub.add_parser('register')
    command.add_argument('--plan', required=True, type=Path)
    command.add_argument('--sha256', required=True)
    command = sub.add_parser('run')
    command.add_argument('--request', required=True, type=Path)
    command.add_argument('--sha256', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.operation == 'freeze':
        value = freeze()
    else:
        ref = reference(args.plan if args.operation == 'register' else args.request)
        if ref['sha256'] != args.sha256:
            raise ValueError('Explicit immutable input hash mismatch')
        value = register(ref) if args.operation == 'register' else run(ref)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
