"""Continue the original unconsumed Qwen tasks with one asynchronous scorer."""
from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import importlib.util
import inspect
import json

from proworksim import software_benchmark_qwen_scope_v084 as scope

VERSION = 'v084-Qwen-tolerant-status-single-grader-recovery-r1'


def old_runner():
    spec = importlib.util.spec_from_file_location('v084_frozen_adaptive_runner', scope.ROOT/'tools/run_adaptive_v076.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@contextmanager
def executors(stop):
    with ThreadPoolExecutor(max_workers=4) as generation, ThreadPoolExecutor(max_workers=1) as grading:
        try:
            yield generation, grading
        finally:
            stop.set()


def binding():
    old = old_runner()
    tree, count = ast.parse(inspect.getsource(old._run)), 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'proworksim.software_benchmark_episodes_v076':
            if [(n.name, n.asname) for n in node.names] != [('EpisodeBindings', None)]:
                raise ValueError('Unexpected original episode import')
            node.module = 'proworksim.software_benchmark_episodes_v084'
            count += 1
    if count != 1:
        raise ValueError('Require the single reviewed Qwen binding substitution')
    namespace = {**old._run.__globals__, 'scope': scope, 'VERSION': VERSION, 'executors': executors}
    # No startup/automatic-API logic from the old run() is copied.  Only _run's
    # primary branch is entered, and it discovers the four unchanged residents.
    exec(compile(ast.fix_missing_locations(tree), 'v084-private-Qwen-runner', 'exec'), namespace)
    return namespace['_run']


def run():
    with ExitStack() as cleanup:
        return binding()('primary', cleanup)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
