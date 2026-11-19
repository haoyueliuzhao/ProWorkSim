"""Manage only a verified ordinary-user experiment coordinator and its descendants."""
import os,signal,json,time
from pathlib import Path

def process(pid):
 p=Path('/proc')/str(pid)
 try:
  stat=(p/'stat').read_text();tail=stat[stat.rfind(')')+2:].split();uid=int(next(x.split()[1] for x in (p/'status').read_text().splitlines() if x.startswith('Uid:')))
  return {'pid':pid,'state':tail[0],'ppid':int(tail[1]),'start_ticks':int(tail[19]),'uid':uid,'argv':(p/'cmdline').read_bytes().decode().strip('\0').split('\0')}
 except (FileNotFoundError,ProcessLookupError):return None

def same_alive(expected):
 p=process(expected['pid']);return bool(p and p['start_ticks']==expected['start_ticks'] and p['uid']==expected['uid'] and p['state']!='Z')

def children(pid):
 found=set()
 for task in (Path('/proc')/str(pid)/'task').glob('*'):
  try:found.update(map(int,(task/'children').read_text().split()))
  except FileNotFoundError:pass
 return [p for x in found if (p:=process(x)) is not None]

def suspend(pid,expected_script):
 p=process(pid)
 if not p or p['uid']!=os.getuid() or str(Path(expected_script).resolve()) not in [str(Path(x).resolve()) for x in p['argv'] if x.endswith('.py')]:raise ValueError('Not the exact owned coordinator')
 if p['state'] in ('T','t','Z'):raise ValueError('Coordinator not independently running')
 os.kill(pid,signal.SIGSTOP)
 for _ in range(100):
  now=process(pid)
  if now and now['state'] in ('T','t'):break
  time.sleep(.01)
 else:raise RuntimeError('Coordinator did not enter stopped dispatch state')
 jobs=children(pid)
 if any(j['uid']!=os.getuid() for j in jobs):os.kill(pid,signal.SIGCONT);raise ValueError('Foreign child, refuse handoff')
 return {'coordinator':p,'children':jobs,'coordinator_dispatch_only_suspended':True,'children_signalled':False,'captured_at':time.time()}

def retire(snapshot):
 owner=snapshot['coordinator']
 if not same_alive(owner):return {'already_exited':True}
 if any(j['state']!='Z' for j in children(owner['pid'])):return {'deferred_live_child':True}
 # Pending SIGTERM is handled on resume before ordinary dispatch resumes.
 os.kill(owner['pid'],signal.SIGTERM);os.kill(owner['pid'],signal.SIGCONT)
 return {'terminated_after_children_finished':True,'hard_kill':False}
