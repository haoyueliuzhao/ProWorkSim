"""Frozen software evaluation with the selected shared actor, no learning export."""

import argparse
import hashlib
import re
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import atomic_write, json_bytes, read_json


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _file_reference(path):
    path = Path(path).resolve()
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            hasher.update(block)
    return {'path': str(path), 'sha256': hasher.hexdigest(), 'bytes': path.stat().st_size}


def validate_software_binding(protocol, *, restore_checkpoint, model, weight_manifest):
    """Read metadata and hash checkpoint bytes only; never import/load tensors.

    The final binding is the final *planned* window checkpoint of a complete
    matching N1 run. Its directory is derived from the actual online layout;
    neither an arbitrary "best" path nor a checkpoint's self-description wins.
    """
    _require(protocol.get('version') == 'software-evaluation-protocol-v0.15', 'Unsupported software evaluation protocol')
    node = protocol.get('node')
    _require(node in {'initial', 'mc-final', 'rtg-final'}, 'Unknown software evaluation node')
    _require(isinstance(protocol.get('candidate_id'), str) and bool(protocol['candidate_id'])
             and isinstance(protocol.get('runtime'), dict), 'Selected candidate/runtime must be explicit')
    condition = 'common' if node == 'initial' else node.split('-')[0]
    initial = node == 'initial'
    _require(protocol.get('stage') == 'software_evaluation' and protocol.get('mode') == 'evaluate', 'Software is evaluation only')
    _require(protocol.get('condition') == condition, 'Software node/condition differs')
    _require(protocol.get('entrypoint') == 'scripts/software_model_v015.py', 'Wrong software entrypoint')
    _require(protocol.get('role_decision_limits') == {'implementer': 18}, 'Software role budget must remain 18')
    _require(protocol.get('planned_evaluation_episodes') == 3 and protocol.get('planned_training_episodes') == 0,
             'Software node must declare three evaluations and zero training')
    _require(protocol.get('planned_optimizer_steps') == {'actor': 0, 'critic': 0}, 'Software optimizer steps must be zero')
    _require(protocol.get('fixed_case', {}).get('case_id') == 'marshmallow-v15-strip-implement', 'Software case differs')
    expected_episodes = [{'episode_id': f'software-{node}-r{i}', 'sampling_seed': 2026140000 + i} for i in range(3)]
    _require(protocol.get('episodes') == expected_episodes, 'Software episodes/seeds differ from the frozen three')
    recipe = protocol.get('recipe', {})
    expected_credit = 'joint_reward_to_go' if condition == 'rtg' else 'terminal_mc'
    _require(recipe.get('seed') == 2026092929 and recipe.get('credit_assignment') == expected_credit,
             'Software recipe is not the declared N1 initial/condition recipe')
    _require(recipe.get('diagnostic_max_groups') == 0 and recipe.get('post_update_max_decisions') == 0,
             'Software evaluation cannot add learning diagnostics')
    binding = protocol.get('checkpoint_binding', {})
    required = {'kind': 'fresh_selected_base' if initial else 'required_completed_N1_final_checkpoint',
                'restore_checkpoint_required': not initial, 'restore_checkpoint_forbidden': initial,
                'source_condition': condition, 'source_node': 'N1-common-initial' if initial else f'pilot-{condition}-final-locked',
                'initial_seed': 2026092929}
    _require(all(binding.get(key) == value for key, value in required.items()), 'Checkpoint binding contradicts the software node')
    _require(set(binding.get('forbidden_sources', [])) == {'screening_actor', 'N0_bridge_actor', 'best_development_checkpoint', 'other_candidate'},
             'Checkpoint source exclusions differ')
    model_path = Path(model).resolve()
    _require(model_path.is_dir(), 'Selected public base model directory is absent')
    weight_reference = _file_reference(weight_manifest)
    report = {'version': 'software-checkpoint-binding-v0.15', 'passed': True, 'node': node,
              'candidate_id': protocol.get('candidate_id'), 'checkpoint_binding': binding,
              'model_path': str(model_path), 'weight_manifest': weight_reference,
              'tensor_loads': 0, 'model_loads': 0, 'evaluation_episodes': 3, 'training_episodes': 0}
    if initial:
        _require(restore_checkpoint is None, 'Initial software evaluation forbids any restored checkpoint, including screening/bridge')
        report['source'] = 'fresh_selected_public_base_and_N1_seed'
        return report
    _require(restore_checkpoint is not None, 'Final software evaluation requires the matching completed N1 checkpoint')
    checkpoint = Path(restore_checkpoint).resolve()
    _require(checkpoint.name == 'checkpoint' and re.fullmatch(r'window-[0-9]+', checkpoint.parent.name) is not None
             and checkpoint.parent.parent.name == 'online', 'Final checkpoint must use the original N1 online/window-N/checkpoint layout')
    online = checkpoint.parent.parent
    run = online.parent
    references = {}

    def read_record(name, path):
        references[name] = _file_reference(path)
        return read_json(Path(path))

    launch = read_record('launch_protocol', run / 'launch-protocol.json')
    declared = read_record('online_protocol', online / 'protocol.json')
    _require(launch == declared, 'N1 launch and online protocols differ')
    _require(declared.get('stage') == 'pilot' and declared.get('mode') == 'online'
             and declared.get('condition') == condition and declared.get('replicate_index') == 0,
             'Checkpoint source is not the matching N1 pilot condition')
    _require(declared.get('candidate_id') == protocol.get('candidate_id'), 'Checkpoint belongs to another candidate')
    _require(declared.get('runtime') == protocol.get('runtime') and declared.get('recipe') == recipe,
             'Software runtime/recipe differs from its N1 checkpoint run')
    _require(declared.get('selection_parent_scope') == 'Fresh same public base; no screening or bridge weights restored',
             'N1 run does not declare the fresh common initial policy')
    _require(not (run / 'restored-checkpoint.json').exists(), 'N1 run restored an external checkpoint instead of starting fresh')
    windows = declared.get('windows', [])
    training = [window for window in windows if window.get('mode') == 'online']
    _require(len(training) == 4 and all(len(window.get('slots', [])) == 16 for window in training),
             'N1 source does not contain the frozen four training windows of sixteen')
    _require(bool(windows) and windows[-1].get('window_id') == binding['source_node']
             and windows[-1].get('mode') == 'evaluate' and windows[-1].get('phase') == 'locked'
             and windows[-1].get('node') == 'final', 'N1 planned terminal node differs')
    expected_path = online / ('window-' + str(len(windows) - 1)) / 'checkpoint'
    _require(checkpoint == expected_path.resolve(), 'Selected checkpoint is an earlier/best node, not the N1 planned terminal checkpoint')
    saved = read_record('online_report', online / 'report.json')
    _require(saved.get('status') == 'complete' and saved.get('mode') == 'online', 'N1 run is incomplete; final software evaluation remains missing')
    expected_protocol_sha = hashlib.sha256(json_bytes(declared)).hexdigest()
    _require(saved.get('protocol_sha256') == expected_protocol_sha, 'N1 report is not bound to its actual protocol')
    records = saved.get('windows', [])
    _require(len(records) == len(windows) and all(record.get('window_id') == window.get('window_id')
             and record.get('mode') == window.get('mode') and record.get('status') == 'complete'
             for record, window in zip(records, windows)), 'N1 report has missing, changed or unfinished planned windows')
    final_record = records[-1]
    guard = read_record('terminal_evaluation_guard', checkpoint.parent / 'evaluation-guard.json')
    _require(final_record.get('evaluation_guard') == guard and guard.get('learning_unchanged') is True
             and guard.get('rng_restored_exactly') is True, 'N1 terminal evaluation lacks its unchanged-learning/RNG guard')
    checkpoint_record = read_record('checkpoint', checkpoint / 'checkpoint.json')
    _require(final_record.get('checkpoint') == checkpoint_record, 'Final checkpoint is not the one recorded at the planned terminal node')
    _require(checkpoint_record.get('serialized_reload_exact') is True, 'N1 checkpoint lacks exact serialization/reload evidence')
    identity = checkpoint_record.get('actor_identity')
    _require(isinstance(identity, dict) and final_record.get('after_actor_identity') == identity
             and saved.get('final_actor_identity') == identity, 'N1 final actor identity is not consistently bound')
    state = _file_reference(checkpoint / 'shared-state.pt')
    _require(checkpoint_record.get('state') == state, 'N1 checkpoint state path/hash/size differs from recorded bytes')
    _require(identity.get('base_manifest_sha256') == weight_reference['sha256'], 'Selected weight manifest differs from N1 base')
    owner = read_record('resident_owner', run / 'resident/owner.json')
    _require(owner.get('recipe', {}).get('seed') == 2026092929
             and owner.get('recipe', {}).get('credit_assignment') == expected_credit,
             'Actual N1 resident recipe does not use the declared initial seed/condition')
    _require(bool(checkpoint_record.get('version')) and checkpoint_record['version'] == saved.get('version') == owner.get('version'),
             'N1 checkpoint, resident and report training versions differ')
    _require(owner.get('base_identity', {}).get('manifest') == weight_reference
             and Path(owner.get('base_identity', {}).get('path', '')).resolve() == model_path,
             'Selected model/manifest is not the actual N1 base identity')
    for key in ('actor', 'critic'):
        _require(type(checkpoint_record.get(key + '_steps')) is int
                 and checkpoint_record[key + '_steps'] == saved.get(key + '_steps_total'),
                 'Final checkpoint step counters differ from completed N1 report')
    report.update(source='completed_N1_planned_final_checkpoint', run=str(run), checkpoint=str(checkpoint),
                  actor_identity=identity, records=references, state=state,
                  scope='Metadata/protocol/path/byte-hash verification before model load; exact tensor/base/recipe restore remains independently checked by SharedActor.')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--weight-manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--restore-checkpoint')
    args = parser.parse_args(argv)
    protocol = read_json(Path(args.protocol))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    source = code_identity()
    atomic_write(output / 'source-before.json', json_bytes(source))
    atomic_write(output / 'protocol.json', json_bytes(protocol))
    report = {'version': 'software-frozen-model-v0.15', 'status': 'validating_binding', 'episodes': [],
              'training_export': False, 'actual_optimizer_steps': {'actor': 0, 'critic': 0},
              'requested_restore_checkpoint': args.restore_checkpoint}
    try:
        binding = validate_software_binding(protocol, restore_checkpoint=args.restore_checkpoint,
                                             model=args.model, weight_manifest=args.weight_manifest)
        atomic_write(output / 'binding-validation.json', json_bytes(binding))
        report['status'] = 'loading'
        from proworksim.online_collection import _config
        from proworksim.online_training import SharedActor
        from proworksim.software_collection import collect_software_episode
        runtime = protocol['runtime']
        if runtime['kind'] in ('qwen_hybrid', 'qwen_hybrid_chatstop'):
            if runtime['kind'] == 'qwen_hybrid_chatstop':
                from proworksim.candidate_runtime_v0151 import CandidateActor
            else:
                from proworksim.candidate_runtime_v015 import CandidateActor
            owner = CandidateActor.from_candidate(args.model, manifest=args.weight_manifest,
                     profile=runtime['profile'], recipe=protocol['recipe'], output=output / 'resident')
        elif runtime['kind'] == 'qwen25_legacy':
            owner = SharedActor.from_pretrained(args.model, weight_manifest=args.weight_manifest,
                     output=output / 'resident', recipe=protocol['recipe'],
                     attention=runtime['attention'], matmul_precision=runtime['matmul_precision'])
        else:
            raise ValueError('Unknown declared candidate runtime')
        if args.restore_checkpoint:
            atomic_write(output / 'restored-checkpoint.json', json_bytes(owner.restore_checkpoint(args.restore_checkpoint)))
        report['status'] = 'running'
        report['actor_identity'] = owner.freeze_identity()
        for spec in protocol['episodes']:
            snapshot = owner.capture_evaluation_state()
            folder = output / spec['episode_id']
            owner.begin_window(spec['episode_id'])
            owner.reseed(spec['sampling_seed'], label=spec['episode_id'])
            config = _config(owner, 'implementer', 'Frozen software work contract', {'implementer': 18})
            try:
                result = collect_software_episode(config, folder, transport=owner.transport,
                                                 model_identity=owner.freeze_identity())
                owner.finish_evaluation([], folder / 'evaluation-close')
            finally:
                guard = owner.finish_evaluation_guard(snapshot)
                atomic_write(folder / 'evaluation-guard.json', json_bytes(guard))
            if not guard['learning_unchanged'] or not guard['rng_restored_exactly']:
                raise ValueError('Software evaluation changed learner state or RNG restoration failed')
            report['episodes'].append({'episode_id': spec['episode_id'], 'sampling_seed': spec['sampling_seed'],
                'assessment': result['assessment'], 'termination': result['termination'],
                'opportunities': result['opportunities'], 'actions': result['actions'], 'evaluation_guard': guard})
            atomic_write(output / 'report.json', json_bytes(report))
            print(json_bytes({'episode': spec['episode_id'], 'assessment': result['assessment'].get('R'),
                              'termination': result['termination']['status']}).decode(), flush=True)
        report['status'] = 'complete'
    except (Exception, KeyboardInterrupt) as error:
        report.update(status='rejected_binding' if report['status'] == 'validating_binding' else 'interrupted',
                      error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        atomic_write(output / 'report.json', json_bytes(report))
        after = code_identity()
        atomic_write(output / 'source-after.json', json_bytes(after))
        atomic_write(output / 'source-comparison.json', json_bytes({'unchanged': source == after}))


if __name__ == '__main__':
    main()
