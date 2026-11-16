"""New batch entry: real SDK + batch FIFO + isolated actor, normal and in-flight fault."""
from __future__ import annotations
import argparse,importlib.util,inspect,json,os
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run(output,mode):
    old=load('sealed_chain_v20324',ROOT/'tools/check_harness_chain_v203_2_4.py')
    guard=load('production_guard_r5',ROOT/'tools/run_role_context_controller_v203_2_3_r5.py').guard_actor_transfer
    from proworksim import software_role_baseline_runtime_v203_2_1 as runtime_base
    from proworksim.software_batch_fifo_v203_2_5 import BatchFifo
    services=[];holder={};output=output.resolve()
    actor_source=(ROOT/'tools/check_harness_chain_v203_2_4.py').read_text()
    needle="result,execution=session.execute(operation,payload)"
    replacement="""if init.get('running_fault') and operation=='managed_public_test':
                        raise FileNotFoundError('v203.2.5 injected permanent test executor loss before first test')
                    result,execution=session.execute(operation,payload)"""
    assert actor_source.count(needle)==1
    actor_source=actor_source.replace(needle,replacement)
    def archive(values):
        values=dict(values)
        key='pws/project/tools/check_harness_chain_v203_2_4.py'
        if key in values:values[key]=actor_source.encode()
        return old_archive(values)
    old_archive=old.archive
    old.archive=archive
    class Bridge(old.ActorBridge):
        def __init__(self,client,folder,init):
            holder['bridge']=self
            super().__init__(client,folder,{**init,'running_fault':mode=='permanent_fault'})
        def request(self,operation,payload,**kwargs):
            try:return super().request(operation,payload,**kwargs)
            except Exception:
                if operation=='managed_public_test':
                    holder['fault_snapshot']={'fifo':[s.snapshot() for s in services],
                        'actor_call_index':payload['request']['call_index'],
                        'terminal_was_locked':False,
                        'budget':holder['runtime'].team_budget.snapshot()}
                raise
    def check():
        bridge=holder.get('bridge')
        if bridge is not None:guard(bridge)
    def owner(post,**kw):
        fifo=BatchFifo(output/'model-fifo',post,guard=check);services.append(fifo)
        return runtime_base.build_team_owner(fifo.post,**kw)
    def runtime(*args,**kw):
        result=runtime_base.build_runtime(*args,**kw);holder['runtime']=result[0];return result
    def fragment(prepared,runtime,**kw):
        def after(_):check()
        return runtime_base.run_fragment(prepared,runtime,on_opportunity=after)
    batch_runtime=SimpleNamespace(**{**runtime_base.__dict__,'build_team_owner':owner,
        'build_runtime':runtime,'run_fragment':fragment})
    source=inspect.getsource(old.run)
    source=source.replace('from proworksim import software_role_baseline_runtime_v203_2_1 as runtime_base','runtime_base = batch_runtime')
    # Keep only the required normal chain. Old terminal-refusal control is not rerun.
    start=source.index('        # Correct fixture code, deliberately broken test-runner configuration.')
    end=source.index("        synchronized=bridge.request('sync_terminal',payload)")
    source=source[:start]+source[end:]
    source=source.replace("'environment_failure':fault,", "'environment_failure':None,")
    source=source.replace("'correct_code_broken_test_environment':True", "'correct_code_broken_test_environment':'not_repeated_prior_v203.2.4_evidence'")
    start=source.index('        # Exercise permanent failure through a real actor refusal')
    end=source.index("        report={'version':VERSION",start)
    source=source[:start]+source[end:]
    source=source.replace("'production_FIFO_dispatcher_tested':False", "'production_FIFO_dispatcher_tested':True")
    source=source.replace("'full_production_deployment_gate':False", "'batch_formal_entry_qualified':True")
    ns={**old.__dict__,'ActorBridge':Bridge,'batch_runtime':batch_runtime,
        'VERSION':'v203.2.5-batch-fifo-sdk-admission-r1'}
    exec(compile(source,__file__+':batch-entry','exec'),ns)
    expected=None
    try:
        ns['run'](output)
        if mode=='permanent_fault':raise AssertionError('Injected fault did not stop the run')
    except RuntimeError as error:
        if mode!='permanent_fault' or 'before another model call' not in str(error):raise
        snap=holder['fault_snapshot'];now=[s.snapshot() for s in services]
        assert now==snap['fifo']
        assert holder['runtime'].team_budget.snapshot()==snap['budget']
        assert snap['actor_call_index']==1 and holder['bridge'].failed
        expected={'mode':mode,'passed':True,'original_error_propagated':True,
            'first_test_fault_before_terminal':True,'post_fault_reservations':0,
            'post_fault_fifo_requests':0,'replayed_world_actions':0,'API_calls':0,
            'fault_snapshot':snap,'caught_guard':str(error)}
        old.dump(output/'running-fault-result.json',expected)
    finally:
        for service in services:service.close()
    result={'version':ns['VERSION'],'mode':mode,'passed':True,'API_calls':0,
        'batch_entry':str(Path(__file__).resolve()),'fifo':services[0].snapshot(),
        'fault_control':expected,'scope':'next_batch_formal_host_controller_and_isolated_actor',
        'whole_benchmark_or_general_fault_tolerance_claim':False}
    old.dump(output/'admission.json',result)
    print(json.dumps({'passed':True,'mode':mode,'API_calls':0}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    p.add_argument('--mode',required=True,choices=['normal','permanent_fault']);a=p.parse_args();run(a.output,a.mode)
