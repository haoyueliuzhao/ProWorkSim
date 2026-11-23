"""Incremental, actor-scoped anomaly projection over committed harness receipts."""
from collections import defaultdict
from copy import deepcopy
import re

from .software_project_relations_v217 import identity

MEMBERS = ('member_001', 'member_002')
EDITS = {'write_file', 'replace_file', 'edit_file', 'create_file', 'delete_file', 'rename_file', 'apply_patch'}
DEPENDENCY = {'upstream_not_current', 'upstream_patch_not_adopted', 'upstream_evidence_version_not_adopted'}
VERIFICATION = {'work_test_missing', 'work_test_stale', 'work_revision_test_required',
                'review_view_test_required', 'stale_work_revision', 'dynamic_completion_version'}
TESTS = {'run_tests', 'run_patch_review_tests'}

def version(result):
    source = result.get('source_reference', {})
    if not isinstance(source, dict) or not source.get('version_id') or not source.get('object_id'):
        return None
    return (source['object_id'], source['version_id'])

def tested_nodes(result):
    """Explicit call-phase cases only. Missing reports, skips and collection errors are unknown."""
    if result.get('executed') is not True:
        return (), ()
    counts = result.get('counts') or {}
    overview = result.get('evidence_overview') or {}
    if counts.get('collected') == 0 or counts.get('errors', 0) or overview.get('error'):
        return (), ()
    failures = (result.get('diagnostic_summary') or {}).get('failed_tests', [])
    evidence = result.get('test_evidence') or {}
    # An inner pytester invocation can intentionally fail. Only outer sessions count.
    sessions = evidence.get('sessions') or []
    outer = [s for s in sessions if s.get('root') is True or s.get('depth') == 0]
    if len(sessions) > 1 or overview.get('nested_report_count', 0):
        failures = []
    reports = [r for s in outer for r in s.get('test_reports', [])]
    failed = {x['nodeid'] for x in [*failures, *reports] if x.get('nodeid')
              and x.get('phase')=='call' and x.get('outcome')=='failed'}
    if overview.get('framework')=='sympy' and counts.get('failed',0)>0 and counts.get('tests_run',0)>0 and not overview.get('nested_report_count'):
        pattern = r'^_+\s+([\w./-]+\.py):(test_[\w]+)\s+_+\s*$'
        for excerpt in (result.get('diagnostic_summary') or {}).get('excerpts',[]):
            if excerpt.get('source')=='saved_visible_result.groups.output':
                failed.update(path+'::'+case for path,case in re.findall(pattern,excerpt.get('text',''),re.M))
    passed = {x['nodeid'] for x in reports if x.get('nodeid') and x.get('phase')=='call'
              and x.get('outcome')=='passed'}
    if result.get('passed') is True:
        failed.clear()
        choice = (result.get('selection_normalization') or {}).get('executed') or {}
        targets = choice.get('targets', [])
        if len(targets)==1 and '::' in targets[0] and counts.get('passed')==1 and counts.get('tests_run')==1 and not any(counts.get(k) for k in ('skipped','xfailed','xpassed')):
            passed.add(targets[0])
    return failed, passed-failed

