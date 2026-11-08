"""Zero-network controls for separate1724 authority, lane and probe limits."""
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import ssl
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v160 as scope
from proworksim.software_benchmark_candidates_v054 import reference,write_new


def setup_scope(tmp_path,monkeypatch):
    cpu=write_new(tmp_path/'cpus.json',{'uid':os.getuid(),'cpu_ids':list(range(176))})
    monkeypatch.setattr(scope,'SOURCE_CPU_POOL_FILE',Path(cpu['path']))
    monkeypatch.setattr(scope,'CPU_POOL_FILE',Path(cpu['path']))
    for name,path in [('BATCH_ROOT',tmp_path/'batch'),('PLAN_FILE',tmp_path/'plan.json'),
        ('AUTH_FILE',tmp_path/'control-authority.json'),('PROBE_AUTH_FILE',tmp_path/'probe-authority.json'),
        ('STANDING_POLICY_FILE',tmp_path/'standing.json')]:
        monkeypatch.setattr(scope,name,path)
    write_new(scope.STANDING_POLICY_FILE,{'ordinary_user_owned_experiment_docker':True})
    image='sha256:'+'d'*64
    plan={'version':scope.VERSION,'constraints':scope.CONSTRAINTS,'model_calls':0,'rows':[],
        'host_cpu_pool':cpu,'environments':{scope.TASK:{'image_id':image}},
        'resources':{key:{'role':'control','instance_id':scope.TASK,'patch_kind':key.rsplit('-',1)[1],
                     'image_id':image} for key in scope.CONTROL_KEYS}}
    planref=write_new(scope.PLAN_FILE,plan)
    sources=write_new(tmp_path/'sources.json',{'files':[reference(scope.__file__)]})
    base={'status':'approved','scope':reference(scope.__file__),'standing_policy':reference(scope.STANDING_POLICY_FILE),
          'source_index':sources,'model_calls':0,'shared_host_configuration_changes':0}
    control={**base,'version':'v160-requests1724-control-authority-r1','plan':planref,
        'resource_keys':list(scope.CONTROL_KEYS),'constraints':scope.CONSTRAINTS,'maximum_containers':2,
        'maximum_concurrent_graders':1,'maximum_real_tls_sessions':2,
        'maximum_tcp_connections_total':1024,'maximum_transfer_bytes_total':128*1024**2}
    probe={**base,'version':'v160-requests1724-probe-authority-r1','instance_id':scope.TASK,
        'hostname':'httpbin.org','ports':[80,443],'maximum_connections':4,
        'maximum_application_bytes':64*1024,'Docker_operations':0}
    write_new(scope.AUTH_FILE,control);write_new(scope.PROBE_AUTH_FILE,probe)
    return plan


def test_separate_ordinary_user_scope_exact_two_controls_and_nonoverlapping_lane(tmp_path,monkeypatch):
    plan=setup_scope(tmp_path,monkeypatch)
    assert scope.cpu_set('grader',0)=='112,113,114,115'
    assert scope.require_grading_allowed('v066.control')['maximum_containers']==2
    assert scope.require_probe_allowed()['maximum_connections']==4
    for operation in ('v066.api.request','v066.actor.create','v066.model.start','v066.score'):
        with pytest.raises(PermissionError):scope.require_grading_allowed(operation)
    with pytest.raises(PermissionError):scope.require_grading_allowed('v066.control',instance_id='other')
    with pytest.raises(PermissionError):scope.require_grading_allowed('v066.control',slot_id='old-model-slot')
    for role,lane in [('grader',1),('actor',0),('model',0)]:
        with pytest.raises(ValueError):scope.cpu_set(role,lane)
    wrong=deepcopy(plan);wrong['resources']['third-control']=wrong['resources'][scope.CONTROL_KEYS[0]]
    with pytest.raises(ValueError):scope.validate_plan(wrong)
    guard=scope.dispatch_view()
    with pytest.raises(PermissionError):guard.claim_resource('actor-15757')
    with pytest.raises(PermissionError):guard.claim_resource(scope.CONTROL_KEYS[0],lane=1)
    assert not (scope.BATCH_ROOT/'resource-claims').exists()


def test_probe_exact_four_mocked_direct_connections_and_strict_tls(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('v160_probe_cpu',Path(__file__).resolve().parents[1]/'tools/check_httpbin_direct_v160.py')
    probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    for name in ('OUTPUT','INTENT','RESOLUTION'):
        monkeypatch.setattr(probe,name,tmp_path/(name.lower()+'.json'))
    monkeypatch.setattr(scope,'require_probe_allowed',lambda *_:None)
    identity={'scope':reference(scope.__file__),'instance_id':scope.TASK}
    monkeypatch.setattr(probe,'readonly_panel_identity',lambda:identity)
    monkeypatch.setattr(probe.socket,'getaddrinfo',lambda *a:[(None,None,None,None,(ip,443)) for ip in ('8.8.8.8','1.1.1.1','9.9.9.9')])
    calls=[];tls=[]
    class Socket:
        def settimeout(self,n):assert n==8
        def connect(self,address):calls.append(address)
        def sendall(self,data):pass
        def makefile(self,mode,buffering=0):return io.BytesIO(b'')
        def close(self):pass
    monkeypatch.setattr(probe.socket,'socket',lambda *a:Socket())
    class Context:
        verify_mode=ssl.CERT_REQUIRED;check_hostname=True
        def wrap_socket(self,sock,server_hostname):tls.append(server_hostname);return sock
    monkeypatch.setattr(probe.ssl,'create_default_context',Context)
    class Connection:
        def __init__(self,host,port,timeout):self.host,self.port=host,port;assert timeout==8
        def request(self,method,path,headers):
            assert method=='GET' and path=='/get' and headers['Host']=='httpbin.org'
            assert self.auto_open==0
            self.sock.sendall(b'GET /get HTTP/1.1\r\nHost: httpbin.org\r\n\r\n')
        def getresponse(self):
            body=json.dumps({'headers':{},'args':{},'url':'https://httpbin.org/get' if self.port==443 else 'http://httpbin.org/get'}).encode()
            self.sock.budget.consume(len(body))
            return SimpleNamespace(status=200,read=lambda n:body)
        def close(self):self.sock.close()
    monkeypatch.setattr(probe.http.client,'HTTPConnection',Connection)
    result=probe.run();record=json.loads(Path(result['diagnostic']['path']).read_bytes())
    assert result['passed'] is True and len(calls)==4 and len(tls)==2
    assert tls==['httpbin.org','httpbin.org']
    assert all(port in (80,443) for _,port in calls)
    assert record['maximum_connections']==4 and record['actual_probe_slots']==4
    assert record['application_bytes']<=64*1024
    assert all(r.get('TLS_verified') and r.get('TLS_check_hostname') for r in record['probes'] if r['port']==443)
    assert json.loads(Path(result['network_resolution']['path']).read_bytes())['source']=='v160_current_DNS_and_bounded_endpoint_probe'
    with pytest.raises(PermissionError,match='One ordinary-user attempt'):
        probe.run()
    budget=probe.ApplicationBudget(4);budget.consume(4)
    with pytest.raises(RuntimeError):budget.consume(1)
