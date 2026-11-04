import os,resource,sys,json
resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,4*1024**3))
def refuse(event,args):
 if event in {'socket.connect','socket.bind','socket.getaddrinfo','socket.sendto','subprocess.Popen','os.system','os.fork','os.posix_spawn'}:
  raise RuntimeError('The CPU-only memory probe refuses external operations')
sys.addaudithook(refuse)
from proworksim import software_benchmark_grading_v127 as grading
def no_authority(*args,**kwargs):
 raise RuntimeError('No execution authority in a CPU memory probe')
engine=grading.factory(watchdog_guard=no_authority)
print(json.dumps({'passed':True,'RLIMIT_AS':resource.getrlimit(resource.RLIMIT_AS),'engine_type':type(engine).__name__,'API_calls':0,'Docker_operations':0,'network_calls':0}))
