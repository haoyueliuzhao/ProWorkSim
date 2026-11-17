from concurrent.futures import ThreadPoolExecutor
from proworksim.software_organization_capacity_v206 import Capacity,PROFILE,GIB

def probe():return {'memory_available_bytes':950*GIB,'disk_free_bytes':1500*GIB,'cpu_busy_percent':15.,'load1':23.,'cpus':176}
def test_full_nine_generation_panel_can_overlap_after_startup():
 c=Capacity(probe)
 assert c.acquire('a','generation',3)[0]
 assert c.acquire('b','generation',3)[0]
 assert c.acquire('c','generation',3)==(False,'parallel_limit')
 c.ready('a')
 assert c.acquire('c','generation',3)[0]
 assert sum(x['count'] for x in c.snapshot()['leases'].values())==9
 assert c.acquire('g1','grader')[0] and c.acquire('g2','grader')[0]
 assert not c.acquire('g3','grader')[0]
def test_pressure_pauses_admission_without_cancelling_active():
 state=probe();c=Capacity(lambda:state)
 assert c.acquire('live','generation')[0];c.ready('live')
 state['cpu_busy_percent']=90
 assert c.acquire('next','generation')==(False,'host_cpu_headroom')
 assert 'live' in c.snapshot()['leases']
 state.update(cpu_busy_percent=10,memory_available_bytes=100*GIB)
 assert c.acquire('next','generation')==(False,'host_memory_headroom')
def test_simultaneous_admission_never_exceeds_global_startup_gate():
 c=Capacity(probe)
 with ThreadPoolExecutor(max_workers=20) as p:accepted=list(p.map(lambda i:c.acquire(str(i),'generation')[0],range(20)))
 assert sum(accepted)==8
 assert sum(v['count'] for v in c.snapshot()['leases'].values())==8
