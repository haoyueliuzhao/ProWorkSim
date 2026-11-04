"""One actual v118->v110 selected-entry dispatch, with only sync/test IO scripted."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def run():
    counts = {'network': 0, 'process': 0}
    def audit(event, args):
        if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'):
            counts['network'] += 1
            raise RuntimeError('The actor binding CPU control cannot use the network')
        if event in ('subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'):
            counts['process'] += 1
            raise RuntimeError('Only scripted sync/test IO is allowed in this CPU control')
    sys.addaudithook(audit)
    from proworksim import software_benchmark_managed_actor_v118 as current
    from proworksim import software_benchmark_managed_actor_v110 as selected
    from proworksim import software_benchmark_managed_actor_v106 as preflight
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_benchmark_candidates_v054 import reference
    mro = [cls.__module__ for cls in current.ManagedOperationSession.__mro__]
    assert mro[:4] == ['proworksim.software_benchmark_managed_actor_v118',
                       'proworksim.software_benchmark_managed_actor_v110',
                       'proworksim.software_benchmark_managed_actor_v106',
                       'proworksim.software_benchmark_managed_actor_v103'], mro
    with tempfile.TemporaryDirectory(prefix='pws-v118-actor-binding-') as temporary:
        folder = Path(temporary)
        public = folder/'public'
        (public/'tests').mkdir(parents=True)
        (public/'tests/test_math.py').write_text('def test_ok(): pass\n')
        task = 'fixture__actor-118'
        manifest = capture_repository(public, folder/'snapshot', task_id=task,
            problem_statement='Synthetic public selected-test routing control.', source_identity={
                'instance_id': task, 'repo': 'fixture/repo', 'base_commit': 'a'*40, 'dataset_revision': 'b'*40})
        baseline = json.loads((manifest.parent/'initial-tree.json').read_bytes())
        entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': task,
                 'argv': ['/public/python', '-m', 'pytest'], 'cwd': '/testbed',
                 'timeout_seconds': 600, 'hidden_material_used': False}
        hard = time.monotonic()+600
        session = current.ManagedOperationSession(config={'instance_id': task, 'lifecycle_deadline': hard},
            baseline=baseline, entry=entry, environment={}, root=public)
        source = current.baseline_source_reference(baseline)
        def payload(request):
            return current.make_delta(baseline, baseline['files'], baseline['entry_metadata'], request=request)
        checked = []
        def sync(root, candidate, **kwargs):
            assert candidate['tree_sha256'] == baseline['tree']['tree_sha256']
            return {'tree_sha256': candidate['tree_sha256'], 'source_files_synchronized': True}
        def execute(chosen, *, root, environment, request, candidate_tree_sha256):
            checked.append(copy.deepcopy(chosen))
            assert chosen['argv'] == ['/public/python', '-m', 'pytest', '--', 'tests/test_math.py::test_ok']
            assert request['public_test_selection'] == {'kind': 'pytest', 'targets': ['tests/test_math.py::test_ok']}
            return {'passed': True, 'execution': {'executed': True, 'argv': chosen['argv'],
                      'input_tree_sha256': candidate_tree_sha256, 'source_reference': request['source_reference']},
                    'groups': {'public_repository_tests': {'tests': [{'test_id': 'cpu-only', 'passed': True}]}},
                    'repository_collection_errors': []}
        request = {'instance_id': task, 'source_reference': source, 'tree_sha256': baseline['tree']['tree_sha256'],
                   'hard_deadline_monotonic': hard-1, 'hidden_evaluation': False, 'arbitrary_command': False}
        with patch.object(preflight, 'synchronize_tree', sync), patch.object(selected, 'synchronize_tree', sync), patch.object(selected, 'run_public_entry', execute):
            session.execute('sync_preflight', payload({**request, 'model_calls_before_preflight': 0}))
            choice = {'kind': 'pytest', 'targets': ['tests/test_math.py::test_ok']}
            result, receipt = session.execute('managed_public_test', payload({**request,
                'version': selected.PUBLIC_TEST_SELECTION_VERSION, 'call_index': 1,
                'public_test_selection_revision': selected.PUBLIC_TEST_SELECTION_VERSION, 'public_test_selection': choice}))
        assert session.test_calls == 1 and len(checked) == 1 and receipt['operation_executed'] is True
        assert result['execution']['public_test_selection'] == choice
        assert session.run_generation_diagnostic() is None
    assert not any(counts.values())
    output = {'version': 'v118-actual-managed-selected-entry-parent-control-r1', 'passed': True,
              'actual_class_MRO': mro, 'real_v110_execute_selected_request': True,
              'reconstruction_and_selection_validation_real': True,
              'only_sync_and_public_test_execution_scripted': True, 'selected_argv': checked[0]['argv'],
              'formal_actor_does_not_repeat_fixture_diagnostic': True, 'forbidden_operation_counts': counts,
              'source': reference(ROOT/'src/proworksim/software_benchmark_managed_actor_v118.py'),
              'frozen_v117_changed': False, 'model_calls': 0, 'Docker_operations': 0}
    destination = ROOT/'artifacts/software-benchmark-v118/generation-admission-r1'
    destination.mkdir(parents=True, exist_ok=True)
    (destination/'selected-entry-control.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
