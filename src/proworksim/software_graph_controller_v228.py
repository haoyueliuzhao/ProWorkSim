"""Versioned local organization decisions on the managed two-member world."""
from copy import deepcopy
from .software_natural_organization_world_v224_2 import World as NaturalWorld, PROJECT
from .software_organization_world_v216_2 import STRUCTURAL
from .software_organization_world_v211 import EDIT_TOOLS
from .software_osa_session_v226 import fingerprint, project_evidence, organizations

ORGANIZING = STRUCTURAL | {'assign_verification','add_collaboration','org_declare_role',
                           'select_arrangement','decline_transfer','decline_joint_arrangement'}
ACCOUNTABLE = ORGANIZING | EDIT_TOOLS | {
    'begin_work','complete_work','complete_evidence','reopen_work','send_message','handoff_patch',
    'fix_patch','integrate_patch','open_patch_review','org_review_patch','review_evidence',
    'run_tests','run_patch_review_tests','submit_integration'}
BLOCK_TYPES = {'permission','dependency','in_flight','budget','state_conflict'}


def graph(world):
    work = {}
    for tid, w in world.dynamic()['work'].items():
        task = world._task(tid)
        work[tid] = {'owner':task['owner'],'reviewer':w['reviewer'],'scope':w['scope'],
                     'depends_on':task['depends_on'],'children':w['children']}
    return deepcopy({'members':sorted(world.live_members()),'work':work,
                     'collaboration':world.dynamic()['collaboration'],
                     'duties':world.protocol().get('graph_control',{}).get('duties',{})})


def menu(world, node, observer):
    """Freeze legal local targets and short references at a settled decision boundary."""
    current = graph(world)
    version = len(world.protocol().get('graph_control',{}).get('versions',[]))
    raw = world._action_dynamic_status(observer,PROJECT)
    visible = organizations(raw)
    options = {'K':{'op':'keep'}}
    for tid in sorted(node['affected_work']):
        w = visible[tid]
        if w['children'] or w['complete']:
            continue
        peer = next(m for m in current['members'] if m != w['owner'])
        if tid not in current['duties']:
            options['D'+str(len(options))] = {'op':'diagnosis','task':tid,'assignee':peer}
        elif current['duties'][tid]['status']=='pending':
            options['R'+str(len(options))] = {'op':'release_diagnosis','task':tid,'assignee':peer}
        if w['reviewer'] is None and peer not in w['authors']:
            options['V'+str(len(options))] = {'op':'verify','task':tid,'assignee':peer}
        if (not w['authors'] and tid not in raw['active_work'].values()
                and not any(o.get('status')=='pending' and o.get('task_id')==tid
                            for o in (*raw.get('joint_offers',{}).values(), *world._software().get('transfer_offers',{}).values()))):
            options['T'+str(len(options))] = {'op':'transfer_unstarted','task':tid,'assignee':peer}
    refs = {'E'+str(i): project_evidence(v) for i,v in enumerate(node['evidence_refs'],1)}
    if not refs:raise ValueError('Decision requires observed evidence')
    return {'base_version':version,'base_sha256':fingerprint(current),'anomaly':node['anomaly_type'],
            'subject':node.get('subject'),'anomaly_id':node['anomaly_id'],'graph':current,
            'evidence':refs,'options':options}


