"""One full zero-model actor/controller entry before any recovered formal call."""
import json,sqlite3
from proworksim import software_benchmark_scope_v203_2_3_r3 as scope
from proworksim.software_benchmark_episode_v203_2_3_r3 import build_episode
from proworksim.software_benchmark_host_memory_v132 import HostMemoryGate
from proworksim.software_benchmark_candidates_v054 import reference


def run():
    scope.require_allowed('v066.run')
    limits=scope.verify_host_limits('diagnostic')
    with sqlite3.connect(scope.LEDGER_FILE.resolve().as_uri()+'?mode=ro',uri=True) as db:
        before=db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
    if before!=0:raise PermissionError('Diagnostic must precede child provider calls')
    memory=HostMemoryGate(maximum=1)
    try:
        implementation=build_episode(scope=scope,guard=scope.require_allowed,host_memory=memory)
        result_ref=implementation.run_diagnostic(1)
        result=scope.load(result_ref)
        quiet=scope.load(result['quiescence'])
        child=scope.load(result['controller_result']) if result.get('controller_result') else {}
        replay=child.get('recorded_provider_replay',{})
        history=replay.get('replay',{})
        with sqlite3.connect(scope.LEDGER_FILE.resolve().as_uri()+'?mode=ro',uri=True) as db:
            after=db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
        passed=(replay.get('passed') is True and replay.get('condition')=='K1'
            and replay.get('recorded_two_tool_response_rejected') is True
            and replay.get('remapped_projection_calls',0)>0
            and sum(history.get('recorded_responses_replayed',{}).values())==7
            and history.get('programmed_boundary_responses')=={'member_001':1,'member_002':1}
            and replay.get('new_provider_calls')==0 and after==before==0
            and result.get('cpu_lane_admission',{}).get('required_lane_cpu_count')==24
            and result.get('passed') is True and result.get('model_calls')==0
            and child.get('diagnostic_passed') is True and child.get('actual_SDK_initialized') is True
            and child.get('team_diagnostic',{}).get('model_calls')==0
            and child.get('team_diagnostic',{}).get('fixed_members')==['member_001','member_002']
            and child.get('content_tokenizer',{}).get('measured',True)
            and quiet.get('quiescent') is True and quiet.get('all_owned_objects_removed') is True
            and quiet.get('cleanup_errors')==[] and quiet.get('create_result_unknown') is False)
        receipt={'version':'v203.2.3-recorded-format-feedback-real-entry-admission-r3','passed':bool(passed),
            'plan':reference(scope.PLAN_FILE),'result':result_ref,'host_limits':limits,
            'CPU_guard':implementation.cpu_guard_binding,'model_calls':0,'API_calls':0,
            'recorded_provider_replay':replay,'provider_rows_before':before,'provider_rows_after':after,
            'actual_actor_controller_package_ready_and_sdk_initialized':bool(child.get('actual_SDK_initialized'))}
        ref=scope.retain(scope.DIAGNOSTIC_RECEIPT,receipt)
        print(json.dumps({'passed':bool(passed),'diagnostic_receipt':ref,'error':result.get('error')}),flush=True)
        if not passed:raise RuntimeError('Actual diagnostic did not pass; no formal API admission')
        return ref
    finally:memory.close()


if __name__=='__main__':run()