class AnomalyGraph:
    def __init__(self, observer, *, regression_targets=()):
        if observer not in MEMBERS:
            raise ValueError('Unknown observer')
        self.observer = observer
        self.nodes = {}
        self.seen = {}
        self.material = defaultdict(set)
        self.regression_targets = frozenset(regression_targets)
        self.test_passes = defaultdict(dict)
        self.current_work = None
        self.edit_refs = {}
        self.last_edit = None
        self.workspace_version = None
        self.failures = defaultdict(dict)
        self.passed = {}
        self.integrations = {}
        self.ready_at = None
        self.own_steps = 0
        self.wakes = []
        self.unknown_tests = 0

    def signal(self, kind, work, subject, refs, *, status=None):
        key = identity([self.observer,kind,work,subject])
        node = self.nodes.get(key)
        if not node:
            if status: return
            node = self.nodes[key] = dict(anomaly_id=key,anomaly_type=kind,affected_work=[work] if work else [],
                affected_agents=[self.observer],subject=subject,recurrence=0,status='OPEN',
                confidence='receipt_supported',evidence_refs=[],resolution_history=[],response_history=[])
        before = node['status']
        fresh = [r for r in refs if r not in node['evidence_refs']]
        if not fresh: return
        node['evidence_refs'].extend(fresh)
        if status: node['status']=status
        elif before=='RESOLVED':
            node['status']='REOPENED'
            node['recurrence']+=1
        elif before=='UNKNOWN': node['status']='OPEN'
        elif before not in ('OPEN','REOPENED'): node['status']='ACTIVE'
        node['resolution_history'].append({'from':before if len(node['evidence_refs'])>len(fresh) else None,
            'to':node['status'],'opportunity':refs[-1]['opportunity']})
        material=identity([kind,subject,node['recurrence'],[(r.get('source_reference'),r.get('evidence_state')) for r in fresh]])
        new_material=material not in self.material[key]
        self.material[key].add(material)
        if new_material and not status and len(self.wakes)<2 and (not self.wakes or self.wakes[-1]['opportunity']!=refs[-1]['opportunity']):
            self.wakes.append({'anomaly_id':key,'opportunity':refs[-1]['opportunity']})

    def observe(self, ordinal, outcome):
        if outcome.get('worker_id')!=self.observer: return
        response = outcome.get('response') or {}
        if not response or type(response.get('ok')) is not bool: return
        op = response.get('command_id')
        if not op: return
        digest = identity(response)
        if op in self.seen:
            if self.seen[op]!=digest: raise ValueError('Conflicting receipt')
            return
        self.seen[op]=digest
        self.own_steps+=1
        action = outcome.get('decision',{})
        tool = action.get('action')
        args = action.get('arguments') or {}
        r = response.get('result') or {}
        ref = {'opportunity':ordinal,'command_id':op,'tool':tool,'sha256':digest}
        v = version(r)
        if v: ref['source_reference']={'object_id':v[0],'version_id':v[1]}
        err=(response.get('error') or {}).get('rejection') or {}
        task=args.get('task_id') or r.get('task_id') or self.current_work
        if response['ok'] and tool=='begin_work':self.current_work=task
        if response['ok'] and tool in EDITS|{'integrate_patch'} and v:
            self.ready_at=None
            if tool in EDITS:
                self.edit_refs[v]=(ref,task,r.get('files_sha256'));self.last_edit=v
            else:
                self.integrations[v]=(ref,task,dict(self.test_passes.get(self.workspace_version,{})))
                if r.get('conflicts') or (r.get('conflict_count') or 0)>0:
                    self.signal('A3',task,'merge_conflict',[ref])
            self.workspace_version=v
        if response['ok'] and tool in TESTS:
            failed,passed=tested_nodes(r)
            if not failed and not passed and r.get('passed') is not True:self.unknown_tests+=1
            for node in sorted(failed):
                if v in self.edit_refs:
                    edit,scope,content=self.edit_refs[v]
                    history=self.failures[(scope,node)]
                    if scope and content and content not in history:
                        history[content]=[edit,ref]
                        if len(history)>=2:self.signal('A1',scope,node,[x for pair in history.values() for x in pair])
                if v in self.integrations:
                    integration,scope,previous=self.integrations[v]
                    if node in previous:self.signal('A3',scope,node,[previous[node],integration,ref])
            for node in passed:
                self.passed[node]=ref
                # A passing target resets the preceding failure streak. Full resolution
                # also needs the frozen regression/dependency checks below.
                if v in self.edit_refs:
                    scope=self.edit_refs[v][1]
                    self.failures.pop((scope,node),None)
                    self.signal('A1',scope,node,[ref],status='UNKNOWN')
                if v:self.test_passes[v][node]=ref
        # A positive readiness receipt after passing target and frozen regression
        # checks is needed for mechanistic resolution. Lack of checks stays unknown.
        if response['ok'] and tool=='work_readiness' and r.get('ready') is True and self.last_edit:
            v=self.last_edit
            scope=self.edit_refs[v][1]
            if scope==r.get('task_id') and self.regression_targets:
                for n in list(self.nodes.values()):
                    checks=self.regression_targets|{n['subject']}
                    if n['anomaly_type']=='A1' and scope in n['affected_work'] and n['status']!='RESOLVED' and checks<=self.test_passes[v].keys():
                        self.signal('A1',scope,n['subject'],[self.test_passes[v][k] for k in sorted(checks)]+[ref],status='RESOLVED')
        if err.get('code') in VERIFICATION:
            self.signal('A4',task,str(err['code']),[ref])
        readiness=r if tool=='work_readiness' and response['ok'] else (err.get('context') or {}).get('readiness',{})
        for gap in readiness.get('gaps',[]):
            if gap.get('kind') in DEPENDENCY:
                self.signal('A2',readiness.get('task_id'),str(gap.get('task_id') or gap.get('patch_id') or gap.get('evidence_id')),[{**ref,'evidence_state':identity(gap)}])
        if readiness.get('ready') is True:
            for n in list(self.nodes.values()):
                if n['anomaly_type']=='A2' and readiness.get('task_id') in n['affected_work'] and n['status']!='RESOLVED':
                    self.signal('A2',readiness['task_id'],n['subject'],[ref],status='RESOLVED')
        if response['ok'] and tool=='delivery_readiness':
            packages=(r.get('package_chain') or {}).get('packages',[])
            unfinished=[p['task_id'] for p in packages if 'complete_current_code_or_evidence' in p.get('missing',[])]
            for package in packages:
                tid = package['task_id']
                missing = set(package.get('missing',[]))
                # A returned checklist binds this obligation to a real package.
                for obligation in ('independent_current_review','evidence_version_differs_from_final_tree_revalidate'):
                    tested_final=(r.get('final_test') or {})
                    scoped=(tid==self.current_work or (unfinished==[tid] and package.get('owner')==tested_final.get('actor_id')))
                    current_work_checked=(scoped and tested_final.get('executed') is True
                        and tested_final.get('passed') is True and version(tested_final) is not None
                        and version(tested_final)==version(r.get('final_identity') or {}))
                    if obligation in missing and (package.get('completion') or current_work_checked):
                        self.signal('A4',tid,obligation,[ref])
                    elif obligation not in missing and package.get('completion'):
                        self.signal('A4',tid,obligation,[ref],status='RESOLVED')
        if response['ok'] and tool=='delivery_readiness' and self.observer=='member_001':
            if r.get('ready_to_submit') is True:
                final_id=identity(r['final_identity']) if r.get('final_identity') else None
                if self.ready_at and final_id and self.ready_at[2]==final_id and self.own_steps-self.ready_at[0]>=3:
                    self.signal('A5',None,'delivery_ready',[self.ready_at[1],ref])
                if not self.ready_at or self.ready_at[2]!=final_id:self.ready_at=(self.own_steps,ref,final_id)
            else:self.ready_at=None
        if response['ok'] and tool=='delivery_readiness' and self.observer=='member_001' and r.get('ready_to_submit') is True:
            final=version(r.get('final_identity') or {})
            # Readiness checks the integrated tree, exact current pass, all packages,
            # independent reviews and zero unresolved integration conflicts.
            if final and r.get('final_test') and r.get('current_fixed_patch_ids') and r.get('gaps')==[]:
                for n in list(self.nodes.values()):
                    if n['anomaly_type']=='A3' and n['status']!='RESOLVED':
                        required=self.regression_targets | ({n['subject']} if n['subject']!='merge_conflict' else set())
                        if required and required<=self.test_passes[final].keys():
                            self.signal('A3',next(iter(n['affected_work']),None),n['subject'],[self.test_passes[final][k] for k in sorted(required)]+[ref],status='RESOLVED')
        if response['ok'] and tool=='submit_integration' and r.get('episode_state')=='DELIVERED':
            self.signal('A5',None,'delivery_ready',[ref],status='RESOLVED')
            self.ready_at=None
            for n in list(self.nodes.values()):
                if n['anomaly_type']=='A4' and n['status']!='RESOLVED':
                    # Managed submit validates all current verification obligations.
                    self.signal('A4',next(iter(n['affected_work']),None),n['subject'],[ref],status='RESOLVED')

    def record_worker_response(self, anomaly_id, outcome, ordinal, *, candidate_id, disposition):
        """Append a witnessed action only after its original authorized receipt was projected."""
        response=outcome.get('response',{})
        if disposition not in ('selected','accepted','declined','executed'):raise ValueError('Invalid response event')
        if (outcome.get('worker_id')!=self.observer or response.get('ok') is not True or
            self.seen.get(response.get('command_id'))!=identity(response)):
            raise ValueError('Missing authorized worker receipt')
        node=self.nodes[anomaly_id]
        item={'opportunity':ordinal,'candidate_id':candidate_id,'disposition':disposition,
              'tool':outcome['decision'].get('action'),'command_id':response['command_id'],'sha256':identity(response)}
        if item not in node['response_history']:node['response_history'].append(item)
        if disposition in ('accepted','executed') and node['status'] in ('OPEN','REOPENED'):
            node['status']='ACTIVE'

    def view(self):
        edges=[]
        for node in self.nodes.values():
            aid=node['anomaly_id']
            for work in node['affected_work']:edges.append([aid,'affects_work',work])
            for actor in node['affected_agents']:edges.append([aid,'observed_by',actor])
            for ref in node['evidence_refs']:
                edges.append([aid,'supported_by',ref['command_id']])
                if ref.get('source_reference'):edges.append([ref['command_id'],'on_version',ref['source_reference']])
        return {'observer':self.observer,'edges':edges,'anomalies':deepcopy(list(self.nodes.values())),
                'wakes':deepcopy(self.wakes),'unclassified_test_receipts':self.unknown_tests}

def mechanism_endpoint(view, anomaly_id, decision_opportunity):
    """Only later evidence answers resolution; terminal silence stays unknown."""
    node=next((n for n in view['anomalies'] if n['anomaly_id']==anomaly_id),None)
    later=[] if node is None else [h for h in node['resolution_history'] if h['opportunity']>decision_opportunity]
    if not later:return {'resolved':None,'recurrences':None,'reason':'no_postdecision_evidence'}
    status=later[-1]['to']
    return {'resolved':True if status=='RESOLVED' else False if status in ('OPEN','ACTIVE','REOPENED') else None,
            'recurrences':sum(h['to']=='REOPENED' and h['from']=='RESOLVED' for h in later),
            'last_opportunity':later[-1]['opportunity'],'status':status}
