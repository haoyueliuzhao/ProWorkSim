"""Offline real SymPy reporter/hash-child controls over new tiny test fixtures."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shlex
import tempfile

from proworksim.software_benchmark_public_test_evidence_v130 import execute_public_entry
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'artifacts/software-benchmark-v130/public-test-evidence-controls-r1'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('frozen_scorer_loader', ROOT/'tools/run_offline_scorer_v096.py')
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    command, environment = loader.launch_spec(['-c', 'pass'])
    # Only this fixture's Python wrapper enables ordinary site processing so
    # that the same observer reaches the framework's normal hash subprocess.
    flags = command.index('-B')
    results = []
    with tempfile.TemporaryDirectory(prefix='pws-v130-sympy-fixture-') as directory:
        root = Path(directory)
        wrapper = root/'python-fixture'
        wrapper.write_text('#!/bin/sh\nexec '+shlex.join(command[:flags])+ ' -B "$@"\n')
        wrapper.chmod(0o755)
        (root/'bin').mkdir()
        (root/'bin/test').write_text('''import os,sys
from sympy.testing.runtests import run_in_subprocess_with_hash_randomization
code=run_in_subprocess_with_hash_randomization("run", module="pws_sympy_fixture",
    command=os.environ["PWS_FIXTURE_PYTHON"], force=True)
sys.exit(code)
''')
        (root/'pws_sympy_fixture.py').write_text('''import os
from sympy.testing.runtests import PyTestReporter, SymPyTests
def run():
    reporter=PyTestReporter(colors=False)
    tests=SymPyTests(reporter)
    tests._testfiles=[] if os.environ["PWS_FIXTURE_KIND"]=="empty" else [os.environ["PWS_FIXTURE_TEST"]]
    return int(not tests.test(sort=True))
''')
        test = root/'test_fixture.py'
        env = {**environment, 'PWS_FIXTURE_PYTHON': str(wrapper),
            'PWS_FIXTURE_TEST': str(test),
            'PYTHONPATH': str(root)+':'+environment['PYTHONPATH']}
        for kind, source, expected in [
            ('pass', 'def test_small():\n    assert 2 + 2 == 4\n', 'verified'),
            ('empty', '', 'no_tests'),
            ('skip', 'from sympy.testing.pytest import skip\ndef test_small():\n    skip("fixture")\n', 'all_skipped_or_xfailed'),
        ]:
            test.write_text(source)
            result = execute_public_entry({'argv': [str(wrapper), 'bin/test']},
                root=root, environment={**env, 'PWS_FIXTURE_KIND': kind}, timeout_seconds=20)
            write_new(OUTPUT/(kind+'.json'), result)
            assert result['validation_status'] == expected, result
            assert result['test_evidence']['report_count'] == 1, result
            assert result['test_evidence']['source']['pid'] != result['test_evidence']['source']['process_group'], result
            results.append({'kind': kind, 'expected': expected, 'result': reference(OUTPUT/(kind+'.json')),
                'real_cached_SymPy_reporter': True, 'original_hash_subprocess_used': True})
    report = {'version': 'v130-real-cached-SymPy-public-observer-controls-r1', 'passed': True,
        'cases': results, 'API_calls': 0, 'Docker_operations': 0, 'benchmark_tests': 0,
        'fixture_test_functions_only': True, 'Django_dependency_available': False,
        'Django_validation_boundary': 'The actual unittest TextTestRunner result path is controlled; no installed Django frontend was executed.'}
    print(write_new(OUTPUT/'sympy-summary.json', report))


if __name__ == '__main__':
    main()
