"""Passive communication observations bound to authoritative World receipts.

No changes to action permissions, test semantics, model prompts or organization.
"""
from __future__ import annotations

import copy
from types import FunctionType

from . import software_collaboration_runtime_observer_v156 as previous
from .software_collaboration_observation_v167 import ObservationLog
from .storage import atomic_write, json_bytes

sha = previous.sha


def _bind(function, **bindings):
    value = FunctionType(function.__code__, {**function.__globals__, **bindings},
                         function.__name__, function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


def root_sessions(report):
    """Verify the full immutable hierarchy; inline only its command-root summary."""
    sessions = report.get('sessions', [])
    if not isinstance(sessions, list):
        raise ValueError('Public-test sessions must be a list')
    by_id = {s['run_id']: s for s in sessions}
    if len(by_id) != len(sessions):
        raise ValueError('Duplicate public-test session identity')
    roots = [s for s in sessions if s.get('root') is True]
    if not sessions:
        return []
    if len(roots) != 1:
        raise ValueError('Public-test sessions require one command root')
    root = roots[0]['run_id']
    reached = {root}
    for item in by_id:
        pending, current = set(), item
        while current not in reached:
            if current in pending or current not in by_id:
                raise ValueError('Public-test session ancestry is cyclic or missing')
            pending.add(current)
            current = by_id[current].get('parent_run_id')
        reached.update(pending)
    return [{k: roots[0].get(k) for k in
             ('run_id', 'parent_run_id', 'root', 'exitstatus', 'counts')}]


class RuntimeObservationBridge(previous.RuntimeObservationBridge):
    __init__ = _bind(previous.RuntimeObservationBridge.__init__, ObservationLog=ObservationLog)

    def executed(self, member, name, arguments, association, response, before):
        if name != 'org_review_patch':
            return super().executed(member, name, arguments, association, response, before)
        request = self.tool_requests.get((member, association.get('model_tool_call_id')))
        evidence = {'model_tool_call_id': association.get('model_tool_call_id'),
                    'model_call_id': association.get('model_call_id'), 'response_sha256': sha(response)}
        self.log.record_action(self.eid('action'), member, name, request,
            response.get('ok') if isinstance(response, dict) else None, evidence=evidence)
        if request is None:
            self.partial.add('actions')
        if not isinstance(response, dict) or response.get('ok') is not True:
            return
        receipt = response.get('result', {})
        world = self.runtime.prepared.world
        actual = [r for r in world.org_state()['reviews']
                  if r.get('review_id') == receipt.get('review_id')]
        if len(actual) != 1 or actual[0] != receipt:
            raise ValueError('Review must match the actual authoritative World receipt')
        if (receipt.get('actor_id') != member or receipt.get('patch_id') != arguments['patch_id']
                or receipt.get('decision') != arguments['decision']):
            raise ValueError('Review receipt identity differs from this successful action')
        identity = world.org_current_identity(member)
        publication = self.publications[arguments['patch_id']][0]
        # Original receipt (including reason/test sequence) remains immutable and
        # complete; bounded event metadata is an explicit projection, not a test.
        raw = json_bytes(receipt)
        path = self.folder/'world-review-receipts'/(sha(receipt)+'.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('World review receipt content changed')
        if not path.exists():
            atomic_write(path, raw)
        facts = {k: copy.deepcopy(receipt.get(k)) for k in (
            'review_id', 'patch_id', 'actor_id', 'author', 'identity', 'decision',
            'adopted_source_reference', 'test_evidence', 'event_sequence')}
        self.log.record(self.eid('world-review'), 'world_review', member,
            publication=publication, current_identity=identity, receipt=facts,
            original_receipt={'path': str(path), 'sha256': sha(receipt), 'bytes': len(raw)},
            evidence=evidence)

    def observe_public_test(self, member, result):
        """Retain v141 parser output; nested session counts never inflate root counts."""
        execution = result.get('execution', {})
        executed = execution.get('executed', result.get('executed'))
        if type(executed) is not bool:
            raise ValueError('Public-test execution status is missing')
        report = result.get('test_evidence', execution.get('test_evidence'))
        if not isinstance(report, dict):
            raise ValueError('Session-bound public-test evidence is missing')
        raw = json_bytes(report)
        if len(raw) > 4*1024**2:
            raise ValueError('Public-test observation report exceeds the established evidence bound')
        digest = sha(report)
        path = self.folder / 'public-test-reports' / (digest+'.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            atomic_write(path, raw)
        elif path.read_bytes() != raw:
            raise ValueError('A public report identity cannot change its contents')
        sessions = root_sessions(report)
        source = result.get('source_reference', execution.get('source_reference'))
        # The same framework report arriving twice is not another test run.
        event = 'public-test:'+sha({'member': member, 'report': digest, 'execution': execution, 'source': source})
        evidence = {'report_sha256': digest, 'execution_sha256': sha(execution)}
        recorded = self.log.record(event, 'public_test', member, source_reference=source,
            executed=executed, passed=result.get('passed'),
            command={'argv': execution.get('argv'), 'returncode': execution.get('returncode'),
                     'timed_out': execution.get('timed_out'), 'executed': executed},
            report={'path': str(path), 'sha256': digest, 'bytes': len(raw), 'saved': True},
            sessions=sessions, session_count=len(report.get('sessions', [])),
            inline_sessions_scope='command_root_only_full_hierarchy_in_saved_report',
            validation_status=result.get('validation_status'), evidence=evidence)
        if recorded['duplicate']:
            return event
        report_obj = self._object(member, 'test-report:'+digest, digest, source=source)
        made = self._stage(member, 'produced', report_obj, evidence=evidence,
                           origin_role='public_test_runner_not_model')
        self.information_objects[event] = (report_obj, made)
        if executed:
            obj = self._object(member, 'tested-source:'+sha(source), execution.get('input_tree_sha256') or sha(source),
                               source=source)
            self._stage(member, 'validated', obj, test_event=event,
                        passed=result.get('passed'), evidence=evidence)
        # Saved reports are not automatically presented to the model.
        return event

