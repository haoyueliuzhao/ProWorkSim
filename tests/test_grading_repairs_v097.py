import builtins
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from proworksim import software_benchmark_grader_probe_v097 as probe
from proworksim import software_benchmark_grading_repairs_v097 as repair
from proworksim import software_benchmark_scorer_v066 as original
from proworksim.software_benchmark_candidates_v054 import reference


def observation(*, cpus=None, namespaces=None):
    return {"cpus": [1, 3, 5, 7] if cpus is None else cpus,
        "namespaces": namespaces or {key: os.stat('/proc/self/ns/' + key).st_ino + 1
                                      for key in probe.NAMESPACES},
        "affinity_source": "proc_self_status"}


def frame(value):
    return (probe.PREFIX + json.dumps(value) + '\n').encode()


def test_legacy_interpreter_branch_reads_actual_kernel_record_without_sched_getaffinity():
    real_import = builtins.__import__
    legacy_os = SimpleNamespace(stat=os.stat)

    def legacy_import(name, *args, **kwargs):
        return legacy_os if name == 'os' else real_import(name, *args, **kwargs)

    namespace = {'__builtins__': {**vars(builtins), '__import__': legacy_import}}
    output = io.StringIO()
    with redirect_stdout(output):
        exec(probe.PROBE_SOURCE, namespace)
    result = probe.parse_probe(output.getvalue().encode())
    assert result['affinity_source'] == 'proc_self_status'
    assert result['cpus'] == sorted(os.sched_getaffinity(0))
    assert result['namespaces'] == {key: os.stat('/proc/self/ns/' + key).st_ino
                                     for key in probe.NAMESPACES}


def test_framing_keeps_noise_but_rejects_empty_ambiguous_or_malformed_evidence(tmp_path):
    body = b'unrelated startup message\n' + frame(observation())
    fake = SimpleNamespace(exec_run=lambda argv, **kw: SimpleNamespace(
        exit_code=0, output=(body, b'warning\n')))
    value, ref = probe.observe(fake, '/task/python', tmp_path / 'probe.json')
    evidence = json.loads(Path(ref['path']).read_bytes())
    assert value == observation()
    assert evidence['stdout']['utf8_prefix'].startswith('unrelated startup message')
    assert evidence['argv'][1:3] == ['-S', '-c']
    for invalid in [b'', frame(observation()) * 2, frame(observation(cpus=[True])),
                    frame(observation(cpus=[3, 1])), probe.PREFIX.encode() + b'{"cpus":[],"cpus":[]}']:
        with pytest.raises(ValueError):
            probe.parse_probe(invalid)


def test_failed_probe_keeps_error_reply_and_never_produces_observation(tmp_path):
    fake = SimpleNamespace(exec_run=lambda argv, **kw: SimpleNamespace(
        exit_code=1, output=(b'', b'AttributeError: unavailable\n')))
    path = tmp_path / 'failed.json'
    with pytest.raises(ValueError, match='interpreter failed'):
        probe.observe(fake, '/task/python', path)
    saved = json.loads(path.read_bytes())
    assert saved['status'] == 'technical_unknown' and saved['exit_code'] == 1
    assert 'observation' not in saved and saved['stderr']['utf8_prefix'].startswith('AttributeError')


def private_fixture(tmp_path, value):
    events = []
    path = tmp_path / 'initial.json'
    path.write_text(json.dumps({'head_git_tree': 'original-tree', 'working_tree_clean': True}))

    class Base:
        def start(self, *args, **kwargs):
            events.append('prepare_original_baseline')
            return 'started'

    namespace = {**vars(original),
        'policy': SimpleNamespace(require_v066_allowed=lambda op, **kw: events.append(op)),
        'validate_attrs': lambda *a: events.append('validate_attrs'),
        'base': SimpleNamespace(**{**vars(original.base), 'PreparationObservedContainer': Base})}
    namespace['score_request'] = repair._bind(original.score_request, namespace)
    namespace['_score'] = repair._bind(original._score, namespace)
    namespace['installation_manifest'] = lambda: {'original': True}
    fixture = ModuleType('cpu_fixture')
    fixture.__dict__.update(namespace)
    bound = repair.bind_scorer(fixture)
    instance = object.__new__(bound.ObservedContainer)
    instance.preparation = {'path': str(path), 'mapping': {'instance_id': 'legacy-task',
        'official_tree': 'original-tree', 'public_python': '/task/python'},
        'cpuset_cpus': '1,3,5,7', 'image_id': 'original-image', 'resource_key': 'control-legacy'}
    instance.delegate = SimpleNamespace(attrs={}, reload=lambda: events.append('reload'),
        exec_run=lambda argv, **kwargs: SimpleNamespace(exit_code=0, output=(frame(value), b'')))
    return bound, instance, events, path


@pytest.mark.parametrize('mismatch', [None, 'cpu', 'namespace'])
def test_real_bound_start_keeps_cpu_namespace_and_baseline_guards(tmp_path, mismatch):
    value = observation()
    if mismatch == 'cpu':
        value['cpus'] = [1]
    if mismatch == 'namespace':
        value['namespaces']['net'] = os.stat('/proc/self/ns/net').st_ino
    bound, instance, events, path = private_fixture(tmp_path, value)
    if mismatch:
        with pytest.raises(ValueError):
            instance.start()
        assert 'namespace_evidence' not in json.loads(path.read_bytes())
    else:
        assert instance.start() == 'started'
        observed = json.loads(path.read_bytes())
        assert observed['namespace_evidence']['all_distinct'] is True
        assert reference(tmp_path / 'private-boundary-probe-v097.json') == observed['boundary_probe']
    assert events[0] == 'v066.grader.start' and 'prepare_original_baseline' in events
    assert bound.Containers.create.__globals__['ObservedContainer'] is bound.ObservedContainer
    assert bound._score.__globals__['Containers'] is bound.Containers


@pytest.mark.parametrize('read_failure', [False, True])
def test_real_private_evaluator_binding_reads_CA_before_removal(tmp_path, read_failure):
    bound, _, _, _ = private_fixture(tmp_path, observation())
    old = original.environment.tls.run_official
    events = []
    state = {'removed': False}
    container = SimpleNamespace(id='owned-grader')

    def cleanup(client, target, logger):
        state['removed'] = True
        events.append('remove')

    namespace = {'cleanup_container': cleanup}
    exec('def run_instance(client, container, logger):\n    cleanup_container(client, container, logger)\n    return "official-result"\n', namespace)

    def finish():
        assert not state['removed']
        events.append('CA_read_while_alive')
        if read_failure:
            raise ValueError('CA unavailable')

    tracking = {'owned_container_ids': [container.id], 'environment_container':
                SimpleNamespace(delegate=container, finish_transport=finish)}
    # This is the callback read by the actual newly bound _score code path.
    actual = bound._score.__globals__['environment'].tls.run_official
    assert actual(namespace['run_instance'], None, container, None, tracking=tracking) == 'official-result'
    assert events == ['CA_read_while_alive', 'remove']
    assert namespace['cleanup_container'] is cleanup
    assert original.environment.tls.run_official is old
    assert tracking.get('transport_cleanup_errors', []) == (['CA unavailable'] if read_failure else [])
