"""Complete real runtime initialization with no HTTP and a temporary cash DB.

The production scope and host-limit functions execute against explicit local
cgroup/lease fixtures. Original authorization, parent, source, registry,
qualification, schemas, tokenizer and accounting preflight are really checked.
Only the client's write-capable ledger is redirected to a SQLite backup.
"""
from __future__ import annotations

from contextlib import closing
import http.client
import json
import os
from pathlib import Path
import resource
import socket
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from proworksim import software_benchmark_api_scope_v092 as scope
from proworksim import software_benchmark_deepseek_budget_v089 as amended
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.software_benchmark_fd_v085 import FDGuard

VERSION = 'v092-real-runtime-initialization-no-HTTP-control-r1'


def fixture_guard(folder):
    cgroup = '/user.slice/test.scope/'+scope.API_UNIT
    proc = folder/'proc-self-cgroup'
    proc.write_text('0::'+cgroup+'\n')
    cgroot = folder/'cgroups'
    group = cgroot/cgroup.lstrip('/')
    group.mkdir(parents=True)
    for name, value in {'memory.max': 64*1024**3, 'memory.high': 32*1024**3,
                        'memory.swap.max': 0, 'pids.max': 512}.items():
        (group/name).write_text(str(value))

    def paths(value):
        return {'/proc/self/cgroup': proc, '/sys/fs/cgroup': cgroot}.get(str(value), Path(value))

    host_calls = []
    actual_limits = private_function(scope.verify_host_limits, Path=paths,
        os=SimpleNamespace(sched_getaffinity=lambda _: set(scope.cpu_affinity()), getuid=os.getuid),
        resource=SimpleNamespace(RLIMIT_NOFILE=resource.RLIMIT_NOFILE, getrlimit=lambda _: (16384, 16384)))

    def host_limits():
        result = actual_limits()
        host_calls.append(result)
        return result

    claim = write_new(folder/'claim.json', {'test_owner': scope.API_UNIT})
    lease = folder/'lease.json'
    lease.write_bytes(Path(claim['path']).read_bytes())
    sources = write_new(folder/'sources.json', {'files': [reference(scope.__file__)]})
    authority = write_new(folder/'authority.json', {'version': scope.VERSION, 'status': 'approved',
        'prior_authorization': reference(scope.predecessor.AUTH_FILE), 'source_index': sources,
        'plan': reference(scope.PLAN_FILE), 'inventory': reference(scope.INVENTORY_FILE),
        'handoff': scope.require_handoff(), 'continued_unconsumed_attempts': 44,
        'additional_generation_attempts': 0, 'API_cash_cap_CNY': '1700.00',
        'original_records_overwritten': False, 'Qwen_lifecycle_operations': 0})
    production_guard = private_function(scope.require_allowed, AUTH_FILE=Path(authority['path']),
        SOURCE_FILE=Path(sources['path']), CLAIM_FILE=Path(claim['path']), LEASE_FILE=lease,
        verify_host_limits=host_limits)
    calls = []

    def guard(operation='v092.run', **identity):
        result = production_guard(operation, **identity)
        calls.append({'operation': operation, **identity})
        return result

    return guard, lease, group, calls, host_calls


