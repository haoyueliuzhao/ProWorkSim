"""Actual offline pytest and Flask WSGI controls; no listener or task evaluation."""
from __future__ import annotations

import importlib.util
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'artifacts/software-benchmark-v130/public-compatibility-controls-r1'
WHEEL = ROOT/'runs/software-benchmark-v057/grading-environment-r1/packages/pytest-7.4.4-py3-none-any.whl'

PROBE = r'''
import importlib.metadata
import json, os, pathlib, resource, sys
resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
sys.path[:0]=[sys.argv[4],sys.argv[5]]
events=[]
def deny(event,args):
    if event in {'socket.connect','socket.bind','socket.getaddrinfo','socket.sendto','subprocess.Popen','os.system','os.fork','os.posix_spawn'}:
        events.append(event)
        raise RuntimeError('This CPU control cannot use network/listeners/child processes')
sys.addaudithook(deny)
import pytest
from httpbin.core import app
mode=sys.argv[1]
assert pytest.__version__=='7.4.4'
app.testing=False
if mode=='before':
    try:
        pytest.raises(ValueError,"int('not-a-number')")
    except TypeError as error:
        legacy_error=str(error)
    else:
        raise AssertionError('The frozen original pytest must reject legacy string calls')
    response=app.test_client().get('/response-headers?Set-Cookie=foo%3Ddeleted&X-Test=one&X-Test=two')
    assert response.status_code==500
    result={'mode':mode,'pytest':pytest.__version__,'legacy_string_error':legacy_error,
            'original_httpbin_status':response.status_code}
else:
    entrypoints=importlib.metadata.entry_points(group='pytest11')
    assert any(e.name=='pws-public-compat-v130' and e.value=='pws_public_compat_v130' for e in entrypoints)
    counts={}
    class Counts:
        def pytest_terminal_summary(self,terminalreporter):
            counts.update({k:len(v) for k,v in terminalreporter.stats.items() if k in {'passed','failed','error','skipped'}})
    status=pytest.main(['-q','-c','/dev/null','-p','no:cacheprovider',sys.argv[2]],plugins=[Counts()])
    assert status==0 and counts.get('passed')==7 and not counts.get('failed') and not counts.get('error'), counts
    import pws_public_compat_v130 as plugin
    assert plugin.install_pytest_compat()['already_installed'] is True
    result={'mode':mode,'pytest':pytest.__version__,'test_counts':counts,
            'actual_pytest11_plugin_autoloaded':True,'original_string_assertions_executed':True}
assert not events
result.update(passed=True,python=sys.version.split()[0],network_attempts=events,listeners=0,
              actual_original_task_suite_run=False,production_python39_not_executed=True)
pathlib.Path(sys.argv[3]).write_text(json.dumps(result,indent=2)+'\n')
'''

TESTS = r'''
import pytest
import requests
from httpbin.core import app, jsonify

def test_legacy_string_real_exception_info_and_scope():
    value='bad-integer'
    caught=pytest.raises(ValueError,'int(value)')
    assert caught.type is ValueError
    assert 'bad-integer' in str(caught.value)
    pytest.raises((ValueError,TypeError),'int(local_value)',local_value='x')

def test_legacy_missing_exception_and_wrong_exception_are_failures():
    with pytest.raises(pytest.fail.Exception,match='DID NOT RAISE'):
        pytest.raises(ValueError,'int("123")')
    with pytest.raises(TypeError):
        pytest.raises(ValueError,'len(7)')
    with pytest.raises(AssertionError):
        pytest.raises(ValueError,'assert False')

def test_legacy_code_really_runs_and_does_not_write_caller_locals():
    changed=[]
    pytest.raises(ValueError,'changed.append(1); int("bad")')
    assert changed==[1]
    local='unchanged'
    pytest.raises(ValueError,'local="changed"; int("bad")')
    assert local=='unchanged'

def test_modern_forms_still_use_the_original_pytest():
    assert pytest.raises(ValueError,int,'x').type is ValueError
    with pytest.raises(ValueError,match='invalid literal'):
        int('x')
    with pytest.raises(pytest.fail.Exception):
        with pytest.raises(ValueError):
            pass

def test_original_requests_conflicting_post_string_expressions():
    # Exact two original public expressions, on the installed Requests library.
    # Invalid multipart input raises before any connection; the audit denies IO.
    url='http://127.0.0.1:1/post'
    u=lambda value:value
    with open(__file__) as f:
        pytest.raises(ValueError, "requests.post(url, data='[{\"some\": \"data\"}]', files={'some': f})")
        pytest.raises(ValueError, "requests.post(url, data=u('[{\"some\": \"data\"}]'), files={'some': f})")

def test_actual_public_httpbin_multivalue_and_expiry_header():
    client=app.test_client()
    response=client.get('/response-headers?Set-Cookie=foo%3Ddeleted%3B+expires%3DThu%2C+01-Jan-1970+00%3A00%3A01+GMT&X-Test=one&X-Test=two')
    assert response.status_code==200
    assert response.headers.getlist('X-Test')==['one','two']
    assert 'foo=deleted' in response.headers.get('Set-Cookie')
    assert 'expires=Thu, 01-Jan-1970 00:00:01 GMT' in response.headers.get('Set-Cookie')
    assert response.get_json()['X-Test']==['one','two']
    assert client.get('/response-headers').status_code==200

def test_actual_httpbin_does_not_hide_json_or_http_errors():
    assert app.test_client().get('/status/418').status_code==418
    with app.app_context(),pytest.raises(TypeError):
        jsonify(object())
'''


