"""Serial real-container synthetic SDK control, no model service or shared changes."""
import json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];root=R/'runs/software-benchmark-v211/docker-sdk-control-r2';root.mkdir(parents=True,exist_ok=False)
for phase in ('prefix','restored'):
 args=[str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools/check_dynamic_organization_sdk_v211.py'),'--output',str(root/phase),'--docker']
 if phase=='restored':args+=['--checkpoint',str(root/'prefix/checkpoint')]
 (root/'progress.json').write_text(json.dumps({'phase':phase,'status':'running','API_calls':0}))
 with (root/(phase+'.log')).open('xb') as log:p=subprocess.run(args,cwd=R,stdout=log,stderr=subprocess.STDOUT)
 if p.returncode:
  (root/'progress.json').write_text(json.dumps({'phase':phase,'status':'failed','exit':p.returncode,'API_calls':0}));raise SystemExit(p.returncode)
(root/'progress.json').write_text(json.dumps({'status':'passed','API_calls':0,'phases':['prefix','restored']}))
