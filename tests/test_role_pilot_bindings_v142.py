"""Construction-only checks: no live grant, resource operation or model call."""
import ast
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_alignment_contract_v141 as alignment
from proworksim import software_benchmark_episode_v142 as episode
from proworksim import software_benchmark_grading_v142 as grading
from proworksim import software_benchmark_scope_v142 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_environment_v141 import _retain


def test_new_episode_actually_binds_new_groups_bundle_closure_and_host_memory():
    calls = []
    def guard(operation, **identity):
        calls.append(operation)
        return {'status': 'approved', 'execution_alignment_version': alignment.VERSION,
                'source_index': {'synthetic_CPU_fixture': True}}
    value = episode.build_episode(scope=scope, guard=guard)
    assert value.allowed_organization_ids == ('S1', 'FREE2', 'REVIEW2')
    assert value.new_system_parent_slice is False
    assert set(value.memory_integration_points.values()) == {1}
    assert value._run.__globals__['runtime'].__name__.endswith('_v141')
    assert value.run_episode.__globals__['_run'] is value._run
    imports = [node.module for node in ast.walk(value.memory_transformed_ast) if isinstance(node, ast.ImportFrom)]
    assert 'software_benchmark_project_closure_v141' in imports
    assert not any(name and 'v131' in name for name in imports)
    with pytest.raises(ValueError):
        value._row_and_config({'organization_id': 'CHIEF'}, False)
    with pytest.raises(PermissionError):
        episode.build_episode(scope=scope, guard=lambda *a, **k: {'status':'approved',
            'execution_alignment_version':'v131', 'source_index': {'old': True}})
    assert calls == ['v066.run']


def test_actual_controller_options_and_validator_share_new_32g_private_limits():
    from proworksim import software_benchmark_docker_actor_v066 as original
    value = episode.build_episode(scope=scope, guard=lambda *a, **k: {
        'status': 'approved', 'execution_alignment_version': alignment.VERSION, 'source_index': {'CPU': True}})
    provider = value.OwnedActorPair.create_container.__globals__
    assert provider['container_options'].__globals__ is provider['validate_container'].__globals__ is provider
    assert provider['ROLES']['controller'][1] == 32*scope.GIB
    assert original.ROLES['controller'][1] == 16*scope.GIB
    ref = {'sha256': 'a'*64}
    claim = {'key': 'controller-1', 'docker_name': 'pws-new-controller',
             'spec': {'role': 'controller', 'image_id': 'sha256:'+'b'*64}}
    volume = 'pws-v066-new-test-volume'
    options = provider['container_options']('controller', ref, claim, volume, ['/opt/pws-runtime/bin/python'])
    assert options['mem_limit'] == options['memswap_limit'] == 32*scope.GIB
    assert not options.get('cgroup_parent')
    attrs = {'Image': options['image'], 'Name': options['name'],
        'Config': {'Labels': options['labels'], 'User': options['user'], 'Tty': options['tty']},
        'HostConfig': {key: options[name] for key, name in {
            'NetworkMode':'network_mode', 'Privileged':'privileged', 'IpcMode':'ipc_mode',
            'CapDrop':'cap_drop', 'CapAdd':'cap_add', 'Memory':'mem_limit', 'MemorySwap':'memswap_limit',
            'NanoCpus':'nano_cpus', 'PidsLimit':'pids_limit', 'SecurityOpt':'security_opt'}.items()},
        'Mounts': [{'Type':'volume','Name':volume,'Destination':'/testbed','RW':False}]}
    container = SimpleNamespace(attrs=attrs, reload=lambda: None)
    assert provider['validate_container'](container, 'controller', ref, claim, volume) is attrs
    attrs['HostConfig']['Memory'] = 16*scope.GIB
    with pytest.raises(ValueError, match='reviewed resource'):
        provider['validate_container'](container, 'controller', ref, claim, volume)


