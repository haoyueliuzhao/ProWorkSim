"""Two declared consumptions of one fresh D0, with exact common learner origin.

Collection identities stay immutable. The separate consumption record declares
which return targets this branch uses; no stored calls/window IDs are relabeled.
"""
from __future__ import annotations

import copy
from pathlib import Path

from .collaboration_training_v024 import training_admission, validate_window_declaration
from .handoff_credit_v024 import CREDIT_MODES
from .online_support import bind_rollout
from .online_training import prepare_window, tensor_tree_digest
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = 'common-origin-credit-consumption-v0.24'
COMMON_WINDOW = 'v024-window-1'


def _raw_binding(entries, declaration, admission):
    return {name + '_sha256': digest(json_bytes(value)) for name, value in (
        ('entries', entries), ('declaration', declaration), ('admission', admission))}


def _admit_raw(entries, declaration, admission, actor_identity, recipe):
    from .templates.retail_collaboration_v024 import registry

    if admission != training_admission(registry(), admission['source_pin']['path']):
        raise ValueError('Only the exact new v024 source and collection admission is accepted')
    contract = validate_window_declaration(declaration, admission)
    if (contract['window_id'] != COMMON_WINDOW or contract['credit_arm'] != 'common'
            or declaration['actor_identity'] != actor_identity
            or [e['slot_id'] for e in entries] != [s['slot_id'] for s in contract['slots']]):
        raise ValueError('Common consumption requires the entire fresh, exact common D0 window')
    for entry, slot in zip(entries, declaration['slots']):
        if entry['active_members'] != slot['active_members']:
            raise ValueError('All declared active members remain in the common denominator')
        if entry['rollout'].get('online_scope', {}).get('version') != 'collaboration-token-projection-v0.24':
            raise ValueError('Historical v023 and fixture projections are not v024 training records')
        proof = bind_rollout(declaration, entry['slot_id'], entry['rollout'])
        if (entry['reward'] != entry['rollout']['reward_eligibility']
                or entry['reward'].get('eligible') is not True
                or entry['rollout']['work_validity']['components']['record']['value'] is not True
                or any(not view['complete_actor_trajectory'] for member, view in proof['member_views'].items()
                       if member in entry['active_members'])):
            raise ValueError('All original members and known rewards must remain admitted')
    return prepare_window(entries, actor_identity, COMMON_WINDOW, recipe)


def compare_credit_admission(entries, actor_identity, window_id, recipe):
    """Demonstrate only row target/credit changes; tokens/masks/counts stay fixed."""
    prepared = {arm: prepare_window(entries, actor_identity, window_id,
                    {**recipe, 'credit_assignment': mode}) for arm, mode in CREDIT_MODES.items()}
    stripped = {}
    for arm, value in prepared.items():
        item = copy.deepcopy(value)
        item['decisions'] = [{k: v for k, v in row.items() if k not in {'reward', 'credit'}}
                             for row in item['decisions']]
        stripped[arm] = item
    if stripped['mc'] != stripped['handoff_rtg']:
        raise ValueError('Changing credit must not change original rows, tokens, features or denominators')
    mc, rtg = prepared['mc']['decisions'], prepared['handoff_rtg']['decisions']
    return {'only_target_and_credit_differ': True, 'scheduled_slots': len(entries),
        'decision_count': len(mc), 'own_output_tokens': sum(len(r['tokens']['output_ids']) for r in mc),
        'raw_entries_sha256': digest(json_bytes(entries)),
        'common_projection_without_target_credit_sha256': digest(json_bytes(stripped['mc'])),
        'prepared_sha256': {arm: digest(json_bytes(value)) for arm, value in prepared.items()},
        'target_changes': [{'slot_id': a['slot_id'], 'member_id': a['member_id'], 'call_id': a['call_id'],
                           'mc': a['reward'], 'handoff_rtg': b['reward']}
                          for a, b in zip(mc, rtg) if a['reward'] != b['reward']],
        'normalization': prepared['mc']['normalization'], 'new_model_calls': 0}


