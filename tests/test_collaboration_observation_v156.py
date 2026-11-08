"""P0 CPU controls for actual observer semantics, recovery and session identity."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_collaboration_observation_v156 import CHANNELS, ObservationError, ObservationLog
from proworksim.software_collaboration_runtime_observer_v156 import RuntimeObservationBridge, sha
from proworksim.software_benchmark_public_test_evidence_v141 import parse_test_evidence

M1, M2 = 'member_001', 'member_002'


def ref(n=1):
    return {'object_id': 'source', 'version_id': 'v'+str(n)}


def proof(name='fixture'):
    return {'trusted_runtime_receipt': name}


def chain(log, *, passed=False, executed=True):
    log.record('pub', 'artifact_published', M2, patch_id='p1', source_reference=ref(5),
               content_identity={'files_sha256': 'a'*64}, evidence=proof())
    log.record('chance', 'artifact_opportunity', M1, publication='pub', eligible=True, evidence=proof())
    log.record('take', 'artifact_acquired', M1, opportunity='chance', adopted_reference=ref(), evidence=proof())
    log.record('test', 'artifact_validated', M1, acquisition='take', tested_reference=ref(),
               executed=executed, passed=passed, evidence=proof())
    log.record('integrate', 'artifact_integrated', M1, publication='pub', result_reference=ref(),
               explicit_agent_action=True, evidence=proof())


def test_failed_public_test_acceptance_matches_world_and_stale_version_is_invalidated(tmp_path):
    with ObservationLog(tmp_path, 'team', [M1, M2]) as log:
        chain(log)
        log.record_review('review', M1, 'test', 'accept', current_reference=ref(), evidence=proof())
        assert log.summary()['review']['current_version_acceptances'] == 1
        assert log._rows['test']['data']['passed'] is False
        log.record('edit', 'version_transition', M1, from_reference=ref(), to_reference=ref(2), evidence=proof())
        assert log.summary()['review']['current_version_acceptances'] == 0
        with pytest.raises(ObservationError, match='same current version'):
            log.record_review('stale', M1, 'test', 'accept', current_reference=ref(2), evidence=proof())
        assert log.summary()['review']['accept_decisions'] == 1


def test_acceptance_without_executed_same_version_test_is_rejected(tmp_path):
    with ObservationLog(tmp_path, 'team', [M1, M2]) as log:
        chain(log, executed=False, passed=None)
        with pytest.raises(ObservationError, match='actually executed'):
            log.record_review('review', M1, 'test', 'accept', current_reference=ref(), evidence=proof())


def test_author_changes_also_invalidate_old_acceptance_without_reviewers_edit(tmp_path):
    with ObservationLog(tmp_path, 'team', [M1, M2]) as log:
        chain(log, passed=True)
        log.record_review('review', M1, 'test', 'accept', current_reference=ref(), evidence=proof())
        log.record('author-edit', 'version_transition', M2,
                   from_reference=ref(5), to_reference=ref(6), evidence=proof())
        assert log.summary()['review']['current_version_acceptances'] == 0
        assert log.summary()['review']['accept_decisions'] == 1
        # Reviewing the old published snapshot is legal; it cannot certify the author's new tree.
        log.record_review('old-again', M1, 'test', 'accept', current_reference=ref(), evidence=proof())
        assert log.summary()['review']['current_version_acceptances'] == 0


def test_request_changes_does_not_invent_a_required_test(tmp_path):
    with ObservationLog(tmp_path, 'team', [M1, M2]) as log:
        log.record('pub', 'artifact_published', M2, patch_id='p1', source_reference=ref(5),
                   content_identity={'files_sha256': 'a'*64}, evidence=proof())
        log.record_review('rework', M1, None, 'request_changes', current_reference=ref(),
                          publication='pub', evidence=proof('actual world accepts request_changes'))
        assert log.summary()['artifacts']['independent_review_events'] == 1
        assert log.summary()['artifacts']['same_version_public_test_executed'] == 0


def test_entering_delivery_chain_does_not_rewrite_test_failure_as_pass(tmp_path):
    with ObservationLog(tmp_path, 'team', [M1, M2]) as log:
        chain(log)
        log.record('lock', 'candidate_locked', M1, reference=ref(), generation_closed=True, evidence=proof())
        log.record('delivery', 'final_delivery', M1, candidate_lock='lock', legal=True,
            submitted_reference=ref(), artifact_chain=[{'integration': 'integrate', 'validation': 'test',
                                                       'transitions': []}], evidence=proof())
        summary = log.summary()['artifacts']
        assert summary['entered_legal_delivery_chain'] == 1
        assert summary['same_version_public_test_passed'] == 0
        assert summary['same_version_public_test_executed'] == 1
        info = {'object_id': 'artifact:p1', 'origin_member': M2, 'allowed_members': [M2, M1],
                'source_reference': ref(5), 'content_sha256': sha({'files_sha256': 'a'*64})}
        log.record_lifecycle('published-lifecycle', M2, stage='published', evidence=proof(), **info)
        log.record_lifecycle('incorporated', M1, stage='incorporated_into_delivery',
            prior_event='published-lifecycle', delivery_event='delivery', integration_event='integrate',
            evidence=proof(), **info)
        assert log.summary()['lifecycle']['incorporated_into_delivery'] == 1


def obj():
    return {'object_id': 'message-one', 'origin_member': M1, 'allowed_members': [M1, M2],
            'content_sha256': 'a'*64, 'source_reference': None}


def stage(log, event, actor, name, prior=None, **facts):
    return log.record_lifecycle(event, actor, stage=name, prior_event=prior,
                                evidence=proof(event), **obj(), **facts)


def test_information_stages_are_independent_and_delivery_is_not_seen_or_used(tmp_path):
    with ObservationLog(tmp_path, 'team', [M1, M2]) as log:
        stage(log, 'draft', M1, 'produced')
        assert log.summary()['lifecycle']['published'] == 0
        stage(log, 'pub', M1, 'published', 'draft')
        assert log.summary()['lifecycle']['delivered'] == 0
        stage(log, 'queue', M2, 'delivered', 'pub')
        assert log.summary()['lifecycle']['presented'] == 0
        with pytest.raises(ObservationError, match='not evidence'):
            stage(log, 'not-used', M2, 'behaviorally_used', 'queue', action_event='absent',
                  source_action_binding=proof())
        stage(log, 'input', M2, 'presented', 'queue', request_id='r2', actual_input=proof())
        stage(log, 'pull', M2, 'retrieved', 'input', authorized=True, tool_receipt=proof())
        assert log.summary()['lifecycle']['behaviorally_used'] == 0
        log.record_action('action', M2, 'read_file', 'r2', True, evidence=proof())
        stage(log, 'use', M2, 'behaviorally_used', 'pull', action_event='action',
              source_action_binding={'message_event': 'pub', 'actual_reference_in_action': 'module.py'})
        assert log.summary()['lifecycle']['behaviorally_used'] == 1
        assert log.summary()['lifecycle']['validated'] == 0
        assert log.summary()['lifecycle']['incorporated_into_delivery'] == 0
        assert stage(log, 'use', M2, 'behaviorally_used', 'pull', action_event='action',
                     source_action_binding={'message_event': 'pub', 'actual_reference_in_action': 'module.py'})['duplicate']


def test_private_information_denied_pull_and_version_change_cannot_claim_lifecycle(tmp_path):
    with ObservationLog(tmp_path, 'team', [M1, M2]) as log:
        private = {**obj(), 'allowed_members': [M1]}
        log.record_lifecycle('private', M1, stage='produced', evidence=proof(), **private)
        with pytest.raises(ObservationError, match='Private information'):
            log.record_lifecycle('foreign', M2, stage='retrieved', evidence=proof(),
                prior_event='private', authorized=True, tool_receipt=proof(), **private)
        with pytest.raises(ObservationError, match='denied retrieval'):
            stage(log, 'denied', M2, 'retrieved', authorized=False, tool_receipt=proof())
        stage(log, 'p', M1, 'produced')
        with pytest.raises(ObservationError, match='object or version'):
            log.record_lifecycle('changed', M1, stage='published', prior_event='p', evidence=proof(),
                                 **{**obj(), 'content_sha256': 'b'*64})


def test_append_only_replay_and_partial_coverage_cannot_be_upgraded(tmp_path):
    with ObservationLog(tmp_path, 'team', [M1, M2]) as log:
        stage(log, 'p', M1, 'produced')
        log.record_coverage('gap', 'lifecycle', False, evidence=proof())
    with ObservationLog(tmp_path, 'team', [M1, M2]) as log:
        assert log.summary()['lifecycle']['produced'] == 1
        with pytest.raises(ObservationError, match='cannot become complete'):
            log.record_coverage('fake', 'lifecycle', True, evidence={
                'coverage_proven': True, 'observation_started_at_initial_state': True, 'finalized_normally': True})


def test_runtime_failed_test_acceptance_does_not_create_observer_error(tmp_path):
    bridge = RuntimeObservationBridge(tmp_path, team_id='runtime', members=[M1, M2])
    chain(bridge.log)
    bridge.validations[(M1, 'p1')] = ('test', False)
    bridge.runtime = SimpleNamespace(prepared=SimpleNamespace(world=SimpleNamespace(
        org_current_identity=lambda member: {'source_reference': ref()})))
    bridge.tool_requests[(M1, 'call1')] = 'request1'
    bridge.executed(M1, 'org_review_patch', {'patch_id': 'p1', 'decision': 'accept'},
        {'model_tool_call_id': 'call1', 'model_call_id': 'model1'}, {'ok': True, 'result': {}}, ref())
    assert not bridge.errors and not bridge.partial
    assert bridge.log.summary()['review']['accept_decisions'] == 1
    bridge.close_partial('CPU fixture complete')


def test_runtime_message_delivery_waits_for_exact_actual_input(tmp_path):
    bridge = RuntimeObservationBridge(tmp_path, team_id='messages', members=[M1, M2])
    world = SimpleNamespace(org_current_identity=lambda member: {'source_reference': ref()}, state={})
    bridge.runtime = SimpleNamespace(prepared=SimpleNamespace(world=world))
    bridge.tool_requests[(M1, 'call1')] = 'r1'
    bridge.executed(M1, 'send_message', {'recipient': M2, 'body': 'inspect module'},
        {'model_tool_call_id': 'call1'}, {'ok': True, 'result': {'message_sequence': 7}}, ref())
    assert bridge.log.summary()['lifecycle']['delivered'] == 1
    assert bridge.log.summary()['lifecycle']['presented'] == 0
    body = {'observation': {'messages': [{'sequence': 7, 'body': 'inspect module'}]}}
    wire = {'messages': [{'role': 'user', 'content': json.dumps(body)}]}
    bridge.provider_returned(M2, {'request_id': 'r2', 'wire': wire, 'usage_id': 'agent'},
        {'usage': {'prompt_tokens': 10, 'completion_tokens': 2}, 'choices': []})
    assert bridge.log.summary()['lifecycle']['presented'] == 1
    assert bridge.log.summary()['lifecycle']['behaviorally_used'] == 0
    assert not bridge.errors
    bridge.close_partial('fixture')


def records(run='root', parent=None, pid=10, passed=1, failed=0):
    identity = dict(version='v141-session-bound-framework-observer-r1', token='command',
                    framework='pytest', pgid=10, pid=pid, run_id=run, parent_run_id=parent)
    return [dict(identity, event='start'), dict(identity, event='finish',
        counts=dict(collected=passed+failed, passed=passed, failed=failed, errors=0,
                    skipped=0, xfailed=0, xpassed=0), exitstatus=int(bool(failed)),
        collection_errors=0, collection_complete=True, partial=False, report_conflicts=[])]


def public_result(rows):
    raw = ('\n'.join(json.dumps(r) for r in rows)+'\n').encode()
    value = parse_test_evidence(raw, framework='pytest', token='command', process_group=10,
                               returncode=0, timed_out=False)
    return {**value, 'source_reference': ref(), 'execution': {'executed': True,
        'argv': ['python', '-m', 'pytest'], 'returncode': 0, 'timed_out': False,
        'input_tree_sha256': 'a'*64, 'source_reference': ref()}}


def test_nested_sessions_reports_saved_presented_and_duplicate_transport_are_separate(tmp_path):
    root, child = records(), records('child', 'root', 20, passed=0, failed=1)
    result = public_result([root[0], child[0], child[1], root[1], root[1]])
    assert result['passed'] and result['counts']['passed'] == 1
    assert result['test_evidence']['duplicate_journal_records_ignored'] == 1
    bridge = RuntimeObservationBridge(tmp_path, team_id='tests', members=[M1])
    event = bridge.observe_public_test(M1, result)
    assert bridge.observe_public_test(M1, result) == event
    summary = bridge.log.summary()['public_tests']
    assert summary['executed'] == summary['passed'] == summary['reports_saved'] == 1
    assert summary['reports_presented'] == 0
    sessions = bridge.log._rows[event]['data']['sessions']
    assert len(sessions) == 2 and next(s for s in sessions if not s['root'])['parent_run_id'] == 'root'
    response = {'ok': True, 'result': result}
    bridge.reads[(M1, 'test-call')] = (event, sha(response))
    wire = {'messages': [{'role': 'tool', 'tool_call_id': 'test-call', 'content': json.dumps(response)}]}
    bridge.provider_returned(M1, {'request_id': 'r1', 'wire': wire, 'usage_id': 'agent'},
        {'usage': {'prompt_tokens': 10, 'completion_tokens': 1}, 'choices': []})
    assert bridge.log.summary()['public_tests']['reports_presented'] == 1
    assert not bridge.errors
    bridge.close_partial('fixture')


def test_zero_tests_executed_command_is_not_test_pass(tmp_path):
    value = public_result(records(passed=0))
    assert value['validation_status'] == 'no_tests' and not value['passed']
    bridge = RuntimeObservationBridge(tmp_path, team_id='zero', members=[M1])
    bridge.observe_public_test(M1, value)
    assert bridge.log.summary()['public_tests']['executed'] == 1
    assert bridge.log.summary()['public_tests']['passed'] == 0
    bridge.close_partial('fixture')


def test_exceptional_exit_preserves_usage_and_recovery_never_fabricates_complete_coverage(tmp_path):
    with pytest.raises(RuntimeError, match='synthetic'):
        with RuntimeObservationBridge(tmp_path, team_id='failure', members=[M1]) as bridge:
            bridge.log.record_usage('u1', M1, 'r1', 'agent', 'settled',
                {'prompt_tokens': 10, 'completion_tokens': 2}, receipt=proof())
            raise RuntimeError('synthetic export failure')
    saved = json.loads((tmp_path/'summary.json').read_text())
    assert saved['completion_status'] == 'partial' and not any(saved['coverage'].values())
    assert saved['usage']['known_actual_tokens']['total_tokens'] == 12
    reopened = RuntimeObservationBridge(tmp_path, team_id='failure', members=[M1])
    coverage = {c: {'complete': True, 'evidence': proof()} for c in CHANNELS}
    value = reopened.finalize(completion_status='normal', coverage_evidence=coverage, lock_receipt=proof())
    assert value['recovery'] and value['completion_status'] == 'partial'
    assert not any(value['coverage'].values())
    assert value['usage']['known_actual_tokens']['total_tokens'] == 12


def test_normal_finalize_requires_explicit_channel_proof_and_is_idempotent(tmp_path):
    bridge = RuntimeObservationBridge(tmp_path/'unproven', team_id='normal', members=[M1])
    value = bridge.finalize(completion_status='normal', lock_receipt=proof())
    assert not any(value['coverage'].values())
    assert bridge.finalize() == value
    bridge = RuntimeObservationBridge(tmp_path/'proven', team_id='normal', members=[M1])
    coverage = {c: {'complete': True, 'evidence': proof('hooks continuous; no requests in CPU fixture')} for c in CHANNELS}
    value = bridge.finalize(completion_status='normal', lock_receipt=proof(), coverage_evidence=coverage)
    assert all(value['coverage'].values())
    with pytest.raises(ValueError, match='finalized normal'):
        RuntimeObservationBridge(tmp_path/'proven', team_id='normal', members=[M1])


def explicit_request(*, unknown=False):
    from proworksim.software_input_provenance_v156 import (
        AnnotatedText, SourceFragment, TextSegment, annotate_tree, build_request, capture_response)
    summary = SourceFragment('Summary', 'summary-one', 'summary-event', M2,
                             transformation='summary', parent_source_ids=('unseen-peer-original',))
    peer = SourceFragment('Peer-message', 'peer-excerpt', 'message-event', M1, transformation='excerpt')
    base = SourceFragment('Base/Template', 'system-template', 'system-event', M2)
    wire = annotate_tree({'model': 'deepseek-flash', 'messages': [
        {'role': 'user', 'content': ''}]}, base)
    wire['messages'][0]['content'] = AnnotatedText((TextSegment('short summary', summary),
        TextSegment('actual peer excerpt', None if unknown else peer)))
    identity = {'request_id': 'r1', 'episode_id': 'explicit', 'member_id': M2,
        'decision_id': 'd1', 'attempt_id': 'a1', 'model_alias': 'deepseek-flash', 'request_time': 'fixture'}
    built = build_request(wire, identity, template_source=base)
    body = {'id': 'response1', 'model': 'deepseek-flash',
        'choices': [{'finish_reason': 'stop', 'message': {'content': 'done'}}],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}}
    response = capture_response(built, body, outcome='success', http_status=200, response_time='fixture')
    return built, body, response


@pytest.mark.parametrize('unknown', [False, True])
def test_explicit_source_exposure_does_not_expand_summary_parents_or_hide_unknown(tmp_path, unknown):
    built, body, response = explicit_request(unknown=unknown)
    bridge = RuntimeObservationBridge(tmp_path, team_id='explicit', members=[M1, M2],
                                      explicit_source_presentations=True)
    bridge.provider_returned(M2, {'request_id': 'r1', 'usage_id': 'agent',
        'wire': json.loads(built.payload_bytes)}, body)
    receipt = bridge.observe_source_presentations(M2, built, response)
    value = json.loads(Path(receipt['path']).read_text())
    summary_rows = [r for r in value['source_occurrences'] if r['source'] and r['source']['category'] == 'Summary']
    assert len(summary_rows) == 1
    assert summary_rows[0]['source']['parent_source_ids'] == ['unseen-peer-original']
    assert not any(r['source'] and r['source']['source_id'] == 'unseen-peer-original'
                   for r in value['source_occurrences'])
    assert bridge.source_presentation_coverage_proof()['complete'] is (not unknown)
    final = bridge.finalize(completion_status='normal', lock_receipt=proof())
    assert final['coverage']['presentations'] is (not unknown)
    assert not final['coverage']['artifacts']  # Source trace cannot upgrade unrelated measurements.
    assert final['source_presentations']['summary_parent_originals_counted_as_presented'] is False
    assert final['lifecycle']['presented'] is None
    assert final['lifecycle_presentation_count_unit'] == 'unavailable_legacy_event_counter_in_explicit_source_mode'
    assert final['source_presentations']['fragment_occurrences'] > 0
    assert final['source_presentations']['source_request_pairs'] > 0


@pytest.mark.parametrize('category', ['Tool-feedback', 'Summary'])
def test_exact_tool_identity_links_report_excerpts_but_summary_parent_does_not(tmp_path, category):
    from proworksim.software_input_provenance_v156 import (
        SourceFragment, annotate_tree, build_request, capture_response)
    bridge = RuntimeObservationBridge(tmp_path, team_id='explicit', members=[M1, M2],
                                      explicit_source_presentations=True)
    test_event = bridge.observe_public_test(M2, public_result(records(passed=0)))
    marker = f'sdk-tool-call:explicit:{M2}:test-call'
    bridge.test_report_sources[marker] = test_event
    source = SourceFragment(category, 'actual-source', 'sdk-event', M2,
        transformation='summary' if category == 'Summary' else 'raw', parent_source_ids=(marker,))
    template = SourceFragment('Base/Template', 'template', 'system', M2)
    wire = annotate_tree({'model': 'deepseek-flash', 'messages': [{'role': 'tool', 'content': '0 tests collected'}]}, source)
    built = build_request(wire, {'request_id': 'r2', 'episode_id': 'explicit', 'member_id': M2,
        'decision_id': 'd2', 'attempt_id': 'a2', 'model_alias': 'deepseek-flash', 'request_time': 'fixture'},
        template_source=template)
    body = {'id': 'response2', 'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}
    response = capture_response(built, body, outcome='success', http_status=200, response_time='fixture')
    bridge.provider_returned(M2, {'request_id': 'r2', 'wire': json.loads(built.payload_bytes)}, body)
    bridge.observe_source_presentations(M2, built, response)
    assert bridge.log.summary()['public_tests']['reports_presented'] == int(category == 'Tool-feedback')
    bridge.close_partial('fixture')


def test_export_result_is_not_lost_when_measurement_finalization_raises(tmp_path, monkeypatch):
    from proworksim import software_role_baseline_runtime_v156 as runtime
    bridge = RuntimeObservationBridge(tmp_path/'observer', team_id='isolation', members=[M1])
    code = tmp_path/'code.json'
    code.write_text(json.dumps({'source_reference': ref()}))
    lock = tmp_path/'lock.json'
    lock.write_text(json.dumps({'terminal_code': {'path': str(code)}, 'last_legal_delivery': None}))
    result = {'path': str(lock)}
    monkeypatch.setattr(runtime.base, 'lock_fixed_candidates', lambda *a, **k: result)
    monkeypatch.setattr(bridge, 'finalize', lambda *a, **k: (_ for _ in ()).throw(ValueError('sidecar only')))
    prepared = SimpleNamespace(world=SimpleNamespace(collaboration_observer_v156=bridge,
                                                     collaboration_observer_v141=bridge))
    assert runtime.lock_fixed_candidates(prepared, tmp_path/'out', sdk_closed=True) == result
    assert bridge.errors[0]['scope'] == 'closure'
    bridge.log.close()
