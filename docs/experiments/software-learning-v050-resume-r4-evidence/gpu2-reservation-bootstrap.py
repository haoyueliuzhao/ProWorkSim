from pathlib import Path
import os,sys,time,json,subprocess,hashlib,traceback
lease=Path(sys.argv[1]).resolve()
source=Path(sys.argv[2]).resolve()
sys.path[:0]=[str(source/'src'),str(source)]
from scripts.software_learning_resources_v050r3 import reserve_before_load,binding_from_env
record={'phase':'reserving','pid':os.getpid(),'started_at':time.time(),'model_started':False}
def save():
    target=lease/'state.json'; tmp=lease/'state.json.tmp'
    tmp.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n'); tmp.replace(target)
save()
try:
    reservation=reserve_before_load(lease/'actual',binding_from_env())
    record.update(phase='reserved_waiting_for_frozen_worker',reserved_at=time.time(),reservation=reservation)
    save()
    request=lease/'handoff.json'
    while not request.exists():
        time.sleep(1)
    handoff=json.loads(request.read_text())
    expected_source=Path('/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-learning-v050/resume-r4-source')
    expected_run=Path('/data1/zhuxinrui/projects/ProWorkSim/runs/software-learning-v050-resume-r4')
    if handoff.get('source_root')!=str(expected_source) or handoff.get('run_root')!=str(expected_run) or handoff.get('worker')!='update-Q_plus':
        raise ValueError('Reservation may serve only its authorized original Q_plus recovery')
    plan=json.loads((expected_run/'plan.json').read_text())
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=expected_source,text=True).strip()
    dirty=subprocess.check_output(['git','status','--porcelain'],cwd=expected_source,text=True)
    if dirty or head!=handoff['source_commit'] or plan['source']['code_commit']!=head:
        raise ValueError('The delegated worker source must be frozen and clean')
    state=json.loads((expected_run/'supervisor.json').read_text())['states']['update-Q_plus']
    if state.get('pid')!=os.getpid() or state.get('attempted') is not True or state.get('status')!='running':
        raise ValueError('Frozen supervisor must own this exact reservation process')
    record.update(phase='handoff_to_frozen_worker',handoff_at=time.time(),handoff=handoff)
    save()
    for name in list(sys.modules):
        if name=='scripts' or name.startswith('scripts.') or name=='proworksim' or name.startswith('proworksim.'):
            del sys.modules[name]
    sys.path=[str(expected_source/'src'),str(expected_source)]+[p for p in sys.path if p not in (str(source/'src'),str(source))]
    os.chdir(expected_source)
    os.environ['PYTHONPATH']=str(expected_source/'src')+os.pathsep+str(expected_source)+os.pathsep+plan['runtime_dependency_path']
    from scripts.software_learning_resume_v050r4 import run_worker
    record.update(phase='worker_entry',worker_entry_at=time.time(),model_started=True)
    save()
    result=run_worker(expected_run,'update-Q_plus',expected_run/'update-Q_plus/actual')
    record.update(phase='complete',ended_at=time.time(),exit_code=0,result_status=result.get('status'))
    save()
except BaseException as error:
    record.update(phase='failed',ended_at=time.time(),exit_code=1,error={'type':type(error).__name__,'message':str(error)})
    save(); traceback.print_exc(); raise
