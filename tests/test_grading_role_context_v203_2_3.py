"""Scope isolation and strict environment equivalence without Docker or models."""
import copy
import pytest

from proworksim import software_benchmark_environment_v203_2_3 as environment
from proworksim import software_benchmark_grading_v203_2_3 as grading
from proworksim import software_benchmark_grading_environment_v066 as original_environment


def test_new_scoring_functions_use_only_new_resource_scope():
    policy = grading.scope.dispatch_view(grading.scope.require_grading_allowed)
    value = grading.scorer(policy)
    assert grading.REUSE_VERSION == 'v203.2.3-exact-v066-qualification-reuse-r1'
    assert value.validate_request.__globals__['policy'].BATCH_ROOT == grading.scope.BATCH_ROOT
    assert value.validate_request.__globals__['MAX_GRADERS'] == 1
    assert value.environment.TLS_TASKS == {environment.TLS_TASK}
    assert not value.environment.OFFLINE_TASKS
    assert value.environment.provider(environment.TLS_TASK) is value.environment.tls
    assert value.environment.provider('psf__requests-1921') is None
    assert original_environment.TLS_TASKS == {'psf__requests-1766', 'psf__requests-1921'}
    assert value.environment.tls.policy.BATCH_ROOT == grading.scope.BATCH_ROOT


def test_ordinary_environment_cannot_gain_capabilities_or_transport():
    assert environment.compare_task_environment({}, {'environment_revision':None, 'network_resolution':None},
        task='astropy__astropy-13033', load=lambda value:value) == {'environment_revision':None,'network_resolution':None}
    with pytest.raises(ValueError):
        environment.compare_task_environment({}, {'environment_revision':{'new':'fixture'},'network_resolution':None},
            task='astropy__astropy-13033',load=lambda value:value)


def test_tls_equivalence_ignores_only_scope_owners_not_ca_endpoints_or_packages():
    old = {'original_ca_changed':False,'tls_verification_changed':False,'policy':'old',
           'wheels':['pinned'], 'cap_add':['NET_ADMIN','NET_BIND_SERVICE']}
    current = {**old,'policy':'new'}
    identity = {'environment_revision':old,'network_resolution':{'ip':'fixed'}}
    fields = {'environment_revision':current,'network_resolution':{'ip':'fixed'}}
    proof = environment.compare_task_environment(identity,fields,task=environment.TLS_TASK,load=lambda value:value)
    assert proof['current_endpoint_health_claimed'] is False
    for key,value in (('original_ca_changed',True),('tls_verification_changed',True),('wheels',['other'])):
        tampered = copy.deepcopy(fields)
        tampered['environment_revision'][key] = value
        with pytest.raises(ValueError):
            environment.compare_task_environment(identity,tampered,task=environment.TLS_TASK,load=lambda value:value)
    with pytest.raises(ValueError):
        environment.compare_task_environment(identity,{**fields,'network_resolution':{'ip':'other'}},
            task=environment.TLS_TASK,load=lambda value:value)


def test_requests_historical_reuse_is_not_current_endpoint_admission(monkeypatch):
    value = grading.scorer(grading.scope.dispatch_view(grading.scope.require_grading_allowed))
    monkeypatch.setattr(grading.scope,'load',lambda ref:{'version':grading.REUSE_VERSION})
    with pytest.raises(ValueError,match='Current-batch gold/empty'):
        value.validate_qualification({}, {'instance_id':environment.TLS_TASK}, {})
