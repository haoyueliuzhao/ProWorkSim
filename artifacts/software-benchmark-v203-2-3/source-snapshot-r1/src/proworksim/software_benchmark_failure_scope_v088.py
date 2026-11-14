"""Keep proved zero-dispatch transport initialization failures within one task.

This is a private episode binding, not a change to a stopped result or to the
shared queue's integrity/money checks. Error text alone never grants isolation.
"""
from __future__ import annotations

import json

from . import software_benchmark_episode_v066 as original
from .software_benchmark_candidates_v054 import checked

VERSION = 'v088-proved-local-model-transport-initialization-scope-r1'
FAULT = 'trusted_model_bridge_initialization_failed'
COUNTERS = ('requests', 'failed_requests', 'count_requests', 'generation_requests',
            'predispatch_admission_replies', 'automatic_retries')
LOCAL_ERRORS = {
    ('ValueError', 'filedescriptor out of range in select()'),
    ('TimeoutError', 'Docker native RPC deadline exceeded'),
    ('TimeoutError', 'Model FIFO response exceeded the original request deadline'),
    ('TimeoutError', 'Model FIFO write deadline exceeded'),
    ('EOFError', 'Model FIFO bridge closed before a complete response'),
    ('EOFError', 'Model FIFO write made no progress'),
    ('OSError', '[Errno 9] Bad file descriptor'),
    ('OSError', '[Errno 23] Too many open files in system'),
    ('OSError', '[Errno 24] Too many open files'),
    ('BrokenPipeError', '[Errno 32] Broken pipe'),
    ('ConnectionResetError', '[Errno 104] Connection reset by peer'),
}
# No controller/ledger/returned candidate exists at this particular zero-dispatch
# boundary. Unknown new result fields require review rather than being ignored.
INITIALIZATION_KEYS = {
    'version', 'status', 'source_slot_id', 'slot_id', 'measurement_kind',
    'execution_arm', 'replicate', 'arm', 'model_key', 'group_id', 'configuration',
    'condition_id', 'instance_id', 'seed', 'automatic_replay', 'capacity_admission',
    'candidate_lock', 'model_calls', 'model_dispatch_started', 'shared_integrity_fault',
    'error', 'traceback', 'lifecycle_deadline_reached', 'model_bridge_thread_finished',
    'model_transport', 'final_writer_quiescence', 'failure_controller_output_transfer',
    'interrupted_worktree', 'quiescence', 'retained_objects', 'failure_scope',
    'batch_stop_required', 'local_failure_classification',
}


def _read(ref):
    path = checked(ref)
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError('Original evidence must be a complete JSON object')
    return path, value


