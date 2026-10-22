"""One-shot, explicitly sealed recovery of the legacy REF ready-schema failure.

This tool retires only the completed, attested GPU7 REF service. It never loads
an MP model, claims an episode, edits ready.json, or changes the frozen reader.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

from proworksim import software_benchmark_ref_handoff_pool_v054_r1 as handoff
from proworksim import software_benchmark_resident_session_v054 as session
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_supervision_v054 import process_identity
from proworksim.storage import atomic_write, json_bytes

ROOT = handoff.ROOT
VERSION = 'v054-ref-retirement-unit-identity-recovery-r2'
OUT = ROOT / 'runs/software-benchmark-v054/ref-handoff-identity-recovery-r2'
POOL_ROOT = ROOT / 'runs/software-benchmark-v054/dynamic-pool-r4'
STATE = POOL_ROOT / 'provisioner-state.json'
OVERLAY = ROOT / 'runs/software-benchmark-v054/ref-generation-handoff-r1/overlay.json'
MONITOR = 'proworksim-v054-dynamic-pool-ref-handoff-r1.service'
REF_UNIT = 'proworksim-v054-resident-ref-r2.service'
GPU_UUID = 'GPU-39eb51c7-179a-1aa6-0735-2e33652bb7b8'
OLD_INTENT = POOL_ROOT / 'ref-to-mp-generation-terminal-r1/intent.json'
OLD_INTENT_SHA = '6c48e3145340a75d980112855d2b93c1f0d43b4ecf4d9583f4cad2ffdacad04c'
TOOL = ROOT / 'tools/repair_ref_handoff_identity_v054_r2.py'
CONTROL = ROOT / 'tools/check_ref_handoff_identity_v054_r2.py'


def read(path):
    return json.loads(Path(path).read_bytes())


def content_sha(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def normalized_owner(ready, unit_state, declaration):
    """The attested unit observation owns InvocationID/cgroup, not legacy ready."""
    unit = declaration['unit']
    process = ready['host_process']
    invocation, group = unit_state.get('InvocationID'), unit_state.get('ControlGroup')
    if (unit != REF_UNIT or declaration.get('mode') != 'REF' or declaration.get('gpu_index') != 7
            or declaration.get('gpu_uuid') != GPU_UUID or ready.get('gpu_uuid') != GPU_UUID
            or ready.get('gpu_index') != 7 or ready.get('ready') is not True
            or ready.get('resident') is not True or ready.get('gpu_lease_held') is not True
            or ready.get('endpoint_lease_held') is not True
            or type(process.get('pid')) is not int or process['pid'] <= 1
            or type(process.get('start_ticks')) is not int or process['start_ticks'] <= 0
            or not isinstance(invocation, str) or re.fullmatch(r'[a-f0-9]{32}', invocation) is None
            or not isinstance(group, str) or not group.startswith('/user.slice/')
            or not group.endswith('/' + unit) or '..' in group.split('/')
            or unit_state.get('ActiveState') != 'active' or unit_state.get('MainPID') != str(process['pid'])):
        raise ValueError('The observed unit does not attest the exact original GPU7 REF process')
    for key, value in (('invocation_id', invocation), ('cgroup', group)):
        if key in ready and ready[key] != value:
            raise ValueError('An optional ready identity field disagrees with the attested unit')
    return {'unit': unit, 'invocation_id': invocation, 'cgroup': group, 'host_process': process,
        'gpu_uuid': GPU_UUID, 'gpu_index': 7,
        'identity_source': 'admitted_resident.unit_state_plus_ready.host_process',
        'legacy_ready_modified': False}


def verify_fresh_owner(owner, state, process):
    if (state.get('ActiveState') != 'active' or state.get('InvocationID') != owner['invocation_id']
            or state.get('ControlGroup') != owner['cgroup']
            or state.get('MainPID') != str(owner['host_process']['pid']) or process != owner['host_process']):
        raise ValueError('The exact REF service/process changed before the one-time stop')


def validate_failed_conversion(conversion, overlay_ref, intent_ref):
    if (conversion.get('status') != 'failed_manual_action_required'
            or conversion.get('error') != "KeyError('invocation_id')"
            or conversion.get('automatic_retry') is not False
            or conversion.get('previous') != {'status': 'retirement_intent', 'intent': intent_ref,
                'resource_retirement_overlay': overlay_ref}):
        raise ValueError('Only the exact preserved pre-stop ready-schema failure is recoverable here')


def load_plan(ref):
    plan = handoff.pool.read_ref(ref)
    if (plan.get('version') != VERSION or plan.get('output') != str(OUT)
            or plan.get('monitor_unit') != MONITOR or plan.get('ref_unit') != REF_UNIT
            or plan.get('gpu_uuid') != GPU_UUID or plan.get('pool_state') != str(STATE)
            or plan.get('model_loads_authorized') != 0 or plan.get('model_calls_authorized') != 0
            or plan.get('formal_claims_authorized') != 0 or plan.get('unchanged_retirement_rule') != handoff.VERSION
            or plan.get('original_ready_modified') is not False):
        raise ValueError('Unknown one-shot REF retirement recovery plan')
    for item in plan['sources']:
        checked(item)
    for name in ('prior_failure', 'old_intent', 'registration', 'declaration', 'ready', 'overlay'):
        checked(plan[name])
    handoff.validate_overlay(plan['overlay'], initial=True)
    if plan['old_intent']['sha256'] != OLD_INTENT_SHA:
        raise ValueError('Original failed intent changed')
    prior = handoff.pool.read_ref(plan['prior_failure'])
    validate_failed_conversion(prior['conversion'], plan['overlay'], plan['old_intent'])
    return plan


def freeze():
    state = read(STATE)
    overlay_ref, intent_ref = reference(OVERLAY), reference(OLD_INTENT)
    overlay = handoff.validate_overlay(overlay_ref, initial=True)
    validate_failed_conversion(state['conversion'], overlay_ref, intent_ref)
    if intent_ref['sha256'] != OLD_INTENT_SHA or GPU_UUID in state['devices']:
        raise ValueError('An unknown intent or an existing GPU7 MP attempt cannot be retried')
    intent = handoff.pool.read_ref(intent_ref)
    registration = handoff.pool.read_ref(intent['registration'])
    declaration = handoff.pool.read_ref(registration['declaration'])
    ready = handoff.pool.read_ref(intent['ready'])
    owner = normalized_owner(ready, intent['unit_state'], declaration)
    OUT.mkdir(parents=True, exist_ok=False)
    prior = write_new(OUT / 'prior-failure.json', {'version': VERSION, 'captured_utc': handoff.pool.now(),
        'conversion': state['conversion'], 'conversion_sha256': content_sha(state['conversion']),
        'pool_policy': state['pool_policy'], 'devices_sha256': content_sha(state['devices']),
        'prior_model_stop_attempt_in_this_path': False,
        'basis': 'KeyError at direct ready invocation_id access precedes subprocess stop call'})
    refs = [reference(p) for p in (TOOL, CONTROL, Path(handoff.__file__), Path(handoff.original.__file__),
        Path(handoff.boundary.__file__), Path(handoff.pool.__file__), Path(session.__file__))]
    plan = {'version': VERSION, 'created_utc': handoff.pool.now(), 'output': str(OUT), 'pool_state': str(STATE),
        'monitor_unit': MONITOR, 'ref_unit': REF_UNIT, 'gpu_uuid': GPU_UUID, 'gpu_index': 7,
        'overlay': overlay_ref, 'pool_policy': overlay['target_pool_policy'], 'slots': overlay['slots'],
        'queue_state': overlay['queue_state_path'], 'old_intent': intent_ref, 'prior_failure': prior,
        'registration': intent['registration'], 'declaration': registration['declaration'], 'ready': intent['ready'],
        'expected_owner': owner, 'original_ready_modified': False,
        'unchanged_retirement_rule': handoff.VERSION, 'unchanged_closure_version': handoff.CLOSURE_VERSION,
        'model_loads_authorized': 0, 'model_calls_authorized': 0, 'formal_claims_authorized': 0,
        'automatic_stop_retry': False, 'sources': refs,
        'future_MP_loading': 'Only original monitor/policy after this tool completes, including six-request qualification'}
    result = write_new(OUT / 'plan.json', plan)
    load_plan(result)
    return result


def manager_stopped():
    value = handoff.original.unit_state(MONITOR)
    if value.get('MainPID', '0') != '0' or value.get('ActiveState') not in {'inactive', 'failed', 'missing'}:
        raise ValueError('Stop only the pool monitor before this explicit recovery; model services stay untouched until qualified stop')
    return value


def assert_state_owner(state, plan, plan_ref):
    previous = handoff.pool.read_ref(plan['prior_failure'])
    if (state.get('pool_policy') != plan['pool_policy'] or content_sha(state['devices']) != previous['devices_sha256']
            or GPU_UUID in state['devices']):
        raise ValueError('Existing devices or pool identity changed; never replay their load attempts')
    conversion = state.get('conversion')
    if conversion == previous['conversion']:
        return 'prior_failure'
    if (conversion.get('recovery_plan') != plan_ref or conversion.get('previous_failure') != plan['prior_failure']
            or conversion.get('status') not in {'retirement_recovery_intent', 'ref_retired_waiting_for_mp_capacity'}):
        raise ValueError('Another handoff mutation owns the pool state')
    return conversion['status']


def capture_boundary(plan, *, label):
    current = handoff.read_pool(plan['pool_policy'])
    event = handoff.pool.read_ref(plan['registration'])
    active = current['active'].get(event['resident_id'])
    if active is None or active['event_reference'] != plan['registration']:
        raise ValueError('The exact original REF registration is no longer active')
    observed = session.admitted_resident(plan['declaration'], pool_policy_reference=plan['pool_policy'],
        registration_reference=plan['registration'])
    if observed is None or observed['ready_reference'] != plan['ready']:
        raise ValueError('The original ready receipt no longer attests this live service')
    owner = normalized_owner(observed['ready'], observed['unit_state'], observed['declaration'])
    if owner != plan['expected_owner']:
        raise ValueError('The original REF invocation/process/cgroup changed since the failed intent')
    queue = read(plan['queue_state'])
    slots = handoff.pool.read_ref(plan['slots'])
    evidence = handoff.boundary.ref_generation_evidence(queue, slots)
    if not evidence['eligible']:
        raise ValueError('All original 500 REF generations must remain terminal')
    proof = handoff.boundary.collect_runtime_boundary(queue, slots, observed,
        slots_reference=plan['slots'], queue_state_path=Path(plan['queue_state']))
    if (not all(proof.get(key) is True for key in ('all_ref_generation_quiescent', 'resident_session_idle',
            'all_ref_generation_workers_quiet', 'all_ref_registered_scopes_quiet'))
            or proof.get('resident_inflight') != 0 or proof.get('generation_evidence') != evidence):
        raise ValueError('The fresh complete runtime boundary did not pass')
    number = 1 + len(list(OUT.glob('validation-*')))
    folder = OUT / f'validation-{number:04d}'
    folder.mkdir(exist_ok=False)
    return {'queue_snapshot': write_new(folder / 'queue-state.json', queue),
        'runtime_boundary': write_new(folder / 'runtime-boundary.json', proof),
        'owner': write_new(folder / 'owner-identity.json', owner), 'label': label,
        'resident_status': observed['status'], 'unit_state': observed['unit_state']}


def stop_exact_once(owner, intent_ref):
    """A persisted stop intent is never automatically replayed after ambiguity."""
    receipt = OUT / 'stop-receipt.json'
    if receipt.exists():
        result = read(receipt)
        if result.get('intent') != intent_ref or result.get('returncode') != 0:
            raise ValueError('A prior failed/ambiguous stop requires separate operator review')
        return reference(receipt)
    if (OUT / 'stop-intent.json').exists():
        raise ValueError('Stop intent without receipt: do not repeat stop or invent its return code')
    fresh = handoff.original.unit_state(owner['unit'])
    process = process_identity(owner['host_process']['pid'])
    verify_fresh_owner(owner, fresh, process)
    command = ['systemctl', '--user', 'stop', owner['unit']]
    action = write_new(OUT / 'stop-intent.json', {'version': VERSION, 'utc': handoff.pool.now(),
        'intent': intent_ref, 'owner': owner, 'fresh_unit': fresh, 'fresh_process': process,
        'command': command, 'maximum_stop_calls': 1, 'automatic_retry': False})
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        value = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    except Exception as error:
        value = {'returncode': None, 'error_type': type(error).__name__, 'error': str(error)}
    ref = write_new(receipt, {'version': VERSION, 'utc': handoff.pool.now(), 'intent': intent_ref,
        'stop_intent': action, **value})
    if value['returncode'] != 0:
        raise ValueError('Exact REF stop lacks a successful durable return code; no retirement event')
    return ref


def observe_stopped(owner):
    state = handoff.original.unit_state(owner['unit'])
    group = Path('/sys/fs/cgroup' + owner['cgroup'])
    populated = any(path.read_text().strip() for path in group.rglob('cgroup.procs')) if group.exists() else False
    try:
        gone = process_identity(owner['host_process']['pid']) != owner['host_process']
    except (FileNotFoundError, ProcessLookupError):
        gone = True
    if (state.get('MainPID', '0') != '0' or state.get('ActiveState') not in {'inactive', 'failed', 'missing'}
            or populated or not gone):
        raise ValueError('Old REF unit, exact launcher and full cgroup are not all quiet')
    return {'post_stop_unit': state, 'old_unit_stopped': True, 'old_cgroup_empty': True, 'old_launcher_gone': True}


def retire_once(plan, closure_ref):
    """Recover an already appended exact event, never append a duplicate."""
    current = handoff.read_pool(plan['pool_policy'])
    for event_ref in current['events']:
        event = handoff.pool.read_ref(event_ref)
        if event['event'] == 'retire' and event.get('registration') == plan['registration']:
            if event.get('closure') != closure_ref or event.get('retirement_rule') != handoff.VERSION:
                raise ValueError('A different retirement already owns this registration')
            return event_ref
    registration = handoff.pool.read_ref(plan['registration'])
    return handoff.append_retirement(plan['overlay'], {'resident_id': registration['resident_id'],
        'registration': plan['registration'], 'closure': closure_ref})


def adopt_state(state, plan, plan_ref, intent_ref, *, closure_ref=None, retirement_ref=None):
    assert_state_owner(state, plan, plan_ref)
    result = deepcopy(state)
    value = {'status': 'retirement_recovery_intent', 'intent': intent_ref,
        'resource_retirement_overlay': plan['overlay'], 'recovery_plan': plan_ref,
        'previous_failure': plan['prior_failure'], 'previous_failed_conversion_sha256':
            handoff.pool.read_ref(plan['prior_failure'])['conversion_sha256']}
    if closure_ref is not None:
        if retirement_ref is None:
            raise ValueError('Completed retirement needs its exact appended event')
        value.update(status='ref_retired_waiting_for_mp_capacity', closure=closure_ref, retirement=retirement_ref)
    result['conversion'] = value
    result['updated_utc'] = handoff.pool.now()
    assert result['devices'] == state['devices']
    assert result['formal_slots_claimed'] == state['formal_slots_claimed']
    assert result['automatically_replayed_formal_episodes'] == state['automatically_replayed_formal_episodes']
    return result


def execute(plan_ref):
    plan = load_plan(plan_ref)
    manager_stopped()
    handoff.install(plan['overlay'])
    with (POOL_ROOT / 'provisioner.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = read(STATE)
        stage = assert_state_owner(state, plan, plan_ref)
        completed = OUT / 'completed.json'
        if completed.exists():
            value = read(completed)
            if stage != 'ref_retired_waiting_for_mp_capacity' or value['plan'] != plan_ref:
                raise ValueError('Completed recovery no longer matches the pool state')
            retire_once(plan, value['closure'])
            return reference(completed)
        intent_path = OUT / 'retirement-intent.json'
        if not intent_path.exists():
            captured = capture_boundary(plan, label='initial_explicit_recovery')
            write_new(OUT / 'state-before-recovery.json', STATE.read_bytes())
            intent_ref = write_new(intent_path, {'version': handoff.VERSION, 'created_utc': handoff.pool.now(),
                'overlay': plan['overlay'], 'registration': plan['registration'], **captured,
                'ready': plan['ready'], 'same_gpu_uuid': GPU_UUID, 'score_completion_required': False,
                'operational_recovery': plan_ref, 'previous_failed_intent': plan['old_intent']})
        else:
            intent_ref = reference(intent_path)
            # If the previous invocation stopped before its stop intent, recheck
            # current quietness. This is evidence only, never a repeated stop.
            if not (OUT / 'stop-intent.json').exists():
                capture_boundary(plan, label='explicit_resume_before_any_stop_intent')
        intent = handoff.pool.read_ref(intent_ref)
        if (intent.get('operational_recovery') != plan_ref or intent['overlay'] != plan['overlay']
                or intent['registration'] != plan['registration'] or intent['ready'] != plan['ready']):
            raise ValueError('Recovery intent differs from its exact sealed plan')
        if stage != 'ref_retired_waiting_for_mp_capacity':
            atomic_write(STATE, json_bytes(adopt_state(state, plan, plan_ref, intent_ref)))
        owner = handoff.pool.read_ref(intent['owner'])
        if owner != plan['expected_owner']:
            raise ValueError('Fresh retirement intent changed the original service identity')
        stop_ref = stop_exact_once(owner, intent_ref)
        closure_path = OUT / 'closure.json'
        if closure_path.exists():
            closure_ref = reference(closure_path)
            closure = handoff.pool.read_ref(closure_ref)
            if closure.get('operational_recovery') != plan_ref or closure.get('stop_receipt') != stop_ref:
                raise ValueError('Existing closure is not this completed stop')
        else:
            quiet = observe_stopped(owner)
            closure_ref = write_new(closure_path, {'version': handoff.CLOSURE_VERSION,
                'overlay': plan['overlay'], 'registration': plan['registration'], 'intent': intent_ref,
                'queue_snapshot': intent['queue_snapshot'], 'runtime_boundary': intent['runtime_boundary'],
                'resource_retirement_only': True, 'score_completion_required': False,
                'historical_results_and_unknown_costs_preserved': True, 'formal_episodes_replayed': 0,
                'resident_session_idle': True, **quiet, 'stop_returncode': 0,
                'created_utc': handoff.pool.now(), 'different_user_processes_stopped': 0,
                'operational_recovery': plan_ref, 'previous_failure': plan['prior_failure'],
                'validated_unit_identity': intent['owner'], 'stop_receipt': stop_ref})
        retirement = retire_once(plan, closure_ref)
        current_state = read(STATE)
        atomic_write(STATE, json_bytes(adopt_state(current_state, plan, plan_ref, intent_ref,
            closure_ref=closure_ref, retirement_ref=retirement)))
        return write_new(completed, {'version': VERSION, 'completed_utc': handoff.pool.now(), 'plan': plan_ref,
            'closure': closure_ref, 'retirement': retirement, 'previous_failure': plan['prior_failure'],
            'state_conversion': 'ref_retired_waiting_for_mp_capacity', 'retired_resident_count': 1,
            'model_loads': 0, 'model_calls': 0, 'formal_claims': 0, 'formal_episodes_replayed': 0,
            'existing_device_records_modified': False, 'original_ready_modified': False,
            'future_MP_load_and_six_request_qualification_delegated_to_original_monitor': True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    sub.add_parser('freeze')
    run = sub.add_parser('execute')
    run.add_argument('--plan', type=Path, required=True)
    run.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if args.operation == 'freeze':
        value = freeze()
    else:
        ref = reference(args.plan)
        if ref['sha256'] != args.sha256:
            raise ValueError('Explicit recovery plan SHA differs')
        value = execute(ref)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
