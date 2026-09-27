"""Formal utility on an immutable four-project episode end boundary only."""
import copy
import json
import math
from pathlib import Path

from .episode import _read_boundary, assess_historical_episode
from .storage import digest, json_bytes, read_json
from .templates.retail_projects import request
from .templates.retail_projects_v017 import REWARD_VERSION, case_spec


def assess_project_episode(episode):
    root = Path(episode)
    result = {'version': REWARD_VERSION, 'eligible': False, 'reward': None, 'completed': None,
              'dimensions': {'P1_quality': None, 'P2_quality': None, 'P3_fixed_input_fidelity': None, 'overall_business_goal': None},
              'scope': 'Closed episode fixed submissions and immutable versions only; no live-world lookup or score feedback to workers.'}
    historical = assess_historical_episode(root)
    result['historical_assessment'] = historical
    if historical.get('assessment_execution', {}).get('status') != 'complete':
        result['reason'] = 'historical_evidence_or_evaluator_unavailable'
        return result
    try:
        manifest = read_json(root / 'manifest.json')
        phase = manifest['scenario']['variation'].get('assessment_phase', 'final')
        if phase not in {'final', 'initial_delivery'}:
            raise ValueError('Unknown predeclared assessment phase')
        result['assessment_phase'] = phase
        spec = manifest['scenario']['variation']['project_case']
        if spec != case_spec(spec['case_id']):
            raise ValueError('Episode case differs from frozen four-project declaration')
        store, state = _read_boundary(root, manifest['end'])
        start_store, start = _read_boundary(root, manifest['start'])
        selected = {state['work_items'][wid]['project_id']: state['work_items'][wid] for wid in manifest['selected_work_ids']}
        if set(selected) != {'P0', 'P1', 'P2', 'P3'}:
            raise ValueError('Episode must declare all four exact project nodes')
        evaluations = {r['project_id']: r['evaluation'] for r in historical['content_quality']['submissions']}
        if any(evaluations[p].get('status') in {'source_unavailable', 'evaluator_error'} for p in ('P1', 'P2', 'P3')):
            result['reason'] = 'required_fixed_product_evidence_unknown'
            return result
        dims = result['dimensions']
        for project, dimension in [('P1', 'P1_quality'), ('P2', 'P2_quality'), ('P3', 'P3_fixed_input_fidelity')]:
            dims[dimension] = evaluations[project].get('passed') is True
        subs = {p: item.get('submissions', [])[-1] if item.get('submissions') else None for p, item in selected.items()}
        valid = {p: bool(s and not s.get('invalidated') and s.get('current_applicability') != 'withdrawn') for p, s in subs.items()}
        refs, data = {}, {}
        for p, sub in subs.items():
            if not sub:
                continue
            alias = 'data' if p == 'P0' else 'result'
            oid = state['workspaces'][p][alias]
            vid = sub['artifact_versions'].get(oid)
            if vid:
                refs[p] = {'object_id': oid, 'version_id': vid}
                data[p] = read_json(store.version_path(state['artifacts'][oid], vid))
        coherent = False
        original_preserved = False
        if set(data) == {'P0', 'P1', 'P2', 'P3'}:
            original_oid = start['workspaces']['P0']['data']
            original = read_json(start_store.version_path(start['artifacts'][original_oid], 'v1'))
            original_preserved = data['P0'] == original
            s1, s2, s3 = [data[p]['sources'] for p in ('P1', 'P2', 'P3')]
            policy_ref = s3['basis']
            policy = read_json(store.version_path(state['artifacts'][policy_ref['object_id']], policy_ref['version_id']))
            coherent = (s1['data'] == s2['data'] == refs['P0'] and s1['basis'] == s2['basis'] == policy_ref
                        and s3['metrics'] == refs['P1'] and s3['analysis'] == refs['P2']
                        and policy == request(1 if phase == 'initial_delivery' else spec['target_policy_edition']))
        institutional = {r['project_id']: r for r in historical['institutional_progress']['works']}
        all_delivered = all(institutional[p]['status'] == 'accepted' and valid[p] for p in selected)
        published = True
        for project, item in selected.items():
            delivery = item['requirements'].get('public_delivery', {})
            if not delivery.get('publish'):
                continue
            targets = {project} | {r['project_id'] for r in delivery.get('recipients', [])}
            sub = subs[project]
            published &= bool(sub) and all(
                any(release['object_id'] == oid and release['version_id'] == vid
                    and target in release['scope']['target_projects'] for release in state['releases'])
                for oid, vid in (sub['artifact_versions'].items() if sub else []) for target in targets)
        # P3 arithmetic can be faithful while both branches share the same error.
        goal = (all(dims[k] for k in ('P1_quality', 'P2_quality', 'P3_fixed_input_fidelity'))
                and coherent and original_preserved and all_delivered and published)
        dims['overall_business_goal'] = bool(goal)
        result.update(eligible=True, reward=int(goal), completed=bool(goal),
                      exact_final_branch_versions=refs, source_preserved=original_preserved,
                      fixed_contract_and_version_coherence=coherent, all_projects_fixed_and_delivered=all_delivered,
                      declared_publication_obligations_complete=published,
                      episode_id=manifest['episode_id'], episode_manifest_sha256=digest((root / 'manifest.json').read_bytes()),
                      component_measurement='Independent branch quality and exact-input fidelity are diagnostic dimensions; scalar R is the conjunction, not a zero-difference shortcut.',
                      end_boundary_sha256=digest(json_bytes(state)))
    except (KeyError, ValueError, OSError, TypeError) as error:
        result['reason'] = 'invalid_or_unavailable_joint_evidence'
        result['diagnostic'] = str(error)
    return result



