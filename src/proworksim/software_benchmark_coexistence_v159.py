"""Read-only accounting of the three draining original teams; no old mutation."""
from __future__ import annotations
import json,os
from pathlib import Path
from .software_benchmark_candidates_v054 import reference,checked
GIB=1024**3
VERSION='v159-draining-predecessor-bounded-coexistence-r1'

def process_alive(record):
    path=Path('/proc')/str(record['pid'])/'stat'
    try:raw=path.read_text()
    except FileNotFoundError:return False
    return raw.rsplit(')',1)[1].split()[19]==record['proc_start_ticks']

def observe(scope):
    policy=scope.load(reference(scope.COEXISTENCE_FILE));old=scope.original_scope
    if (policy.get('version')!=VERSION or policy.get('original_plan')!=reference(old.PLAN_FILE)
        or policy.get('shared_ledger')!=str(old.LEDGER_FILE)
        or policy.get('initial_new_generation_limit')!=11 or policy.get('normal_new_generation_limit')!=16
        or len(policy.get('reserved_original_actor_claims',[]))!=3
        or set(policy['admitted_original_slots'])&set(policy['used_original_slots'])):
        raise PermissionError('The fixed old/new identity and combined resource policy changed')
    for ref in policy['reserved_original_actor_claims']:checked(ref)
    permitted=set(policy['reserved_old_slots']);used=set(policy['used_original_slots'])
    if not permitted<=used:raise PermissionError('An old predecessor slot lacks actual prior usage')
    active=[];other=[]
    for path in (old.BATCH_ROOT/'resource-claims').glob('active-*.json'):
        try:value=json.loads(path.read_bytes())
        except FileNotFoundError:continue
        role=value.get('spec',{}).get('role')
        if role=='actor':
            slot=value['spec']['slot_id']
            if slot not in permitted or slot not in used or value['lane'] not in policy['reserved_old_lanes']:
                raise PermissionError('A predecessor task entered outside its frozen draining ownership')
            active.append(slot)
        elif role!='auxiliary_coordinator':other.append(value.get('key'))
    if other:raise PermissionError('Unexpected predecessor score/model resource is outside coexistence limits')
    progress=json.loads((old.API_ROOT/'progress.json').read_bytes())
    if progress.get('draining_new_generation') is not True:
        raise PermissionError('The predecessor must irreversibly drain new admissions before overlap')
    alive=process_alive(policy['old_coordinator_process'])
    old_quiet=False
    if not active and not alive and not old.LEASE_FILE.exists():
        final=scope.load(reference(old.API_ROOT/'coordinator-finalization.json'))
        old_quiet=(final.get('cleanup_errors')==[] and scope.load(final['coordinator_release']).get('released') is True)
    held=not old_quiet
    return {'version':VERSION,'passed':True,'old_new_generation_admission_closed':True,
        'active_old_slots':sorted(active),'frozen_old_slots':sorted(permitted),
        'old_coordinator_alive':alive,'old_fully_quiescent':old_quiet,
        'reserved_old_lanes':policy['reserved_old_lanes'] if held else [],
        'reserved_old_cpu':26 if held else 0,'reserved_old_memory_bytes':176*GIB if held else 0,
        'maximum_new_generation':11 if held else 16,
        'combined_peak_cpu':108 if held else 112,
        'combined_peak_memory_bytes':776*GIB if held else 840*GIB,
        'shared_cash_cap_CNY':'500.00','shared_physical_HTTP_limit':16,
        'old_files_services_or_processes_modified':False,'policy':reference(scope.COEXISTENCE_FILE)}
