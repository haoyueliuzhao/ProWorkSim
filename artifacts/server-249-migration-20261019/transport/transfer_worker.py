import sys,subprocess,json,time
from pathlib import Path
p=Path(sys.argv[1]); data=json.loads(p.read_text()); t=time.time()
with Path(data['log']).open('wb') as log:
 result=subprocess.run(data['command'],stdout=log,stderr=subprocess.STDOUT)
Path(data['result']).write_text(json.dumps({'started_at':t,'ended_at':time.time(),'returncode':result.returncode,'command':data['command'],'password_in_command_or_file':False},indent=2)+'\n')
raise SystemExit(result.returncode)
