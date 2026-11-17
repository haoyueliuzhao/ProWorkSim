"""Future batch admission only. No host settings, root operations or running-job cancellation."""
import os,shutil,threading,time
from pathlib import Path
GIB=1024**3
PROFILE={'generation_limit':48,'grader_limit':2,'starting_generation_limit':8,
 'memory_floor_bytes':96*GIB,'disk_floor_bytes':128*GIB,'managed_memory_budget_bytes':832*GIB,
 'generation_peak_allowance_bytes':32*GIB,'grader_peak_allowance_bytes':32*GIB,
 'startup_disk_allowance_bytes':8*GIB,'cpu_busy_percent':85.,'minimum_cpu_headroom':8}
class Probe:
 def __init__(self,root):self.root=Path(root);self.previous=None;self.lock=threading.Lock()
 def __call__(self):
  with self.lock:
   mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
   nums=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]));now=time.monotonic();sample=(now,sum(nums),nums[3]+nums[4]);busy=None
   if self.previous:
    dt=sample[1]-self.previous[1]
    if now-self.previous[0]>=1 and dt>0:busy=100*(1-(sample[2]-self.previous[2])/dt)
   if self.previous is None or now-self.previous[0]>=1:self.previous=sample
   return {'memory_available_bytes':mem,'disk_free_bytes':shutil.disk_usage(self.root).free,
    'cpu_busy_percent':busy,'load1':os.getloadavg()[0],'cpus':len(os.sched_getaffinity(0))}
class Capacity:
 def __init__(self,probe,profile=None):self.probe=probe;self.profile=dict(profile or PROFILE);self.lock=threading.Lock();self.leases={}
 def acquire(self,key,kind,count=1):
  if kind not in ('generation','grader') or type(count)!=int or count<1:raise ValueError('Invalid lease')
  with self.lock:
   if key in self.leases:raise ValueError('Duplicate resource identity')
   p=self.profile;s=self.probe();gen=sum(x['count'] for x in self.leases.values() if x['kind']=='generation');grade=sum(x['count'] for x in self.leases.values() if x['kind']=='grader');starting=sum(x['count'] for x in self.leases.values() if x['starting'])
   if (kind=='generation' and (gen+count>p['generation_limit'] or starting+count>p['starting_generation_limit'])) or (kind=='grader' and grade+count>p['grader_limit']):return False,'parallel_limit'
   memory=count*p[kind+'_peak_allowance_bytes'];reserved=sum(x['memory'] for x in self.leases.values())
   budget=p['managed_memory_budget_bytes']
   if kind=='generation':
    # Preserve both asynchronous grader lanes even before they start.
    budget-=(p['grader_limit']-grade)*p['grader_peak_allowance_bytes']
   if reserved+memory>budget:return False,'batch_memory_envelope'
   # Physical available memory already reflects live tasks. Do not subtract
   # their entire ceilings again; add only still-starting growth allowance.
   growth=sum(x['memory'] for x in self.leases.values() if x['starting'])
   if s['memory_available_bytes']<p['memory_floor_bytes']+growth+memory:return False,'host_memory_headroom'
   if s['disk_free_bytes']<p['disk_floor_bytes']+(starting+count)*p['startup_disk_allowance_bytes']:return False,'disk_headroom'
   head=max(p['minimum_cpu_headroom'],int(s['cpus']*.1))
   if s['load1']>max(1,s['cpus']-head) or (s['cpu_busy_percent'] is not None and s['cpu_busy_percent']>p['cpu_busy_percent']):return False,'host_cpu_headroom'
   self.leases[key]={'kind':kind,'count':count,'memory':memory,'starting':kind=='generation'}
   return True,None
 def ready(self,key):
  with self.lock:self.leases[key]['starting']=False
 def release(self,key):
  with self.lock:del self.leases[key]
 def snapshot(self):
  with self.lock:return {'profile':self.profile,'leases':{k:dict(v) for k,v in self.leases.items()}}
