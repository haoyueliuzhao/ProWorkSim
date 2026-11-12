"""Passive durable capture over the unchanged v141 REVIEW2 execution policy."""
from __future__ import annotations

import inspect
import json
import resource
import time
from pathlib import Path
from types import MethodType

from . import software_role_baseline_runtime_v141 as base
from .software_observer_journal_v203_2_1 import ObserverJournal
from .storage import atomic_write, json_bytes

VERSION = REPAIR_REVISION = 'v203.2.1-passive-review2-runtime-r1'
prepare_case = base.prepare_case
worker_config = base.worker_config
worker_type = base.worker_type
member_wire_tools = base.member_wire_tools
prepare_schema_inventory = base.prepare_schema_inventory

# Only the non-authoritative legacy observer implementation changes. Its old
# local import otherwise bypasses namespace rebinding; original files stay frozen.
_source = inspect.getsource(base.build_team_owner)
_old = 'from .software_collaboration_runtime_observer_v141 import RuntimeObservationBridge'
assert _source.count(_old) == 1
_namespace = dict(base.build_team_owner.__globals__)
exec(compile(_source.replace(_old, 'from .software_collaboration_runtime_observer_v172 import RuntimeObservationBridge'),
             __file__ + ':original-owner', 'exec'), _namespace)
_build_owner = _namespace['build_team_owner']


class Sidecar:
    """Append only; graph projection is offline, not copied on every tool action."""
    def __init__(self, folder, episode):
        self.folder = Path(folder)
        self.episode = episode
        self.journal = None
        self.fault_count = 0
        self.last_fault = None
        self.calls = 0
        self.cpu_seconds = self.wall_seconds = 0.0
        self._finished_summary = None
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            fault_path = self.folder / 'capture-fault.json'
            if fault_path.exists():
                previous = json.loads(fault_path.read_bytes())
                self.fault_count = int(previous['fault_count'])
                self.last_fault = previous['last_fault']
            self.journal = ObserverJournal(self.folder / 'events.sqlite')
        except Exception as error:
            self._fault('CAPTURE_INIT', 'capture-init', error)

    def _fault(self, kind, key, error):
        self.fault_count += 1
        self.last_fault = {'kind':kind, 'key':key, 'type':type(error).__name__,
                           'message':str(error)[:500], 'world_action_not_replayed':True}
        # A storage outage can also prevent this receipt. Independent primary
        # controller/host records remain necessary for completeness decisions.
        try:
            atomic_write(self.folder / 'capture-fault.json', json_bytes({
                'fault_count':self.fault_count, 'last_fault':self.last_fault}))
        except Exception:
            pass

    def record(self, kind, key, payload, source=None):
        wall, cpu = time.perf_counter(), time.process_time()
        self.calls += 1
        try:
            if self.journal is None:
                raise OSError('Observer journal initialization failed; no memory retry queue')
            # Canonical source must remain stable for an idempotent same-key retry.
            # Wall-clock capture time is not part of observation identity.
            return self.journal.append(kind, key, payload, source if source is not None else {
                'episode_id':self.episode, 'evidence_scope':'controller_actual_boundary'})
        except Exception as error:
            self._fault(kind, key, error)
        finally:
            self.cpu_seconds += time.process_time() - cpu
            self.wall_seconds += time.perf_counter() - wall

    def finish(self, status):
        if self._finished_summary is not None:
            return self._finished_summary
        self.record('CAPTURE_CLOSED', 'capture-closed', {'episode_id':self.episode, 'status':status})
        if self.journal is not None:
            try:
                self.journal.close()
            except Exception as error:
                self._fault('CAPTURE_CLOSE', 'capture-close', error)
        try:
            storage_bytes = sum(p.stat().st_size for p in self.folder.glob('*') if p.is_file())
        except OSError as error:
            storage_bytes = None
            self._fault('CAPTURE_SUMMARY', 'capture-storage-size', error)
        value = {'version':VERSION, 'episode_id':self.episode, 'capture_status':status,
                 'observed_boundary_calls':self.calls, 'observer_fault_count':self.fault_count,
                 'last_fault':self.last_fault, 'observer_CPU_seconds':self.cpu_seconds,
                 'observer_wall_seconds':self.wall_seconds,
                 'controller_peak_RSS_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                 'storage_bytes':storage_bytes,
                 'no_memory_queue':True, 'graph_projection_online':False,
                 'COMPLETE_requires_independent_request_and_action_reconciliation':True}
        try:
            atomic_write(self.folder / 'capture-summary.json', json_bytes(value))
        except Exception as error:
            self._fault('CAPTURE_SUMMARY', 'capture-summary', error)
            value.update(observer_fault_count=self.fault_count, last_fault=self.last_fault)
        self._finished_summary = value
        return value


