"""Necessary actual-entry regressions: strict pytest and own-score reuse."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_delivery_reuse_v175 import bind_host,same_score_manifest
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_public_test_evidence_v175 import execute_public_entry
from proworksim.software_benchmark_public_test_evidence_v141 import execute_public_entry as old_execute

ROOT=Path(__file__).resolve().parents[1]


def run(execute,folder):
    env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTEST_PLUGINS':'',
        'PYTHONPATH':str(Path(pytest.__file__).resolve().parent.parent)}
    return execute({'argv':[sys.executable,'-m','pytest','-q','test_local.py']},
        root=folder,environment=env,timeout_seconds=20)


def test_strict_warning_old_failure_and_repaired_public_entry(tmp_path):
    (tmp_path/'pytest.ini').write_text('[pytest]\nfilterwarnings = error\n')
    (tmp_path/'test_local.py').write_text('def test_real(): assert 1 + 1 == 2\n')
    before=run(old_execute,tmp_path)
    assert not before['passed'] and 'PytestAssertRewriteWarning' in before['output']
    after=run(execute_public_entry,tmp_path)
    assert after['passed'] and after['counts']['passed']==1,after['output']
    assert after['deployment_revision']=='v175-deferred-pytest-plugin-import-r1'


def test_project_warnings_are_still_errors(tmp_path):
    (tmp_path/'pytest.ini').write_text('[pytest]\nfilterwarnings = error\n')
    (tmp_path/'test_local.py').write_text('import warnings\ndef test_real(): warnings.warn("actual project warning")\n')
    result=run(execute_public_entry,tmp_path)
    assert not result['passed'] and result['counts']['failed']==1
    assert 'actual project warning' in result['output']


def test_strict_nested_pytest_root_and_child_remain_distinct(tmp_path):
    (tmp_path/'pytest.ini').write_text('[pytest]\nfilterwarnings = error\n')
    (tmp_path/'test_local.py').write_text('''import pytest
def test_nested(tmp_path):
    path=tmp_path/'test_child.py'
    path.write_text('def test_bad(): assert False\\n')
    assert pytest.main(['-q',str(path)]) == 1
''')
    result=run(execute_public_entry,tmp_path)
    assert result['passed'],result['output']
    assert result['counts']['passed']==1 and result['counts']['failed']==0
    children=[r for r in result['test_evidence']['sessions'] if not r['root']]
    assert len(children)==1 and children[0]['counts']['failed']==1


def test_manifest_requires_exact_scored_request_and_unchanged_bytes(tmp_path):
    a=tmp_path/'actual.json';b=tmp_path/'other.json'
    a.write_text('{"score":"fixed"}');b.write_bytes(a.read_bytes())
    ar,br=reference(a),reference(b)
    assert same_score_manifest(ar,ar)
    assert not same_score_manifest(ar,br)
    a.write_text('{"score":"tampered"}')
    with pytest.raises(ValueError):same_score_manifest(ar,ar)


def test_actual_delivery_entry_uses_own_manifest_and_keeps_other_guards(tmp_path):
    from types import FunctionType
    from proworksim.software_benchmark_candidates_v054 import write_new
    spec=importlib.util.spec_from_file_location('frozen_delivery_entry',ROOT/'tools/run_capability_grading_v066.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def put(name,value):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True)
        return write_new(path,value)
    def load(ref):return json.loads(Path(ref['path']).read_bytes())
    cfg=put('config.json',{'slot_id':'slot','instance_id':'fixture'})
    row={'slot_id':'slot','slot_index':1,'arm':'PROJECT','instance_id':'fixture','configuration':cfg}
    plan=put('plan.json',{'rows':[row]})
    actual=put('candidate-manifest.json',{'version':'fixed','same_official_tests':True})
    preparation=put('preparation-manifest.json',load(actual))
    lock={'tree_sha256':'a'*64,'patch_receipt':{'base_tree_sha256':'b'*64}}
    code=put('code.json',lock);delivery=put('delivery.json',lock)
    evidence=put('evidence.json',{'submitted':True,'same_tree':True})
    result=put('result.json',{'slot_id':'slot','candidate_lock':code,
        'delivery_candidate_lock':delivery,'delivery_evidence':evidence})
    folder=tmp_path/'score-1'
    request=put('score-1/request.json',{'resource_key':'score-1','generation_result':result,
        'slot_id':'slot','candidate_lock':code,'scorer_manifest':actual,'directory':str(folder)})
    identity=put('score-1/identity.json',{'request':request,'candidate_lock':code,
        'configuration':cfg,'endpoint':'code','plan':plan,'scorer_manifest':actual})
    put('score-1/receipt.json',{'identity':identity,'version':'fixture','resource_key':'score-1',
        'slot_id':'slot','status':'official_report','resolved':True,
        'official_result':['fixture',{'fixture':{'resolved':True,'patch_successfully_applied':True,'infra_failure':False}}]})
    put('score-1/completion.json',{'returncode':0})
    put('score-1/quiescence.json',{'quiescent':True,'resource_key':'score-1','cleanup_errors':[],
        'create_result_unknown':False})
    visited=[]
    scorer=SimpleNamespace(VERSION='fixture',_generation_result=lambda *a:visited.append('generation'),
        validate_project_delivery=lambda *a:visited.append('legal_delivery') or load(evidence))
    def retain(path,value):path.parent.mkdir(parents=True,exist_ok=True);return write_new(path,value)
    ns={**module.delivery_disposition.__globals__,'load':load,'reference':reference,
        'policy':SimpleNamespace(PLAN_FILE=Path(plan['path']),load=load),
        'scorer':scorer,'prepare_manifest':lambda:preparation,'RUN_ROOT':tmp_path/'recovered',
        'VERSION':'fixture','retain':retain}
    original=FunctionType(module.delivery_disposition.__code__,ns,
        'delivery_disposition',module.delivery_disposition.__defaults__)
    with pytest.raises(ValueError,match='Delivery reuse requires'):
        original(result,request)
    repaired=bind_host(SimpleNamespace(delivery_disposition=original)).delivery_disposition
    completed=repaired(result,request)
    assert completed['status']=='same_tree_official_result_reused' and completed['resolved'] is True
    assert visited==['generation','legal_delivery','generation','legal_delivery']
    # Same scored request cannot validate a different delivery tree.
    Path(delivery['path']).write_text(json.dumps({**lock,'tree_sha256':'c'*64}))
    with pytest.raises(ValueError,match='Delivery reuse requires'):
        repaired(result,request)
