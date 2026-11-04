"""CPU-only gate controls; this cannot manufacture a live actor qualification."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
from contextlib import redirect_stdout

from proworksim import software_benchmark_generation_admission_v131 as admission
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def main():
    descriptor = admission.diagnostic_descriptor()
    spec = importlib.util.spec_from_file_location('v131_diagnostic_guard_control', admission.HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    observed = io.StringIO()
    with redirect_stdout(observed):
        code = helper.run({**descriptor, 'organization_id': 'FOREIGN'})
    result = json.loads(observed.getvalue().split(helper.PREFIX)[1])
    assert code == 2 and result['passed'] is False
    assert not any(result['socket_and_process_counts'].values())
    assert not admission.qualification_valid(result, descriptor)
    # Synthetic shapes exercise only the validator, never an execution proof.
    sample = {key: descriptor[key] for key in ('version','instance_id','diagnostic_id',
        'profile_manifest_sha256','helper_sha256','observer_sha256','execution_sha256',
        'organization_id','fixed_members','model_calls','hidden_material_used','network_scope')}
    sample.update(passed=True, status='qualified', fixture_parent_binding_verified=True,
        tests=admission.TESTS, repository_CA_and_public_baseline_unchanged=True,
        new_count_semantics_verified=True, actual_python='3.9.20', actual_pytest='7.4.4',
        pytest_returncode=0, socket_and_process_counts={'nonloopback_attempts':0,
            'child_process_attempts':0,'loopback_connections':5,'loopback_binds':4},
        public_test_evidence={'positive':{'passed':True,'counts':{'passed':4,'tests_run':4}},
            'no_tests':{'passed':False,'validation_status':'no_tests','counts':{'collected':0}},
            'all_skipped':{'passed':False,'validation_status':'all_skipped_or_xfailed','counts':{'skipped':1}}})
    assert admission.qualification_valid(sample, descriptor)
    cases = []
    for key,value in [('version','v119-private-localhost-public-fixture-diagnostic-r1'),
                      ('profile_manifest_sha256','0'*64),('helper_sha256','0'*64),
                      ('fixed_members',['member_001']),('new_count_semantics_verified',False)]:
        changed = copy.deepcopy(sample)
        changed[key] = value
        assert not admission.qualification_valid(changed, descriptor)
        cases.append(key)
    changed = copy.deepcopy(sample)
    changed['public_test_evidence']['no_tests']['passed'] = True
    assert not admission.qualification_valid(changed, descriptor)
    cases.append('zero_test_false_pass')
    output = admission.ROOT/'artifacts/software-benchmark-v131/generation-admission-controls-r1/summary.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    return write_new(output, {'version':'v131-public-environment-gate-cpu-control-r1',
        'passed':True,'source':reference(__file__),'admission_source':reference(admission.__file__),
        'helper':reference(admission.HELPER),'descriptor':descriptor,
        'actual_helper_refused_foreign_scope_before_import_or_IO':True,
        'rejected_synthetic_shapes':cases,'synthetic_validation_is_runtime_qualification':False,
        'actual_actor_qualified':False,'Docker_operations':0,'model_calls':0,
        'network_connections':0,'fixture_listeners':0,'task_tests_executed':0})


if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False))
