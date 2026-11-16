"""Explicit checkpoint scope: restorable managed-world controls, not invented SDK histories."""
from __future__ import annotations
import copy,hashlib,json,shutil
from pathlib import Path
from .storage import Store,json_bytes

def manifest(root):
    result={}
    for path in sorted(Path(root).rglob('*')):
        if path.is_symlink():raise ValueError('Checkpoint cannot follow symlinks')
        if path.is_file():result[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def capture(prepared,folder,*,histories,budget,schedule,inflight=0):
    if inflight:raise ValueError('Checkpoint only between settled opportunities')
    if set(histories)!={'member_001','member_002'}:raise ValueError('Both private histories required')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    with prepared.world.store.lock():
        shutil.copytree(prepared.world.store.root,folder/'world')
    state={'kind':'controlled_managed_world','histories':histories,'budget':budget,'schedule':schedule,
        'model_calls':0,'SDK_continuation_qualified':False,
        'scope':'complete scripted-control state; no claim of restored live model session'}
    (folder/'continuation.json').write_bytes(json_bytes(state))
    files=manifest(folder)
    receipt={'version':'v203.3.1-checkpoint-r1','files':files,
        'identity':hashlib.sha256(json_bytes(files)).hexdigest(),**{k:state[k] for k in ('kind','SDK_continuation_qualified')}}
    (folder/'manifest.json').write_bytes(json_bytes(receipt));return receipt

def restore(prepared,checkpoint,folder):
    checkpoint,folder=Path(checkpoint),Path(folder)
    expected=json.loads((checkpoint/'manifest.json').read_text())
    if expected['identity']!=hashlib.sha256(json_bytes(expected['files'])).hexdigest():
        raise ValueError('Checkpoint manifest identity changed')
    actual=manifest(checkpoint);actual.pop('manifest.json')
    if actual!=expected['files']:raise ValueError('Checkpoint bytes changed')
    if folder.exists():raise ValueError('New branch identity and directory required')
    shutil.copytree(checkpoint,folder)
    restored=copy.deepcopy(prepared)
    restored.world.store=Store(folder/'world')
    restored.world.state=restored.world.store.load()
    restored.source_provider.runner.world=restored.world
    restored.source_provider.runner.folder=folder/'public-test-rpc'
    state=json.loads((folder/'continuation.json').read_text())
    return restored,state,expected['identity']

def require_live_resume(manifest):
    required={'code_versions','private_workspaces','member_SDK_sessions','summaries',
        'remaining_work','test_state','team_budget','request_id_namespace','scheduler',
        'no_inflight_requests','runtime_revision','restore_replay_receipt'}
    if not required <= set(manifest) or manifest.get('SDK_continuation_qualified') is not True:
        raise ValueError('Do not fabricate a paired API start from a Git tree or observation packet')
    return True


def capture_live_runtime(prepared,runtime,folder):
    """Save actual settled SDK state for a prospective checkpoint.

    This is an exporter. It deliberately does not claim a new runtime can resume
    these bytes until request identities, clocks and SDK reconstruction are tested.
    """
    if runtime.owner.adapter.ledger.inflight is not None:
        raise ValueError('Never snapshot an in-flight request as a new branch')
    if prepared.world.scheduled_member is not None:
        raise ValueError('Snapshot between completed world opportunities only')
    budget=runtime.team_budget.snapshot()
    if budget.get('integrity_failure'):raise ValueError('Damaged budget cannot form a clean fork')
    runtime.owner.save()
    histories={m:w.snapshot() for m,w in runtime.policies.items()}
    # The inherited generic runtime.snapshot follows a single-owner transport;
    # this team has separate member transports. Capture explicit team fields.
    schedule={'version':'v203.3.1-explicit-team-scheduler-snapshot',
        'fixed_schedule':runtime.schedule.snapshot(),
        **{key:copy.deepcopy(getattr(runtime,key)) for key in
           ('members','labels','stopped','waiting','work_ended','work_boundaries','terminal_details','opportunities','actions')},
        'organization_runtime_revision':'v203.2.1-passive-review2-runtime-r1'}
    folder=Path(folder)
    receipt=capture(prepared,folder,histories=histories,budget=budget,
        schedule=schedule,inflight=0)
    sessions={}
    for member,worker in runtime.policies.items():
        target=folder/'members'/member
        shutil.copytree(worker.directory,target)
        sessions[member]={'conversation_id':str(worker.conversation.id),
            'snapshot':histories[member],'files':manifest(target)}
    shutil.copytree(runtime.owner.folder,folder/'model-ledger')
    state={'version':'v203.3.1-prospective-SDK-checkpoint-r1',
        'kind':'actual_SDK_snapshot_without_resume_admission','member_SDK_sessions':sessions,
        'code_versions':prepared.world._software()['workspaces'] if 'workspaces' in prepared.world._software() else 'world/control/state.json',
        'private_workspaces':'world/control/versions','remaining_work':'world/control/state.json',
        'test_state':'world/control/state.json','team_budget':budget,'scheduler':schedule,
        'summaries':'members/*/history-summaries','no_inflight_requests':True,
        'runtime_revision':schedule['organization_runtime_revision'],
        'request_id_namespace':'original preserved; distinct continuation namespace not yet qualified',
        'restore_replay_receipt':None,'SDK_continuation_qualified':False}
    (folder/'live-state.json').write_bytes(json_bytes(state))
    files=manifest(folder);files.pop('manifest.json')
    receipt.update(kind=state['kind'],files=files,identity=hashlib.sha256(json_bytes(files)).hexdigest())
    (folder/'manifest.json').write_bytes(json_bytes(receipt));return receipt
