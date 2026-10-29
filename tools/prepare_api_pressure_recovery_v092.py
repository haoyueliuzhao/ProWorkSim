"""Seal a new owner for 44 existing, still wholly unconsumed recovery IDs."""
from __future__ import annotations

import argparse
from contextlib import closing
import importlib.util
import json
import sqlite3
import subprocess
import time

from proworksim import software_benchmark_api_scope_v092 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v092-same-44-zero-consumption-preparation-r1'


def prepare_failed_initialization_handoff():
    """Record an already naturally exited owner; do not stop or signal it."""
    scope.predecessor.require_allowed(grading_only=True)
    root = scope.HANDOFF_FILE.parent
    if scope.HANDOFF_FILE.exists():
        return scope.require_handoff()
    observed = subprocess.run(['systemctl', '--user', 'show', scope.OLD_API_UNIT, '--no-pager',
        '--property=MainPID,ActiveState'], env=user_manager_environment(), capture_output=True,
        text=True, timeout=20)
    state = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
    if observed.returncode or state.get('MainPID') != '0' or state.get('ActiveState') not in ('inactive', 'failed'):
        raise PermissionError('Failed initialization manager has not naturally exited')
    if scope.predecessor.LEASE_FILE.exists() or (scope.OLD_API_ROOT/'execution-started.json').exists():
        raise PermissionError('Only a fully released manager that never started execution may transfer')
    stderr = scope.OLD_API_ROOT/'coordinator.stderr.log'
    text = stderr.read_text()
    if ('api.initialize_for_run()' not in text or "scope_guard('v089.api.request'" not in text
            or not text.rstrip().endswith('PermissionError: Operation outside the proven-unentered manager scope')):
        raise PermissionError('Original fixed pre-initialization guard error is not established')
    released = reference(scope.OLD_API_ROOT/'coordinator-capacity-released.json')
    if scope.load(released).get('claim') != reference(scope.predecessor.CLAIM_FILE):
        raise PermissionError('Failed owner did not release its exact manager claim')
    scope.parent_module().require_qualified()
    root.mkdir(parents=True, exist_ok=True)
    proof = write_new(root/'zero-consumption-proof.json', verify_unconsumed())
    return write_new(scope.HANDOFF_FILE, {'version': 'v092-exact-zero-consumption-owner-handoff-r1',
        'unix': time.time(), 'old_unit': scope.OLD_API_UNIT, 'old_main_pid_exited': True,
        'old_unit_state': state, 'old_manager_lease_released': released,
        'all_44_model_attempts_unconsumed': True, 'all_44_physical_identities_unconsumed': True,
        'original_API_parent_preserved': reference(scope.parent_module().CREATED),
        'original_API_parent_stopped': False, 'zero_consumption_proof': proof,
        'failure_trace': reference(stderr), 'execution_started': False,
        'signals_sent': 0, 'root_operations': 0, 'Docker_operations': 0})


def verify_unconsumed():
    inventory = scope.load(reference(scope.INVENTORY_FILE))
    plan = scope.load(reference(scope.PLAN_FILE))
    rows = inventory['rows']
    if rows != plan['rows'] or len(rows) != 44:
        raise ValueError('Only the unchanged authorized recovery rows may continue')
    root = scope.original.BATCH_ROOT
    consumed = [str(path) for key in plan['resources'] for path in
        (root/'resource-claims'/(key+'.json'), root/'resource-claims'/('active-'+key+'.json')) if path.exists()]
    episodes = [str(root/'episodes'/str(row['slot_index'])) for row in rows
                if (root/'episodes'/str(row['slot_index'])).exists()]
    with closing(sqlite3.connect(scope.amendment_ledger().resolve().as_uri()+'?mode=ro', uri=True)) as connection:
        requests = connection.execute('SELECT COUNT(*) FROM requests WHERE slot_id IN ('+
            ','.join('?' for _ in rows)+')', [row['slot_id'] for row in rows]).fetchone()[0]
        inflight = connection.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]
    if consumed or episodes or requests or inflight:
        raise PermissionError('A recovery identity was consumed; continuation cannot replay it')
    return {'rows': 44, 'API_requests': requests, 'global_inflight': inflight,
        'consumed_claims': consumed, 'episode_directories': episodes,
        'plan': reference(scope.PLAN_FILE), 'inventory': reference(scope.INVENTORY_FILE)}


def prepare():
    handoff = scope.require_handoff()
    previous = scope.predecessor.require_allowed(grading_only=True)
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists():
        raise ValueError('New-manager preparation is single use')
    observed = subprocess.run(['systemctl', '--user', 'show', scope.OLD_API_UNIT, '--no-pager',
        '--property=MainPID,ActiveState'], env=user_manager_environment(), capture_output=True,
        text=True, timeout=20)
    state = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
    if observed.returncode or state.get('MainPID') != '0' or state.get('ActiveState') not in ('inactive', 'failed'):
        raise PermissionError('Original owner has not fully exited')
    proof = verify_unconsumed()
    scope.BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    scope.COORDINATOR_ROOT.mkdir()
    spec = importlib.util.spec_from_file_location('v092_launch_prepare', scope.ROOT/'tools/launch_api_pressure_recovery_v092.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    unit = launcher.prepare()
    sources = {ref['path']: ref for ref in scope.load(previous['source_index'])['files']}
    for path in (*scope.ROOT.glob('src/proworksim/*v092*.py'), *scope.ROOT.glob('tools/*v092*.py')):
        sources[str(path)] = reference(path)
    index = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': [sources[key] for key in sorted(sources)]})
    authorization = write_new(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'prior_authorization': reference(scope.predecessor.AUTH_FILE), 'source_index': index,
        'plan': reference(scope.PLAN_FILE), 'inventory': reference(scope.INVENTORY_FILE), 'handoff': handoff,
        'explicit_recovery_authorization': scope.require_explicit_recovery_authorization(),
        'continued_unconsumed_attempts': 44, 'additional_generation_attempts': 0,
        'API_cash_cap_CNY': '1700.00', 'original_records_overwritten': False,
        'Qwen_lifecycle_operations': 0, 'unit': unit['specification'],
        'basis': '原已明确授权的44项全部零模型调用、零物理资源消费；只更换管理进程及精确压力身份适配'})
    receipt = write_new(scope.BATCH_ROOT/'preparation.json', {'version': VERSION, 'unix': time.time(),
        'authorization': authorization, 'handoff': handoff, 'unconsumed': proof,
        'old_unit': state, 'parent_lifecycle_reused': reference(scope.parent_module().CREATED),
        'new_model_calls': 0, 'Docker_operations': 0, 'service_operations': 0})
    return {'preparation': receipt, 'continued_unconsumed_attempts': 44, 'additional_generation_attempts': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--handoff-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else prepare_failed_initialization_handoff(), ensure_ascii=False))
