"""CPU startup control up to the real episode's first Docker constructor.

All claims and results are redirected in fresh private namespaces to a temporary
directory. No Docker client, container, HTTP request, model or GPU is started.
Later controller projection and broker authorization are checked separately;
this explicitly is not an end-to-end container or model test.
"""
from __future__ import annotations

from contextlib import closing
import copy
import http.client
import importlib.util
import json
import os
from pathlib import Path
import resource
import socket
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from proworksim import software_benchmark_api_scope_v093 as scope
from proworksim import software_benchmark_recovery_runtime_v093 as runtime
from proworksim import software_benchmark_deepseek_budget_v089 as budget
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.software_benchmark_fd_v085 import FDGuard
from proworksim.repository_sources_v054 import normalize_policy

VERSION = 'v093-real-episode-pre-Docker-CPU-control-r1'


class ReachedDockerConstructor(RuntimeError):
    """Expected CPU boundary; real DockerClient was not constructed."""


def load_tool(name):
    spec = importlib.util.spec_from_file_location('v093_CPU_'+name, scope.ROOT/'tools'/name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_guard(folder):
    """Execute actual scope/host-limit code using explicit temporary OS fixtures."""
    cgroup = '/user.slice/cpu-control/'+scope.API_UNIT
    proc = folder/'proc-cgroup'
    proc.write_text('0::'+cgroup+'\n')
    cgroot = folder/'cgroups'
    group = cgroot/cgroup.lstrip('/')
    group.mkdir(parents=True)
    for key, value in {'memory.max': 64*1024**3, 'memory.high': 32*1024**3,
                       'memory.swap.max': 0, 'pids.max': 512}.items():
        (group/key).write_text(str(value))

    def paths(value):
        return {'/proc/self/cgroup': proc, '/sys/fs/cgroup': cgroot}.get(str(value), Path(value))

    host_limits = private_function(scope.verify_host_limits, Path=paths,
        os=SimpleNamespace(sched_getaffinity=lambda _: set(scope.cpu_affinity()), getuid=os.getuid),
        resource=SimpleNamespace(RLIMIT_NOFILE=resource.RLIMIT_NOFILE, getrlimit=lambda _: (16384, 16384)))
    claim = write_new(folder/'claim.json', {'CPU_fixture_owner': scope.API_UNIT})
    lease = folder/'lease.json'
    lease.write_bytes(Path(claim['path']).read_bytes())
    sources = write_new(folder/'sources.json', {'files': [reference(scope.__file__), reference(runtime.__file__)]})
    auth = write_new(folder/'authority.json', {'version': scope.VERSION, 'status': 'approved',
        'prior_authorization': reference(scope.previous_owner.AUTH_FILE), 'source_index': sources,
        'plan': reference(scope.PLAN_FILE), 'inventory': reference(scope.INVENTORY_FILE),
        'physical_zero_model_audit': scope.require_physical_audit(),
        'logical_model_attempts': 44, 'additional_model_attempts': 0,
        'API_cash_cap_CNY': '1700.00', 'old_records_overwritten': False, 'Qwen_lifecycle_operations': 0})
    simulated_parent = SimpleNamespace(require_qualified=lambda: {'CPU_fixture_only': True})
    actual = private_function(scope.require_allowed, AUTH_FILE=Path(auth['path']), SOURCE_FILE=Path(sources['path']),
        CLAIM_FILE=Path(claim['path']), LEASE_FILE=lease, verify_host_limits=host_limits,
        parent_module=lambda: simulated_parent)
    calls = []

    def guard(operation='v093.run', **identity):
        result = actual(operation, **identity)
        calls.append({'operation': operation, **identity})
        return result

    return guard, auth, sources, calls


def run_control():
    plan = scope.load(reference(scope.PLAN_FILE))
    inventory = scope.load(reference(scope.INVENTORY_FILE))
    scope.validate_complete_plan(plan, inventory)
    canonical = scope.canonical_rows()
    blocked_network, constructors = [], []

    def no_network(*_args, **_kwargs):
        blocked_network.append(True)
        raise AssertionError('CPU control cannot make HTTP/socket/DNS calls')

    def constructor(*args, **kwargs):
        constructors.append({'args': list(args), 'kwargs': kwargs})
        raise ReachedDockerConstructor('Expected CPU stop before constructing any Docker client')

    result = {'version': VERSION, 'passed': False, 'real_Docker_clients_created': 0,
        'containers_started': 0, 'HTTP_calls': 0, 'model_calls': 0, 'GPU_operations': 0,
        'formal_episode_results_changed': False, 'real_host_cpu_pool_stubbed': False,
        'parent_and_manager_cgroups_simulated_not_verified': True,
        'cases': [], 'uncovered_stages': ['actual Docker create/start and kernel isolation',
            'container rootfs, executable interpreter and baseline snapshot',
            'PID1 SDK process and FIFO/stdio transfer', 'first SDK-generated model request and HTTP response',
            'public tests, writer quiescence, candidate export and official grading']}
    with tempfile.TemporaryDirectory(prefix='v093-episode-startup-control-') as temporary:
        folder = Path(temporary)

        def audit(event, values):
            if event in {'subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn', 'os.exec'}:
                raise AssertionError('No process or command execution in this CPU boundary control')
            writing = False
            if event == 'open' and values:
                mode = values[1] if len(values) > 1 else None
                flags = values[2] if len(values) > 2 else 0
                writing = isinstance(mode, str) and any(c in mode for c in 'wax+') or (
                    isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            elif event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename'}:
                writing = True
            if writing and values and isinstance(values[0], (str, bytes)):
                target = Path(os.fsdecode(values[0]))
                if (not target.is_absolute() and event in {'os.remove', 'os.rmdir', 'os.mkdir'}
                        and len(values) > 1 and type(values[-1]) is int and values[-1] >= 0):
                    target = Path(os.readlink('/proc/self/fd/'+str(values[-1])))/target
                target = target.resolve()
                if not target.is_relative_to(folder):
                    raise AssertionError('CPU fixture attempted a write outside its temporary directory: '+str(target))
        # Install only while executing the production path. The separate final
        # artifact writer is admitted below after all simulated work is closed.
        audit_active = [True]
        sys.addaudithook(lambda event, values: audit(event, values) if audit_active[0] else None)
        guard, auth, sources, operations = fixture_guard(folder)
        physical = {'observed_unix': 0, 'memory_available_bytes': 1024**4,
            'disk_free_bytes': 1024**4, 'cpu_sample_fresh': True,
            'host_cpu_utilization_percent': 1.0, 'host_cpu_sample_interval_seconds': 2,
            'load_1m': 1.0}
        cpu_scope = SimpleNamespace(**{**vars(scope), 'AUTH_FILE': Path(auth['path']),
                                     'SOURCE_FILE': Path(sources['path'])})
        dispatch_view = private_function(runtime.bindings.dispatch_view, scope=cpu_scope)
        policy_factory = private_function(runtime.bindings.policy, scope=cpu_scope, dispatch_view=dispatch_view)
        policy = policy_factory(guard, watchdog_guard=lambda: {'fresh': True, 'admit': True},
            authorization_ref=auth, qwen_target=0, capacity_probe=lambda: copy.deepcopy(physical))
        # These are newly constructed private function dictionaries, never the
        # frozen module globals. The original CPU inventory binding is untouched.
        claim_namespace = policy.claim_resource.__globals__
        assert claim_namespace is not vars(scope.original)
        assert policy.release_resource.__globals__ is claim_namespace
        batch = folder/'physical-batch'
        claim_namespace.update(BATCH_ROOT=batch, AUTHORIZATION_FILE=Path(auth['path']))
        policy.BATCH_ROOT, policy.AUTHORIZATION_FILE = batch, Path(auth['path'])
        episode = runtime.bindings.episode(policy)
        episode_namespace = episode.run_episode.__globals__
        assert episode._run.__globals__ is episode_namespace
        episode_namespace['BATCH'] = batch
        episode.BATCH = batch
        cpu_pool = policy.host_cpu_pool()
        assert len(cpu_pool) >= 176 and cpu_pool == scope.original.host_cpu_pool()
        assert claim_namespace['PLAN_FILE'] == scope.PLAN_FILE
        assert claim_namespace['CPU_POOL_FILE'] == scope.original.CPU_POOL_FILE
        result['fixed_cpu_inventory'] = plan['host_cpu_pool']
        result['fixed_cpu_count'] = len(cpu_pool)
        captured = {}
        original_public = episode_namespace['public_environment']

        def public_environment(config):
            value = original_public(config)
            captured['mapping'], captured['public'] = value
            return value

        episode_namespace['public_environment'] = public_environment
        # Filesystem metadata checks remain real; no socket is connected.
        with patch('docker.DockerClient', constructor), \
             patch.object(socket.socket, 'connect', no_network), \
             patch.object(socket.socket, 'connect_ex', no_network), \
             patch.object(socket, 'getaddrinfo', no_network), \
             patch.object(http.client.HTTPSConnection, 'connect', no_network):
            for arm in ('REF', 'PROJECT'):
                row = next(r for r in inventory['rows'] if r['arm'] == arm)
                before = len(constructors)
                ref = episode.run_episode(row, {}, api_transport_factory=lambda *_: None)
                observed = scope.load(ref)
                assert len(constructors) == before+1, observed.get('traceback')
                assert observed['error']['type'] == 'ReachedDockerConstructor'
                assert observed['model_calls'] == 0 and not observed['model_dispatch_started']
                quiet = scope.load(observed['quiescence'])
                assert quiet['quiescent'] and quiet['all_owned_objects_removed']
                assert not list((batch/'resource-claims').glob('active-*.json'))
                config = scope.load(row['configuration'])
                condition = scope.load(config['configuration'])
                context = scope.load(reference(Path(ref['path']).parent/'public-context-provenance.json'))
                public, mapping = captured['public'], captured['mapping']
                public_entry = {'version': 'v064-repository-public-test-entry-r1',
                    'instance_id': row['instance_id'], 'argv': config['public_test_entry']['argv'],
                    'cwd': '/testbed', 'timeout_seconds': 1800, 'hidden_material_used': False}
                # Ready is explicitly simulated here: no actor or isolated
                # namespace has been initialized by this control.
                model_identity = {'model_key': 'DEEPSEEK', 'context_limit': 131072,
                                  'max_output_tokens': 32768, 'thinking': True}
                inputs = episode_namespace['runtime'].controller_inputs(
                    {**config, 'dataset_revision': condition['dataset_revision']}, row,
                    {'CPU_simulated_ready_not_attestation': True}, model_identity, 'http://127.0.0.1:18219',
                    public_context=context, public_environment=public, public_test_entry=public_entry,
                    file_policy=normalize_policy(), gitlinks=[{'path': s['path'], 'oid': s['official_commit']}
                                                             for s in mapping.get('submodules', [])])
                projected = json.loads(inputs['controller-config.json'])
                controller = load_tool('run_ref_controller_v066.py' if arm == 'REF' else 'run_project_controller_v066.py')
                controller.validate_config(projected)
                assert json.loads(inputs['condition.json']) == condition
                result['cases'].append({'arm': arm, 'physical_slot_index': row['slot_index'],
                    'logical_slot_id': row['slot_id'], 'actual_episode_reached_Docker_constructor': True,
                    'actor_claim_in_temporary_directory': True, 'temporary_claim_released': True,
                    'original_row_configuration_validation_executed': True,
                    'original_bundle_validation_executed': True, 'original_public_context_executed': True,
                    'original_controller_inputs_and_validator_executed': True,
                    'controller_condition_bytes_preserved': True,
                    'result_is_CPU_expected_stop_not_formal_experiment': True})
            # Independently execute the real runtime initialization and the
            # physical-to-canonical broker path. This is not an SDK-generated
            # request: its declared schema-shaped payload stops at authorize().
            copied = folder/'client-ledger.sqlite3'
            with closing(sqlite3.connect(budget.LEDGER.resolve().as_uri()+'?mode=ro', uri=True)) as original_db:
                original_requests = original_db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
                with closing(sqlite3.connect(copied)) as destination:
                    original_db.backup(destination)
            with patch.object(budget.wire, 'LEDGER', copied), \
                 patch.object(budget.API_VIEW, 'load_api_key', lambda _: 'CPU-only-unused-key'):
                api = runtime.build_api_runtime(rows=inventory['rows'], fd_guard=FDGuard(),
                    identity_file=folder/'api-runtime/identity.json', scope_guard=guard)
                resident = api.initialize_for_run()
                raw = api.delegate.runtime
                assert raw.client.ledger.path == copied.resolve()
                assert len(raw.rows) == 44 and raw.counter is not None and raw.qualified['passed'] is True
                checks = []
                for arm in ('REF', 'PROJECT'):
                    row = next(r for r in inventory['rows'] if r['arm'] == arm)
                    broker = api.transport_factory(row, folder/('broker-'+arm))
                    old = api.canonical_row(row)
                    assert old['slot_index'] == row['slot_index']-44 and old['slot_id'] == row['slot_id']
                    payload = {'request_id': row['slot_id']+':0001', 'slot_id': row['slot_id'],
                        'condition': row['condition_id'], 'usage_id': 'agent',
                        'wire': {'max_tokens': budget.API_VIEW.MAX_OUTPUT_TOKENS,
                                 'tools': raw.schemas['schemas'][arm]}}
                    admitted = broker.authorize(payload)
                    assert admitted['token_budget'] == 5_000_000
                    try:
                        api.transport_factory({**row, 'slot_index': old['slot_index']}, folder/'forbidden')
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError('Canonical row incorrectly admitted as a fresh physical launch')
                    checks.append({'arm': arm, 'physical_index': row['slot_index'],
                        'canonical_index': old['slot_index'], 'logical_slot_id_unchanged': True,
                        'real_transport_factory_and_authorize': True, 'altered_physical_row_rejected': True})
                with closing(sqlite3.connect(copied)) as db:
                    assert db.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == original_requests
                result['broker_controls'] = checks
                result['real_original_runtime_initialized'] = True
                result['real_canonical_preflight_replaced'] = False
                result['real_tokenizer_and_client_initialized'] = True
                result['client_write_ledger_was_temporary_copy'] = True
                result['logical_resident_deployment_version'] = resident['identity_value']['deployment_version']
            with closing(sqlite3.connect(budget.LEDGER.resolve().as_uri()+'?mode=ro', uri=True)) as db:
                assert db.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == original_requests
            result['live_ledger_request_count_unchanged'] = original_requests
        result['scope_operations'] = operations
        result['Docker_constructor_boundary_calls'] = constructors
        result['physical_rows'] = len(inventory['rows'])
        result['canonical_rows'] = len(canonical)
        result['broker_mapping_stage'] = 'real_initialization_transport_factory_and_authorize_no_HTTP'
        result['interfaces_checked'] = ['REF', 'PROJECT']
        result['broker_controls_complete'] = True
        result['full_required_CPU_control_complete'] = True
        result['full_system_runtime_verified'] = False
        assert not blocked_network
        result['passed'] = True
        audit_active[0] = False
    return result


if __name__ == '__main__':
    output = scope.ROOT/'artifacts/software-benchmark-v093/episode-startup-control-r1/summary.json'
    value = run_control()
    value['sources'] = [reference(__file__), reference(scope.__file__), reference(runtime.__file__)]
    output.parent.mkdir(parents=True, exist_ok=True)
    write_new(output, value)
    print(json.dumps({'passed': value['passed'], 'cases': len(value['cases']),
                      'stage': 'Docker constructor boundary only; separate controller projection'}, ensure_ascii=False))
