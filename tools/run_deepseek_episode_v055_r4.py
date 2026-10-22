"""Route only future all-arm episodes to the new financial controller binding."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from proworksim import software_benchmark_runner_v055 as original
from proworksim.software_benchmark_budget_runtime_v055_r4 import validate_activation
from proworksim.software_benchmark_candidates_v054 import checked,reference,write_new


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();config=json.loads(args.config.read_bytes())
    activation_ref=config['solver_activation'];activation=validate_activation(activation_ref)
    if config['arm'] not in activation['arms'] or config['runtime_revision']!=activation['runtime_revision']:
        raise ValueError('Future all-arm runtime identity differs')
    entry=checked(activation['controller_entrypoint']);before=original.direct_environment_command;routed=[]
    def direct(command):
        command=list(map(str,command));old=str(original.ROOT/'tools/run_deepseek_controller_v055.py')
        if command.count(old)!=1:raise ValueError('Unexpected runner controller invocation')
        command[command.index(old)]=str(entry);routed.append(command)
        return before(command)
    intent=write_new(args.output.parent/'solver-routing.json',{
        'version':'v055-all-arm-budget-controller-routing-r4','solver_activation':activation_ref,
        'config':reference(args.config),'controller_entrypoint':activation['controller_entrypoint'],
        'runtime_revision':activation['runtime_revision'],'original_runner_implementation_unchanged':True,
        'model_calls_by_wrapper':0,'original_slot_and_budget_cap_unchanged':True})
    original.direct_environment_command=direct
    try:result=original.run(config,args.output)
    finally:original.direct_environment_command=before
    if result['status']=='closed' and len(routed)!=1:raise RuntimeError('One exact controller routing required')
    write_new(args.output.parent/'solver-routing-result.json',{'routing_intent':intent,
        'result':reference(args.output/'result.json'),'actual_controller_routing_count':len(routed),
        'runtime_revision':activation['runtime_revision']})
    return 0 if result['status']=='closed' else 75


if __name__=='__main__':raise SystemExit(main())
