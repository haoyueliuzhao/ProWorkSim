import collections, datetime, json, os, pathlib, subprocess, time
ROOT=pathlib.Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT=ROOT/'runs/software-benchmark-v055/data-volume-reserve-r1/observation-r1'
OUT.mkdir(parents=True,exist_ok=True)
PATHS={'deepseek':ROOT/'runs/software-benchmark-v055/queue-r1/state.json','qwen':ROOT/'runs/software-benchmark-v054/formal-queue-r1/state.json'}
def compact_gate(g):
 return {k:g.get(k) for k in ['kind','admitted','target_volume','free_bytes','active_peak_reserved_bytes','requested_peak_bytes','minimum_remaining_bytes','estimated_unreserved_bytes_after_launch','observed_utc']}
def sample(index):
 now=datetime.datetime.now(datetime.timezone.utc);s={'sample_index':index,'observed_utc':now.isoformat(),'observed_cst':now.astimezone(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'read_only_queue_observer':True,'volumes':{},'queues':{}}
 for path in ['/data0','/data1','/data2','/data3']:
  v=os.statvfs(path);s['volumes'][path]={'device':os.stat(path).st_dev,'available_bytes':v.f_bavail*v.f_frsize,'root_inclusive_free_bytes':v.f_bfree*v.f_frsize}
 for name,p in PATHS.items():
  x=json.loads(p.read_text());counts=collections.Counter(r['generation']['status'] for r in x['rows']);by={}
  for r in x['rows']:
   group=r['slot'].get('condition_id',r['slot']['arm']);by.setdefault(group,collections.Counter())[r['generation']['status']]+=1
  d=x.get('disk_reservation_status',{});cap=x.get('capacity',{});q={'state_updated_utc':x.get('updated_utc'),'status':x.get('status'),'dispatch_stopped':x.get('dispatch_stopped'),'generation_counts':dict(counts),'groups':{k:dict(v) for k,v in by.items()},'active_generation':counts.get('running',0),'target_generation':cap.get('desired_generation_concurrency'),'capacity':{k:cap.get(k) for k in ['admit','load_1m','available_memory_bytes','generation_disk_admitted','preparation_disk_admitted']},'metadata_error':d.get('metadata_error'),'last_gate':compact_gate(x.get('last_disk_dispatch_admission',{})),'environment_coverage':x.get('environment_coverage',{}).get('task_status_counts'),'prewarm_backlog':x.get('prewarm_backlog'),'shared_preparation_demand':{k:x.get('shared_preparation_demand',{}).get(k) for k in ['selected_task_ids','running_preparation_count','priority_reserve_required']}}
  s['queues'][name]=q
  if index==0 and name=='deepseek':
   active={k:v for k,v in x.get('preparation',{}).items() if v.get('status')=='running' or v.get('readiness',{}).get('status')=='preparing' or any(a.get('status')=='running' for a in v.get('attempts',[]))}
   units=set()
   def walk(v):
    if isinstance(v,dict):
     for k,w in v.items():
      if k=='unit' and isinstance(w,str): units.add(w)
      else:walk(w)
    elif isinstance(v,list):
     for w in v:walk(w)
   walk(active)
   q['initial_preparation_task_ids']=list(active)
   if units:
    proc=subprocess.run(['systemctl','--user','show',*sorted(units),'--property=Id,ActiveState,SubState,MainPID,InvocationID'],capture_output=True,text=True)
    q['initial_preparation_units']={'units':sorted(units),'returncode':proc.returncode,'output':proc.stdout,'stderr':proc.stderr}
 (OUT/'latest.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
 with (OUT/'samples.jsonl').open('a') as f:f.write(json.dumps(s,ensure_ascii=False,sort_keys=True)+'\n')
 print(json.dumps({'utc':s['observed_utc'],'cst':s['observed_cst'],'available_GiB':{k:round(v['available_bytes']/2**30,2) for k,v in s['volumes'].items()},'queues':{k:{'counts':v['generation_counts'],'target':v['target_generation'],'coverage':v['environment_coverage'],'backlog':v['prewarm_backlog'],'metadata_error':v['metadata_error'],'gate_admitted':v['last_gate']['admitted']} for k,v in s['queues'].items()}}),flush=True)
 return s
start=time.monotonic()
for i in range(11):
 if i:time.sleep(max(0,start+60*i-time.monotonic()))
 sample(i)
(OUT/'observer-completed.json').write_text(json.dumps({'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sample_count':11,'duration_seconds':time.monotonic()-start,'queue_state_and_services_modified':False},indent=2)+'\n')
