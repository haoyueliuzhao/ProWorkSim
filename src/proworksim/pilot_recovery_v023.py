"""One predeclared replay of a proven unstepped v023 training window.

This helper does not allocate resources, extend a deadline or choose a new
window. The supervisor enforces the once-only attempt and cumulative budget.
"""
import copy
import math
import os
from pathlib import Path

from .audit import code_identity
from .collaboration_training_v023 import training_admission, validate_window_declaration
from .online_support import bind_rollout
from .online_training import VERSION as TRAINER_VERSION, prepare_window, tensor_tree_digest
from .storage import digest, read_json

VERSION = 'same-unstepped-pilot-window-recovery-v0.23'
PRE_STEP_ARTIFACTS = (
    'gradient-probability-check.json', 'losses.json',
    'signal-diagnostics.json', 'gradients-before-clip.pt',
)
ACCEPTED_UPDATES = {'updated', 'zero_step_zero_actor_advantage_or_gradient', 'zero_step_no_admitted_own_actions'}


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': digest(path.read_bytes())}


def checked(ref):
    path = Path(ref['path']).resolve()
    if reference(path)['sha256'] != ref['sha256']:
        raise ValueError('Original recovery input changed: ' + str(path))
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


def admit_recovery(old_stage_dir, plan):
    """Freeze source, no-step proof, original data and complete prior device cost."""
    root = Path(old_stage_dir).resolve()
    actual = root / 'actual'
    state_path, report_path = root / 'state.json', actual / 'report.json'
    state, report = read_json(state_path), read_json(report_path)
    source = code_identity()
    if (source.get('code_dirty') is not False or state.get('source') != source
            or report.get('source_before') != source):
        raise ValueError('Recovery requires the exact same clean frozen source')
    if (state.get('stage') != 'train' or state.get('status') != 'stopped'
            or state.get('stop_reason') not in {'task_time_budget', 'supervisor_interrupted'}
            or state.get('exit_code') is None or state.get('ended_at') is None
            or pid_alive(state.get('pid'))):
        raise ValueError('Only a terminal supervised train interruption with a dead worker can recover')
    if state.get('task', {}).get('kind') != 'update':
        raise ValueError('Interrupted collection, loading or saving cannot be replayed as an update')
    elapsed = state.get('elapsed_gpu_seconds')
    if type(elapsed) not in (float, int) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('All original device time must be recorded')
    if read_json(checked(report['plan'])) != plan:
        raise ValueError('The frozen original experiment plan changed')
    progress_path = actual / 'training-progress.json'
    progress = read_json(progress_path)
    if not progress or len(progress) > 4 or progress[-1].get('status') != 'updating':
        raise ValueError('Only the final collected but unstepped window may be replayed')
    index = len(progress) - 1
    if ([r.get('window_index') for r in progress] != list(range(index + 1))
            or any(r.get('status') != 'closed' or r.get('update', {}).get('status') not in ACCEPTED_UPDATES
                   for r in progress[:-1])):
        raise ValueError('Earlier closed training windows must remain intact and qualified')
    window_id = progress[-1]['window_id']
    if state['task'].get('task') != window_id + ':update':
        raise ValueError('Supervisor task and interrupted window differ')
    folder = actual / f'window-{index}'
    update = folder / 'update'
    current = read_json(update / 'report.json')
    if (current.get('window_id') != window_id or current.get('status') != 'preparing'
            or current.get('stage') != 'backward' or current.get('scheduled_slots') != 6
            or current.get('actor_optimizer_steps') != 0 or current.get('critic_optimizer_steps') != 0
            or current.get('training_happened') is not False
            or current.get('behavior_probability_passed') is not True):
        raise ValueError('Only a probability-qualified pre-step backward interruption can recover')
    if any((update / name).exists() for name in PRE_STEP_ARTIFACTS):
        raise ValueError('Mandatory pre-step artifact exists; a no-step boundary is not proven')
    if (folder / 'checkpoint').exists() or (actual / 'checkpoint-final').exists():
        raise ValueError('A successor checkpoint already exists')
    refs = {name: reference(path) for name, path in {
        'state': state_path, 'report': report_path, 'progress': progress_path,
        'declaration': folder / 'declaration.json', 'entries': folder / 'entries.json',
        'admission': update / 'admission.json', 'shared_before': update / 'shared-before.pt',
        'behavior_checks': update / 'behavior-probability-check.json',
        'update_report': update / 'report.json', 'training_admission': actual / 'admission.json',
        'plan': checked(report['plan']),
    }.items()}
    declaration = read_json(checked(refs['declaration']))
    recorded_training_admission = read_json(checked(refs['training_admission']))
    from .templates.retail_collaboration_v023 import registry
    if recorded_training_admission != training_admission(
            registry(), recorded_training_admission['source_pin']['path']):
        raise ValueError('Original training admission differs from the frozen canonical catalog')
    contract = validate_window_declaration(declaration, recorded_training_admission)
    if contract['window_index'] != index or declaration['window_id'] != window_id:
        raise ValueError('Original declared window does not match its frozen sequence')
    entries = read_json(checked(refs['entries']))
    original = read_json(checked(refs['admission']))
    checks = read_json(checked(refs['behavior_checks']))
    rows = original['decisions']
    if (original['window_id'] != window_id or original['slot_count'] != 6 or len(entries) != 6
            or current['admitted_decisions'] != len(rows)
            or len(checks) != len(rows) or any(c.get('passed') is not True for c in checks)
            or [c.get('call_id') for c in checks] != [r['call_id'] for r in rows]):
        raise ValueError('Original complete admitted window and probability checks are required')
    if [(e['slot_id'], e['rollout']['window']['xi_id']) for e in entries] != [
            (s['slot_id'], s['xi_id']) for s in declaration['slots']]:
        raise ValueError('Original entries differ from all six scheduled slots')
    for entry in entries:
        bind_rollout(declaration, entry['slot_id'], entry['rollout'])
        if entry['reward'] != entry['rollout']['reward_eligibility']:
            raise ValueError('Original attached reward differs from the collection record')
    prior_steps = {kind: sum(r['update'][kind + '_optimizer_steps'] for r in progress[:-1])
                   for kind in ('actor', 'critic')}
    if any(not 0 <= count <= index for count in prior_steps.values()):
        raise ValueError('Prior step count exceeds completed window count')
    return {'version': VERSION, 'source': source, 'old_stage_dir': str(root),
            'original_window_index': index, 'original_window_id': window_id,
            'original_window_folder': str(folder), 'completed_rows': copy.deepcopy(progress[:-1]),
            'interrupted_row': copy.deepcopy(progress[-1]), 'entries': entries,
            'inputs': refs, 'prior_steps': prior_steps, 'prior_gpu_seconds': elapsed,
            'no_step_proof': {'admitted': True, 'missing_pre_step_artifacts': list(PRE_STEP_ARTIFACTS),
                'worker_dead': True, 'behavior_checks_passed': len(checks),
                'last_persisted_backward_completed': current.get('backward_decisions_completed'),
                'proof': 'Frozen updater writes all four required files before either optimizer step; all absent after worker exit. This is control-flow proof, not a terminal live tensor read.'},
            'new_training_model_calls': 0, 'partial_gradients_reused': False}


