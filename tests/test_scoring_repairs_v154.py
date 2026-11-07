"""Exercise the actual container-construction branch with a CPU fake delegate."""
import inspect
from types import SimpleNamespace

from proworksim import software_benchmark_rescore_v154 as repair
from proworksim.software_benchmark_candidates_v054 import write_new


def construct(tmp_path,monkeypatch,task):
    scorer=repair.build_scorer(manifest_provider=lambda:{})
    actual_create=inspect.getclosurevars(scorer.Containers.create).nonlocals['create']
    namespace=actual_create.__globals__
    monkeypatch.setitem(namespace,'validate_options',lambda *_:None)
    monkeypatch.setitem(namespace,'validate_attrs',lambda *_:None)
    monkeypatch.setattr(namespace['policy'],'require_v066_allowed',lambda *a,**k:{})
    claim=write_new(tmp_path/'claim.json',{'key':'cpu','plan':{'sha256':'a'*64},'docker_name':'cpu-owned'})
    observed={'mapping':{'instance_id':task},'capacity_claim':claim,'cpuset_cpus':'0,1,2,3'}
    tracking={'owned_container_ids':[]}
    options=[]
    container=SimpleNamespace(id='cpu-only',attrs={},reload=lambda:None,stop=lambda **kw:None)
    def create(**kw):
        options.append(kw)
        return container
    wrapper=scorer.Containers(SimpleNamespace(create=create),'cpu-image',observed,tracking).create()
    tracking['deadline_timer'].cancel()
    return scorer,wrapper,options[0]


def test_actual_tls_constructor_uses_the_same_qualified180_manifest(tmp_path,monkeypatch):
    scorer,wrapper,options=construct(tmp_path,monkeypatch,'psf__requests-1766')
    provider=scorer.environment.provider('psf__requests-1766')
    assert type(wrapper) is provider.EnvironmentContainer
    assert provider is scorer.environment.tls
    assert provider.transport.Limits().idle_seconds==180
    assert repair.previous.current_environment.assert_runtime_binding(provider)
    assert options['network_mode']=='none' and options['cap_add']==['NET_ADMIN','NET_BIND_SERVICE']


def test_actual_offline_build_constructor_sets_owned_wheelhouse_without_host_network(tmp_path,monkeypatch):
    scorer,wrapper,options=construct(tmp_path,monkeypatch,'pytest-dev__pytest-6197')
    assert type(wrapper) is scorer.ObservedContainer
    environment=options['environment']
    assert environment['PIP_NO_INDEX']=='1'
    assert environment['PIP_FIND_LINKS']=='file:///pws-v154-build-wheels'
    assert options['network_mode']=='none' and options['cap_add']==[]
    plan=repair.load(repair.reference(repair.RUN/'offline-build-plan.json'))
    assert plan['original_build_requires']==['setuptools>=40.0','setuptools-scm','wheel']
    assert plan['host_installation'] is False and plan['automatic_download'] is False
