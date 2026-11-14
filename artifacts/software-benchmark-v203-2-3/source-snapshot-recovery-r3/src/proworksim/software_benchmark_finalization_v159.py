"""Persist the original controller outcome before closing its budget channel.

This helper makes no model calls. Ledger snapshots may use only the already
bound read-only budget RPC; finalizer faults never erase the primary failure.
"""
from __future__ import annotations
from pathlib import Path
import sys
from .software_benchmark_candidates_v054 import reference,write_new
from .storage import atomic_write,json_bytes
VERSION='v159-controller-finalization-before-owned-transport-close-r1'

def error_record(error):
    return {'type':type(error).__name__,'message':str(error)}

def finalize_controller(result,output,*,runtime,close_runtime,owner,transport,
                        writer=write_new,reference_file=reference):
    output=Path(output);secondary=[];order=[];snapshot_source='prior_result' if isinstance(result.get('ledger'),dict) else None
    def record_failure(step,error):
        secondary.append({'step':step,**error_record(error)})
        if result.get('status')=='closed':
            result['status']='technical_unknown'
            result.setdefault('error',error_record(error))
            result.setdefault('failure_classification','controller_finalization_unknown')
    if runtime is not None:
        order.append('close_private_SDK_while_budget_channel_open')
        try:close_runtime(runtime)
        except BaseException as error:record_failure('close_runtime',error)
    if owner is not None:
        order.append('snapshot_owner_while_budget_channel_open')
        try:
            snapshot=owner.save()
            if not isinstance(snapshot,dict):raise ValueError('Final owner snapshot must be a JSON object')
            result['ledger']=snapshot
            result['member_usage']=snapshot.get('per_member',{})
            result['usage_complete']=snapshot.get('complete_actual_tokens') is not None
            result['auxiliary_uncertain_reserved_tokens']=snapshot.get('uncertain_reserved_tokens',0)
            snapshot_source='final_owner_save_before_transport_close'
        except BaseException as error:
            # A previous actual snapshot remains evidence; never replace it by
            # zero or fabricate a provider response after the channel is closed.
            record_failure('owner_save',error)
            result['final_owner_snapshot_unavailable']=True
        observation=output/'model-ledger/collaboration-observation/summary.json'
        if observation.is_file():
            try:result['collaboration_observation']=reference_file(observation)
            except BaseException as error:record_failure('observation_reference',error)
    if transport is not None:
        order.append('close_owned_model_transport_after_last_budget_read')
        try:
            close=getattr(transport,'close',None)
            if close is not None:close()
        except BaseException as error:record_failure('transport_close',error)
    result['controller_finalization']={'version':VERSION,'operation_order':order,
        'secondary_errors':secondary,'ledger_snapshot_source':snapshot_source,
        'existing_primary_error_preserved':True,'missing_usage_filled_with_zero':False,
        'model_calls':0,'new_model_dispatch':False}
    order.append('persist_controller_result_even_after_cleanup_failure')
    try:writer(output/'controller-result.json',result)
    except BaseException as error:
        failure={'version':VERSION,'result':result,'write_error':error_record(error),
                 'original_controller_result_not_overwritten':True}
        # The alternative is diagnostic evidence, never a normal result marker.
        try:atomic_write(output/'controller-result-write-failure.json',json_bytes(failure))
        except BaseException:
            sys.stderr.write('Controller result persistence failed; original failure: '+repr(result.get('error'))+'; write error: '+repr(error)+'\n')
        raise
    return result
