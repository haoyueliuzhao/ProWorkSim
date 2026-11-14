"""Current endpoint scopes preserve formal identities and consume new controls."""
from proworksim import software_benchmark_grading_v203_2_3_r2 as grading
from proworksim import software_benchmark_scope_v203_2_3 as formal
from proworksim import software_benchmark_preparation_grading_v203_2_3_r2 as preparation
from proworksim.software_benchmark_candidates_v054 import reference


def test_r2_formal_policy_keeps_main_plan_and_shares_exact_capacity_lane():
    policy=grading.scope.dispatch_view()
    assert policy.PLAN_FILE==formal.PLAN_FILE
    assert policy.BATCH_ROOT==formal.BATCH_ROOT
    assert policy.GRADING_ROOT==preparation.GRADING_ROOT
    assert policy.cpu_set('grader',0)==formal.cpu_set('grader',0)
    scoring=grading.scorer(policy)
    assert scoring.validate_request.__globals__['policy'] is policy
    assert scoring.environment.TLS_TASKS=={'psf__requests-1766'}


def test_r2_preparation_has_two_new_identical_official_control_kinds_only():
    policy=preparation.dispatch_view()
    assert policy.PLAN_FILE==preparation.CONTROL_PLAN_FILE
    assert policy.BATCH_ROOT==formal.BATCH_ROOT
    assert policy.COORDINATOR_RUN_ROOT==preparation.COORDINATOR_ROOT
    plan=preparation.validate_control_plan(formal.load(reference(preparation.CONTROL_PLAN_FILE)))
    assert plan['rows']==[] and set(plan['resources'])==preparation.KEYS
    assert {row['patch_kind'] for row in plan['resources'].values()}=={'gold','empty'}
    assert all(row['instance_id']=='psf__requests-1766' for row in plan['resources'].values())


def test_cold_command_uses_explicit_inside_loader_bootstrap_not_inherited_flag():
    args=grading.command(['--manifest'])
    assert '-c' in args and 'PWS_V20323_GRADING_REVISION_R2' in args[args.index('-c')+1]
    assert "='0'" in args[args.index('-c')+1]
    assert args[-1]=='--manifest'
