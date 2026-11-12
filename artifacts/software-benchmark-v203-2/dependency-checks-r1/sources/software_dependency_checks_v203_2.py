"""Two limited confirmation contracts, neither a universal task-dependency oracle."""
from .storage import digest,json_bytes

def structural_confirmation(contract,producer_task,consumer_task,artifact_id):
    if contract.get('origin')!='independently_frozen_task_definition' or not contract.get('registered_before_actions'):
        return {'supported':False,'reason':'not_an_independent_preexisting_definition'}
    produced=contract.get('tasks',{}).get(producer_task,{}).get('produces',[])
    required=contract.get('tasks',{}).get(consumer_task,{}).get('requires',[])
    return {'supported':artifact_id in produced and artifact_id in required,'confirmation_kind':'structural_contract',
        'scope':'this_registered_task_definition_only','definition_sha256':digest(json_bytes(contract)),
        'real_SWE_semantic_necessity_proven':False,'organization_misalignment_proven':False}

def execution_confirmation(before,after,*,consumer_path,artifact_paths):
    checks={}
    for name,w in [('before',before),('after',after)]:
        test=w['test'];checks[name+'_executed']=test.get('executed') is True
        checks[name+'_version_bound']=test.get('source_reference')==w['version']
        checks[name+'_tree_bound']=test.get('files_sha256')==digest(json_bytes(w['files']))
    changed={p for p in before['files'].keys()|after['files'].keys() if before['files'].get(p)!=after['files'].get(p)}
    checks['consumer_unchanged']=before['files'].get(consumer_path)==after['files'].get(consumer_path) and consumer_path in before['files']
    checks['only_named_artifacts_changed']=bool(changed) and changed<=set(artifact_paths)
    checks['same_environment_and_selector']=before['environment_id']==after['environment_id'] and before['selector']==after['selector']
    checks['failure_then_success']=before['test'].get('passed') is False and after['test'].get('passed') is True
    checks['actual_exact_adoption']=after.get('adopted_artifact') is not None and after['adopted_artifact'].get('recipient_version')==after['version']
    return {'supported':all(checks.values()),'confirmation_kind':'bounded_execution_transition','checks':checks,'changed_paths':sorted(changed),
        'scope':'same_consumer_same_runner_only_selected_artifact_transition','alternative_solutions_excluded':False,
        'unique_necessary_path_proven':False,'organization_misalignment_proven':False}
