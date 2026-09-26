"""Execute an explicitly frozen native-model work protocol with shared online RL."""

import argparse
import importlib
import importlib.metadata
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.online_training import SharedActor, run_online_windows
from proworksim.storage import atomic_write, json_bytes, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--weight-manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--restore-checkpoint')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    protocol = read_json(Path(args.protocol))
    runtime = protocol['runtime']
    dependencies = {name: importlib.metadata.version(name) for name in ('duckdb', 'openpyxl', 'torch', 'transformers', 'peft')}
    if dependencies['duckdb'] != '1.5.5':
        raise ValueError('Use the same project-pinned DuckDB executor as the source contract')
    atomic_write(output / 'runtime-dependencies.json', json_bytes(dependencies))
    atomic_write(output / 'launch-protocol.json', json_bytes(protocol))
    before = code_identity()
    atomic_write(output / 'source-before.json', json_bytes(before))
    owner = None
    try:
        if runtime['kind'] == 'qwen_hybrid':
            from proworksim.candidate_runtime_v015 import CandidateActor
            owner = CandidateActor.from_candidate(args.model, manifest=args.weight_manifest,
                        profile=runtime['profile'], recipe=protocol['recipe'], output=output / 'resident')
        elif runtime['kind'] == 'qwen25_legacy':
            owner = SharedActor.from_pretrained(args.model, weight_manifest=args.weight_manifest,
                        output=output / 'resident', recipe=protocol['recipe'],
                        attention=runtime['attention'], matmul_precision=runtime['matmul_precision'])
        else:
            raise ValueError('Unknown explicitly registered runtime; no silent fallback')
        if args.restore_checkpoint:
            atomic_write(output / 'restored-checkpoint.json', json_bytes(owner.restore_checkpoint(args.restore_checkpoint)))
        module, name = protocol.get('collector', 'proworksim.online_collection:collect_window').split(':', 1)
        collector = getattr(importlib.import_module(module), name)
        result = run_online_windows(owner, protocol, output / 'online', collector)
        print(json_bytes({'status': result['status'], 'actor_steps': owner.actor_steps,
                          'critic_steps': owner.critic_steps, 'output': str(output)}).decode(), flush=True)
    except (Exception, KeyboardInterrupt) as error:
        atomic_write(output / 'interruption.json', json_bytes({'type': type(error).__name__, 'message': str(error),
            'actor_steps': owner.actor_steps if owner else None, 'critic_steps': owner.critic_steps if owner else None,
            'scope': 'No result-based retry, role substitution, state repair or imputed future slots'}))
        raise
    finally:
        after = code_identity()
        atomic_write(output / 'source-after.json', json_bytes(after))
        atomic_write(output / 'source-comparison.json', json_bytes({'unchanged': before == after}))


if __name__ == '__main__':
    main()
