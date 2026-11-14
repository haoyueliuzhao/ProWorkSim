"""The fixed v058 scorer loader with bounded host-library thread reservations.

Only this new scorer process receives these environment limits. Docker test
containers, the API owner, old launchers and shared-host settings are unchanged.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
VERSION='v096-single-thread-host-scorer-library-profile-r1'
THREAD_LIMITS={
    'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
    'NUMEXPR_NUM_THREADS':'1','NUMEXPR_MAX_THREADS':'1','TOKENIZERS_PARALLELISM':'false',
}


def launch_spec(arguments,*,inherited=None):
    source=ROOT/'tools/run_offline_scorer_v058.py'
    spec=importlib.util.spec_from_file_location('v096_fixed_scorer_loader',source)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    command,env=module.launch_spec(arguments,inherited=inherited)
    env.update(THREAD_LIMITS,PROWORKSIM_SCORER_HOST_THREAD_PROFILE=VERSION)
    return command,env


if __name__=='__main__':
    command,env=launch_spec(sys.argv[1:])
    os.chdir(ROOT)
    os.execve(command[0],command,env)
