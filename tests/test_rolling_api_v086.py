import importlib.util
from pathlib import Path

import pytest

from proworksim import software_benchmark_rolling_handoff_v086 as handoff
from proworksim import software_benchmark_rolling_scope_v086 as scope
from proworksim import software_benchmark_resources_v086 as resources
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024**3


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prepare = module('v086_prepare_test', 'prepare_rolling_api_v086.py')
runner = module('v086_runner_test', 'run_rolling_api_v086.py')
launcher = module('v086_launcher_test', 'launch_rolling_api_v086.py')


def physical():
    return {'memory_available_bytes': 1100*GIB, 'disk_free_bytes': 2000*GIB,
            'cpu_sample_fresh': True, 'host_cpu_utilization_percent': 20}


def test_actual_policy_has_sixteen_startups_and_eleven_pending_leave_five():
    policy = resources.policy(lambda *args, **kwargs: {},
        watchdog_guard=lambda: {'fresh': True, 'admit': True}, capacity_probe=physical, qwen_target=0)
    active = [{'key': f'actor-{100000+i}', 'spec': {'role': 'actor', 'slot_id': f'v064:fixture-{i}:DEEPSEEK_REF_B5000K:1'},
               'reserved_cpu': 6, 'reserved_memory_bytes': 32*GIB, 'reserved_spool_bytes': 0}
              for i in range(11)]
    value = policy.admission_snapshot(active)
    assert value['maximum_starting_pairs'] == 16
    assert value['additional_slots_by_constraint']['starting_batch'] == 5
    assert value['additional_pair_slots'] == 5
    assert policy.admission_snapshot.__globals__['pending_pairs'] is resources.safe_pending_pairs
    assert resources.original.MAX_STARTING_PAIRS == 4
    assert resources.previous.MAX_STARTING_PAIRS == 8


def test_old_unclaimed_futures_have_priority_over_wider_startup_gate():
    assert runner.own_future_limit({'additional_pair_slots': 16}, own_actors=0,
        old_actors=34, old_unclaimed=2, desired=48, ramp=48) == 0
    assert runner.own_future_limit({'additional_pair_slots': 16}, own_actors=4,
        old_actors=34, old_unclaimed=2, desired=48, ramp=48) == 4
    assert runner.own_future_limit({'additional_pair_slots': 16}, own_actors=4,
        old_actors=34, old_unclaimed=0, desired=48, ramp=48) == 14


def test_strict_old_quiet_rejects_preparation_and_delivery_jobs_without_request():
    progress = {'unix': 110, 'failure': None, 'effective_generation_limit': 0,
        'actual_generation_futures': 0, 'active_generation': 0, 'active_grading': 0,
        'pending_scores': 0, 'pending_controls': 0}
    cursor = {'failure': None, 'active_generation': [], 'active_grading': [], 'pending_scores': [],
        'pending_controls': [], 'active_grading_jobs': [], 'pending_grading_jobs': []}
    assert handoff.quiet_reasons(progress, cursor, [], 0, now=111, gate_unix=100) == []
    for key in ('active_grading_jobs', 'pending_grading_jobs'):
        assert key+'_not_empty' in handoff.quiet_reasons(progress, {**cursor, key: [{'job': 'fixed'}]},
                                                       [], 0, now=111, gate_unix=100)
    assert handoff.quiet_reasons(progress, cursor, ['actor-7'], 0, now=111, gate_unix=100)
    assert handoff.quiet_reasons(progress, cursor, [], 1, now=111, gate_unix=100)


def test_new_manager_CPU_affinity_is_disjoint_with_predecessor_and_has_NOFILE():
    spec = {**launcher.fixed_spec(), 'ownership_token': 'a'*32}
    command = launcher.command(spec)
    assert scope.cpu_affinity() == scope.original.host_cpu_pool()[168:176]
    assert set(scope.cpu_affinity()).isdisjoint(scope.prior.cpu_affinity())
    assert '--property=CPUQuota=800%' in command and '--property=LimitNOFILE=16384' in command
    assert '--property=MemoryMax=64G' in command and command[:2] == ['systemd-run', '--user']
    assert scope.MANAGER_CPUS == 8 and scope.MAX_STARTING_PAIRS == 16


def test_manager_CPU_gate_requires_fresh_below_85_observation(monkeypatch):
    observation = {'cpu_sample_fresh': True, 'host_cpu_utilization_percent': 20}
    class Probe:
        def snapshot(self):
            return observation
    monkeypatch.setattr(resources.original, 'CapacityProbe', Probe)
    assert scope.manager_cpu_admission() is observation
    observation['host_cpu_utilization_percent'] = 85
    with pytest.raises(scope.original.ResourceBusy):
        scope.manager_cpu_admission()


def test_actual_episode_and_owner_probe_use_new_scope_and_existing_parent(tmp_path, monkeypatch):
    monkeypatch.setattr(scope, 'AUTH_FILE', tmp_path/'auth.json')
    write_new(scope.AUTH_FILE, {'approved': True})
    cls = runner.episode_binding_class()
    bound = cls(lambda *args, **kwargs: {}, watchdog_guard=lambda: {'fresh': True, 'admit': True},
        capacity_probe=physical, authorization_ref=None, qwen_target=0)
    assert bound.api.OwnedActorPair.start.__globals__['parent'] is parent
    assert bound.api.OwnedActorPair.create_container.__globals__['container_options'].__globals__['parent'] is parent
    assert cls.run_api.__globals__['parent'] is parent
    assert runner.OWNER_PROBE.__globals__['scope'] is scope
    assert handoff.stage.__globals__['identity'] is handoff.identity
    assert handoff.stage.__globals__['scope'] is scope


def test_rolling_inventory_excludes_every_prior_consumption_category():
    rows = [{'slot_id': f'api-{i}', 'slot_index': i, 'model_key': 'DEEPSEEK',
             'input_plus_output_tokens': 5_000_000} for i in range(1000)]
    rows += [{'slot_id': f'qwen-{i}', 'slot_index': 1000+i, 'model_key': 'QWEN',
              'input_plus_output_tokens': 5_000_000} for i in range(5000)]
    _, states, allowed, old, external, _ = prepare.partition(rows,
        {'generation': {'api-0': {'status': 'closed', 'result': {'fixed': True}}}},
        {'excluded_old_scheduled_slot_ids': ['api-1']}, ['api-2'], ['api-3'], ['api-4'], ['api-5'])
    assert len(allowed) == 994 and set(allowed).isdisjoint(old)
    assert external == ['api-2'] and states['generation']['api-2']['status'] == 'external_running'
    assert not {f'api-{i}' for i in range(6)} & set(allowed)


def test_fd_runtime_wraps_before_initialization():
    import ast
    tree = ast.parse(Path(runner.__file__).read_text())
    runtime_assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
        and node.value.func.id == 'RuntimeView']
    initializations = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == 'initialize_for_run']
    assert len(runtime_assignments) == len(initializations) == 1
    assert runtime_assignments[0].targets[0].id == initializations[0].func.value.id == 'api'
    assert runtime_assignments[0].lineno < initializations[0].lineno
