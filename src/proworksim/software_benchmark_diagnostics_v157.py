"""Validate and reuse actual zero-model diagnostics; never replay owned objects."""
from . import software_benchmark_scope_v157 as scope
from .software_benchmark_alignment_contract_v157 import condition,shared_strategy
from .software_benchmark_candidates_v054 import reference,checked
from .software_benchmark_diagnostic_receipts_v143 import inspect_diagnostic

def validate_preparation():
    value=scope.load(reference(scope.PREPARATION_QUALIFICATION_FILE))
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    authority=scope.load(reference(scope.DIAGNOSTIC_AUTH_FILE))
    if (value.get('passed') is not True or value.get('API_calls')!=0
        or value.get('all_planned_groups_checked') is not True
        or len(value.get('diagnostics',[]))!=3 or authority.get('plan')!=reference(scope.PLAN_FILE)):
        raise ValueError('Three real zero-model diagnostics must precede formal dispatch')
    for source in scope.load(authority['source_index'])['files']:checked(source)
    for spec,record in zip(plan['diagnostics'],value['diagnostics']):
        ref=reference(scope.BATCH_ROOT/f"diagnostic-{spec['index']}"/'result.json')
        current=inspect_diagnostic(ref,spec,load=scope.load,condition=lambda _org:condition(spec['group_id']),
            shared_strategy=shared_strategy,controller_memory_bytes=scope.CONSTRAINTS['controller_memory_bytes'],gib=scope.GIB)
        if any(record.get(k)!=v for k,v in current.items()):
            raise ValueError('Retained diagnostic receipt or its private SDK identity changed')
    return {'passed':True,'preparation':reference(scope.PREPARATION_QUALIFICATION_FILE),
        'reused_actual_diagnostics':3,'new_model_calls':0,'new_containers':0}
