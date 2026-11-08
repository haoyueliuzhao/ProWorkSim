"""CPU-only1724 provider controls: no sockets, Docker, API, or host mutations."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_requests1724_v158 as env
from proworksim.software_benchmark_candidates_v054 import reference,write_new


def fixture(tmp_path, label='new'):
    folder=tmp_path/label;folder.mkdir()
    scope=folder/'scope.py';scope.write_text('# CPU scope; no live authorization.\n')
    scope_ref=reference(scope)
    diagnostic=write_new(folder/'diagnostic.json',{'scope':scope_ref,'current_DNS_ipv4':['8.8.8.8'],
        'probes':[{'ip':'8.8.8.8','port':port,'get_contract_valid':True} for port in env.PORTS],
        'synthetic_CPU_fixture_not_real_probe':True})
    resolution=write_new(folder/'resolution.json',{'scope':scope_ref,
        'source':'synthetic_CPU_fixture','hostname':'httpbin.org','ports':list(env.PORTS),
        'ipv4':['8.8.8.8'],'selected_ip':'8.8.8.8','automatic_retry':False,'diagnostic':diagnostic})
    calls=[]
    policy=SimpleNamespace(require_v066_allowed=lambda *a,**kw:calls.append((a,kw)))
    value=env.cold_environment(policy,scope_ref=scope_ref,directory=folder/'bindings',
        resolution_ref=resolution,resolution_source='synthetic_CPU_fixture')
    return value,folder,calls


def test_cold_exact_scope_and_single_task_profile_no_pip_or_host_network(tmp_path):
    first,folder,calls=fixture(tmp_path)
    second,_,_=fixture(tmp_path,'other')
    first.prepare();second.prepare()
    request=first.request_fields(env.TASK)
    assert first.validate_request(request,env.TASK) is first.tls
    assert first.capabilities(env.TASK)==['NET_BIND_SERVICE']
    assert first.capabilities('psf__requests-1766')==[]
    assert first.request_fields('psf__requests-1766')=={'environment_revision':None,'network_resolution':None}
    manifest=first.tls.environment_manifest()
    assert manifest['new_packages_installed'] is False and manifest['task_interpreter_unchanged'] is True
    assert manifest['host_mounts_or_network_configuration_changed'] is False
    assert manifest['effective_CA_changed'] is False and manifest['TLS_bytes_opaque_to_host'] is True
    assert calls==[]
    with pytest.raises(ValueError,match='identity changed'):
        second.validate_request(request,env.TASK)
    with pytest.raises(ValueError,match='binding'):
        bad=deepcopy(manifest);bad['cap_add'].append('NET_ADMIN')
        first.tls.validate_environment(write_new(folder/'bad.json',bad))


def attrs():
    return {'Image':'sha256:pinned','Mounts':[],
        'Config':{'Env':[],'Labels':{'owned':'this-container'}},
        'HostConfig':{'NetworkMode':'none','CapAdd':['NET_BIND_SERVICE'],'CapDrop':['ALL'],
            'SecurityOpt':['no-new-privileges:true'],'Privileged':False,'CpusetCpus':'0,1,2,3',
            'Memory':16*1024**3,'MemorySwap':16*1024**3,'NanoCpus':4*10**9,'PidsLimit':512,
            'ExtraHosts':['httpbin.org:127.0.0.1']}}


def resource_limits():
    return {'memory_bytes':16*1024**3,'nano_cpus':4*10**9,'pids_limit':512}


def test_exact_container_options_reject_foreign_capability_host_mapping_and_proxy():
    request={'mapping':{'instance_id':env.TASK},'image_id':'sha256:pinned','cpuset_cpus':'0,1,2,3'}
    env.validate_container_config(attrs(),request,resource_limits(),env.PROFILE)
    for field,value in [('NetworkMode','host'),('CapAdd',['NET_ADMIN','NET_BIND_SERVICE']),
                        ('ExtraHosts',['httpbin.org:127.0.0.1','foreign:127.0.0.2']),
                        ('Binds',['/tmp:/testbed'])]:
        changed=attrs();changed['HostConfig'][field]=value
        with pytest.raises(ValueError):env.validate_container_config(changed,request,resource_limits(),env.PROFILE)
    changed=attrs();changed['Config']['Env']=['HTTPS_PROXY=https://foreign.invalid']
    with pytest.raises(ValueError,match='proxy'):
        env.validate_container_config(changed,request,resource_limits(),env.PROFILE)
    assert env.fixture_environment({'HTTP_PROXY':'x','REQUESTS_CA_BUNDLE':'x','LEGIT':'y'})['LEGIT']=='y'
    assert 'REQUESTS_CA_BUNDLE' not in env.fixture_environment({'REQUESTS_CA_BUNDLE':'x'})


class Container:
    id='owned-1724'
    def __init__(self):self.attrs=attrs();self.commands=[];self.actions=[]
    def reload(self):pass
    def start(self,*a,**kw):self.actions.append('start');return 'started'
    def stop(self,*a,**kw):self.actions.append('stop');return 'stopped'
    def remove(self,*a,**kw):self.actions.append('remove');return 'removed'
    def exec_run(self,argv,**kwargs):
        self.commands.append(argv)
        source=argv[-1]
        if argv[0]=='/bin/bash':
            result='a'*40+'\n'+'b'*40+'\n'
        elif 'PWS_GRADER_BOUNDARY_V097:' in source:
            result='PWS_GRADER_BOUNDARY_V097:'+json.dumps({'namespaces':dict(net=1,mnt=2,pid=3,ipc=4),
                'cpus':[0,1,2,3],'affinity_source':'proc_self_status'})+'\n'
        elif 'has_set_blocking' in source:
            result=json.dumps({'executable':env.RELAY_PYTHON,'python_version':[3,12,0],
                'has_set_blocking':True,'httpbin_ipv4':['127.0.0.1'],'interfaces':['lo'],'gateway_present':False})
        elif 'hashlib.sha256' in source:
            result=json.dumps({'path':env.ORIGINAL_CA,'sha256':'c'*64})
        else:raise AssertionError('Unexpected container command')
        output=(result.encode(),b'') if kwargs.get('demux') else result.encode()
        return SimpleNamespace(output=output,exit_code=0)


def test_actual_wrapper_keeps_python2_and_closure_evaluator_finishes_before_cleanup(tmp_path):
    value,folder,calls=fixture(tmp_path);value.prepare()
    request={**value.request_fields(env.TASK),'mapping':{'instance_id':env.TASK,
        'official_tree':'b'*40,'public_python':'/original/python2'},'base_commit':'a'*40,
        'image_id':'sha256:pinned','cpuset_cpus':'0,1,2,3','path':str(folder/'initial-container.json'),
        'resource_key':'control-new-1724-gold'}
    container=Container();execs=[]
    class DockerAPI:
        def exec_create(self,identity,argv,**kwargs):
            assert identity==container.id;execs.append((argv,kwargs));return {'Id':'owned-exec'}
        def exec_start(self,identity,**kwargs):return SimpleNamespace(close=lambda:None)
        def exec_inspect(self,identity):return {'Running':False,'ExitCode':0}
    tracking={'owned_container_ids':[container.id],'create_identity':{'labels':{'owned':'this-container'}},
        'client':SimpleNamespace(api=DockerAPI())}
    def relay(channel,ip,**kwargs):
        assert ip=='8.8.8.8' and kwargs['instance_id']==env.TASK
        kwargs['on_ready']();assert kwargs['stop_event'].wait(2)
        return {'ok':True,'status':'completed','ready':True,'network_errors':[],'cleanup_errors':[],
            'error':None,'target_ip':ip,'target_hostname':'httpbin.org','listen_ports':[80,443],
            'connection_attempts':1,'max_active_observed':1,'application_payload_bytes':10,'connections':[]}
    value.tls.transport.relay_many=relay
    wrapper=value.tls.EnvironmentContainer(container,request,resource_limits(),tracking)
    tracking['environment_container']=wrapper
    def wrapped_official():
        assert wrapper.start()=='started'
        assert wrapper.stop()=='stopped'
        assert tracking['transport_result']
        assert container.actions==['start','stop']
        assert wrapper.remove()=='removed'
        return 'official-body'
    # This ordinary closure has no cleanup_container global; old globals-hook
    # lifecycle would reject it. The actual owned wrapper is the narrow seam.
    assert 'cleanup_container' not in wrapped_official.__globals__
    assert value.tls.run_official(wrapped_official,tracking=tracking)=='official-body'
    assert execs[0][0][:5]==[env.RELAY_PYTHON,'-S','-u','-B','-c']
    assert all('pip' not in ' '.join(argv) for argv in container.commands)
    assert any(argv[0]=='/original/python2' for argv in container.commands)
    assert value.tls.finish_transport(tracking)['original_ca_unchanged'] is True
    assert value.tls.cleanup_transport(tracking)==[]
    assert tracking['tls_lifecycle']['shared_harness_globals_modified'] is False
    assert all(x['relay_thread_finished'] for x in tracking['tls_lifecycle']['stop_remove_calls'])
    observed=json.loads((folder/'initial-container.json').read_bytes())
    identity={'instance_id':env.TASK,**value.request_fields(env.TASK)}
    receipt={'instance_id':env.TASK,'transport_result':tracking['transport_result']}
    quiet={'transport_result':tracking['transport_result'],'quiescent':True,'cleanup_errors':[],
        'deadline_reached':False,'TLS_lifecycle':tracking['tls_lifecycle']}
    result=env.validate_transport_evidence(receipt,quiet,observed,identity,folder,
                                           transport_directory=folder)
    assert result['ok'] is True
    assert value.validate_control_environment(observed,identity,mapping={'public_python':'/original/python2'})['passed']
    bad=deepcopy(quiet);bad['TLS_lifecycle']['stop_remove_calls'][0]['relay_thread_finished']=False
    with pytest.raises(ValueError,match='before actual container cleanup'):
        env.validate_transport_evidence(receipt,bad,observed,identity,folder,transport_directory=folder)
