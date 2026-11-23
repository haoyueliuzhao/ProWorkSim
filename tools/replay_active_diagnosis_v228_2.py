"""Exercise a historical, model-authored diagnosis on a private copy of its actual predecision world."""
import argparse
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from proworksim import software_natural_organization_world_v224_2 as natural
from proworksim import software_role_baseline_world_v141 as base
from proworksim import software_sdk_resume_v203_3_4 as resume
from proworksim.harness_port import HarnessPort
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_graph_controller_v228 import ControlledWorld, activate, graph, menu
from proworksim.software_graph_evidence_v228_1 import explain
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.software_osa_session_v226 import fingerprint, project_evidence
from proworksim.storage import atomic_write, json_bytes, read_json

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT/'artifacts/software-benchmark-v228/control-r2/panel.json'
M1, M2 = 'member_001','member_002'


def replay(folder):
    row = read_json(PLAN)['rows'][0]
    prefix = Path(row['archived_prefix'])
    checked(row['checkpoint_manifest'])
    plan_file = prefix/'osa/plan.json'
    historical = read_json(plan_file)
    if historical['keep'] or historical['response_categories'] != ['peer_diagnosis']:
        raise ValueError('Historical OSA plan does not identify one diagnostic responsibility')

    def no_tests(**kwargs):
        raise RuntimeError('This diagnostic only exercises managed actions')

    prepared = base.prepare_case(prefix/'actor/source-manifest.json',folder/'prepared',
        organization_id='FREE2',public_test_entry=read_json(prefix/'prepared/role-public-test-selection.json')['entry'],
        public_test_callback=no_tests,deadline=DispatchDeadline(soft_seconds=2400,hard_seconds=2700))
    natural.attach(prepared,[x['id'] for x in row['requirements']],condition='G')
    state, proof = resume.restore_world(prepared,prefix/'checkpoint')
    if proof['identity'] != row['checkpoint_id']:
        raise ValueError('Wrong decision state')
    world = prepared.world
    world.__class__ = ControlledWorld
    node = state['control_state']['node']
    if historical['anomaly_id'] != node['anomaly_id']:
        raise ValueError('Historical decision addressed another anomaly')
    node2 = explain(node,read_json(prefix/'observations.json'),row['observer'])
    target = menu(world,node2,row['observer'])
    old = {project_evidence(r)['id']:r['command_id'] for r in node['evidence_refs']}
    new = {v['command_id']:k for k,v in target['evidence'].items()}
    citing = [new[old[k]] for k in historical['evidence_ids']]
    edge, notification = historical['actions']
    work = edge['arguments']['task_id']
    peer = edge['arguments']['peer']
    if (edge['tool'],edge['actor'],notification['tool'],notification['arguments']['recipient'],
        notification['arguments']['task_id']) != ('add_collaboration',M1,'send_message',peer,work):
        raise ValueError('Unexpected historical operation chain')
    choices = [k for k,v in target['options'].items() if v=={'op':'diagnosis','task':work,'assignee':peer}]
    if len(choices)!=1:raise ValueError('No unique corresponding legal graph operation')
    before_events = deepcopy(world.state['software_events'])
    def protected():
        sw=world._software()
        return fingerprint({'patches':sw['patches'],'deliveries':sw['deliveries'],'tests':sw['test_reports'],
            'authors':{k:v['authors'] for k,v in world.dynamic()['work'].items()},
            'workspaces':{m:world.org_current_identity(m) for m in (M1,M2)}})
    before = protected()
    decision = activate(world,node2,row['observer'],target,{'option':choices[0],'evidence':citing,
                        'reason':historical['reason']},origin='osa')
    assert decision['changed'] and protected()==before and world.state['software_events']==before_events
    ports = {}
    for m in (M1,M2):
        ports[m]=HarnessPort(natural.Port(world.session(m,natural.PROJECT),m),m,project_id=natural.PROJECT,
            public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None)
        ports[m].tools()
    receipts=[]
    def call(actor,tool,**args):
        r=ports[actor].call(tool,request_key=f'v228.2-control-{len(receipts)}',association={},**args)
        receipts.append({'actor':actor,'tool':tool,'command_id':r.get('command_id'),'ok':r['ok'],
                         'rejection':((r.get('error') or {}).get('rejection') or {}).get('code'),
                         'receipt_sha256':fingerprint(r)})
        return r
    forged=call(peer,'send_message',recipient=M1,task_id=work,body='DIAG 999999 diagnostic control')
    assert not forged['ok'] and receipts[-1]['rejection']=='graph_evidence_required'
    source=node['subject'].split('::',1)[0]
    read=call(peer,'read_file',path=source,start_line=1,max_lines=12)
    assert read['ok'],read
    event=next(e for e in reversed(world.state['software_events']) if e['actor_id']==peer and e['kind']=='read' and e['path']==source)
    sent=call(peer,'send_message',recipient=M1,task_id=work,
              body=f"DIAG {event['sequence']} Inspected the public test file {source}; target {node['subject']}. Root cause not established by this read.")
    assert sent['ok'],sent
    latest=call(M1,'dynamic_status')
    assert latest['ok'],latest
    duty=latest['result']['active_organization']['duties'][work]
    assert duty['owner']==peer and duty['status']=='handed_off' and duty['evidence']==event['sequence']
    assert protected()==before and world.state['software_events'][:len(before_events)]==before_events
    return {'evidence_class':'historical model proposal; scripted worker execution on a private checkpoint copy',
            'instance_id':row['instance_id'],'checkpoint':proof['identity'],'historical_plan':reference(plan_file),
            'historical_evidence_ids':historical['evidence_ids'],'mapped_evidence':citing,'target':target['options'][choices[0]],
            'activation':decision,'handoff':duty,'receipts':receipts,'historical_events_preserved':len(before_events),
            'before_and_after_protected_digest':before,'new_model_calls':0,'new_official_scores':0,'cn_updates':0,
            'does_not_establish_natural_adoption_or_diagnostic_correctness':True}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    parent=ROOT/'runs/software-benchmark-v228/supplement-r1'
    parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=parent,prefix='offline-') as temp:
        result=replay(Path(temp))
    atomic_write(a.output,json_bytes(result))
    print(result['handoff'])
