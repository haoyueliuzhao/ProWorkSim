import json
from types import SimpleNamespace
import pytest
from proworksim.software_namespace_witness_v183 import read_witness


def test_stderr_is_preserved_without_corrupting_json(tmp_path):
    warning=b"ModuleNotFoundError: No module named '_distutils_hack'\n"
    container=SimpleNamespace(exec_run=lambda argv,demux:SimpleNamespace(exit_code=0,output=(b'{"namespaces":{},"cpus":[1]}\n',warning)))
    value=read_witness(container,['python','-c','fixed probe'],{'path':str(tmp_path/'initial-container.json')})
    assert value['cpus']==[1]
    evidence=json.loads((tmp_path/'namespace-witness-output-v183.json').read_bytes())
    assert evidence['stderr']==warning.decode() and not evidence['site_initialization_disabled']


def test_invalid_stdout_is_not_replaced_with_stderr_or_filtered(tmp_path):
    container=SimpleNamespace(exec_run=lambda argv,demux:SimpleNamespace(exit_code=0,output=(b'not json',b'{"cpus":[1]}')))
    with pytest.raises(ValueError):read_witness(container,['python'],{'path':str(tmp_path/'initial-container.json')})
