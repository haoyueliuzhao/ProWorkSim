"""New archival identity with narrowly pinned session-helper read exclusions.

The r1 sources, plan, zero-release failure and archive identities remain intact.
Uninspectable standard-session helpers are recorded as exclusions, not proof
that every own process was fully scanned. All readable history references and
all other unreadable own-process fields still stop archival admission.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import re
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
R1_SOURCE=ROOT/'tools/archive_passive_pilot_history_v203_2_1.py'
R1_SOURCE_SHA='c6526c330b2e0df25f238ab7e190a30b698ea0db0c1ae77e5798c6b1d3667eed'
R1_ART=ROOT/'artifacts/software-benchmark-v203-2-1/history-archive-preparation-r1'
ART=ROOT/'artifacts/software-benchmark-v203-2-1/history-archive-preparation-r2'
PLAN=ART/'plan.json'
WITNESS=ART/'session-helper-identity-witness.json'
OUT=Path('/data1/proworksim-zhuxinrui/passive-history-v203-2-1/r2')
VERSION='v203.2.1-owner-closed-request-json-lossless-archive-r2'
_AUDIT_LOCK=threading.Lock()


def load_base():
    if hashlib.sha256(R1_SOURCE.read_bytes()).hexdigest()!=R1_SOURCE_SHA:
        raise ValueError('Frozen r1 archival implementation changed')
    spec=importlib.util.spec_from_file_location('_v203_2_1_archive_r2_private_base',R1_SOURCE)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


base=load_base()


def read_identity(pid,proc_root=Path('/proc')):
    p=Path(proc_root)/str(pid)
    status={line.split(':',1)[0]:line.split(':',1)[1].strip()
            for line in (p/'status').read_text().splitlines() if ':' in line}
    tail=(p/'stat').read_text().rsplit(')',1)[1].split()
    return {'pid':int(pid),'name':status['Name'],'uid_vector':[int(v) for v in status['Uid'].split()],
        'ppid':int(status['PPid']),'comm':(p/'comm').read_text().rstrip('\n'),
        'starttime_ticks':int(tail[19]),'cgroup':(p/'cgroup').read_text().splitlines()}


def validated_witness():
    value=json.loads(WITNESS.read_bytes());uid=os.getuid()
    if value.get('ordinary_uid')!=uid or value.get('root_operations')!=0 or value.get('process_control_operations')!=0:
        raise ValueError('Wrong session-helper witness owner or collection scope')
    rows=value.get('witnesses',[])
    if len(rows)!=2 or len({r['process']['pid'] for r in rows})!=2:
        raise ValueError('Exactly the two reviewed session helpers must be pinned')
    for row in rows:
        child,parent=row['process'],row['parent']
        if (child['uid_vector']!=[uid]*4 or child['ppid']!=parent['pid']
            or child['starttime_ticks']<=0 or parent['starttime_ticks']<=0
            or child['cgroup']!=parent['cgroup'] or child['name']!=child['comm']):
            raise ValueError('Incomplete or inconsistent pinned process identity')
        if child['name']=='sshd':
            if (parent['comm']!='sshd' or parent['name']!='sshd' or parent['uid_vector']!=[0]*4
                or len(child['cgroup'])!=1
                or not re.fullmatch(r'0::/user.slice/user-'+str(uid)+r'.slice/session-[0-9]+\.scope',child['cgroup'][0])):
                raise ValueError('Not the reviewed ordinary-user SSH session helper')
        elif child['name']=='(sd-pam)':
            if (parent['comm']!='systemd' or parent['name']!='systemd' or parent['uid_vector']!=[uid]*4
                or child['cgroup']!=[f'0::/user.slice/user-{uid}.slice/user@{uid}.service/init.scope']):
                raise ValueError('Not the reviewed user-manager PAM helper')
        else:raise ValueError('Unknown process kind is never a session exclusion')
    if {r['process']['name'] for r in rows}!={'sshd','(sd-pam)'}:raise ValueError('Helper classes changed')
    return rows


def exact_exclusion(process,parent,witnesses,uid):
    """Only exact PID/starttime+UID+name+cgroup+parent evidence can qualify."""
    if process.get('uid_vector')!=[uid]*4:return None
    for witness in witnesses:
        if process==witness['process'] and parent==witness['parent']:
            return {'process':process,'parent':parent,
                'classification':'pinned_standard_session_helper_unreadable_fields_excluded',
                'excluded_fields_not_proven_free_of_history_references':True}
    return None


def decide_process(process,parent,paths,denied,roots,witnesses,uid):
    for kind,target in paths:
        if any(target==root or target.startswith(root+'/') for root in roots):
            raise PermissionError('Actual historical path reference even for a session helper: '+repr(
                {'pid':process['pid'],'kind':kind,'path':target}))
    if not denied:return None
    exclusion=exact_exclusion(process,parent,witnesses,uid)
    if exclusion is None:
        raise PermissionError('Unreviewed unreadable own process remains blocked: '+repr(
            {'pid':process.get('pid'),'name':process.get('name'),'denied_fields':denied}))
    return {**exclusion,'denied_fields':sorted(set(denied)),'readable_fields_still_checked':len(paths)}


def own_process_references(roots):
    roots=[str(Path(r)) for r in roots];uid=os.getuid();witnesses=validated_witness()
    exclusions=[];count=readable=0
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if proc.stat().st_uid!=uid:continue
        except FileNotFoundError:continue
        count+=1;paths=[];denied=[]
        for leaf in ('cwd','exe','root'):
            try:paths.append((leaf,os.readlink(proc/leaf)))
            except (FileNotFoundError,ProcessLookupError):pass
            except PermissionError:denied.append(leaf)
        try:fds=list((proc/'fd').iterdir())
        except (FileNotFoundError,ProcessLookupError):fds=[]
        except PermissionError:fds=[];denied.append('fd-directory')
        for fd in fds:
            try:paths.append(('fd',os.readlink(fd)))
            except (FileNotFoundError,ProcessLookupError):pass
            except PermissionError:denied.append('fd-link')
        try:
            for line in (proc/'maps').read_text().splitlines():
                fields=line.split(None,5)
                if len(fields)==6:paths.append(('mmap',fields[5]))
        except (FileNotFoundError,ProcessLookupError):pass
        except PermissionError:denied.append('maps')
        readable+=len(paths)
        # Readable references must fail even if an exited process no longer has
        # metadata or a denied field would otherwise qualify for an exclusion.
        minimal={'pid':int(proc.name)}
        if any(target==root or target.startswith(root+'/') for _,target in paths for root in roots):
            decide_process(minimal,None,paths,[],roots,witnesses,uid)
        if denied:
            try:
                process=read_identity(int(proc.name));parent=read_identity(process['ppid'])
            except (FileNotFoundError,ProcessLookupError):
                if not proc.exists():continue
                raise PermissionError('Incomplete live process identity cannot be excluded')
            exclusion=decide_process(process,parent,paths,denied,roots,witnesses,uid)
            # Refuse PID replacement or reparenting during the observations.
            if read_identity(process['pid'])!=process or read_identity(parent['pid'])!=parent:
                raise PermissionError('Session helper identity changed during inspection')
            exclusions.append(exclusion)
    value={'version':VERSION,'unix':time.time(),'roots':roots,'ordinary_uid':uid,
        'own_processes_seen':count,'readable_references_checked':readable,
        'session_helper_unreadable_exclusions':exclusions,'actual_history_references_found':0,
        'all_own_process_fields_were_inspected':not exclusions,
        'other_users_private_process_references_not_inspected':True,
        'independent_admission_evidence':['ended_result','complete_owned_resource_quiescence',
            'no_active_batch_claims','source_inode_stability','streamed_original_hash_and_full_archive_readback'],
        'witness':base.ref(WITNESS)}
    ART.mkdir(parents=True,exist_ok=True)
    with _AUDIT_LOCK,(ART/'process-inspection-exclusions.jsonl').open('a') as stream:
        stream.write(json.dumps(value,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
    return value


base.ART,base.PLAN,base.OUT,base.VERSION=ART,PLAN,OUT,VERSION
base.own_process_references=own_process_references
# The frozen base body runs in this private module namespace. Only the new
# receipt/restore entrypoint identity differs; no frozen source file is patched.
_source=inspect.getsource(base.archive_one)
_source=_source.replace("'model-ledger-archive-v203-2-1.json'","'model-ledger-archive-v203-2-1-r2.json'")
_source=_source.replace("'tools/archive_passive_pilot_history_v203_2_1.py'","'tools/archive_passive_pilot_history_v203_2_1_r2.py'")
exec(compile(_source,__file__+':r2-archive-identity','exec'),vars(base))


def prepare():
    if PLAN.exists():raise ValueError('Do not overwrite an r2 plan')
    validated_witness();base.output_ready()
    prior=json.loads((R1_ART/'plan.json').read_bytes());progress=json.loads((R1_ART/'progress.json').read_bytes())
    if (progress.get('completed')!=0 or progress.get('source_allocated_bytes_released')!=0
        or progress.get('status')!='stopped_on_error'):
        raise PermissionError('This r2 scope expects the retained zero-release r1 failure')
    for item in prior['items']:
        if (OUT.parent/item['item_id']).exists():raise PermissionError('r1 has an entered episode archive identity')
    value={**prior,'version':VERSION,'source':base.ref(Path(__file__).resolve()),
        'source_dependencies':[base.ref(R1_SOURCE),base.ref(WITNESS)],'output_root':str(OUT),
        'previous_plan':base.ref(R1_ART/'plan.json'),'previous_zero_release_result':base.ref(R1_ART/'progress.json'),
        'session_helper_identity_witness':base.ref(WITNESS),
        'r1_file_snapshot_inventory_reused_not_rehashed':True,
        'all_source_files_rechecked_immediately_before_encoding_and_release':True,
        'process_inspection_scope':'Readable own process references checked; only two exact pinned standard-session helpers may have recorded unreadable-field exclusions.',
        'no_claim_of_complete_own_process_fd_scan':True,
        'other_unknown_or_experiment_process_unreadable_fields_still_rejected':True,
        'real_payload_archive_actions_during_preparation':0}
    ref=base.save(PLAN,value);summary={k:v for k,v in value.items() if k not in {'items','excluded'}}
    summary.update(plan=ref,episodes=len(value['items']),files=sum(i['file_count'] for i in value['items']),
        excluded_count=len(value['excluded']),potential_source_GiB=value['maximum_source_allocated_bytes']/base.GIB)
    base.save(ART/'summary.json',summary);return summary


def verify_dependencies():
    plan=json.loads(PLAN.read_bytes())
    for witness in plan['source_dependencies']:base.checked(witness)
    base.checked(plan['session_helper_identity_witness'])
    if plan['output_root']!=str(OUT):raise ValueError('r2 archive destination changed')


def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--run',action='store_true')
    group.add_argument('--restore',type=Path);parser.add_argument('--member')
    parser.add_argument('--workers',type=int,default=2);parser.add_argument('--target-free-gib',type=int,default=180)
    args=parser.parse_args()
    if args.prepare:result=prepare()
    else:
        verify_dependencies()
        if args.run:result=base.run(args.target_free_gib,args.workers)
        else:
            if not args.member:parser.error('--restore requires --member')
            result=base.restore(args.restore,args.member)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
