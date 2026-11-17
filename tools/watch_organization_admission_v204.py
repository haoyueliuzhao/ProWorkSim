"""After the registered real pair closes, verify feedback gate without grading hints."""
import argparse,json,os,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--block',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
ROOT=Path(__file__).resolve().parents[1]
while True:
 f=a.block/'progress.json'
 if f.exists():
  q=json.loads(f.read_text())
  if q['status']=='generation_block_ended':break
 time.sleep(20)
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD')}
p=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/run_offline_scorer_v096.py'),str(ROOT/'tools/check_organization_model_feedback_v204.py'),
 '--block',str(a.block),'--output',str(a.output)],cwd=ROOT,env=env)
raise SystemExit(p.returncode)
