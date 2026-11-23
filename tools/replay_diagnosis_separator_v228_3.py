"""Replay two real rejected messages on an isolated copy. No solver, score or token charge."""
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil

from proworksim import software_role_baseline_world_v141 as base,software_natural_organization_world_v224_2 as natural
from proworksim.harness_port import HarnessPort
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_graph_controller_v228_3 import ControlledWorld
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.storage import atomic_write,json_bytes,read_json

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v228/supplement-r1/astropy-evidence-r2-launch2/W1'
OUTPUT=ROOT/'artifacts/software-benchmark-v228/diagnosis-supplement-results-r1/separator-replay.json'


def run(folder):
    original=read_json(RUN/'boundary.json')
    messages=[o for o in original['outcomes'] if (o.get('decision') or {}).get('action')=='send_message'
              and ((o.get('decision') or {}).get('arguments',{}).get('body') or '').startswith('DIAG ')]
    assert len(messages)==2 and all(o['worker_id']=='member_002' and not o['response']['ok'] for o in messages)
    def no_tests(**kwargs):raise RuntimeError('No tests requested in offline message replay')
    prep=base.prepare_case(RUN/'actor/source-manifest.json',folder/'prepared',organization_id='FREE2',
        public_test_callback=no_tests,public_test_entry=read_json(RUN/'prepared/role-public-test-selection.json')['entry'],
        deadline=DispatchDeadline(soft_seconds=2400,hard_seconds=2700))
    row=read_json(ROOT/'artifacts/software-benchmark-v228/diagnosis-supplement-r1/panel.json')['rows'][0]
    natural.attach(prep,[x['id'] for x in row['requirements']],condition='G')
    w=prep.world
    shutil.copytree(RUN/'prepared/world',w.store.root,dirs_exist_ok=True)
    w.state=w.store.load();w.__class__=ControlledWorld
    ctrl=w.protocol()['graph_control']
    assert ctrl['duties']['work_root']['status']=='pending'
    original_events=w.state['software_events'][:]
    port=HarnessPort(natural.Port(w.session('member_002',natural.PROJECT),'member_002'),'member_002',
        project_id=natural.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None)
    port.tools();seen=[]
    for i,msg in enumerate(messages):
        args=msg['decision']['arguments']
        receipt=port.call('send_message',request_key=f'offline-v228.3-{i}',association={},**args)
        seq=int(args['body'].split()[1].rstrip(':'))
        event=next((e for e in original_events if e['sequence']==seq),None)
        at=msg['response']['logical_time']
        seen.append({'original_command_id':msg['response']['command_id'],'claimed_sequence':seq,
                     'event_existed_at_original_attempt':bool(event and event['logical_time']<=at),
                     'event_owner':event['actor_id'] if event else None,'event_kind':event['kind'] if event else None,
                     'old_ok':msg['response']['ok'],'replay_ok':receipt['ok'],
                     'rejection':(receipt.get('error') or {}).get('rejection')})
    assert [r['replay_ok'] for r in seen]==[False,True]
    duty=w.protocol()['graph_control']['duties']['work_root']
    assert duty['status']=='handed_off' and duty['evidence']==55
    assert [e for e in w.state['software_events'] if e['sequence']<=len(original_events)]==original_events
    atomic_write(OUTPUT,json_bytes({'source':reference(RUN/'boundary.json'),'scope':'exact saved arguments on private copy of end state; original receipt time compared separately',
        'original_duty':'pending','replay_duty':duty,'attempts':seen,'new_api_calls':0,'official_outcomes_modified':False}))


if __name__=='__main__':
    with TemporaryDirectory(dir=RUN.parent,prefix='separator-offline-') as folder:run(Path(folder))