def local_initialization_evidence(result, cleanup):
    """Return an audit record only for the exact clean, unentered host boundary.

    Any missing evidence, later model work, protocol/content violation, different
    actor identity, retention error or unproved cleanup fails closed. Receipts
    are host-owned immutable files; model/issue text is never inspected.
    """
    if (set(result)-INITIALIZATION_KEYS or result.get('version') != original.VERSION
            or result.get('model_key') != 'DEEPSEEK' or result.get('status') != 'technical_unknown'
            or result.get('shared_integrity_fault') != FAULT
            or type(result.get('model_calls')) is not int or result['model_calls'] != 0
            or result.get('model_dispatch_started') is not False
            or result.get('model_bridge_thread_finished') is not True
            or result.get('lifecycle_deadline_reached') is not False
            or result.get('automatic_replay') is not False or result.get('candidate_lock') is not None
            or result.get('retained_objects') != []
            or result.get('error') != {'type': 'RuntimeError',
                                     'message': 'Trusted model FIFO bridge did not initialize'}):
        return None
    try:
        quiet_path, quiet = _read(result['quiescence'])
        folder = quiet_path.parent
        if (quiet_path.name != 'quiescence.json' or not folder.name.isdecimal()
                or folder.parent.name != 'episodes' or quiet != cleanup
                or quiet.get('version') != 'v066-owned-private-docker-actor-pair-r1'
                or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
                or quiet.get('create_result_unknown') is not False
                or quiet.get('create_result_unknown_roles') != []
                or quiet.get('retained_objects') != [] or quiet.get('all_owned_objects_removed') is not True
                or quiet.get('unrelated_objects_touched') is not False
                or sorted(quiet.get('removed_roles', [])) != ['actor', 'controller', 'volume']
                or set(quiet.get('claims', {})) != {'actor', 'controller', 'volume'}):
            return None
        claims = quiet['claims']
        for role, ref in claims.items():
            path, claim = _read(ref)
            spec = claim.get('spec', {})
            if (path != folder.parent.parent/'resource-claims'/f'{role}-{folder.name}.json'
                    or claim.get('key') != f'{role}-{folder.name}'
                    or spec.get('role') != role or spec.get('slot_id') != result['slot_id']
                    or spec.get('instance_id') != result['instance_id']
                    or (role != 'actor' and claim.get('parent_actor_key') != f'actor-{folder.name}')):
                return None
        transport_path, transport = _read(result['model_transport'])
        if (transport_path != folder/'model-transport.json'
                or transport.get('version') != 'v064-controller-model-fifo-r1'
                or transport.get('status') != 'technical_unknown' or transport.get('ready') is not False
                or any(type(transport.get(key)) is not int or transport[key] != 0 for key in COUNTERS)
                or transport.get('model_key_sent_to_container') is not False
                or transport.get('host_listener') is not False
                or set(transport.get('error', {})) != {'type', 'message'}
                or (transport['error']['type'], transport['error']['message']) not in LOCAL_ERRORS):
            return None
        writer_path, writers = _read(result['final_writer_quiescence'])
        if (writer_path != folder/'final-writer-quiescence.json'
                or writers.get('all_quiet') is not True or writers.get('errors') != []
                or writers.get('create_result_unknown_roles') != []
                or len(writers.get('writers', [])) != 2
                or {writer.get('role') for writer in writers['writers']} != {'actor', 'controller'}):
            return None
        for writer in writers['writers']:
            state = writer.get('state', {})
            if (writer.get('claim') != claims[writer['role']]
                    or state.get('Running') is not False or state.get('Pid') != 0
                    or state.get('Paused') is not False or state.get('Restarting') is not False
                    or state.get('Status') not in {'exited', 'dead'}
                    or not isinstance(writer.get('container_id'), str)
                    or len(writer['container_id']) != 64
                    or any(c not in '0123456789abcdef' for c in writer['container_id'])):
                return None
        return {'version': VERSION, 'scope': 'local', 'category': 'zero_dispatch_transport_initialization',
            'slot_id': result['slot_id'], 'original_shared_fault_marker': FAULT,
            'model_transport': result['model_transport'], 'quiescence': result['quiescence'],
            'writer_quiescence': result['final_writer_quiescence'], 'claims': claims,
            'trusted_host_error': transport['error'], 'model_dispatch_observed': False,
            'automatic_retry': False, 'ledger_records_changed': False,
            'cash_amount_inferred_as_zero': False, 'old_results_reclassified': False}
    except (KeyError, TypeError, ValueError, OSError):
        return None


def classify_failure_scope(result, cleanup):
    evidence = local_initialization_evidence(result, cleanup)
    if evidence is not None:
        if result.get('local_failure_classification', evidence) != evidence:
            return 'global'
        result['local_failure_classification'] = evidence
        return 'local'
    return original.classify_failure_scope(result, cleanup)


def bind_episode(delegate):
    """Apply after IO binding, only to a newly constructed private episode."""
    namespace = delegate.run_episode.__globals__
    if (namespace is vars(original) or namespace.get('_run') is not delegate._run
            or delegate._run.__globals__ is not namespace
            or namespace.get('classify_failure_scope').__code__ is not original.classify_failure_scope.__code__):
        raise ValueError('Expected an untouched private original episode namespace')
    namespace['classify_failure_scope'] = classify_failure_scope
    delegate.__dict__['classify_failure_scope'] = classify_failure_scope
    if delegate._run.__globals__['classify_failure_scope'] is not classify_failure_scope:
        raise RuntimeError('The real private episode classification binding did not change')
    return delegate