def main(output=OUTPUT):
    from proworksim import software_benchmark_public_dependencies_v130 as payload
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    output=Path(output).resolve()
    if output.exists():
        raise ValueError('Preserve the existing CPU control; do not silently rerun it')
    output.mkdir(parents=True)
    manifest_ref = payload.prepare()
    with tempfile.TemporaryDirectory(prefix='pws-public-v130-') as temporary:
        folder = Path(temporary)
        pytest_site = folder/'pytest-site'
        with zipfile.ZipFile(WHEEL) as archive:
            for name in archive.namelist():
                relative=Path(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Unsafe cached pytest wheel path')
                if not name.endswith('/'):
                    path=pytest_site/relative
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(archive.read(name))
        probe, tests = folder/'probe.py', folder/'test_public_compat.py'
        probe.write_text(PROBE)
        tests.write_text(TESTS)
        for mode,site in [('before',payload.SOURCE/'site'),('after',payload.OUTPUT/'site')]:
            environment={**os.environ,'PYTHONPATH':os.pathsep.join(map(str,(pytest_site,site))),
                'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1',
                'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','LITELLM_LOCAL_MODEL_COST_MAP':'True',
                'OPENHANDS_SUPPRESS_BANNER':'1','HTTP_PROXY':'','HTTPS_PROXY':'','ALL_PROXY':'',
                'http_proxy':'','https_proxy':'','all_proxy':'','NO_PROXY':'*','no_proxy':'*'}
            environment.pop('PYTEST_DISABLE_PLUGIN_AUTOLOAD',None)
            for key in ('PYTEST_ADDOPTS','PYTEST_PLUGINS','PYTHONHOME','LD_PRELOAD','LD_LIBRARY_PATH'):
                environment.pop(key,None)
            completed=subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(ROOT/'tools/run_offline_scorer_v096.py'),
                str(probe),mode,str(tests),str(output/(mode+'.json')),str(pytest_site),str(site)],
                cwd=folder,env=environment,capture_output=True,text=True,timeout=60,check=False)
            (output/(mode+'.stdout')).write_text(completed.stdout)
            (output/(mode+'.stderr')).write_text(completed.stderr)
            if completed.returncode:
                raise RuntimeError(mode+' actual CPU control failed: '+completed.stderr[-1500:])
    helper_path=ROOT/'tools/public_test_dependencies_v130.py'
    spec=importlib.util.spec_from_file_location('v130_public_dependency_control',helper_path)
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    descriptor={'version':helper.VERSION,'instance_id':helper.TASK,'actor_root':helper.ACTOR_ROOT,
        'manifest':{key:manifest_ref[key] for key in ('sha256','bytes')}}
    profile=helper.validate_descriptor(descriptor,instance_id=helper.TASK,root=payload.OUTPUT)
    original={'PATH':'/original/task/python/bin','HOME':'/actor'}
    environment=helper.effective_test_environment(original,profile)
    assert original=={'PATH':'/original/task/python/bin','HOME':'/actor'}
    assert environment['PYTHONPATH']==str(payload.OUTPUT/'site')
    summary={'version':'v130-real-public-compatibility-offline-control-r1','passed':True,
        'manifest':manifest_ref,'source':reference(__file__),'plugin_source':reference(payload.PLUGIN_SOURCE),
        'descriptor_helper':reference(helper_path),'cached_pytest_wheel':reference(WHEEL),
        'before':reference(output/'before.json'),'after':reference(output/'after.json'),
        'new_model_calls':0,'Docker_operations':0,'network_connections':0,'listeners':0,
        'ordinary_child_processes':2,'each_child_address_space_bytes':1024**3,
        'task_repository_files_modified':False,'hidden_test_material_used':False,
        'public_environment_only':True,'official_scoring_changed':False,
        'descriptor_verified':True,'parent_environment_mutated':False,
        'validation_limits':['Python3.12 with cached pytest7.4.4, not original image Python3.9.',
            'Two original string expressions execute against locally installed Requests; no whole repository test suite.',
            'Actual Flask WSGI requests use in-memory test_client, not a listener or production actor.',
            'A new zero-model actor diagnostic is still required before deploying this changed environment.']}
    print(json.dumps(write_new(output/'summary.json',summary),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    main(parser.parse_args().output)