def assess_collection_records(episode, captures, expected_identity):
    """Check actual responses/receipts, independently of stop-status names.

    This is record provenance, not a probability recomputation or actor-training
    admission. A fully recorded protocol rejection remains a model observation.
    """
    from .presentations import response_matches_receipt
    from .templates.retail_projects import ACTORS

    root = Path(episode)
    issues, completed, verified_calls, format_rejections = [], [], 0, []
    try:
        manifest = read_json(root / 'manifest.json')
        # Reuse immutable boundary verification; do not read the live world.
        _, state = _read_boundary(root, manifest['end'])
        raw = (root / manifest['experience']['path']).read_bytes()
        if digest(raw) != manifest['experience']['sha256']:
            raise ValueError('Experience bytes differ from the closed boundary')
        events = json.loads(raw)['events'][manifest['experience']['start']:manifest['experience']['end']]
        starts, finishes = {}, {}
        for event in events:
            payload, label = event['payload'], event.get('worker_id')
            if event['kind'] == 'model_attempt':
                key = (label, payload.get('attempt_id'))
                target = starts if payload.get('stage') == 'started' else finishes
                if key in target:
                    issues.append({'kind': 'duplicate_model_attempt_stage', 'key': key})
                target[key] = payload
            elif event['kind'] == 'model_call' and payload.get('stage') == 'finished' and payload.get('status') in {'model_format_error', 'protocol_rejection'}:
                format_rejections.append({'role': label, 'call_id': payload.get('call_id'), 'reason': payload.get('error') or payload.get('reason'),
                                          'sequence': event['sequence']})
            elif event['kind'] in {'interface_error', 'interface_exception', 'binding_error'}:
                issues.append({'kind': 'explicit_interface_or_identity_evidence_gap', 'role': label, 'sequence': event['sequence'], 'evidence': payload})
            elif event['kind'] == 'policy_error':
                # These are Python policy exceptions, not ordinary tool refusals.
                # Without an associated actual rejected output their attribution
                # is incomplete, even when the terminal world remains readable.
                if not payload.get('model_call_id'):
                    issues.append({'kind': 'unattributed_worker_exception', 'role': label, 'sequence': event['sequence'], 'evidence': payload})
            elif event['kind'] == 'controller_action':
                response = payload.get('response', payload.get('result', {}))
                if response.get('ok') is False:
                    issues.append({'kind': 'actual_environment_action_rejected', 'sequence': event['sequence'], 'evidence': response})
        if set(starts) != set(finishes):
            issues.append({'kind': 'unpaired_model_attempt', 'started': list(starts), 'finished': list(finishes)})
        for key, end in finishes.items():
            response = end.get('response', {})
            body = response.get('body')
            if (key[0] not in ACTORS or end.get('weight_identity') != expected_identity
                    or (starts.get(key) or {}).get('weight_identity') != expected_identity):
                issues.append({'kind': 'model_request_identity_not_bound', 'key': key})
            if response.get('http_status') != 200 or not isinstance(body, dict):
                issues.append({'kind': 'model_service_response_unavailable', 'key': key, 'http_status': response.get('http_status')})
                continue
            try:
                exact = json.loads(response['raw_body']) == body
            except (KeyError, TypeError, ValueError):
                exact = False
            if not exact:
                issues.append({'kind': 'missing_or_changed_original_response', 'key': key})
            if body.get('actor_identity') != expected_identity:
                issues.append({'kind': 'actual_response_identity_missing_or_changed', 'key': key})
            trace = body.get('token_trace') or {}
            outputs, probabilities = trace.get('output_ids'), trace.get('behavior_logprobs')
            if (not isinstance(trace.get('input_ids'), list) or not isinstance(outputs, list)
                    or not isinstance(probabilities, list) or len(outputs) != len(probabilities)
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in probabilities)
                    or trace.get('raw_output_ids', outputs) != outputs
                    or trace.get('raw_behavior_logprobs', probabilities) != probabilities):
                issues.append({'kind': 'critical_original_token_record_missing_or_changed', 'key': key})
            completed.append((key[0], end.get('call_id')))
        for rejection in format_rejections:
            if (rejection['role'], rejection['call_id']) not in completed:
                issues.append({'kind': 'format_rejection_lacks_original_completed_response', 'evidence': rejection})
        for label in ACTORS:
            actual = [e['payload'] for e in events if e['kind'] == 'tool_call' and e.get('worker_id') == label]
            captured = [r['payload'] for r in captures.get(label, []) if r['kind'] == 'tool_call']
            fields = ('action', 'arguments', 'request_key', 'response')
            if [{k: p.get(k) for k in fields} for p in actual] != [{k: p.get(k) for k in fields} for p in captured]:
                issues.append({'kind': 'independent_world_capture_differs', 'role': label})
            for call in actual:
                response = call.get('response', {})
                commit = state['operation_commits'].get(response.get('command_id'))
                if (commit is None or commit.get('bound_actor') != ACTORS[label]
                        or not response_matches_receipt(commit, response, action=call['action'], arguments=call.get('arguments'))):
                    issues.append({'kind': 'actual_world_receipt_missing_or_changed', 'role': label, 'request_key': call.get('request_key')})
                else:
                    verified_calls += 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        issues.append({'kind': 'closed_record_boundary_unavailable', 'diagnostic': str(error)})
    return {'version': 'retail-project-record-trust-v0.18', 'trusted': not issues, 'issues': issues,
            'fixture_only': expected_identity.get('fixture') is True, 'probabilities_recomputed': False,
            'completed_original_responses': len(completed), 'verified_world_calls': verified_calls,
            'recorded_format_rejections': format_rejections,
            'scope': 'Original output/identity/token preservation and exact world receipts; stop labels alone do not remove known business failures.'}