def test_actual_diagnostic_reaches_scripted_claim_without_fake_formal_lease(tmp_path):
    row = {'slot_index': 123, 'slot_id': 'synthetic-diag', 'instance_id':'fixture__task-1', 'organization_id':'S1'}
    plan_file = tmp_path/'plan.json'
    plan = {'diagnostics':[{'index':1,'slot_id':row['slot_id'],'organization_id':'S1','model_calls':0}],
        'resources':{f'diagnostic-1-{role}':{'role':role,'diagnostic':True,'diagnostic_index':1,
            'slot_id':row['slot_id'],'instance_id':row['instance_id']} for role in ('actor','controller','volume')}}
    plan_ref = write_new(plan_file, plan)
    private_scope = SimpleNamespace(**{**vars(scope), 'PLAN_FILE': plan_file,
        'load': lambda ref: json.loads(open(ref['path']).read())})
    authority = {'status':'approved','execution_alignment_version':alignment.VERSION,
                 'source_index':{'CPU':True},'plan':plan_ref}
    def no_formal_lease(row):
        raise ValueError('No startup lease for this identity')
    value = episode.build_episode(scope=private_scope, guard=lambda *a, **k: authority,
                                   admission_check=no_formal_lease)
    claims = []
    class ClaimReached(RuntimeError):
        pass
    def claim(key):
        claims.append(key)
        raise ClaimReached('scripted boundary before any Docker operation')
    namespace = value._run.__globals__
    namespace.update(BATCH=tmp_path, _row_and_config=lambda *a: ({},{},{}), wait_capacity=lambda *a: {},
                     policy=SimpleNamespace(claim_resource=claim, ResourceBusy=scope.ResourceBusy))
    with pytest.raises(PermissionError, match='Diagnostic row'):
        value._run(row, {}, diagnostic=True, diagnostic_index=2)
    assert claims == []
    with pytest.raises(ClaimReached):
        value._run(row, {}, diagnostic=True, diagnostic_index=1)
    assert claims == ['diagnostic-1-actor']
    with pytest.raises(ValueError, match='No startup lease'):
        value._run(row, {}, diagnostic=False)
    assert claims == ['diagnostic-1-actor']


def test_new_scorer_actual_private_bindings_and_no_old_authority_or_control_reuse():
    value = grading.scorer(scope.dispatch_view(scope.require_grading_allowed), manifest_provider=lambda: {})
    namespace = value.validate_request.__globals__
    assert namespace['environment'] is value.environment
    assert namespace['policy'].VERSION == scope.VERSION
    assert namespace['validate_delivery_evidence'].__module__.endswith('_v141')
    assert namespace['_score'] is value._score
    assert namespace['Containers'] is value.Containers
    assert value._v142_reset_scorer._score.__globals__['validate_delivery_evidence'] is namespace['validate_delivery_evidence']
    assert namespace['MAX_GRADERS'] == 2
    assert grading.control_key('psf__requests-1921', 'gold') == 'control-v142-psf__requests-1921-gold'
    with pytest.raises(ValueError, match='requires fresh'):
        grading.reuse_value('psf__requests-1921', {}, {'environments': {}})


def test_later_tls_preparation_appends_without_overwriting_initial_pending(monkeypatch, tmp_path):
    task = 'psf__requests-1766'
    plan = {'environments': {task: {'configuration': {'synthetic': True}}}, 'resources': {
        grading.control_key(task, kind): {'role': 'control', 'instance_id': task, 'patch_kind': kind}
        for kind in ['gold', 'empty']}}
    plan_file = tmp_path/'plan.json'
    write_new(plan_file, plan)
    ready = [False]
    def fields(task):
        if not ready[0]:
            raise ValueError('No separately authorized endpoint probe yet')
        return {'environment_revision': {'synthetic': True}, 'network_resolution': {'synthetic': True}}
    private_scope = SimpleNamespace(PLAN_FILE=plan_file, COORDINATOR_ROOT=tmp_path/'coordinator',
        GRADING_ROOT=tmp_path/'grading', load=lambda ref: json.loads(open(ref['path']).read()),
        validate_plan=lambda value: value, dispatch_view=lambda guard: None,
        require_grading_allowed=lambda *a: None, retain=_retain)
    fake = SimpleNamespace(environment=SimpleNamespace(prepare=lambda: None, request_fields=fields),
        installation_manifest=lambda: {'synthetic': True}, LIMITS={'synthetic': True})
    monkeypatch.setattr(grading, 'scope', private_scope)
    monkeypatch.setattr(grading, 'scorer', lambda policy: fake)
    initial = grading.prepare_environment_qualifications_local()
    first = (tmp_path/'coordinator/qualification-preparation.json').read_bytes()
    assert len(initial['pending_environments']) == 1 and not initial['controls']
    ready[0] = True
    later = grading.prepare_environment_qualifications_local()
    assert len(later['controls']) == 2 and not later['pending_environments']
    assert (tmp_path/'coordinator/qualification-preparation.json').read_bytes() == first
    assert later['preparation_reference'] != initial['preparation_reference']
    assert later['preparation_reference']['path'] != reference(tmp_path/'coordinator/qualification-preparation.json')['path']