def run_control():
    rows = scope.load(reference(scope.INVENTORY_FILE))['rows']
    live_ledger = amended.LEDGER
    network_attempts = []

    def no_network(*args, **kwargs):
        network_attempts.append(True)
        raise AssertionError('No HTTP, socket or DNS is allowed in this CPU control')

    with tempfile.TemporaryDirectory(prefix='v092-initialize-control-') as temporary:
        folder = Path(temporary)
        guard, lease, group, calls, host_calls = fixture_guard(folder)
        copied = folder/'client-ledger.sqlite3'
        with closing(sqlite3.connect(live_ledger.resolve().as_uri()+'?mode=ro', uri=True)) as source:
            original_requests = source.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
            with closing(sqlite3.connect(copied)) as destination:
                source.backup(destination)
        with patch.object(socket.socket, 'connect', no_network), patch.object(socket.socket, 'connect_ex', no_network), \
             patch.object(socket, 'getaddrinfo', no_network), patch.object(http.client.HTTPSConnection, 'connect', no_network), \
             patch.object(amended.wire, 'LEDGER', copied), \
             patch.object(amended.API_VIEW, 'load_api_key', lambda _: 'cpu-only-unused-key'):
            raw = amended.build_runtime(scope_guard=guard, retry_rows=rows,
                inventory_ref=reference(scope.INVENTORY_FILE), identity_file=folder/'api/identity.json')
            api = amended.RuntimeView(raw, FDGuard())
            resident = api.initialize_for_run()
            assert raw.client.ledger.path == copied.resolve()
            assert raw.client.ledger.snapshot()['cap_nanoyuan'] == 1700*amended.original_api.NANOYUAN
            assert resident['identity_value']['context_limit'] == amended.API_VIEW.CONTEXT_TOKENS
            assert len(raw.rows) == 44 and raw.counter is not None and raw.qualified['passed'] is True
            transport_checks = []
            for arm in ('REF', 'PROJECT'):
                row = next(item for item in rows if item['arm'] == arm)
                broker = raw.transport_factory(row, folder/arm)
                payload = {'request_id': row['slot_id']+':0001', 'slot_id': row['slot_id'],
                    'condition': row['condition_id'], 'usage_id': 'agent',
                    'wire': {'max_tokens': amended.API_VIEW.MAX_OUTPUT_TOKENS,
                             'tools': raw.schemas['schemas'][arm]}}
                admitted = broker.authorize(payload)
                assert admitted['token_budget'] == 5_000_000
                transport_checks.append({'arm': arm, 'scope_request_and_broker_authorize': True})
            for operation in ('v089.run', 'v089.api.run', 'v076.run', 'v079.run', 'v066.run',
                              'v066.grader.create', 'v066.grader.start', 'v066.transport'):
                guard(operation)
            lease.unlink()
            try:
                api.initialize_for_run()
            except PermissionError as error:
                assert 'reservation' in str(error)
            else:
                raise AssertionError('Missing lease did not prevent initialized-runtime reuse')
            lease.write_text('{"foreign":true}')
            try:
                api.initialize_for_run()
            except PermissionError as error:
                assert 'reservation' in str(error)
            else:
                raise AssertionError('Foreign lease did not prevent initialized-runtime reuse')
            (group/'memory.max').write_text(str(65*1024**3))
            try:
                api.initialize_for_run()
            except PermissionError as error:
                assert 'boundaries' in str(error)
            else:
                raise AssertionError('Changed hard memory bound was accepted')
            for operation in ('v999.api.request', 'unrestricted.root.operation'):
                try:
                    guard(operation)
                except PermissionError:
                    pass
                else:
                    raise AssertionError('Unknown operation accepted')
            with closing(sqlite3.connect(copied)) as copied_db:
                assert copied_db.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == original_requests
        with closing(sqlite3.connect(live_ledger.resolve().as_uri()+'?mode=ro', uri=True)) as original:
            assert original.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == original_requests
        assert not network_attempts
        return {'version': VERSION, 'passed': True, 'runtime_initialized': True,
            'original_read_only_preflight_replaced': False, 'real_tokenizer_loaded': True,
            'real_amended_client_initialized': True, 'write_capable_client_ledger_was_temporary_copy': True,
            'production_scope_and_host_limits_code_executed': True,
            'host_environment_was_explicit_temporary_cgroup_fixture': True,
            'host_limit_checks': len(host_calls), 'scope_operations': calls,
            'transport_authorization_checks': transport_checks,
            'rejected': ['missing_lease', 'foreign_lease', 'wrong_memory_max', 'unknown_operation'],
            'original_ledger_requests_before_and_after': original_requests,
            'HTTP_socket_DNS_attempts': 0, 'model_calls': 0, 'Docker_operations': 0, 'GPU_operations': 0}


if __name__ == '__main__':
    output = scope.ROOT/'artifacts/software-benchmark-v092/real-initialization-control-r1/summary.json'
    value = run_control()
    value['sources'] = [reference(__file__), reference(scope.__file__)]
    output.parent.mkdir(parents=True, exist_ok=True)
    write_new(output, value)
    print(json.dumps(value, ensure_ascii=False))
