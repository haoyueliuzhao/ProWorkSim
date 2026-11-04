"""The manager admits only the full four-member and public-count protocol proof."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v131 as scope
from proworksim import software_benchmark_generation_admission_v131 as admission
from proworksim.software_benchmark_alignment_contract_v131 import condition, shared_strategy
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def test_diagnostic_binds_actual_registry_private_sessions_and_full_fixture(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('diagnostic_manager_v131_CPU', root/'tools/run_fixed_organization_v131.py')
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    plan = scope.load(reference(scope.PLAN_FILE))
    descriptor = admission.diagnostic_descriptor()
    fixture = {**descriptor, 'passed':True,'status':'qualified','fixture_parent_binding_verified':True,
        'tests':admission.TESTS,'repository_CA_and_public_baseline_unchanged':True,
        'new_count_semantics_verified':True,'actual_pytest':'7.4.4','actual_python':'3.9.20',
        'pytest_returncode':0,'public_test_evidence':{
            'positive':{'passed':True,'counts':{'passed':4,'tests_run':4}},
            'no_tests':{'passed':False,'validation_status':'no_tests','counts':{'collected':0}},
            'all_skipped':{'passed':False,'validation_status':'all_skipped_or_xfailed','counts':{'skipped':1}}},
        'socket_and_process_counts':{'nonloopback_attempts':0,'child_process_attempts':0,
                                    'loopback_connections':4,'loopback_binds':2}}
    members = condition('CHIEF')['fixed_members']
    sessions = {member:member+'-private-session' for member in members}
    child = {'diagnostic_passed':True,'execution_alignment':shared_strategy('CHIEF'),
        'actual_member_registry':{member:{'status':'live'} for member in members},
        'private_sessions':sessions,'team_diagnostic':{'passed':True,'model_calls':0,
            'organization_id':'CHIEF','fixed_members':members,'registry_members':members,
            'private_session_ids':sessions},'public_fixture_qualification':fixture}
    quiet = write_new(tmp_path/'quiet.json',{'quiescent':True,'all_owned_objects_removed':True,
        'cleanup_errors':[],'create_result_unknown':False})
    def implementation(value, number):
        ref = write_new(tmp_path/f'child-{number}.json',value)
        result = write_new(tmp_path/f'result-{number}.json',{'passed':True,'model_calls':0,
            'quiescence':quiet,'controller_result':ref})
        return SimpleNamespace(_run=lambda *args,**kwargs: result)
    monkeypatch.setattr(scope,'PREPARATION_QUALIFICATION_FILE',tmp_path/'qualification.json')
    admitted = scope.load(manager.diagnostic(implementation(child,1),plan))
    assert admitted['public_fixture_descriptor'] == descriptor
    assert admitted['private_sessions'] == sessions
    wrong = copy.deepcopy(child)
    wrong['public_fixture_qualification']['actual_pytest'] = '8.0.0'
    with pytest.raises(ValueError,match='public fixture/count protocol'):
        manager.diagnostic(implementation(wrong,2),plan)
    wrong = copy.deepcopy(child)
    wrong['actual_member_registry'] = members
    with pytest.raises(ValueError,match='four-member SDK diagnostic'):
        manager.diagnostic(implementation(wrong,3),plan)