def save_common_origin(owner, origin_dir, raw_entries, declaration, admission):
    """Close a completed collection for branching, without pretending evaluation."""
    if (owner.busy or owner.phase != 'collecting' or owner.window_id != COMMON_WINDOW
            or owner.recipe['credit_assignment'] != 'terminal_mc'
            or owner.actor_steps or owner.critic_steps or owner.policy_revision):
        raise ValueError('Common origin requires the unupdated collecting initial actor and MC recipe')
    prepared = _admit_raw(raw_entries, declaration, admission, owner.freeze_identity(), owner.recipe)
    comparison = compare_credit_admission(raw_entries, owner.freeze_identity(), COMMON_WINDOW, owner.recipe)
    # No optimizer step, reseeding or window-ID rewrite occurs at this boundary.
    owner.phase = 'idle'
    directory = Path(origin_dir)
    saved = owner.save_checkpoint(directory)
    report = {'version': VERSION, 'kind': 'closed_common_collection_no_update',
        **_raw_binding(raw_entries, declaration, admission), 'checkpoint': saved,
        'original_collection_window_id': COMMON_WINDOW, 'new_sampling': False,
        'comparison': comparison, 'admitted_slots': prepared['slot_count'],
        'actor_steps': owner.actor_steps, 'critic_steps': owner.critic_steps,
        'evaluation_boundary_claimed': False}
    atomic_write(directory / 'consumption-origin.json', json_bytes(report))
    return report


def prepare_common_consumption(owner, origin_dir, raw_entries, declaration, admission, arm):
    """Restore actor/critic/2 optimizers/RNG, then switch only credit recipe."""
    if arm not in CREDIT_MODES:
        raise ValueError('Predeclared credit arm must be mc or handoff_rtg')
    if (owner.busy or owner.phase != 'idle' or owner.recipe['credit_assignment'] != 'terminal_mc'
            or owner.actor_steps or owner.critic_steps or owner.policy_revision):
        raise ValueError('Each branch starts as a fresh idle MC owner before common restoration')
    directory = Path(origin_dir)
    origin = read_json(directory / 'consumption-origin.json')
    if (origin.get('version') != VERSION or origin.get('kind') != 'closed_common_collection_no_update'
            or origin.get('original_collection_window_id') != COMMON_WINDOW
            or any(origin.get(k) != v for k, v in _raw_binding(raw_entries, declaration, admission).items())
            or origin.get('actor_steps') != 0 or origin.get('critic_steps') != 0
            or read_json(directory / 'checkpoint.json') != origin['checkpoint']):
        raise ValueError('Common checkpoint must bind the unchanged actual D0 records and fresh state')
    restored = owner.restore_checkpoint(directory)
    state = owner._state_bundle()
    common_digest = tensor_tree_digest(state, owner.torch)
    if (common_digest != restored['state_tensor_digest'] or owner.window_id != COMMON_WINDOW
            or owner.freeze_identity() != declaration['actor_identity']
            or owner.actor_steps or owner.critic_steps or owner.policy_revision):
        raise ValueError('Full actor, critic, two optimizer and RNG origin was not restored exactly')
    _admit_raw(raw_entries, declaration, admission, owner.freeze_identity(), owner.recipe)
    comparison = compare_credit_admission(raw_entries, owner.freeze_identity(), COMMON_WINDOW, owner.recipe)
    if comparison != origin['comparison']:
        raise ValueError('The original common projection changed before branch consumption')
    before_recipe = copy.deepcopy(owner.recipe)
    owner.recipe = {**owner.recipe, 'credit_assignment': CREDIT_MODES[arm]}
    owner.actor_optimizer.zero_grad(set_to_none=True)
    owner.critic_optimizer.zero_grad(set_to_none=True)
    changed = owner._state_bundle()
    changed['recipe'] = before_recipe
    if tensor_tree_digest(changed, owner.torch) != common_digest:
        raise ValueError('Credit selection changed learner state beyond the declared recipe field')
    owner.phase = 'collecting'
    return {'version': VERSION, 'consumption_id': COMMON_WINDOW + ':consume:' + arm,
        'credit_arm': arm, 'credit_assignment': CREDIT_MODES[arm],
        'exact_common_state_restored': True, 'common_state_tensor_digest': common_digest,
        'restored': ['actor', 'critic', 'actor_optimizer', 'critic_optimizer', 'CPU/CUDA RNG'],
        'only_recipe_field_changed': 'credit_assignment', 'recipe_before': before_recipe,
        'recipe_after': copy.deepcopy(owner.recipe), **_raw_binding(raw_entries, declaration, admission),
        'original_collection_window_id': owner.window_id, 'comparison': comparison,
        'new_model_calls': 0, 'raw_trajectory_ids_rewritten': False,
        'scope': 'Two declared consumptions of six current-experiment on-policy episodes; no historical v023 replay and no independent-episode double count.'}
