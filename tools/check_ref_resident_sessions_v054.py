"""Prepare/run exactly two synthetic REF sessions; never claim a benchmark slot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid
import subprocess

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
VERSION = 'v054-ref-resident-two-session-preparation-v1'


def reference(path):
    raw = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    return reference(path)


def gpu_residency(ready):
    """Read metadata for the largest GPU process in this exact resident cgroup."""
    from proworksim.software_benchmark_ref_resident_v054 import identity
    expected = ready['host_process']
    if identity(expected['pid']) != expected:
        raise ValueError('Registered resident host process exited')
    group = next(line[3:] for line in Path('/proc/' + str(expected['pid']) + '/cgroup').read_text().splitlines()
                 if line.startswith('0::'))
    if (not group.startswith('/user.slice/') or '..' in group.split('/')
            or not group.rsplit('/', 1)[-1].startswith('proworksim-v054-')):
        raise ValueError('Expected a dedicated project resident user unit')
    result = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,used_gpu_memory',
                             '--format=csv,noheader,nounits'], check=True,
                            capture_output=True, text=True, timeout=15)
    owned = []
    for line in result.stdout.splitlines():
        device, pid, memory = [value.strip() for value in line.split(',')]
        if device != ready['gpu_uuid']:
            continue
        try:
            lines = Path('/proc/' + pid + '/cgroup').read_text().splitlines()
            if any(line == '0::' + group or line.startswith('0::' + group + '/') for line in lines):
                owned.append({'process': identity(int(pid)), 'used_mib': int(memory)})
        except FileNotFoundError:
            continue
    if not owned or max(row['used_mib'] for row in owned) < 8192:
        raise ValueError('The registered unit does not retain a model-sized GPU process')
    return {'gpu_uuid': ready['gpu_uuid'], 'cgroup': group,
            'largest_owned_gpu_process': max(owned, key=lambda row: row['used_mib'])}


def prepare(output):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    interface_path = ROOT / 'artifacts/software-benchmark-v054/manifests/native-interface.json'
    interface = json.loads(interface_path.read_bytes())
    sessions = []
    for ordinal, seed in enumerate((202610210611, 202610210612), 1):
        slot = {'slot_id': 'synthetic-v054-ref-resident-handoff-r1-' + str(ordinal),
                'arm': 'REF', 'seed': seed, 'preparation_only': True}
        request = {'model': 'raw-qwen3.5-9b-v054-ref',
            'messages': [{'role': 'system', 'content': interface['static_system_prompt']},
                         {'role': 'user', 'content': 'Synthetic resident preparation only; no repository or task. Call finish once with message ready.'}],
            'tools': list(interface['tool_schemas'].values()), 'tool_choice': 'auto', 'stream': False,
            'max_tokens': 32768, 'temperature': .6, 'top_p': .95, 'top_k': 20,
            'min_p': 0.0, 'presence_penalty': 0.0, 'repetition_penalty': 1.0,
            'seed': seed, 'chat_template_kwargs': {'enable_thinking': True},
            'add_generation_prompt': True, 'continue_final_message': False, 'add_special_tokens': False}
        sessions.append({'slot': slot, 'request': write_new(output / ('request-' + str(ordinal) + '.json'), request)})
    return write_new(output / 'permit.json', {
        'version': VERSION, 'model_execution_authorized': True, 'formal_execution_authorized': False,
        'authorization_basis': 'Root coordinator explicitly authorized two synthetic GPU session controls',
        'maximum_generation_calls': 2, 'maximum_calls_per_session': 1,
        'maximum_input_tokens': 8192, 'maximum_input_output_tokens': 81920,
        'original_output_cap_unchanged': 32768, 'full_capacity_retest': False,
        'benchmark_task_material_used': False, 'formal_slot_claims': 0,
        'automatic_retry': False, 'sessions': sessions, 'native_interface': reference(interface_path),
        'model_manifest': reference(ROOT / 'runs/assets/models/Qwen3.5-9B-c20223623576/proworksim-manifest.json')})


def run(ready_path, permit_path, permit_sha, output):
    from proworksim.software_benchmark_capacity_guards_v054 import SmokeLedger
    from proworksim.software_benchmark_exact_transport_v054 import HTTPFailure
    from proworksim.software_benchmark_ref_resident_v054 import (
        RefResidentClient, SessionAuthenticatedLoopbackHTTP, checked, identity,
    )
    permit_ref = reference(permit_path)
    if permit_ref['sha256'] != permit_sha:
        raise ValueError('Preparation permit changed')
    permit = checked(permit_ref)
    ready_ref = reference(ready_path)
    ready = checked(ready_ref)
    spec = checked(ready['source_spec'])
    if (permit['version'] != VERSION or spec.get('preparation_permit') != permit_ref
            or ready.get('resident') is not True or ready.get('ready') is not True
            or identity(ready['host_process']['pid']) != ready['host_process']):
        raise ValueError('No live resident bound to this two-call preparation permit')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_new(output / 'control-claim.json', {'permit': permit_ref, 'resident_ready': ready_ref,
              'actual_formal_slot_claims': 0, 'automatic_retry': False})
    admin = RefResidentClient(ready['admin_endpoint'], ready['api_key_file'])
    first_status = admin.call('status')
    if (first_status['poisoned'] or first_status['active_claim'] is not None
            or first_status['preparation_generation_calls'] != 0):
        raise ValueError('Preparation cannot resume or repeat an already-used resident')
    initial_gpu = gpu_residency(ready)
    active = previous_token = None
    ledgers, receipts = [], []
    result = {'version': VERSION, 'passed': False, 'formal_slot_claims': 0,
              'actual_capacity_retested': False, 'automatic_retry': False,
              'permit': permit_ref, 'resident_ready': ready_ref,
              'host_process': ready['host_process'], 'api_pid': first_status['resident_pid']}
    result['initial_gpu_residency'] = initial_gpu
    try:
        for ordinal, entry in enumerate(permit['sessions'], 1):
            directory = output / ('session-' + str(ordinal))
            directory.mkdir()
            claim_id = uuid.uuid4().hex
            acquired = admin.call('acquire_preparation', slot=entry['slot'], claim_id=claim_id,
                                  authorization=permit_ref, host_process=identity(os.getpid()))
            if acquired.get('state') != 'acquired':
                raise ValueError('Fresh preparation session was not acquired')
            active = acquired
            token = acquired['ref_session_token']
            transport = SessionAuthenticatedLoopbackHTTP(ready['admin_endpoint'], ready['api_key_file'], token)
            request = checked(entry['request'])
            if previous_token is not None:
                before = admin.call('status')['preparation_generation_calls']
                stale = SessionAuthenticatedLoopbackHTTP(ready['admin_endpoint'], ready['api_key_file'], previous_token)
                try:
                    stale.post('/v1/chat/completions', request)
                    raise AssertionError('The prior session token was accepted')
                except HTTPFailure as error:
                    if error.evidence['http_status'] != 409:
                        raise
                after = admin.call('status')['preparation_generation_calls']
                if before != after:
                    raise AssertionError('Rejected stale token reached generation')
                write_new(directory / 'old-token-rejection.json', {
                    'http_status': 409, 'before_generation_calls': before,
                    'after_generation_calls': after, 'additional_model_calls': 0})
            counted = transport.post('/tokenize', {key: request[key] for key in (
                'model', 'messages', 'tools', 'chat_template_kwargs', 'add_generation_prompt',
                'continue_final_message', 'add_special_tokens')})
            if (counted['count'] != len(counted['tokens']) or counted['max_model_len'] != 131072
                    or not 0 < counted['count'] <= 8192):
                raise ValueError('Small exact-input preparation gate failed')
            ledger = SmokeLedger(directory / 'ledger.json')
            ledgers.append(ledger)
            ledger.prepare(1, counted['count'], 32768)
            write_new(directory / 'request-evidence.json', {'request': entry['request'],
                      'slot': entry['slot'], 'claim_id': claim_id, 'exact_prompt_tokens': counted['count']})
            ledger.dispatched()
            response = transport.post('/v1/chat/completions', request)
            write_new(directory / 'response.json', response)
            ledger.settle(response['usage'])
            until = time.monotonic() + 5
            while admin.call('status')['inflight'] and time.monotonic() < until:
                time.sleep(.01)
            released = admin.call('release', claim_id=claim_id, session_token=token)
            if (released.get('quiescent') is not True or released.get('cache_reset') is not True
                    or released.get('engine_unfinished') != 0 or released.get('resident_still_loaded') is not True):
                raise ValueError('Session did not release an empty resident with weights retained')
            status = admin.call('status')
            current_gpu = gpu_residency(ready)
            if (status['resident_pid'] != first_status['resident_pid']
                    or identity(ready['host_process']['pid']) != ready['host_process']
                    or current_gpu['largest_owned_gpu_process']['process']
                    != initial_gpu['largest_owned_gpu_process']['process']
                    or status['active_claim'] is not None or status['inflight'] != 0):
                raise ValueError('Resident process or empty session identity changed')
            released['observed_gpu_residency_after_release'] = current_gpu
            receipts.append(write_new(directory / 'release.json', released))
            active, previous_token = None, token
        status = admin.call('status')
        if status['preparation_generation_calls'] != 2 or status['preparation_completed_sessions'] != 2:
            raise ValueError('The resident did not complete exactly two independent preparation calls')
        result.update(passed=True, same_resident_process=True, same_api_process=True,
                      same_model_gpu_process=True, GPU_memory_retained_after_each_session=True,
                      independent_predeclared_seeds=True, independent_ledgers=True,
                      stale_session_rejected_without_generation=True, release_receipts=receipts,
                      final_resident_status=status)
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error), technical_unknown=True)
        if active:
            try:
                result['poison'] = RefResidentClient(ready['admin_endpoint'], ready['api_key_file'],
                                                     timeout_seconds=2).call('poison', claim_id=active['claim_id'])
            except BaseException as poison_error:
                result['poison_error'] = type(poison_error).__name__ + ': ' + str(poison_error)
        raise
    finally:
        totals = [ledger.summary() for ledger in ledgers]
        result.update(session_ledgers=totals, actual_generation_calls=sum(x['generation_calls'] for x in totals),
            known_actual_tokens=sum(x['known_actual_tokens'] for x in totals),
            actual_tokens=(sum(x['actual_tokens'] for x in totals)
                           if all(x['actual_tokens'] is not None for x in totals) else None),
            unsettled_reserved_tokens=sum(x['unsettled_reserved_tokens'] for x in totals))
        write_new(output / 'receipt.json', result)
    return reference(output / 'receipt.json')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('prepare')
    make.add_argument('--output', required=True, type=Path)
    call = sub.add_parser('run')
    call.add_argument('--ready', required=True, type=Path)
    call.add_argument('--permit', required=True, type=Path)
    call.add_argument('--permit-sha256', required=True)
    call.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    value = (prepare(args.output) if args.command == 'prepare' else
             run(args.ready, args.permit, args.permit_sha256, args.output))
    print(json.dumps(value))


if __name__ == '__main__':
    main()
