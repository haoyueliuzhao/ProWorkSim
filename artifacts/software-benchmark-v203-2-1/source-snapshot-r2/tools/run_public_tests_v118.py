"""Public stdlib-only launcher copied into the existing native actor.

Invoke with /opt/pws-runtime/bin/python /opt/pws-runtime/public-test.py
--selection '{"kind":"pytest","targets":["tests/test_x.py::test_y"]}'.
This is a convenience entry, not an immutable permission gate for native bash.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def library():
    source = Path(__file__).resolve()
    here = source.parent
    path = here/('public-test-library.py' if source.name == 'public-test.py' else 'public_test_library_v118.py')
    spec = importlib.util.spec_from_file_location('_v118_public_test_cli_library', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate selection JSON key')
        value[key] = item
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', default='{"kind":"full"}', help='Bounded public selection JSON')
    args = parser.parse_args()
    if len(args.selection.encode()) > 16384:
        raise ValueError('Public selection JSON is too large')
    selected = json.loads(args.selection, object_pairs_hook=strict_object)
    if not isinstance(selected, dict):
        raise ValueError('Public selection JSON must be an object')
    result = library().run_native_public_test(selected)
    output = result.pop('output')
    print(output, end='' if output.endswith('\n') else '\n')
    print('\nPublic-test execution receipt: ' + json.dumps(result, ensure_ascii=False))
    return 124 if result['timed_out'] else max(0, result['returncode']) if result['returncode'] >= 0 else 128-result['returncode']


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print('Public test selection refused: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
