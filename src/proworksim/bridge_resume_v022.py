"""One narrowly admitted restart of the interrupted, unstepped B1 window.

The old failed run remains untouched. Partial gradients are discarded; the same
complete four-slot window is recomputed from its pre-update state.
"""
from __future__ import annotations

import copy
import io
import os
from pathlib import Path
import re
import subprocess
import tarfile

from .online_support import bind_rollout
from .online_training import VERSION as TRAINER_VERSION, prepare_window, tensor_tree_digest
from .storage import digest, read_json

VERSION = 'same-window-bridge-recovery-v0.22-R1'
ROOT = Path(__file__).resolve().parents[2]
OLD_COMMIT = '04b9a1725e3eed09110860cec5bd91d59272173d'
UPDATER_SHA = 'a4ebf812ca28154002cc1d798b035ec41e3879f8b57f5f56797ea5de022f41c8'
PRE_STEP_ARTIFACTS = (
    'gradient-probability-check.json', 'losses.json',
    'signal-diagnostics.json', 'gradients-before-clip.pt',
)


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': digest(path.read_bytes())}


def checked(ref):
    path = Path(ref['path']).resolve()
    if reference(path) != ref:
        raise ValueError('Pinned recovery input changed: ' + str(path))
    return path


def pid_alive(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError('Original positive worker PID required')
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def verify_unchanged_sources(commit):
    """Compare every old src Python file and both reused bridge scripts."""
    if commit != OLD_COMMIT or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Only the specifically audited interrupted B1 source may resume')
    data = subprocess.check_output(
        ['git', 'archive', commit, 'src', 'scripts/bridge_work_v022.py', 'scripts/evaluate_work_v022.py'],
        cwd=ROOT, timeout=15)
    hashes = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for item in archive:
            if not item.isfile() or not item.name.endswith('.py'):
                continue
            body = archive.extractfile(item).read()
            if (ROOT / item.name).read_bytes() != body:
                raise ValueError('Model/data/loss or reused post-development code changed: ' + item.name)
            hashes[item.name] = digest(body)
    if hashes.get('src/proworksim/online_training.py') != UPDATER_SHA:
        raise ValueError('Audited updater byte identity differs')
    return hashes


def prove_no_step(state, bridge_report, update_report, actual):
    actual = Path(actual)
    if (state.get('line') != 'B1' or state.get('status') != 'stopped'
            or state.get('stop_reason') != 'task_time_budget' or state.get('exit_code') != -15
            or state.get('source', {}).get('code_commit') != OLD_COMMIT
            or state.get('source', {}).get('code_dirty') is not False
            or pid_alive(state.get('pid')) or pid_alive(state.get('observer_pid'))):
        raise ValueError('Original B1 must be stopped by its timer with worker and observer gone')
    if (bridge_report.get('status') != 'updating'
            or bridge_report.get('source_before') != state['source']
            or len(bridge_report.get('train_rows', [])) != 4
            or any(row.get('status') != 'closed' for row in bridge_report['train_rows'])
            or update_report.get('window_id') != 'v022-b1-train'
            or update_report.get('stage') != 'backward'
            or update_report.get('backward_decisions_completed') != 12
            or update_report.get('admitted_decisions') != 24 or update_report.get('scheduled_slots') != 4
            or update_report.get('actor_optimizer_steps') != 0 or update_report.get('critic_optimizer_steps') != 0
            or update_report.get('training_happened') is not False):
        raise ValueError('Recovery is restricted to the observed 12/24 pre-step interruption')
    present = [name for name in PRE_STEP_ARTIFACTS if (actual / 'update' / name).exists()]
    if present or any((actual / name).exists() for name in ('checkpoint', 'post-0', 'post-1', 'post-progress.json')):
        raise ValueError('A mandatory pre-step marker or successor exists; cannot prove unstepped boundary')
    return {'admitted': True, 'proof': 'Audited original updater writes all four named artifacts before either optimizer.step; all absent after original processes died.',
            'updater_sha256': UPDATER_SHA, 'missing_pre_step_artifacts': list(PRE_STEP_ARTIFACTS),
            'last_persisted_backward_completed': 12, 'scheduled_backward_decisions': 24,
            'terminal_tensor_hash_read_claimed': False, 'partial_gradients_reused': False}


def build_resume_plan(actual, historical_states):
    """Create JSON inputs before launch; this does not load a model or start work."""
    actual = Path(actual).resolve()
    state_path = actual.parent / 'state.json'
    state = read_json(state_path)
    bridge_report = read_json(actual / 'report.json')
    update_report = read_json(actual / 'update/report.json')
    proof = prove_no_step(state, bridge_report, update_report, actual)
    sources = verify_unchanged_sources(state['source']['code_commit'])
    inputs = {'old_state': reference(state_path), 'old_bridge_report': reference(actual / 'report.json'),
              'old_update_report': reference(actual / 'update/report.json'),
              'old_admission': reference(actual / 'update/admission.json'),
              'shared_before': reference(actual / 'update/shared-before.pt'),
              'declaration': reference(actual / 'train-declaration.json'),
              'behavior_checks': reference(actual / 'update/behavior-probability-check.json'),
              'old_b1_plan': bridge_report['plan'],
              'rollouts': [reference(actual / f'train-{i}/team-rollout.json') for i in range(4)]}
    checked(inputs['old_b1_plan'])
    states = {name: reference(path) for name, path in historical_states.items()}
    if set(states) != {'N1', 'W1', 'B1'} or states['B1'] != inputs['old_state']:
        raise ValueError('All original N1/W1/B1 resource states must be bound')
    elapsed = 0
    for ref in states.values():
        prior = read_json(checked(ref))
        if prior.get('status') not in {'complete', 'stopped'} or type(prior.get('elapsed_gpu_seconds')) not in (float, int):
            raise ValueError('Historical device costs must be terminal and known')
        elapsed += prior['elapsed_gpu_seconds']
    if elapsed + 2400 > 7200:
        raise ValueError('The new capped recovery would exceed the full project resource limit')
    return {'version': VERSION, 'old_actual': str(actual), 'inputs': inputs, 'old_source_files': sources,
            'no_step_proof': proof, 'historical_states': states, 'prior_gpu_seconds': elapsed,
            'limits': {'line_seconds': 2400, 'update_seconds': 2100, 'post_task_seconds': 900,
                       'project_gpu_seconds': 7200, 'model_instances': 1, 'actor_steps': 1, 'critic_steps': 1},
            'new_training_collection': False, 'replay_original_window': 'v022-b1-train',
            'scope': 'Explicit R1 recovery of the same 24 real current-policy decisions; original B1 remains failed, all recomputation cost is additional.'}


def validate_resume_plan(plan):
    if plan.get('version') != VERSION or plan.get('new_training_collection') is not False:
        raise ValueError('Only the explicit same-window R1 plan is accepted')
    rebuilt = build_resume_plan(plan['old_actual'], {name: ref['path'] for name, ref in plan['historical_states'].items()})
    if rebuilt != plan:
        raise ValueError('Recovery source, original records or cumulative cost bindings changed')
    return plan['no_step_proof']


def rebuild_entries(plan, actor_identity, recipe):
    """Read the same immutable records and reproduce the old exact admission."""
    inputs = plan['inputs']
    declaration = read_json(checked(inputs['declaration']))
    original = read_json(checked(inputs['old_admission']))
    entries = []
    if len(declaration['slots']) != 4 or declaration['window_id'] != 'v022-b1-train':
        raise ValueError('Original complete four-slot window required')
    for slot, ref in zip(declaration['slots'], inputs['rollouts']):
        rollout = read_json(checked(ref))
        bind_rollout(declaration, slot['slot_id'], rollout)
        entries.append({'slot_id': slot['slot_id'], 'rollout': rollout,
                        'reward': copy.deepcopy(rollout['reward_eligibility']),
                        'active_members': list(slot['active_members'])})
    replay = prepare_window(entries, actor_identity, 'v022-b1-train', recipe)
    if replay != original or replay['slot_count'] != 4 or len(replay['decisions']) != 24:
        raise ValueError('Reconstructed window does not equal the original 24-row admission')
    return entries, {'admission_exactly_equal': True, 'scheduled_slots': 4, 'decisions': 24,
                     'original_admission': inputs['old_admission'], 'new_sampling': False}


def restore_before_update(owner, before_ref, expected_actor):
    """Restore raw shared-before state without forging an old checkpoint."""
    if owner.phase != 'idle' or owner.busy:
        raise ValueError('Recovery requires one freshly loaded idle learner')
    torch = owner.torch
    state = torch.load(checked(before_ref), map_location='cpu', weights_only=True)
    if (state['version'] != TRAINER_VERSION or state['recipe'] != owner.recipe
            or state['base_identity'] != owner.base_identity or state['inference_profile'] != owner.inference_profile
            or set(state['actor']) != set(owner.actor_parameters)
            or any(state[name] != 0 for name in ('actor_steps', 'critic_steps', 'policy_revision'))
            or state['actor_identity'] != expected_actor or state['last_window_id'] != 'v022-b1-train'
            or state['used_window_ids'] != ['v022-b1-train']):
        raise ValueError('Raw before-update state differs from the exact unstepped shared learner')
    with torch.no_grad():
        for name, parameter in owner.actor_parameters.items():
            parameter.copy_(state['actor'][name].to(parameter.device))
    owner.critic.load_state_dict(state['critic'])
    owner.actor_optimizer.load_state_dict(state['actor_optimizer'])
    owner.critic_optimizer.load_state_dict(state['critic_optimizer'])
    owner.actor_optimizer.zero_grad(set_to_none=True)
    owner.critic_optimizer.zero_grad(set_to_none=True)
    for name in ('actor_steps', 'critic_steps', 'policy_revision', 'critic_has_nonzero_reward_history'):
        setattr(owner, name, state[name])
    owner.window_id = state['last_window_id']
    owner.used_window_ids = list(state['used_window_ids'])
    owner._identity = owner._make_identity()
    torch.set_rng_state(state['rng_cpu'].cpu())
    if owner.device.startswith('cuda'):
        torch.cuda.set_rng_state_all([value.cpu() for value in state['rng_cuda']])
    elif state['rng_cuda']:
        raise ValueError('CPU fixture cannot restore actual CUDA RNG')
    owner.clear_generation_cache()
    actual = owner._state_bundle()
    if tensor_tree_digest(actual, torch) != tensor_tree_digest(state, torch) or owner.freeze_identity() != expected_actor:
        raise ValueError('Complete actor/critic/optimizers/RNG restoration was not exact')
    # The old collection is already complete. Resume that original boundary;
    # do not begin a new sampling window or reset its consumed identity.
    owner.phase = 'collecting'
    return {'exact_state_restored': True, 'state_tensor_digest': tensor_tree_digest(state, torch),
            'shared_before': before_ref, 'actor_identity': owner.freeze_identity(),
            'window_id': owner.window_id, 'phase': owner.phase, 'partial_gradients_reused': False,
            'restored': ['actor', 'critic', 'actor_optimizer', 'critic_optimizer', 'CPU/CUDA RNG', 'window and policy identity']}
