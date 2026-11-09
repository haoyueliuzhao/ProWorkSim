"""Keep a bounded derived report without confusing raw and formatted byte limits.

The actor already limits its framework journal to4MiB. Parsed report projection
and indented canonical JSON have a different size; allow32MiB for passive disk
storage only. Tools/model presentation, public testing and verdicts are unchanged.
Any observation error still remains measurement_partial in the v167 boundary.
"""
from .software_collaboration_runtime_observer_v167 import (
    RuntimeObservationBridge as PreviousBridge, root_sessions, sha)
from .storage import atomic_write, json_bytes

MAX_SERIALIZED_REPORT_BYTES = 32*1024**2


class RuntimeObservationBridge(PreviousBridge):
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
        if len(raw) > MAX_SERIALIZED_REPORT_BYTES:
            raise ValueError('Serialized public-test observation report exceeds32MiB')
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