def build_team_owner(post, *, organization_id, slot_id, condition_id, folder, deadline, identity,
                     observation_token_counter=None, observation_tokenizer_id=None,
                     require_content_counter=False):
    if organization_id != 'REVIEW2':
        raise ValueError('This pilot freezes original two-member REVIEW2')
    sidecar = Sidecar(Path(folder) / 'passive-observer', slot_id)

    def captured_post(route, payload):
        if route != '/chat/completions':
            return post(route, payload)
        request_id = payload['request_id']
        sidecar.record('MODEL_REQUEST', 'request:'+request_id, payload)
        try:
            result = post(route, payload)
        except BaseException as error:
            sidecar.record('MODEL_EXCEPTION', 'exception:'+request_id, {
                'actor':payload.get('member_id'), 'request_id':request_id,
                'type':type(error).__name__, 'actual_usage_not_inferred':True})
            raise
        sidecar.record('MODEL_RESPONSE', 'response:'+request_id, {
            'actor':payload.get('member_id'), 'request_id':request_id, 'body':result})
        return result

    owner = _build_owner(captured_post, organization_id=organization_id, slot_id=slot_id,
        condition_id=condition_id, folder=folder, deadline=deadline, identity=identity,
        observation_token_counter=observation_token_counter,
        observation_tokenizer_id=observation_tokenizer_id, require_content_counter=require_content_counter)
    owner.passive_sidecar = sidecar
    return owner


def build_runtime(owner, prepared, folder, *, deadline, public_initial_message, worker_factory=None):
    runtime, captured, interfaces = base.build_runtime(owner, prepared, folder, deadline=deadline,
        public_initial_message=public_initial_message, worker_factory=worker_factory)
    capture = owner.passive_sidecar
    capture.record('INITIAL', 'initial', {'episode_id':owner.window_id,
        'fixed_members':list(runtime.members), 'organization':runtime.fixed_spec,
        'public_initial_message':public_initial_message, 'case_id':prepared.case['case_id'],
        'agent_schema_unchanged':True, 'policy_input_is_not_global_observer_graph':True})
    original_execute = runtime.execute

    def execute(self, actor, tool, arguments, association):
        key = actor+':'+str(association.get('model_call_id'))+':'+str(association.get('model_tool_call_id'))
        capture.record('INTENT', 'intent:'+key, {'actor':actor, 'tool':tool,
            'arguments':arguments, 'association':association})
        try:
            response = original_execute(actor, tool, arguments, association)
        except BaseException as error:
            capture.record('ACTION_EXCEPTION', 'action-exception:'+key, {
                'actor':actor, 'tool':tool, 'arguments':arguments, 'association':association,
                'type':type(error).__name__, 'world_effect_not_inferred':True})
            raise
        capture.record('RECEIPT', 'receipt:'+key, {'actor':actor, 'tool':tool,
            'arguments':arguments, 'association':association, 'response':response})
        return response
    runtime.execute = MethodType(execute, runtime)
    return runtime, captured, interfaces


def run_fragment(prepared, runtime, *, on_opportunity=None):
    count = 0
    def opportunity(outcome):
        nonlocal count
        count += 1
        runtime.owner.passive_sidecar.record('OPPORTUNITY', f'opportunity:{count}', outcome)
        if on_opportunity:
            on_opportunity(outcome)
    result = base.run_fragment(prepared, runtime, on_opportunity=opportunity)
    runtime._passive_boundary = result['status']
    runtime.owner.passive_sidecar.record('BOUNDARY', 'boundary', {
        'status':result['status'], 'closure_reason':result['closure_reason'],
        'opportunities':result['opportunities'], 'actions':result['actions']})
    return result


def close_runtime(runtime):
    try:
        return base.close_runtime(runtime)
    finally:
        runtime.owner.passive_sidecar.finish(getattr(runtime, '_passive_boundary', 'abnormal_or_incomplete'))


def lock_fixed_candidates(prepared, folder, *, sdk_closed):
    return base.lock_fixed_candidates(prepared, folder, sdk_closed=sdk_closed)
