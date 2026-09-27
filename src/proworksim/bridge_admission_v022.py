"""Read-only B1 qualification: exact N1, token projection and frozen work protocol.

W1 outcomes and completion are deliberately not dependencies of the bridge.
No model, world scoring or optimizer is run by this module.
"""
from __future__ import annotations

import math
from pathlib import Path
import re
import subprocess

from .storage import digest, read_json

ROOT = Path(__file__).resolve().parents[2]
FUNCTIONAL_PATH = 'src/proworksim/functional_qwen_v022.py'
PROJECTION_FILES = {
    'src/proworksim/collaboration_training_v022.py',
    'src/proworksim/online_support.py',
    'tests/test_collaboration_training_v022.py',
}
WORK_FILES = {
    'src/proworksim/templates/retail_collaboration_v021.py',
    'src/proworksim/templates/retail_collaboration_v022.py',
    'src/proworksim/work_view_v022.py',
    'examples/retail-collaboration-v22/catalog.json',
    'examples/retail-collaboration-v22/source-manifest.json',
}


def checked(reference):
    if not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}:
        raise ValueError('Exact path/SHA reference required for bridge qualification')
    path = Path(reference['path']).resolve()
    if str(path) != reference['path'] or digest(path.read_bytes()) != reference['sha256']:
        raise ValueError('Frozen bridge qualification reference changed')
    return path


def _load(reference):
    return read_json(checked(reference))


