"""Freeze nine software evaluations for an explicitly selected candidate.

This generator never chooses a model, loads weights, executes an episode, or
imports the UCI reporter. The selected protocol must be provided explicitly.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

VERSION = 'software-evaluation-protocol-v0.15'
STUDY_VERSION = 'software-evaluation-study-v0.15'
INITIAL_SEED = 2026092929
SAMPLING_SEEDS = (2026140000, 2026140001, 2026140002)
NODES = ('initial', 'mc-final', 'rtg-final')
CASE_ID = 'marshmallow-v15-strip-implement'


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build_protocols(selected_screen):
    """Return three runner protocols and a separate software study manifest."""
    for key in ('version', 'candidate_id', 'runtime', 'recipe'):
        if key not in selected_screen:
            raise ValueError('Explicit selected-screen-protocol is missing ' + key)
    if not isinstance(selected_screen['runtime'], dict) or not isinstance(selected_screen['recipe'], dict):
        raise ValueError('Selected runtime and recipe must be explicit objects')
    candidate = selected_screen['candidate_id']
    if not isinstance(candidate, str) or not candidate or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in candidate):
        raise ValueError('Candidate identity must be a nonempty path-safe label')
    # Same fresh initial seed and no diagnostic learning passes as N1. Credit is
    # retained only to restore each condition's exact checkpoint recipe later;
    # this runner does zero optimizer updates and has no reward-assignment use.
    recipe = copy.deepcopy(selected_screen['recipe'])
    recipe.update(seed=INITIAL_SEED, diagnostic_max_groups=0, post_update_max_decisions=0,
                  credit_assignment='terminal_mc')
    runtime = copy.deepcopy(selected_screen['runtime'])
    protocols, jobs = {}, []
    for node in NODES:
        own_recipe = copy.deepcopy(recipe)
        condition = 'rtg' if node == 'rtg-final' else 'mc' if node == 'mc-final' else 'common'
        if node == 'rtg-final':
            own_recipe['credit_assignment'] = 'joint_reward_to_go'
        initial = node == 'initial'
        binding = {
            'kind': 'fresh_selected_base' if initial else 'required_completed_N1_final_checkpoint',
            'restore_checkpoint_required': not initial,
            'restore_checkpoint_forbidden': initial,
            'forbidden_sources': ['screening_actor', 'N0_bridge_actor', 'best_development_checkpoint', 'other_candidate'],
            'source_condition': condition,
            'source_node': 'N1-common-initial' if initial else f'pilot-{condition}-final-locked',
            'initial_seed': INITIAL_SEED,
            'missing_rule': 'Do not substitute another checkpoint or candidate; retain this evaluation node as missing.',
        }
        episodes = [{'episode_id': f'software-{node}-r{repeat}', 'sampling_seed': seed}
                    for repeat, seed in enumerate(SAMPLING_SEEDS)]
        protocol = {
            'version': VERSION, 'stage': 'software_evaluation', 'mode': 'evaluate',
            'candidate_id': candidate, 'node': node, 'condition': condition,
            'runtime': copy.deepcopy(runtime), 'recipe': own_recipe, 'episodes': episodes,
            'entrypoint': 'scripts/software_model_v015.py',
            'fixed_case': {'case_id': CASE_ID, 'selection': 'Fixed by software_model/collect_software_episode; no per-episode case override.'},
            'role_decision_limits': {'implementer': 18},
            'planned_evaluation_episodes': 3, 'planned_training_episodes': 0,
            'planned_optimizer_steps': {'actor': 0, 'critic': 0},
            'checkpoint_binding': binding,
            'comparison_scope': 'Same software responsibility, runtime, sampling seeds, output/context budget and role deadline across nodes. Episode identities differ; final actor weights intentionally differ.',
            'recipe_restore_exception': 'RTG final credit_assignment matches its exact N1 checkpoint recipe. It does not alter evaluation sampling, task, grading or perform an update.',
        }
        name = 'software-' + node
        filename = name + '.json'
        protocols[filename] = protocol
        jobs.append({'name': name, 'node': node, 'condition': condition, 'candidate_id': candidate,
                     'protocol': filename, 'protocol_relative_to': 'study_manifest_parent',
                     'run': f'runs/software-v015-{candidate}-{node}', 'run_relative_to': 'project_root',
                     'checkpoint_binding': copy.deepcopy(binding),
                     'planned_episode_ids': [e['episode_id'] for e in episodes],
                     'planned_sampling_seeds': list(SAMPLING_SEEDS),
                     'result_layout': {'report': 'report.json', 'episode_result': '{episode_id}/result.json',
                                       'episode_manifest': '{episode_id}/episode/manifest.json',
                                       'evaluation_guard': '{episode_id}/evaluation-guard.json'}})
    study = {
        'version': STUDY_VERSION, 'stage': 'software_evaluation', 'candidate_id': candidate,
        'selection': 'Caller supplies a previously selected screen protocol; this generator performs no selection.',
        'selected_screen_protocol_content_sha256': _sha(selected_screen),
        'entrypoint': 'scripts/software_model_v015.py', 'case_id': CASE_ID,
        'initial_seed': INITIAL_SEED, 'sampling_seeds': list(SAMPLING_SEEDS),
        'planned_evaluation_episodes': 9, 'planned_training_episodes': 0,
        'planned_optimizer_steps': {'actor': 0, 'critic': 0},
        'max_opportunities_per_episode': 18, 'max_total_opportunities': 162,
        'initial_baseline': 'One common three-episode baseline, shared by MC and RTG comparisons; count it once.',
        'source_use': 'Marshmallow is excluded from model selection, UCI training and outer tuning; one code family and one simulated maintenance request do not establish broad transfer.',
        'missing_rule': 'Unstarted, failed-to-load or absent nodes are missing, never imputed as zero reward.',
        'reporter': {'kind': 'separate_software_readonly_manifest', 'uci_reporter_compatible': False,
                     'scope': 'Read saved report/episode/result/guard only; never regrade, execute code, load weights or train while summarizing.'},
        'jobs': jobs,
    }
    return protocols, study


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selected-screen-protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    source_bytes = args.selected_screen_protocol.read_bytes()
    protocols, study = build_protocols(json.loads(source_bytes))
    study['selected_screen_protocol'] = {'path': str(args.selected_screen_protocol.resolve()),
                                         'sha256': hashlib.sha256(source_bytes).hexdigest()}
    args.output.mkdir(parents=True, exist_ok=False)
    for name, protocol in protocols.items():
        (args.output / name).write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'software-study.json').write_text(json.dumps(study, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'candidate_id': study['candidate_id'],
                      'evaluation_episodes': 9, 'training_episodes': 0, 'nodes': list(NODES)}))


if __name__ == '__main__':
    main()
