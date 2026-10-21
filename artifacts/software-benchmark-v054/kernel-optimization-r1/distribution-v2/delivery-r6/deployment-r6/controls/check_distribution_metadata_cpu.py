"""Narrow CPU controls for the new distribution v2 metadata and exact r5 release."""
import ast
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path('/tmp/v054-kernel-rollout-r1')

def module(name):
    path = ROOT / 'tools' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def rejected(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return
    raise AssertionError('Invalid metadata admitted')

prepare = module('prepare_kernel_deployment_v054')
guard = module('guard_kernel_owner_v054')
audit = dict(actual_generation_requests=2, known_actual_generation_tokens=384,
             all_started_requests_settled=True, learning_unchanged=True,
             rng_restored_exactly=True, formal_slots_claimed=0)
closure = dict(completed_requests=2, known_actual_tokens=384, guard=dict(
    learning_unchanged=True, rng_restored_exactly=True, new_actor_steps=0,
    new_critic_steps=0, new_backward_calls=0))
failure = dict(model_load_started=True, error=dict(message='Fixed full-vocabulary numerical engineering gate failed'))
spec = dict(unit='proworksim-v054-resident-mp-g6-kernel-r5.service', kernel_runtime_revision='FP32-recurrent-kernel-g6-r1')
kernel = dict(backend_id='project-fp32-recurrent-triton-r1', enabled_symbols=['torch_recurrent_gated_delta_rule'],
    kernel_install_entrypoint={'reference': 'immutable'}, operator_control='immutable-control',
    dependencies_manifest='immutable-deps', overlay_path='immutable-overlay')
unit = dict(MainPID='4321', ControlGroup='/exact/' + spec['unit'], InvocationID='exact')
launcher = dict(host_process=dict(pid=4321))
args = [audit, closure, failure, spec, kernel, kernel, unit, launcher]
prepare.validate_failed_preparation(*args)
bad = dict(audit, actual_generation_requests=4, known_actual_generation_tokens=1536)
rejected(prepare.validate_failed_preparation, bad, *args[1:])
bad = copy.deepcopy(closure); bad['guard']['rng_restored_exactly'] = False
rejected(prepare.validate_failed_preparation, audit, bad, *args[2:])
bad = dict(kernel, operator_control='different-control')
rejected(prepare.validate_failed_preparation, *args[:5], bad, *args[6:])
qualifier = dict(version='v054-kernel-model-diagnostic-r2', passed=True,
    actual_model_requests=6, model_loads=1, formal_tasks_used=0,
    original_gate_is_diagnostic=True, original_gate_passed=False)
prepare.validate_distribution_qualifier(qualifier)
for change in ({'version': 'v054-kernel-model-diagnostic-r1'},
               {'actual_model_requests': 2}, {'original_gate_is_diagnostic': False}):
    rejected(prepare.validate_distribution_qualifier, dict(qualifier, **change))
previous = dict(version='v054-kernel-previous-failed-preparation-r3',
    one_additional_model_load_authorized=True, maximum_additional_model_loads=1,
    automatic_retry=False, unit=spec['unit'], protocol_revision_only=True,
    kernel_implementation_unchanged=True, original_failure_reclassified_as_pass=False,
    prior_completed_generation_requests=2, prior_known_actual_tokens=384,
    cumulative_preparation_generation_upper_bound=97792,
    invocation_id='exact', cgroup=unit['ControlGroup'])
reference = {'path': 'preserved-r5-metadata'}
evidence = dict(previous_failed_preparation=reference, unit=spec['unit'],
    invocation_id='exact', cgroup=unit['ControlGroup'], unit_stopped=True,
    cgroup_empty=True, launcher_gone=True, guard_gone=True)
guard.validate_failed_predecessor_exit(reference, previous, evidence)
rejected(guard.validate_failed_predecessor_exit, reference, previous, dict(evidence, guard_gone=False))
for filename in ('prepare_kernel_deployment_v054.py', 'prepare_kernel_source_root_v054.py',
                 'run_kernel_resident_v054.py', 'guard_kernel_owner_v054.py'):
    ast.parse((ROOT / 'tools' / filename).read_text())
print(json.dumps({'version': 'v054-distribution-v2-deployment-metadata-control-r1',
    'passed': True, 'r5_exact_actual_requests': 2, 'r5_exact_actual_tokens': 384,
    'old_request_counts_rejected': True, 'unrestored_rng_rejected': True,
    'changed_kernel_control_rejected': True, 'old_gate_false_preserved': True,
    'old_qualifier_wrong_count_missing_diagnostic_flag_rejected': True,
    'missing_guard_exit_rejected': True, 'changed_sources_parse': True,
    'model_loads': 0, 'GPU_operations': 0, 'services_launched': 0}))
