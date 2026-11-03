"""Enter the real concrete evaluator and TLS cleanup hook without any Docker IO."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
forbidden = []


def deny(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto', 'socket.bind',
                 'subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'}:
        forbidden.append(event)
        raise RuntimeError('This evaluator control cannot contact Docker/network or spawn a process')


sys.addaudithook(deny)


def main():
    from swebench.harness import run_evaluation as official
    from swebench.harness.utils import make_test_spec
    from proworksim import software_benchmark_grading_requests_v116 as grading
    from proworksim import software_benchmark_requests_tls_v068 as lifecycle
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    task = 'psf__requests-1766'
    events, intercepted = [], []

    class CPUContainer:
        id = 'cpu-only-v116-owned-evaluator'
        name = 'cpu-only-v116-never-created'

        def start(self):
            events.append('real_evaluator_reached_scripted_start')
            raise RuntimeError('Intentional CPU stop before patch application or test execution')

    container = CPUContainer()
    with tempfile.TemporaryDirectory(prefix='pws-v116-real-evaluator-control-') as folder:
        folder = Path(folder)
        policy = SimpleNamespace(GRADING_ROOT=folder/'grading',
            require_v066_allowed=lambda *_a, **_kw: (_ for _ in ()).throw(
                RuntimeError('No execution authority may be used in this CPU control')))
        scorer = grading.scorer(policy, manifest_provider=lambda: {'CPU_ONLY_manifest': True})
        actual_factory = scorer._score.__globals__['diagnostics'].make_repaired_run_instance
        evaluator, provenance = actual_factory(official, folder/'diagnostics')
        namespace = evaluator.__globals__
        real_cleanup = official.cleanup_container
        assert namespace['cleanup_container'] is real_cleanup
        assert namespace is not vars(official)
        assert evaluator.__code__.co_name == 'run_instance'
        assert scorer.environment.tls.run_official is lifecycle.run_official
        assert actual_factory is grading.previous.original.diagnostics.make_repaired_run_instance
        namespace['RUN_EVALUATION_LOG_DIR'] = folder/'logs'

        def scripted_create(*_args, **_kwargs):
            events.append('real_evaluator_reached_scripted_create')
            return container

        namespace['create_container'] = scripted_create
        subprocess_module = real_cleanup.__globals__['subprocess']
        original_run = subprocess_module.run

        def scripted_cleanup_command(command, **kwargs):
            if command not in (['docker', 'stop', '--time=15', container.id],
                               ['docker', 'rm', '--force', container.id]):
                raise AssertionError('An unexpected subprocess would have been launched')
            intercepted.append(command)
            events.append('official_cleanup_'+command[1])
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        dataset = json.loads((grading.scope.ROOT/'artifacts/software-benchmark-v054/source/trusted-evaluation.json').read_bytes())
        row = next(item for item in dataset if item['instance_id'] == task)
        spec = make_test_spec(row)
        tracking = {'owned_container_ids': [container.id], 'environment_container': SimpleNamespace(
            delegate=container, finish_transport=lambda: events.append('finish_transport_before_cleanup'))}
        subprocess_module.run = scripted_cleanup_command
        try:
            result = scorer.environment.tls.run_official(evaluator, spec,
                {'instance_id': task, 'model_name_or_path': 'CPU-fixture', 'model_patch': ''},
                SimpleNamespace(), 'CPU-only-v116', timeout=1, skip_patch=True, tracking=tracking)
        finally:
            subprocess_module.run = original_run
        assert result is None
        assert namespace['cleanup_container'] is real_cleanup
        assert events == ['real_evaluator_reached_scripted_create', 'real_evaluator_reached_scripted_start',
                          'finish_transport_before_cleanup', 'official_cleanup_stop', 'official_cleanup_rm']
        assert tracking['tls_lifecycle']['cleanup_calls'] == 1
        assert tracking['tls_lifecycle']['finish_attempts_before_cleanup'] == 1
        assert tracking['tls_lifecycle']['binding_restored'] is True
        assert not forbidden
        value = {'version': 'v116-real-concrete-evaluator-tls-binding-control-r1', 'passed': True,
            'actual_task_spec': task, 'actual_official_evaluator_body_entered': True,
            'actual_official_cleanup_body_entered': True, 'scripted_dependencies': ['container creation/start', 'cleanup subprocess IO'],
            'evaluator_has_actual_cleanup_globals': True, 'evaluator_was_not_replaced_by_passthrough_wrapper': True,
            'events': events, 'intercepted_never_executed_cleanup_commands': intercepted,
            'TLS_lifecycle': tracking['tls_lifecycle'], 'official_diagnostic_provenance': provenance,
            'scorer_source': reference(grading.__file__), 'control_source': reference(__file__),
            'official_source': reference(official.__file__),
            'cold_interpreter': sys.version, 'forbidden_operation_attempts': forbidden,
            'Docker_operations': 0, 'model_calls': 0, 'network_connections': 0,
            'official_tests_executed': 0, 'completed_candidates_rescored': False,
            'runtime_gold_empty_qualification_complete': False}
    output = grading.scope.ROOT/'artifacts/software-benchmark-v116/concrete-evaluator-control-r1/summary.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    write_new(output, value)
    print(json.dumps({'passed': True, 'actual_concrete_evaluator_entered': True,
                      'Docker_operations': 0, 'summary': str(output)}))


if __name__ == '__main__':
    main()