def combine_project_measurement(independent, records):
    """Preserve the independent assessment separately; qualify study use by facts."""
    measurement = copy.deepcopy(independent)
    if not records['trusted']:
        measurement.update(eligible=False, reward=None, completed=None,
                           reason='critical_action_record_unavailable_or_untrusted', record_issues=copy.deepcopy(records['issues']))
    return measurement


def project_phase_diagnostics(episode, initial_episode, runtime_snapshot, initial_workers, final_assessment):
    """E4 facts from snapshots and actual inputs, never an inferred mental state."""
    from .core.projections import derive_current_work_view
    from .templates.retail_projects import ACTORS

    root, initial_root = Path(episode), Path(initial_episode)
    manifest = read_json(root / 'manifest.json')
    initial_manifest = read_json(initial_root / 'manifest.json')
    _, end = _read_boundary(root, manifest['end'])
    _, start = _read_boundary(root, manifest['start'])
    _, initial_end = _read_boundary(initial_root, initial_manifest['end'])
    events = read_json(root / manifest['experience']['path'])['events']
    initial = assess_project_episode(initial_root)
    final = final_assessment
    case = manifest['scenario']['variation']['project_case']
    termination = manifest['termination']
    controller = termination.get('controller', {})
    event_id = 'declared-half-year-net-contract'
    event_status = controller.get('fired', {}).get(event_id)
    triggered = event_status == 'executed'
    views = derive_current_work_view(end)
    per_role = {}
    for role in ACTORS:
        new_ids = sorted(wid for wid, work in end['work_items'].items()
                         if triggered and wid not in initial_end['work_items'] and work['project_id'] == role)
        receptions = []
        for event in events:
            payload = event['payload']
            if event['kind'] != 'model_attempt' or event.get('worker_id') != role or payload.get('stage') != 'finished':
                continue
            response = payload.get('response', {})
            if response.get('http_status') != 200 or not (response.get('body') or {}).get('token_trace', {}).get('input_ids'):
                continue
            for message in payload.get('request', {}).get('messages', []):
                if message.get('role') != 'user' or not isinstance(message.get('content'), str):
                    continue
                try:
                    body = json.loads(message['content'])
                except (ValueError, TypeError):
                    continue
                observation = body.get('observation', {}) if isinstance(body, dict) else {}
                seen = [wid for wid in new_ids if observation.get('work_items', {}).get(wid, {}).get('is_current') is True]
                if seen:
                    receptions.append({'call_id': payload.get('call_id'), 'decision_index': payload.get('decision_index'),
                                       'work_ids': seen, 'world_clock': observation.get('clock')})
                    break
        first = receptions[0] if receptions else None
        limit = case['role_decision_limits'][role]
        used_before = first['decision_index'] - 1 if first and type(first['decision_index']) is int else None
        resumption = [e['payload'] for e in events if e['kind'] == 'new_obligation_reactivation' and e.get('worker_id') == role]
        initial_worker = initial_workers.get(role, {})
        final_worker = runtime_snapshot.get('worker_conversations', {}).get(role, {})
        conversation_id = initial_worker.get('conversation_id')
        conversation_same = (conversation_id == final_worker.get('conversation_id')) if conversation_id is not None and new_ids else None
        final_ids = [wid for wid in new_ids if views[wid].get('is_current') is True
                     and not end['work_items'][wid].get('superseded_by')]
        accepted = [wid for wid in final_ids if views[wid].get('status') == 'accepted'
                    and end['work_items'][wid].get('submissions')]
        per_role[role] = {'new_obligations': new_ids, 'observed_in_actual_model_input': bool(receptions) if new_ids else None,
                          'first_actual_receipt': first, 'declared_decision_budget': limit,
                          'decisions_used_before_receipt': used_before,
                          'remaining_decisions_at_receipt': max(0, limit - used_before) if used_before is not None else None,
                          'initial_conversation_id': conversation_id,
                          'final_conversation_id': final_worker.get('conversation_id'),
                          'same_sdk_conversation': conversation_same,
                          'reactivation_count': len(resumption),
                          'reactivation_preserved_budget': all(r.get('budget_reset') is False and r.get('before', {}).get('meter') == r.get('after', {}).get('meter') for r in resumption) if resumption else None,
                          'reactivation_events': [{'old_work': r['old_work'], 'new_work': r['new_work'],
                             'before_conversation_id': r.get('before', {}).get('conversation_id'),
                             'after_conversation_id': r.get('after', {}).get('conversation_id'),
                             'before_meter': r.get('before', {}).get('meter'), 'after_meter': r.get('after', {}).get('meter'),
                             'budget_reset': r.get('budget_reset'), 'original_event_sha256': digest(json_bytes(r))} for r in resumption],
                          'accepted_successor_work_ids': accepted,
                          'successor_fixed_delivery_completed': bool(final_ids) and len(accepted) == len(final_ids) if new_ids else None,
                          'stop_reason': termination.get('role_stops', {}).get(role)}
    start_views = derive_current_work_view(start)
    inherited = all(wid in start['work_items'] and start_views[wid]['status'] == 'accepted'
                    and start['work_items'][wid].get('submissions')
                    and start['work_items'][wid]['submissions'][-1]['submission_id'] == initial_manifest['fixed_deliveries'][wid]['submission_id']
                    for wid in initial_manifest['selected_work_ids'])
    if case['changed'] and not triggered:
        breakpoint = ('change_event_rejected' if event_status == 'rejected'
                      else 'initial_delivery_not_completed_change_not_entered')
    elif final.get('reward') == 1:
        breakpoint = 'final_business_goal_completed'
    elif any(r['new_obligations'] and not r['observed_in_actual_model_input'] for r in per_role.values()):
        breakpoint = 'new_obligation_not_presented_in_actual_model_input'
    elif case['changed']:
        breakpoint = 'change_entered_successor_delivery_or_quality_incomplete'
    else:
        breakpoint = 'static_delivery_or_quality_incomplete'
    return {'version': 'retail-project-phase-diagnostics-v0.18',
            'initial_worker_snapshot_sha256': digest(json_bytes(initial_workers)),
            'initial_delivery': {'scope': 'Independent fixed-product evaluation; record trust and model attribution remain separate.',
                                 'institutional_fixed_deliveries_completed': initial.get('all_projects_fixed_and_delivered', False),
                                 'published_deliveries_completed': initial.get('declared_publication_obligations_complete', False),
                                 'business_completed': initial.get('completed'), 'reward': initial.get('reward'),
                                 'dimensions': initial['dimensions'], 'inherited_fixed_deliveries': inherited,
                                 'episode_manifest_sha256': digest((initial_root / 'manifest.json').read_bytes())},
            'change': {'declared': case['changed'], 'event_id': event_id if case['changed'] else None,
                       'triggered': triggered, 'event_status': event_status,
                       'handling_measured': triggered and any(r['observed_in_actual_model_input'] is True for r in per_role.values()),
                       'phase_entered': triggered, 'actual_event_records': controller.get('log', []),
                       'trigger_contract': 'First institutional fixed deliveries accepted; this trigger does not call hidden quality evaluation.'},
            'roles': per_role, 'final_independent_dimensions': final['dimensions'], 'breakpoint': breakpoint,
            'scope': 'Receipt means an actual original model request contains the new current work; assignment, logs and mechanical observations alone do not count.'}
