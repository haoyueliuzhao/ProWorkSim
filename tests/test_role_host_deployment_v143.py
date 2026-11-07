"""Necessary cold bindings for the zero-model deployment amendment; no IO services."""
import importlib.util
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_host_api_v143 as host
from proworksim import software_benchmark_scope_v143 as scope
from proworksim import software_benchmark_sdk_bundle_v143 as bundle
from proworksim import software_benchmark_deepseek_api_v142 as cash
from proworksim.software_benchmark_candidates_v054 import reference


def module(name):
    spec=importlib.util.spec_from_file_location(name,scope.ROOT/'tools'/(name+'.py'))
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_actual_host_keeps_one_original_cash_policy_and_new_bundle():
    assert host.DeepSeekRuntime.initialize_for_run.__globals__['scope'] is scope
    assert host.HostTeamTransport.post.__globals__['scope'] is scope
    assert host.group_api is cash.group_api
    policies=[host.api_for(g).POLICY for g in scope.GROUP_IDS]
    assert all(p==policies[0] for p in policies)
    assert policies[0]['cap_nanoyuan']==400_000_000_000
    assert policies[0]['pilot_panel']==reference(scope.previous.PANEL_FILE)
    schemas=json.loads(host.SCHEMAS.read_text())
    assert schemas['runtime_bundle']==reference(bundle.OUTPUT/'manifest.json')
    assert {k:len(v) for k,v in schemas['schemas'].items()}=={'S1':1,'FREE2':2,'REVIEW2':2}
    assert scope.LEDGER_FILE==scope.previous.LEDGER_FILE
    assert not scope.LEDGER_FILE.exists()


def test_new_activation_refuses_before_any_side_effect(monkeypatch):
    activate=module('activate_role_pilot_v143')
    calls=[]
    def deny(*args,**kwargs):
        raise PermissionError('scripted_missing_concrete_authority')
    monkeypatch.setattr(scope,'require_allowed',deny)
    monkeypatch.setattr(activate,'run_phase',lambda *a,**k:calls.append(a))
    monkeypatch.setattr(activate,'verify_probe_if_available',lambda:calls.append('probe'))
    with pytest.raises(PermissionError,match='scripted_missing_concrete_authority'):
        activate.activate()
    assert calls==[]
    assert activate.postgrant_sequence()==['reuse_completed_endpoint_probe','cold_grading_preparation','launch_unique_user_coordinator']


def test_user_unit_and_seal_match_actual_deployment():
    launcher=module('launch_role_pilot_v143')
    spec=json.loads(launcher.SPEC.read_text())
    argv=launcher.command(spec)
    assert argv[:2]==['systemd-run','--user']
    assert str(scope.ROOT/'tools/run_role_pilot_v143.py') in argv
    assert '--property=MemoryMax=32G' in argv and '--property=MemoryHigh=30G' in argv
    assert not any('sudo' in str(item) or 'slice=' in str(item).lower() for item in argv)
    sealer=module('seal_role_pilot_v143')
    assert sealer.postgrant_sequence()==module('activate_role_pilot_v143').postgrant_sequence()
    assert sealer.BUDGET_GRANT==scope.previous.ARTIFACT_ROOT/'budget-grant-r1/authorization.json'
    assert Path(spec['entrypoint']['path']).name=='run_role_pilot_v143.py'
