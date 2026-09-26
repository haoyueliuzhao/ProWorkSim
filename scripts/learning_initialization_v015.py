"""Compare actual shared initial learner tensors before either N1 run starts."""
import copy
from pathlib import Path
import time

from proworksim.online_training import tensor_tree_digest
from proworksim.storage import atomic_write, json_bytes, read_json

FIELDS = {'actor', 'critic', 'actor_optimizer', 'critic_optimizer', 'policy_revision',
          'actor_steps', 'critic_steps', 'critic_has_nonzero_reward_history'}


def actual_initial_state(owner):
    if owner.actor_steps or owner.critic_steps:
        raise ValueError('N1 initialization must precede all optimizer updates')
    snapshot = owner.capture_evaluation_state()
    recipe = copy.deepcopy(owner.recipe)
    credit = recipe.pop('credit_assignment')
    return {'learning_sha256': snapshot['learning'],
            'rng_sha256': tensor_tree_digest(snapshot['rng'], owner.torch),
            'actor_identity': owner.freeze_identity(), 'base_identity': owner.base_identity,
            'inference_profile': owner.inference_profile, 'recipe_except_credit': recipe}, credit


def compare_initializations(left, right):
    if ({left['participant'], right['participant']} != {'mc', 'rtg'}
            or left['credit_assignment'] != {'mc': 'terminal_mc', 'rtg': 'joint_reward_to_go'}[left['participant']]
            or right['credit_assignment'] != {'mc': 'terminal_mc', 'rtg': 'joint_reward_to_go'}[right['participant']]):
        raise ValueError('Only the registered MC and joint-RTG conditions may share initialization')
    for row in (left, right):
        hashes = row['common']['learning_sha256']
        if set(hashes) != FIELDS or any(not isinstance(v, str) or len(v) != 64 for v in hashes.values()):
            raise ValueError('Actual initial learner component fingerprints are required')
        if not isinstance(row['common'].get('rng_sha256'), str) or len(row['common']['rng_sha256']) != 64:
            raise ValueError('Actual initial RNG fingerprint is required')
    if left['common'] != right['common']:
        raise ValueError('N1 conditions do not share the same actual actor/critic/optimizers/RNG/base/profile and non-credit recipe')
    return {'passed': True, 'learning_sha256': left['common']['learning_sha256'],
            'rng_sha256': left['common']['rng_sha256'], 'actor_identity': left['common']['actor_identity'],
            'scope': 'Actual initial tensor fingerprints match before either condition collects its first window. Only declared time credit differs.'}


def synchronize_initialization(owner, declaration, output):
    who = declaration['participant']
    if who not in {'mc', 'rtg'} or declaration['participants'] != ['mc', 'rtg']:
        raise ValueError('Declare the two fixed N1 participants')
    timeout = declaration['timeout_seconds']
    if type(timeout) not in (int, float) or not 0 < timeout <= 1800:
        raise ValueError('Initialization wait must be positive and bounded by 1800 seconds')
    directory = Path(declaration['directory']).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    own_path = directory/(who+'.json')
    if own_path.exists():
        raise FileExistsError('Initialization participant already attempted: '+str(own_path))
    common, credit = actual_initial_state(owner)
    own = {'version': 'shared-initialization-v0.15', 'participant': who,
           'credit_assignment': credit, 'common': common, 'recorded_at': time.time()}
    atomic_write(own_path, json_bytes(own))
    peer_path = directory/(('rtg' if who == 'mc' else 'mc')+'.json')
    started = time.monotonic()
    while not peer_path.exists():
        if time.monotonic()-started >= timeout:
            raise TimeoutError('Other fixed N1 initialization did not arrive; no window collected')
        time.sleep(1)
    peer = read_json(peer_path)
    result = compare_initializations(own, peer)
    current, current_credit = actual_initial_state(owner)
    if current != common or current_credit != credit:
        raise ValueError('Own initialization changed while waiting for peer')
    result.update(own_record=str(own_path), peer_record=str(peer_path),
                  waited_seconds=time.monotonic()-started)
    atomic_write(Path(output)/'shared-initialization-check.json', json_bytes(result))
    return result
