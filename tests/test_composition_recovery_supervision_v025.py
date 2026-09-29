"""CPU check of recovery-supervisor stop precedence under unknown telemetry."""
import json

from proworksim.resource_monitor_v025 import TelemetryGuard
from scripts.run_composition_recovery_v025 import other_stop_reason


def test_telemetry_grace_continues_but_never_masks_independent_resource_gates():
    plan = {'max_wall_seconds': 172800}
    summary = {'started_at': 0}
    state = {'started_at': 0, 'budget_seconds': 72000}
    task = {'kind': 'update', 'started_at': 0}
    sample = {'time': 100, 'scope': {'kind': 'target_gpu', 'gpu_selector': '4'},
              'worker_identity': {'pid': 123, 'available': True, 'alive': True, 'start_ticks': 456},
              'gpus': {'returncode': None, 'stdout': '', 'stderr': 'synthetic timeout',
                       'error': {'type': 'TimeoutExpired', 'timeout_seconds': 5}},
              'processes': {'returncode': None, 'stdout': '', 'stderr': 'synthetic timeout'}}
    telemetry = TelemetryGuard(4, 'GPU-bound', 456, worker_pid=123)
    observation = telemetry.observe(sample, 110, 123, 4, own_memory_limit_mib=57344)
    assert observation['failure_seconds'] == 10 and observation['stop_reason'] is None
    assert observation['own_gpu_memory_mib'] is None
    # Match production's literal stop precedence and JSON null representation.
    structural = other_stop_reason(plan, summary, state, task, now=110, host_rss=0, size=0)
    assert (structural or observation['stop_reason']) is None
    assert json.loads(json.dumps({'own_gpu_memory_mib': observation['own_gpu_memory_mib']}))['own_gpu_memory_mib'] is None
    structural = other_stop_reason(plan, summary, state, task, now=110, host_rss=64*1024**3+1, size=0)
    assert (structural or observation['stop_reason']) == 'host_rss_limit'
    expired_task = {'kind': 'episode', 'started_at': 110-(1200-30)}
    structural = other_stop_reason(plan, summary, state, expired_task, now=110, host_rss=0, size=0)
    assert (structural or observation['stop_reason']) == 'task_time_budget'
    structural = other_stop_reason(plan, summary, state, task, now=110, host_rss=0, size=32*1024**3)
    assert (structural or observation['stop_reason']) == 'artifact_limit'
