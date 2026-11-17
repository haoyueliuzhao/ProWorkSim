"""Prepare or launch a future-only parallel window under an ordinary user unit.

Never modifies a running unit, old plan, cash limit, model or root resource group.
"""
import argparse,json,subprocess,re
from pathlib import Path
from proworksim.software_organization_capacity_v206 import PROFILE,Probe,GIB
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--unit',required=True);p.add_argument('--launch',action='store_true');a=p.parse_args()
if not re.fullmatch(r'proworksim-v207-[a-z0-9-]+',a.unit):p.error('New v207 unit name required')
plan=json.loads(a.plan.read_text());jobs=sum(len(b['branches']) for b in plan['blocks']);n=min(jobs,PROFILE['generation_limit'],int(PROFILE['managed_memory_budget_bytes']//(32*GIB))-2)
# Size the user unit to this launch's feasible concurrency, not all 48 ceilings.
physical=Probe(R)();n=min(n,int((physical['memory_available_bytes']-PROFILE['memory_floor_bytes']-72*GIB)//(32*GIB)))
if n<max(len(b['branches']) for b in plan['blocks']):raise RuntimeError('No whole candidate block fits current memory envelope')
memory=16*n+40;cpu=min(128,2*n+16)
if a.output.exists():raise ValueError('No takeover or replay of an old output root')
command=['systemd-run','--user','--unit='+a.unit,'--property=MemoryMax='+str(memory)+'G','--property=MemorySwapMax=0',
 '--property=CPUQuota='+str(cpu*100)+'%','--property=TasksMax=4096','--property=LimitNOFILE=16384','--property=RuntimeMaxSec=259200',
 '--working-directory='+str(R),'/usr/bin/env','-u','HTTP_PROXY','-u','HTTPS_PROXY','-u','ALL_PROXY','-u','http_proxy','-u','https_proxy','-u','all_proxy',
 str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools/run_organization_window_v207.py'),
 '--plan',str(a.plan.resolve()),'--output',str(a.output.resolve()),'--generation-limit',str(n)]
print(json.dumps({'command':command,'generation_upper':n,'API_upper':48,'graders':2,'startup':8,'resource_profile':PROFILE,'root_system_slice_changes':False,'existing_units_modified':False},indent=2))
if a.launch:raise SystemExit(subprocess.run(command,cwd=R).returncode)
