"""Frozen software evaluation with the selected shared actor, no learning export."""

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.online_collection import _config
from proworksim.online_training import SharedActor
from proworksim.software_collection import collect_software_episode
from proworksim.storage import atomic_write, json_bytes, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--weight-manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--restore-checkpoint')
    args = parser.parse_args()
    protocol = read_json(Path(args.protocol))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    source = code_identity()
    atomic_write(output / 'source-before.json', json_bytes(source))
    atomic_write(output / 'protocol.json', json_bytes(protocol))
    report = {'version': 'software-frozen-model-v0.15', 'status': 'loading', 'episodes': [],
              'training_export': False, 'actual_optimizer_steps': {'actor': 0, 'critic': 0}}
    try:
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
        report.update(status='interrupted', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        atomic_write(output / 'report.json', json_bytes(report))
        after = code_identity()
        atomic_write(output / 'source-after.json', json_bytes(after))
        atomic_write(output / 'source-comparison.json', json_bytes({'unchanged': source == after}))


if __name__ == '__main__':
    main()
