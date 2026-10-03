"""Bind completed targeted CPU controls to the same frozen source bytes.

This only verifies the compact control indices and source fingerprints. It does
not rerun historical tests or reinterpret scripted CPU routes as model samples.
"""

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import reference, write

SOURCE = Path(__file__).resolve().parents[1]


def qualify(controls, output):
    controls = Path(controls).resolve()
    source = code_identity()
    if source['code_dirty'] is not False:
        raise ValueError('Freeze a clean checkout before binding the final qualification')
    checks = read_json(controls / 'integrated-checks.json')
    if (checks['source_tree_sha256'] != source['source_tree_sha256']
            or any(row['returncode'] != 0 for row in checks['checks'])):
        raise ValueError('Tested source or required checks differ')
    for relative, expected in checks['file_sha256'].items():
        if digest((SOURCE / relative).read_bytes()) != expected:
            raise ValueError('Qualified file changed: ' + relative)
    paths = {name: controls / relative for name, relative in {
        'world': 'world/summary.json', 'mapper': 'mapper/index.json',
        'learning': 'learning/summary.json', 'sdk_tokenizer': 'source-sdk-tokenizer/qualification.json',
        'integration': 'integrated-checks.json'}.items()}
    evidence = {name: read_json(path) for name, path in paths.items()}
    world, tokenizer = evidence['world'], evidence['sdk_tokenizer']
    if (world['model_calls'] != 0 or len(world['controls']) != 9
            or sum(row['R'] == 1 for row in world['controls']) != 3
            or tokenizer.get('passed') is not True or tokenizer['model_calls'] != 0
            or tokenizer['source']['source_tree_sha256'] != source['source_tree_sha256']
            or evidence['learning']['gpu_calls'] != 0
            or evidence['learning']['actual_consumption']['backward_decisions_completed'] != 16):
        raise ValueError('New-source CPU control evidence is incomplete')
    result = {'version': 'software-allocation-qualification-v0.29', 'source': source,
              'passed': True, 'model_calls': 0, 'gpu_used': False,
              'evidence': {name: reference(path) for name, path in paths.items()},
              'checks': checks['checks'], 'tested_files_sha256': checks['file_sha256'],
              'world_controls': world['controls'], 'mapper_controls': evidence['mapper']['controls'],
              'tiny_cpu_learning': evidence['learning']['actual_consumption'],
              'source_context_controls': tokenizer['controls'],
              'scope': 'Existing targeted CPU evidence bound by exact source/file hashes to the clean execution commit. No repeated historical suite, new model sampling or 9B effect claim.'}
    write(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controls', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(qualify(args.controls, args.output)['passed'])


if __name__ == '__main__':
    main()
