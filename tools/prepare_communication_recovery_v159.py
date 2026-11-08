"""Freeze never-called rows and bounded coexistence with the draining old owner."""
from __future__ import annotations
from collections import Counter
import copy,json,sqlite3,time
from proworksim import software_benchmark_scope_v159 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration

def prepare():
    old=scope.original_scope
    if scope.PLAN_FILE.exists():return {'plan':reference(scope.PLAN_FILE),'already_prepared':True}
    original=old.validate_plan(scope.load(reference(old.PLAN_FILE)))
    progress=scope.load(reference(old.API_ROOT/'progress.json'))
    if progress.get('draining_new_generation') is not True:
        raise PermissionError('Original owner must irreversibly close new admission first')
    db=sqlite3.connect(old.LEDGER_FILE.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        db.execute('BEGIN');states=db.execute('SELECT status,count(*) FROM requests GROUP BY status').fetchall()
        counts=dict(db.execute('SELECT slot_id,count(*) FROM requests GROUP BY slot_id').fetchall())
        inflight={r[0] for r in db.execute("SELECT DISTINCT slot_id FROM requests WHERE status='reserved'")}
    finally:db.close()
    if set(counts)-{r['slot_id'] for r in original['rows']}:raise ValueError('Foreign physical usage')
    rows=[copy.deepcopy(r) for r in original['rows'] if not counts.get(r['slot_id'])]
    used=[r['slot_id'] for r in original['rows'] if counts.get(r['slot_id'])]
    if not rows:raise ValueError('No never-called original slot remains')
    # These three tasks were specifically observed running when overlap was
    # approved. Their immutable claims retain exact actual lane/ownership IDs.
    frozen_claims=[reference(old.BATCH_ROOT/'resource-claims'/f'actor-{i}.json') for i in (15706,15708,15714)]
    claims=[scope.load(ref) for ref in frozen_claims]
    reserved_slots=[r['spec']['slot_id'] for r in claims];lanes=sorted(r['lane'] for r in claims)
    if len(set(lanes))!=3 or not set(reserved_slots)<=set(used):raise PermissionError('Frozen old ownership changed')
    signal_ref=reference(scope.ARTIFACT_ROOT/'owned-coordinator-drain-r1/signal-intent.json')
    signal=scope.load(signal_ref)
    if signal['unit']!=old.API_UNIT or signal['cancel_entered_tasks'] is not False:
        raise PermissionError('Only the controlled no-cancellation predecessor drain permits overlap')
    coexistence=scope.retain(scope.COEXISTENCE_FILE,{
        'version':'v159-draining-predecessor-bounded-coexistence-r1','original_plan':reference(old.PLAN_FILE),
        'original_source_index':reference(old.SOURCE_FILE),'shared_ledger':str(old.LEDGER_FILE),
        'used_original_slots':used,'admitted_original_slots':[r['slot_id'] for r in rows],
        'reserved_original_actor_claims':frozen_claims,'reserved_old_slots':reserved_slots,'reserved_old_lanes':lanes,
        'old_coordinator_process':{k:signal[k] for k in ('pid','proc_start_ticks','uid')},'drain_signal':signal_ref,
        'initial_new_generation_limit':11,'normal_new_generation_limit':16,
        'fixed_old_cpu_reservation':26,'fixed_old_memory_reservation_bytes':176*scope.GIB,
        'combined_peak_during_overlap_cpu':108,'combined_peak_during_overlap_memory_bytes':776*scope.GIB,
        'new_manager_cpu_ids':scope.manager_cpu_ids(),'old_files_services_changed':False})
    status=scope.coexistence_status()
    if not inflight<=set(status['active_old_slots']):raise PermissionError('Old HTTP inflight is outside frozen active ownership')
    proof=scope.retain(scope.ARTIFACT_ROOT/'predecessor-drain-r1/proof.json',{
        'version':scope.VERSION,'observed_unix':time.time(),'original_plan':reference(old.PLAN_FILE),
        'coexistence_policy':coexistence,'coexistence_status':status,
        'provider_request_counts_by_original_slot':counts,'provider_states':states,
        'same_ledger':str(old.LEDGER_FILE),'old_naturally_running_work_not_cancelled':True,
        'no_called_identity_resampled':True})
    resources={}
    for row in rows:
        for role in ('actor','controller','volume','score','delivery-score'):
            key=f"{role}-{row['slot_index']}";resources[key]=copy.deepcopy(original['resources'][key])
    inventory=scope.retain(scope.INVENTORY_FILE,{'version':scope.VERSION,'rows':rows,
        'generation':{},'scores':{},'deliveries':{},'original_plan':reference(old.PLAN_FILE)})
    plan={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'original_plan':reference(old.PLAN_FILE),
        'panel':reference(scope.PANEL_FILE),'matrix':reference(scope.PANEL_FILE),'rows':rows,'generation_rows':rows,
        'admitted_original_slots':[r['slot_id'] for r in rows],'used_original_slots':used,
        'original72_planned_denominator':72,'original_ledger':str(old.LEDGER_FILE),'new_cash_budget_CNY':'0.00',
        'input_plus_output_token_upper_bound_for_remaining':len(rows)*5_000_000,
        'predecessor_drain':proof,'coexistence_policy':coexistence,'constraints':scope.CONSTRAINTS,
        'host_cpu_pool':reference(scope.CPU_POOL_FILE),'inventory':inventory,
        'environments':copy.deepcopy(original['environments']),'environment_sources':copy.deepcopy(original['environment_sources']),
        'resources':resources,'resource_role_counts':dict(Counter(x['role'] for x in resources.values())),
        'diagnostics':[],'training':False,'old_results_preserved':True,'model_calls_during_preparation':0,
        'dispatch_admission':declaration(scope.BATCH_ROOT),'wave_policy':{
            'task_wave_and_order_unchanged':True,'new_version_wave1_episodes':sum(r['wave']==1 for r in rows),
            'new_version_wave2_episodes':sum(r['wave']==2 for r in rows),
            'old_failed_measurement_is_not_a_pass':True,'scores_consulted':False,
            'revised_source_results_separately_identified':True}}
    scope.validate_plan(plan);plan_ref=scope.retain(scope.PLAN_FILE,plan)
    scope.retain(scope.STATE_ROOT/'admission-control.json',{'version':'v132-fair-group-admission-r1',
        'batch_root':str(scope.BATCH_ROOT),'mode':'run','groups':[],'maximum_generations':11,
        'revision':0,'reason':'initial_bounded_predecessor_coexistence'})
    return {'plan':plan_ref,'remaining_original_episodes':len(rows),'used_original_episodes_preserved':len(used),
        'coexistence':status,'new_model_calls':0,'Docker_operations':0}

if __name__=='__main__':print(json.dumps(prepare(),ensure_ascii=False))
