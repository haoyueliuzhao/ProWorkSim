from pathlib import Path
import fcntl,importlib.util,json,os,subprocess
ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT=ROOT/'runs/software-benchmark-v055/final-shared-cache-recovery-r4'
spec=importlib.util.spec_from_file_location('original_fresh_proof',ROOT/'tools/reclaim_terminal_cache_v055_r2.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
base=helper.original()
names=['django__django-13344','django__django-14053','django__django-16136','django__django-16877','pytest-dev__pytest-7236','sphinx-doc__sphinx-9230']
intent=base.write_new(OUT/'preaudit-intent.json',{'created_utc':base.now(),'source':base.ref(__file__),'helper':base.ref(helper.__file__),'names':names,'scope':'read-only exact six original cache roots; no astropy recovery paths','new_model_calls':0,'deletions':0})
old,new=base.snapshot();registry=base.registry();results=[]
for name in names:
 lockpath=base.CACHE/'locks'/(name+'.lock')
 descriptor=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
  a,b,prep=base.task_rows(old,new,name)
  rootfs=base.CACHE/name/registry[name]['baseline_mapping']['sha256'][:16]/'rootfs'
  identity=rootfs.lstat()
  proof=helper.current_proof(base,a,b,prep,intent)
  proofref=base.write_new(OUT/(name+'.preaudit-proof.json'),proof)
  result={'instance_id':name,'rootfs':str(rootfs),'device':identity.st_dev,'inode':identity.st_ino,'nine_consumers_terminal':True,'fresh_quiescence':True,'proof':proofref,'original_lock':str(lockpath)}
 except Exception as error:
  result={'instance_id':name,'status':'blocked','error':{'type':type(error).__name__,'message':str(error)}}
 finally:os.close(descriptor)
 results.append(result)
 print(json.dumps(result),flush=True)
paths=[r['rootfs'] for r in results if r.get('fresh_quiescence')]
if paths:
 measured=subprocess.run(['sudo','-n','du','-s','-B1','-x',*paths],capture_output=True,text=True,check=True)
 allocated={line.split('\t',1)[1]:int(line.split('\t',1)[0]) for line in measured.stdout.splitlines()}
 for row in results:
  if row.get('rootfs') in allocated:row['allocated_bytes']=allocated[row['rootfs']]
base.write_new(OUT/'preaudit.json',{'observed_utc':base.now(),'intent':intent,'results':results,'new_model_calls':0,'deletions':0})
