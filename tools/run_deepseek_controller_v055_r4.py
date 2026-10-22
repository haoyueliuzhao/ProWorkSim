"""Bind the new financial client, then execute each arm's exact previous controller."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import runpy

from proworksim.software_benchmark_budget_runtime_v055_r4 import (
    validate_activation,controller_target,bind_controller_client,policy_sha256,new_api)
from proworksim.software_benchmark_candidates_v054 import reference,write_new


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True,type=Path)
    args=parser.parse_args();config=json.loads(args.config.read_bytes())
    activation=validate_activation(config['solver_activation'])
    target=controller_target(config,activation)
    with bind_controller_client():
        write_new(Path(config['output'])/'budget-client-binding-r4.json',{
            'version':'v055-private-controller-client-binding-r4','activation':config['solver_activation'],
            'runtime_revision':config['runtime_revision'],'arm':config['arm'],'condition_id':config['condition_id'],
            'controller_implementation':reference(target),'actual_API_source':reference(new_api.__file__),
            'budget_policy_sha256':policy_sha256(),'all_agent_and_condenser_calls_share_new_client':True,
            'request_payload_builder_unchanged':True,'model_calls_by_wrapper':0})
        # Keep the same --config argv; the unchanged previous main parses it.
        runpy.run_path(str(target),run_name='__main__')


if __name__=='__main__':main()
