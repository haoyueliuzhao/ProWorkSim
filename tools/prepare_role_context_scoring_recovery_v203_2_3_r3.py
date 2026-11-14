"""Freeze strict r4 task environment links for all twelve independent attempts."""
import json
from proworksim import software_benchmark_scope_v203_2_3_r3 as scope
from proworksim import software_benchmark_grading_recovery_v203_2_3_r3 as grading
from proworksim.software_benchmark_candidates_v054 import reference


def prepare():
    pref=reference(scope.PLAN_FILE);plan=scope.validate_plan(scope.load(pref));refs={}
    scoring=grading.scorer(scope.dispatch_view());scoring.environment.prepare()
    manifest=scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
    for task,environment in plan['environments'].items():
        canonical=grading.original_environment_config(scope.load(environment['configuration']),pref)
        original=reference(scope.PREVIOUS_BATCH_ROOT/'grading-coordinator-r4/qualifications'/(task+'.json'))
        refs[task]=scope.retain(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'),{
            'version':'v203.2.3-independent-recovery-environment-link-r3','instance_id':task,'passed':True,
            'plan':pref,'original_plan':reference(grading.OLD_PLAN),'original_qualification':original,
            'environment_identity':grading.base.environment_identity(canonical),'actual_scorer_revision':'r4_HTTP_framing_original_TLS'})
    for row in plan['rows']:
        scoring.validate_qualification(refs[row['instance_id']],scope.load(row['configuration']),pref)
    request_fields=scoring.environment.request_fields('psf__requests-1766')
    tls=scope.load(request_fields['environment_revision'])
    if (tls.get('http_idle_requires_complete_framing_and_both_queues_empty') is not True
            or tls.get('TLS_idle_timeout_exempted') is not False):
        raise PermissionError('Actual candidate scorer does not retain the qualified r4 HTTP/TLS rules')
    index=scope.retain(scope.COORDINATOR_ROOT/'qualification-completion-index.json',{
        'version':'v203.2.3-recovery12-r4-environment-admission-r3','plan':pref,'qualifications':refs,
        'pending_tasks':{},'all_four_tasks_qualified':True,'planned_denominator':12,
        'Requests_actual_grader_revision':'r4_HTTP_framing_and_original_TLS'})
    return {'passed':True,'strict_condition_qualifications':12,'index':index,'scorer_manifest':manifest,
        'actual_Requests_environment':request_fields,'API_calls':0,'Docker_operations':0}

if __name__=='__main__':print(json.dumps(prepare()))