def _commit(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{40}', value):
        raise ValueError('Source must identify one full 40-hex Git commit')
    return value


def _git_file(commit, relative):
    commit = _commit(commit)
    if relative not in WORK_FILES | {FUNCTIONAL_PATH}:
        raise ValueError('Source lookup outside fixed bridge module inventory')
    result = subprocess.run(['git', 'show', f'{commit}:{relative}'], cwd=ROOT,
                            capture_output=True, timeout=10, check=False)
    if result.returncode:
        raise ValueError('Qualified Git source object is unavailable: ' + relative)
    return result.stdout


def _source(report):
    before = report.get('source_before', {})
    if (before.get('code_dirty') is not False or report.get('source_after') != before
            or report.get('source_unchanged') is not True):
        raise ValueError('N1 source did not close unchanged and clean')
    return _commit(before.get('code_commit'))


def _same_owner(left, right):
    # Compare the complete checked original recipe/profile/weight manifest plan.
    if _load(left) != _load(right):
        raise ValueError('N1/W1/B1 owner recipe or model source differs')


def _numeric_report(n, initial):
    from .functional_qwen_v022 import CONTRACT

    if (n.get('version') != 'functional-state-N1-experiment-v0.22'
            or n.get('status') != 'qualified_fixed_list' or n.get('qualification_passed') is not True
            or n.get('candidate_contract') != CONTRACT
            or n.get('planned_requests') != 3 or n.get('actual_backward_calls') != 3
            or n.get('backward_calls_attempted') != 3 or n.get('new_sampling') is not False
            or any(n.get(key) != 0 for key in ('actor_steps', 'critic_steps', 'parameter_steps'))
            or n.get('initial_actor_identity') != initial or n.get('final_actor_identity') != initial
            or n.get('actor_identity_unchanged') is not True
            or n.get('learning_state_guard', {}).get('learning_unchanged') is not True
            or n.get('learning_state_guard', {}).get('rng_restored_exactly') is not True):
        raise ValueError('Bridge requires all three N1 backward requests and unchanged actor/learner guards')
    plan = _load(n['plan'])
    if (plan.get('version') != 'functional-state-N1-heldout-selection-v0.22'
            or plan.get('candidate_count') != 1 or plan.get('new_sampling') is not False
            or plan.get('optimizer_steps') != 0 or plan.get('actual_backward_required') is not True
            or plan.get('auto_retry_or_new_candidate') is not False
            or plan.get('probability_gate') != {'max_abs_logp': .02, 'mean_abs_logp': .002}
            or [(r['input_tokens'], r['output_tokens']) for r in plan.get('heldout_requests', [])]
               != [(4251, 308), (13275, 2048)]):
        raise ValueError('N1 frozen three-request inventory changed')
    requests = [('development', plan['development_response'], 8473, 146)] + [
        (f'heldout-{i}', row['response'], row['input_tokens'], row['output_tokens'])
        for i, row in enumerate(plan['heldout_requests'])]
    rows = n.get('rows', [])
    if len(rows) != 3:
        raise ValueError('N1 request denominator is incomplete')
    for row, (name, reference, inputs, outputs) in zip(rows, requests):
        if (row.get('request') != name or row.get('record') != reference
                or row.get('input_tokens') != inputs or row.get('output_tokens') != outputs
                or row.get('status') != 'complete' or row.get('actual_backward') is not True
                or row.get('finite_gradients') is not True or row.get('nonzero_gradient_elements', 0) <= 0
                or row.get('parameter_steps') != 0 or row.get('actor_identity_unchanged') is not True
                or row.get('raw_tokens_and_behavior_preserved') is not True
                or row.get('all_output_targets_included') != outputs):
            raise ValueError('N1 row differs from the full frozen request/backward inventory')
        saved = _load(reference)
        body = saved['response']
        trace = body['token_trace']
        if (saved.get('status') != 200 or saved.get('actor_identity') != initial
                or body.get('actor_identity') != initial
                or len(trace['input_ids']) != inputs or len(trace['output_ids']) != outputs
                or trace.get('raw_output_ids') != trace['output_ids']
                or trace.get('raw_behavior_logprobs') != trace['behavior_logprobs']):
            raise ValueError('N1 original request identity or complete tokens changed')
        probability = row.get('probability', {})
        actual, behavior = probability.get('recomputed_logprobs'), probability.get('actual_behavior_logprobs')
        if (not isinstance(actual, list) or len(actual) != outputs
                or behavior != trace['behavior_logprobs'] or len(behavior) != outputs
                or not all(type(x) in (int, float) and math.isfinite(x) for x in actual + behavior)):
            raise ValueError('N1 full probability evidence missing')
        delta = [a - b for a, b in zip(actual, behavior)]
        maximum, mean = max(map(abs, delta)), sum(map(abs, delta)) / outputs
        if (probability.get('passed') is not True or probability.get('signed_delta') != delta
                or probability.get('max_abs_delta') != maximum or probability.get('mean_abs_delta') != mean
                or maximum > .02 or mean > .002):
            raise ValueError('N1 saved probabilities do not satisfy the unchanged numerical gate')
    return plan


def validate_bridge_qualification(supervisor):
    """Validate immutable prerequisites, without requiring final W1 outcomes."""
    bridge = _load(supervisor['experiment_plan'])
    if bridge.get('supervisor_qualification') != {k: v for k, v in supervisor.items() if k != 'experiment_plan'}:
        raise ValueError('Bridge and supervisor qualification bindings differ; no cyclic/self SHA reference')
    initial = _load(bridge['initial_identity_response'])['response']['actor_identity']
    n = _load(supervisor['N1_qualification'])
    n_plan = _numeric_report(n, initial)
    n_commit = _source(n)
    module_sha = digest(_git_file(n_commit, FUNCTIONAL_PATH))
    qualified_path = checked(bridge['qualified_functional_module'])
    if (digest(qualified_path.read_bytes()) != module_sha
            or digest((ROOT / FUNCTIONAL_PATH).read_bytes()) != module_sha):
        raise ValueError('Bridge functional implementation differs from the actual N1 frozen Git source')
    _same_owner(n_plan['owner_plan_ref'], bridge['prior_model_plan'])

    projection = _load(bridge['token_projection_qualification'])
    if (projection.get('passed') is not True or type(projection.get('tests_passed')) is not int
            or projection['tests_passed'] < 5 or set(projection.get('source_files', {})) != PROJECTION_FILES):
        raise ValueError('Exact CPU token-projection qualification is incomplete')
    for path, sha in projection['source_files'].items():
        if digest((ROOT / path).read_bytes()) != sha:
            raise ValueError('CPU-qualified token projection source changed: ' + path)

    protocol = bridge['work_protocol_qualification']
    work_commit = _commit(protocol['source_commit'])
    if set(protocol.get('source_files', {})) != WORK_FILES:
        raise ValueError('Frozen work protocol file inventory differs')
    for path, sha in protocol['source_files'].items():
        if digest(_git_file(work_commit, path)) != sha or digest((ROOT / path).read_bytes()) != sha:
            raise ValueError('Bridge work protocol differs from the frozen W1 source: ' + path)
    w_plan = _load(protocol['w1_plan'])
    if (w_plan.get('version') != 'paired-work-presentation-v0.22'
            or w_plan.get('parameter_updates') != 0 or w_plan.get('model_api_calls') != 0
            or _load(w_plan['catalog']) != _load(bridge['catalog'])):
        raise ValueError('W1 work protocol/catalog or frozen-parameter contract differs')
    _same_owner(w_plan['prior_model_plan'], bridge['prior_model_plan'])
    if _load(w_plan['initial_identity_response'])['response']['actor_identity'] != initial:
        raise ValueError('W1 declared initialization differs from N1/B1')
    # owner.json is written once when the real W1 resident is constructed. No
    # business outcomes or incomplete mutable W1 report are read here.
    owner = _load(protocol['w1_initial_identity'])
    if owner.get('initial_actor_identity') != initial:
        raise ValueError('Actual immutable W1 resident initialization differs from N1/B1')
    controls = _load(protocol['cpu_work_controls'])
    if (controls.get('version') != 'work-view-cpu-controls-v0.22' or controls.get('passed') is not True
            or controls.get('same_initial_business_state') is not True or controls.get('model_calls') != 0
            or {row.get('arm') for row in controls.get('arms', [])} != {'original_history', 'compact_work'}
            or len(controls['arms']) != 2 or any(row.get('passed') is not True for row in controls['arms'])
            or controls.get('source_manifest_sha256') != protocol['source_files']['examples/retail-collaboration-v22/source-manifest.json']):
        raise ValueError('Actual paired CPU work/negative-control qualification is incomplete')
    return {'version': 'bridge-prerequisites-v0.22', 'passed': True,
            'N1_report': supervisor['N1_qualification'], 'N1_source_commit': n_commit,
            'functional_module_sha256': module_sha, 'actor_identity': initial,
            'token_projection_qualification': bridge['token_projection_qualification'],
            'work_protocol_qualification': protocol,
            'W1_outcomes_required_or_read': False,
            'scope': 'N1 numerical/backward and exact CPU projection/work protocol qualifications; W1 outcomes remain an independent running experiment.'}