def restore_window(owner, recovery):
    """Restore full saved state and re-admit exactly the same original six slots."""
    if owner.phase != 'idle' or owner.busy or recovery.get('version') != VERSION:
        raise ValueError('Recovery needs a fresh idle owner and admitted original window')
    # Recheck all referenced original bytes before restoring tensors. Resource
    # once-only/cumulative accounting remains the supervisor's responsibility.
    for ref in recovery['inputs'].values():
        checked(ref)
    if code_identity() != recovery['source']:
        raise ValueError('Frozen recovery source changed')
    torch = owner.torch
    state = torch.load(checked(recovery['inputs']['shared_before']), map_location='cpu', weights_only=True)
    original = read_json(checked(recovery['inputs']['admission']))
    entries = read_json(checked(recovery['inputs']['entries']))
    declaration = read_json(checked(recovery['inputs']['declaration']))
    index = recovery['original_window_index']
    expected_windows = [r['window_id'] for r in recovery['completed_rows']] + [recovery['original_window_id']]
    if (state['version'] != TRAINER_VERSION or state['recipe'] != owner.recipe
            or state['base_identity'] != owner.base_identity or state['inference_profile'] != owner.inference_profile
            or set(state['actor']) != set(owner.actor_parameters)
            or state['actor_steps'] != recovery['prior_steps']['actor']
            or state['critic_steps'] != recovery['prior_steps']['critic']
            or not 0 <= state['actor_steps'] <= index or not 0 <= state['critic_steps'] <= index
            or state['policy_revision'] != state['actor_steps']
            or state['actor_identity'] != original['actor_identity']
            or state['actor_identity'] != declaration['actor_identity']
            or state['last_window_id'] != recovery['original_window_id']
            or state['used_window_ids'] != expected_windows):
        raise ValueError('Saved actor/critic/optimizer window state differs from the proven boundary')
    with torch.no_grad():
        for name, parameter in owner.actor_parameters.items():
            saved = state['actor'][name]
            if saved.shape != parameter.shape or saved.dtype != parameter.dtype:
                raise ValueError('Saved adapter shape or precision differs')
            parameter.copy_(saved.to(parameter.device))
    owner.critic.load_state_dict(state['critic'])
    owner.actor_optimizer.load_state_dict(state['actor_optimizer'])
    owner.critic_optimizer.load_state_dict(state['critic_optimizer'])
    owner.actor_optimizer.zero_grad(set_to_none=True)
    owner.critic_optimizer.zero_grad(set_to_none=True)
    for name in ('actor_steps', 'critic_steps', 'policy_revision', 'critic_has_nonzero_reward_history'):
        setattr(owner, name, state[name])
    owner.window_id, owner.used_window_ids = state['last_window_id'], list(state['used_window_ids'])
    owner._identity = owner._make_identity()
    torch.set_rng_state(state['rng_cpu'].cpu())
    if owner.device.startswith('cuda'):
        torch.cuda.set_rng_state_all([value.cpu() for value in state['rng_cuda']])
    elif state['rng_cuda']:
        raise ValueError('A CPU fixture cannot restore saved CUDA RNG')
    owner.clear_generation_cache()
    expected_digest = tensor_tree_digest(state, torch)
    if tensor_tree_digest(owner._state_bundle(), torch) != expected_digest:
        raise ValueError('Complete actor/critic/optimizers/RNG restore differs')
    if owner.freeze_identity() != original['actor_identity']:
        raise ValueError('Restored effective actor identity differs')
    for entry in entries:
        bind_rollout(declaration, entry['slot_id'], entry['rollout'])
    reconstructed = prepare_window(entries, owner.freeze_identity(), owner.window_id, owner.recipe)
    if reconstructed != original:
        raise ValueError('Reconstructed complete six-slot admission differs from the original')
    owner.phase = 'collecting'
    return {'entries': entries,
            'restoration': {'exact_state_restored': True, 'state_tensor_digest': expected_digest,
                'actor_steps_before_window': owner.actor_steps, 'critic_steps_before_window': owner.critic_steps,
                'actor_identity': owner.freeze_identity(), 'window_id': owner.window_id,
                'partial_gradients_reused': False, 'new_training_model_calls': 0},
            'admission_reconstruction': {'exactly_equal': True, 'scheduled_slots': 6,
                'admitted_decisions': len(reconstructed['decisions']), 'original': recovery['inputs']['admission']}}
