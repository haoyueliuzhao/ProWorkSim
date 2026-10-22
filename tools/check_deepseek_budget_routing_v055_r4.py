"""Pure mock all-arm/client/worker routing; no ledger constructor or migration."""
import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from proworksim import software_benchmark_budget_runtime_v055_r4 as r
from proworksim import software_benchmark_queue_native_host_v055_r8 as h
from proworksim.software_benchmark_deepseek_interfaces_v055 import DeepSeekAdapter,NATIVE_TOOLS
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_benchmark_queue_v055 import load
from proworksim.storage import digest,json_bytes


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    args.output=args.output.resolve();args.output.parent.mkdir(parents=True,exist_ok=False);root=args.output.parent
    old_client=r.old_api.DeepSeekClient
    assert r.new_api.DeepSeekClient.complete is old_client.complete
    previous_ref=reference(h.ROOT/'runs/software-benchmark-v055/native-host-revision-r3/activation.json')
    activation={'runtime_revision':'budget-client-r4-control','generation_entrypoint':reference(h.ROOT/'tools/run_deepseek_episode_v055_r4.py'),
        'controller_entrypoint':reference(h.ROOT/'tools/run_deepseek_controller_v055_r4.py'),
        'previous_native_activation':previous_ref,'original_project_controller':reference(h.ROOT/'tools/run_deepseek_controller_v055.py'),
        'files':[reference(r.new_api.__file__),reference(r.__file__)]}
    aref=write_new(root/'fixture-activation.json',activation)
    observations=[];targets=[]
    def counter(request):return {'prompt_tokens':10,'method':'CPU_fixture_only','request_sha256':digest(json_bytes(request))}
    def complete(self,request,**kwargs):
        assert type(self) is r.new_api.DeepSeekClient
        observations.append({'condition':kwargs['condition'],'usage_id':kwargs['usage_id'],
                             'max_tokens':request['max_tokens'],'thinking':request['thinking']})
        return {'id':'fixture-'+str(len(observations)),'model':r.new_api.MODEL,
            'choices':[{'message':{'role':'assistant','content':'fixture','reasoning_content':''},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':1,'total_tokens':11}}
    with patch.object(r.new_api.DeepSeekClient,'complete',complete):
        for arm in ('REF','MATCH','PROJECT'):
            for thinking in (False,True):
                condition=arm+('-thinking' if thinking else '-nonthinking')
                names=NATIVE_TOOLS if arm!='PROJECT' else {'fixture_read'}
                tools=[{'type':'function','function':{'name':name,'parameters':{'type':'object','properties':{}}}} for name in sorted(names)]
                client=object.__new__(r.new_api.DeepSeekClient)
                client.ledger=SimpleNamespace(snapshot=lambda:{'halted':None,'inflight_count':0})
                adapter=DeepSeekAdapter(client=client,arm=arm,thinking=thinking,slot_id='fixture-'+condition,
                    condition_id=condition,folder=root/condition,allowed_tool_names=names,counter=counter)
                messages=[{'role':'user','content':'CPU fixture, no task or answer'}]
                payload=adapter.request(messages,tools)
                with r.bind_controller_client():
                    assert r.old_api.DeepSeekClient is r.new_api.DeepSeekClient
                    target=r.controller_target({'arm':arm,'runtime_revision':activation['runtime_revision']},activation)
                    targets.append({'condition':condition,'implementation':str(target)})
                    assert adapter.request(messages,tools)==payload
                    adapter.complete(payload,'agent')
                    if arm!='PROJECT':adapter.complete(adapter.request(messages,[]),'condenser')
                assert r.old_api.DeepSeekClient is old_client
    assert len(observations)==10 and sum(x['usage_id']=='condenser' for x in observations)==4
    assert all(x['implementation'].endswith('controller_v055.py' if x['condition'].startswith('PROJECT') else 'controller_v055_r3.py') for x in targets)
    jobs=[];calls=[]
    def materialize(plan,template,slot,output):
        return write_new(output,{**slot,'frozen_sources':[],'fixture_config_only':True})
    def subprocess(*a,**kw):calls.append(a);return SimpleNamespace(returncode=0)
    with patch.object(h.builder,'materialize_config',materialize),patch.object(h.builder.subprocess,'run',subprocess):
        with h.builder_routes(aref,activation):
            for arm in ('REF','MATCH','PROJECT'):
                subject=object.__new__(h.builder.NativeHostCoordinator);subject.root=root/('worker-'+arm);subject.root.mkdir()
                subject.plan={};subject.template={};subject.plan_ref={'fixture_only':True};subject.activation=activation;subject.activation_ref=aref;subject.save=lambda:None
                row={'slot':{'arm':arm,'slot_id':'fixture-builder-'+arm}};record={'status':'pending'}
                h.builder.NativeHostCoordinator.launch(subject,row,record,kind='generation')
                job=load(record['job']);argv=job['argv']
                assert str(h.ROOT/'tools/run_deepseek_episode_v055_r4.py') in argv
                config=load(reference(Path(argv[argv.index('--config')+1])))
                assert config['solver_activation']==aref and config['runtime_revision']==activation['runtime_revision']
                jobs.append({'arm':arm,'job':record['job'],'all_arm_new_entry':True})
    assert len(calls)==3
    assert h.NativeHostCoordinator.tick is h.previous.NativeHostCoordinator.tick
    print(write_new(args.output,{'version':'v055-all-arm-budget-client-routing-cpu-control-r4','passed':True,
        'checks':['all_six_conditions_preserve_request_payloads','ten_agent_and_native_condenser_calls_bind_new_client',
            'PROJECT_uses_original_controller_native_uses_qualified_r3','all_three_worker_configs_and_argv_select_new_entry',
            'original_completion_transport_method_identity_retained','original_phase_volume_and_budget_scheduling_tick_retained'],
        'mock_client_calls':observations,'original_controller_targets':targets,'mock_worker_jobs':jobs,
        'sources':[reference(r.__file__),reference(h.__file__),reference(r.new_api.__file__),reference(__file__)],
        'real_API_calls':0,'ledger_constructors_called':0,'migration_functions_called':0,
        'real_ledger_reads_or_writes':0,'formal_queue_writes':0,'real_workers_started':0}))

if __name__=='__main__':main()
