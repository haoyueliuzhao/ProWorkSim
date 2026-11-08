"""Read-only deployment admission for the source/finalization recovery."""
from . import software_benchmark_scope_v168 as scope
from .software_benchmark_candidates_v054 import reference,checked

def validate_preparation():
    value=scope.load(reference(scope.PREPARATION_QUALIFICATION_FILE))
    if (value.get('version')!='v168-second-wave-preparation-r1' or value.get('passed') is not True
        or value.get('model_calls')!=0 or value.get('no_previously_called_slot_restarted') is not True):
        raise ValueError('Recovery requires source-feedback and finalization engineering evidence')
    for key in ('source_feedback_replay','finalization_controls','offline_bundle','predecessor_drain','wave1_actual_measurement_gate','deployment_cpu'):
        ref=value.get(key)
        if not isinstance(ref,dict):raise ValueError('Missing exact recovery proof: '+key)
        checked(ref)
    gate=scope.load(value['wave1_actual_measurement_gate'])
    if gate.get('advance_to_wave_2') is not True or gate.get('scores_consulted') is not False:
        raise ValueError('The real first-wave gate has not passed')
    manifest=scope.load(value['offline_bundle'])
    if (manifest.get('probe',{}).get('model_calls')!=0
        or not manifest.get('probe',{}).get('all_controller_and_worker_entrypoints_imported')):
        raise ValueError('Current recovery bundle did not pass real SDK imports')
    return {'passed':True,'preparation':reference(scope.PREPARATION_QUALIFICATION_FILE),
        'model_calls':0,'new_diagnostic_containers':0,'prior_Docker_diagnostics_not_claimed_to_execute_new_code':True}