def activate(world, node, observer, frozen, choice, *, origin):
    if origin != 'osa' or set(choice) != {'option','evidence','reason'}:
        raise ValueError('Expected controller decision')
    ids = choice['evidence']
    if (not isinstance(ids,list) or not ids or any(i not in frozen['evidence'] for i in ids)
            or not isinstance(choice['reason'],str) or not 0<len(choice['reason'].strip())<=1200):
        raise ValueError('Use the listed short evidence IDs and a bounded reason')
    with world.store.lock():
        world.state = world.store.load()
        if world.protocol()['terminal'] or menu(world,node,observer) != frozen:
            raise ValueError('Closed or stale decision state')
        option = frozen['options'].get(choice['option'])
        if not option:raise ValueError('Unknown target')
        ctrl = world.protocol().setdefault('graph_control',{'versions':[],'duties':{},'blockers':[]})
        op = option['op']
        if op != 'keep':
            tid, peer = option['task'], option['assignee']
            task = world._task(tid)
            owner = task['owner']
            w = world.dynamic()['work'][tid]
            if op == 'transfer_unstarted':
                task['owner'],w['reviewer'] = peer,owner
            elif op == 'release_diagnosis':
                del ctrl['duties'][tid]
            elif op == 'verify':
                w['reviewer'] = peer
            elif op == 'diagnosis':
                ctrl['duties'][tid] = {'owner':peer,'recipient':owner,'status':'pending',
                                       'scope':'independent diagnosis and evidence handoff'}
            for edge in ([tid,owner,peer],[tid,peer,owner]):
                if edge not in world.dynamic()['collaboration']:world.dynamic()['collaboration'].append(edge)
        after=graph(world)
        record={'version':frozen['base_version']+1,'before':frozen['graph'],'after':after,
                'changed':fingerprint(after)!=frozen['base_sha256'],'decision':deepcopy(choice),
                'evidence_refs':[deepcopy(frozen['evidence'][i]) for i in ids],
                'world_clock':world.state['clock'],'after_event':len(world.state['software_events'])}
        ctrl['versions'].append(record)
        world.store.save(world.state)
    return record


class ControlledWorld(NaturalWorld):
    def _action_dynamic_status(self,actor,project_id):
        result=super()._action_dynamic_status(actor,project_id)
        ctrl=self.protocol().get('graph_control')
        if ctrl:
            result['active_organization']={'version':len(ctrl['versions']),'duties':deepcopy(ctrl['duties']),
                                           'reported_blockers':deepcopy(ctrl['blockers'])}
        return result

    def _tool_project_action(self,actor,project_id,tool,arguments,interface_profile=None):
        ctrl=self.protocol().get('graph_control')
        if not ctrl:
            return super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
        if tool in ORGANIZING:
            self.org_reject('Graph is active. Inspect dynamic_status or report a concrete blocker via send_message.',
                            'graph_authority',version=len(ctrl['versions']))
        tid=arguments.get('task_id')
        if tool=='org_review_patch':
            for scope in self._patch(arguments['patch_id'])['task_snapshots']:
                duty=ctrl['duties'].get(scope)
                if duty and duty['owner']==actor and duty['status']=='pending':
                    self.org_reject('Hand off the assigned diagnosis before recording the candidate review.',
                                    'graph_diagnosis_outstanding',task_id=scope)
        body=arguments.get('body','') if tool=='send_message' else ''
        duty=ctrl['duties'].get(tid)
        handoff=body.startswith('DIAG ')
        blocked=body.startswith('BLOCK ')
        if handoff or blocked:
            parts=body.split(maxsplit=2)
            if len(parts)!=3 or not parts[2].strip():
                self.org_reject('Use DIAG <own-event-sequence> <finding> or BLOCK <kind> <specific obstacle>.','graph_report_format')
            if handoff:
                seq=parts[1]
                if not (duty and duty['owner']==actor and arguments.get('recipient')==duty['recipient']
                        and seq.isdecimal() and any(e['sequence']==int(seq) and e['actor_id']==actor
                            and e['sequence']>ctrl['versions'][-1]['after_event']
                            and (e['kind'] in ('read','test','search') or 'review' in e['kind'])
                            for e in self.state['software_events'])):
                    self.org_reject('Cite your own new work evidence and address the assigned owner.','graph_evidence_required')
            elif parts[1] not in BLOCK_TYPES:
                self.org_reject('Report permission, dependency, in_flight, budget or state_conflict.','graph_blocker_kind')
        result=super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
        if handoff:
            duty.update(status='handed_off',message_sequence=result['message_sequence'],evidence=int(parts[1]))
        if blocked:
            ctrl['blockers'].append({'version':len(ctrl['versions']),'actor':actor,'kind':parts[1],
                                     'task_id':tid,'reason':parts[2][:800],'message_sequence':result['message_sequence']})
        return result
