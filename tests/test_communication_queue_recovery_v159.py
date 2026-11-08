"""An administrative drain must terminate after owned work, not await wave2."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

def test_all_group_file_drain_closes_without_second_wave_wait(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[1]/'tools/run_communication_pilot_v159.py'
    spec=importlib.util.spec_from_file_location('v159_queue_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from proworksim.software_benchmark_group_admission_v157 import FairAdmission,DrainControl,VERSION
    control_path=tmp_path/'drain.json';control_path.write_text(json.dumps({'version':VERSION,
        'batch_root':str(tmp_path.resolve()),'mode':'drain','groups':['C0','C1','C2'],
        'maximum_generations':16,'revision':1,'reason':'known owned startup repair'}))
    control=DrainControl(control_path,batch_root=tmp_path,groups=module.GROUP_IDS,maximum=16)
    admission=FairAdmission(module.GROUP_IDS,control=control,maximum=16,maximum_startups=4)
    rows=[{'slot_id':'test:first','instance_id':'example__repo-1','slot_index':1,'wave':1,'group_id':'C0','seed':1},
          {'slot_id':'test:later','instance_id':'example__repo-2','slot_index':2,'wave':2,'group_id':'C1','seed':2}]
    plan={'rows':rows,'used_original_slots':[]};plan_path=tmp_path/'plan.json';plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(module.scope,'PLAN_FILE',plan_path)
    runtime=SimpleNamespace(for_group=lambda _:SimpleNamespace(settled_route_witnesses=lambda:True))
    instance=module.Coordinator(runtime=runtime,implementation=None,grading=None,memory=SimpleNamespace(snapshot=lambda:{}),
        admission=admission,plan=plan,qualifications={r['instance_id']:{'passed':True} for r in rows},output=tmp_path/'output',
        cash_status=lambda _:dict(state='ready',can_start_generation=False))
    def forbidden_sleep(_):raise AssertionError('A drained owner must not wait for the next wave gate')
    monkeypatch.setattr(module.time,'sleep',forbidden_sleep)
    result=instance.execute()
    assert not instance.generation and not instance.scores
    assert set(result['deferred'])=={r['slot_id'] for r in rows}
    assert result['generation_records']=={}
