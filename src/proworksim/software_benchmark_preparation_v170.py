"""Read-only engineering gate for the14 independent technical recoveries."""
from . import software_benchmark_scope_v170 as scope
from .software_benchmark_candidates_v054 import reference,checked

def validate_preparation():
    value=scope.load(reference(scope.PREPARATION_QUALIFICATION_FILE))
    if (value.get('version')!='v170-completion-technical-recovery-preparation-r1'
        or value.get('passed') is not True or value.get('model_calls')!=0
        or value.get('recovery_proposal')!=reference(scope.RECOVERY_PROPOSAL_FILE)
        or value.get('planned_episodes')!=13 or value.get('original_context_or_patch_reused') is not False):
        raise ValueError('Independent technical recovery requires its exact engineering gate')
    for key in ('deployment_cpu_controls','source_feedback_replay','finalization_controls','offline_bundle','observer_SDK','observer_sources','observer_CPU','explicit_user_recovery_grant'):
        checked(value[key])
    manifest=scope.load(value['offline_bundle'])
    if (manifest.get('probe',{}).get('model_calls')!=0
        or not manifest.get('probe',{}).get('all_controller_and_worker_entrypoints_imported')):
        raise ValueError('The current key-free recovery bundle has no successful SDK import proof')
    return {'passed':True,'preparation':reference(scope.PREPARATION_QUALIFICATION_FILE),'model_calls':0}
