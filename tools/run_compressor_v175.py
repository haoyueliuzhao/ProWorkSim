"""Use the existing private Python; expose one specifically chosen GPU only."""
import importlib.util
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in [str(i) for i in range(8)]+['cpu']:
        raise ValueError('Choose a concrete CPU or physical GPU index')
    gpu=sys.argv[1]
    spec=importlib.util.spec_from_file_location('bounded_existing_python',ROOT/'tools/run_offline_scorer_v096.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    command,env=module.launch_spec([str(ROOT/'tools/score_context_units_v175.py'),'--device','cpu' if gpu=='cpu' else 'cuda:0'])
    if gpu!='cpu':env.update(CUDA_VISIBLE_DEVICES=gpu,NVIDIA_VISIBLE_DEVICES=gpu)
    os.execve(command[0],command,env)
