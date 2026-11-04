"""Audit existing stopped REF endpoints offline, without replay or scoring."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/software-benchmark-v125/ref-stopped-audit-r1'
BATCH = ROOT / 'runs/software-benchmark-v111/aligned-interface-r1'
RECOVERY = ROOT / 'runs/software-benchmark-v114/stopped-code-recovery-r1'
VERSION = 'v125-existing-stopped-REF-evidence-audit-r1'
SOURCES = {}


def read_bytes(path):
    path = Path(path).resolve()
    if path.stat().st_size > 8 * 1024**2:
        raise ValueError('Do not reread large archived trees for this metadata audit')
    data = path.read_bytes()
    SOURCES[str(path)] = {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def load(path):
    return json.loads(read_bytes(path))


def checked(ref, *, as_json=True):
    data = read_bytes(ref['path'])
    if SOURCES[str(Path(ref['path']).resolve())] != ref:
        raise ValueError('Frozen evidence reference changed: ' + ref['path'])
    return json.loads(data) if as_json else data


def main():
    if OUT.exists():
        raise FileExistsError('Do not overwrite the first stopped-REF audit')
    controls = load(ROOT / 'artifacts/software-benchmark-v114/stopped-recovery-controls-r1/summary.json')
    repair_control = load(ROOT / 'artifacts/software-benchmark-v114/rejected-history-controls-r1/summary.json')
    assert controls['passed'] is True and repair_control['passed'] is True
    assert repair_control['API_calls'] == repair_control['Docker_operations'] == 0
    cases = []
    for item in controls['results']:
        index = item['slot_index']
        assert index in (7244, 7251)
        recovery = checked(item['result'])
        lock = checked(item['lock'])
        checked(item['patch'], as_json=False)
        source = checked(recovery['source'])
        original_refs = source['original_evidence']
        original = checked(original_refs['original_result'])
        child = checked(original_refs['controller_result'])
        writers = checked(original_refs['writer_quiescence'])
        quiet = checked(original_refs['quiescence'])
        interrupted = checked(original_refs['interrupted'])
        response = checked(original_refs['final_provider_response'])
        assert original['status'] == child['status'] == 'technical_unknown'
        assert original['candidate_lock'] is None and interrupted['official_final_candidate'] is False
        assert writers['all_quiet'] is True and writers['errors'] == []
        assert len(writers['writers']) == 2
        assert all(writer['state']['Running'] is False and writer['state']['Pid'] == 0
                   for writer in writers['writers'])
        assert quiet['quiescent'] is True and quiet['all_owned_objects_removed'] is True
        assert quiet['cleanup_errors'] == [] and quiet['retained_objects'] == []
        assert lock['tree_sha256'] == recovery['candidate_tree_sha256'] == item['candidate_tree_sha256']
        assert lock['patch_receipt']['patch'] == item['patch'] == recovery['patch']
        assert recovery['round_trip_verified'] is True and recovery['replaces_original_endpoint'] is False
        assert source['selection_rule'] == 'The sole complete original archive after both namespace writers stopped'
        assert source['original_bad_tool_call_executed'] is False

        last = child['ledger']['calls'][-1]
        choice = response['choices'][0]
        call = choice['message']['tool_calls'][0]
        try:
            json.loads(call['function']['arguments'])
        except json.JSONDecodeError as error:
            parse_error = {'type': type(error).__name__, 'message': error.msg,
                           'offset': error.pos, 'line': error.lineno, 'column': error.colno}
        else:
            raise ValueError('The original malformed provider call is no longer malformed')
        event_refs = source['rejected_action_evidence']['final_action_error_crash_events']
        action, rejected, crash = [checked(ref) for ref in event_refs]
        assert action['kind'] == 'ActionEvent' and action.get('action') is None
        assert action['tool_call_id'] == rejected['tool_call_id'] == call['id']
        assert action['llm_response_id'] == response['id']
        assert rejected['kind'] == 'AgentErrorEvent' and rejected['parent_id'] == action['id']
        assert rejected['classification']['retryable'] is True
        assert crash['kind'] == 'ConversationErrorEvent' and crash['parent_id'] == rejected['id']
        assert crash['code'] == 'JSONDecodeError'
        assert 'software_benchmark_deepseek_interfaces_v055.py' in child['traceback']
        assert '_canonical_call' in child['traceback'] and 'self.history.restore' in child['traceback']

        score_path = BATCH / 'grading-v114' / f'score-v114-{index}' / 'receipt.json'
        score = load(score_path)
        identity = checked(score['identity'])
        qualification = checked(identity['qualification'])
        assert qualification['passed'] is True
        assert identity['candidate_lock'] == item['lock']
        assert identity['patch_sha256'] == item['patch']['sha256']
        assert identity['patch_bytes'] == item['patch']['bytes']
        assert score['recovery_result'] == item['result']
        assert score['resolved'] is False and score['status'] == 'official_report'
        assert score['actor_feedback'] is False and score['candidate_changed'] is False
        assert score['replaces_original_endpoint'] is False and score['model_resampling'] is False
        official = score['official_result'][1][score['instance_id']]
        assert official['patch_successfully_applied'] is True and official['infra_failure'] is False
        tests = {category: {outcome: len(names) for outcome, names in group.items()}
                 for category, group in official['tests_status'].items()}
        ledger = child['ledger']
        assert ledger['known_actual_tokens'] == ledger['complete_actual_tokens'] == item['original_tokens']
        assert ledger['uncertain_reserved_tokens'] == 0 and ledger['inflight'] is None
        remaining = ledger['token_limit'] - ledger['known_actual_tokens']
        if index == 7244:
            assert choice['finish_reason'] == 'tool_calls' and last['max_output_tokens'] == 32768
            assert last['usage']['completion_tokens'] == 271 and remaining == 3262739
            interpretation = {
                'observed': 'Malformed file_editor arguments contain an invalid control character. SDK rejected the action; project raw-history canonicalization reparsed the rejected raw JSON and aborted the conversation.',
                'is_only_scoring_or_reporting_problem': False,
                'known_lost_generation_opportunity': 'The attempt ended with 3,262,739 tokens still unused; a corrected fresh attempt could use further work opportunities.',
                'cannot_infer': 'The stopped tree failing does not prove that the same model would fail after using the remaining budget.'}
        else:
            assert choice['finish_reason'] == 'length' and last['max_output_tokens'] == 268
            assert last['usage']['completion_tokens'] == 268 and remaining == 142
            interpretation = {
                'observed': 'The final terminal arguments were truncated at the dynamically reduced 268-token output cap. SDK rejected them, then the same project history parser crashed.',
                'is_only_scoring_or_reporting_problem': False,
                'budget_boundary_role': 'Only 142 total tokens remained, while the final input consumed 31,911. The recorded ordinary next-request shape would not fit; handling the rejected history is chiefly needed for honest budget-end closure here.',
                'inference_limit': 'This does not reconstruct an unobserved normal terminal boundary or prove a counterfactual repaired run would make the same choices.'}
        cases.append({'slot_index': index, 'instance_id': score['instance_id'], 'slot_id': score['slot_id'],
            'original_generation_status': 'technical_unknown', 'original_normal_candidate_locked': False,
            'existing_code_endpoint': 'recovered_stopped_code', 'existing_code_resolved': False,
            'official_score_is_environment_unknown': False,
            'original_calls': ledger['attempts'], 'agent_decisions': ledger['decisions'],
            'actual_total_tokens': ledger['known_actual_tokens'], 'unused_total_tokens': remaining,
            'last_provider_request': {'attempt': last['attempt'], 'tool': call['function']['name'],
                'finish_reason': choice['finish_reason'], 'output_cap': last['max_output_tokens'],
                'actual_input_tokens': last['usage']['prompt_tokens'],
                'actual_output_tokens': last['usage']['completion_tokens'],
                'bad_tool_call_id': call['id'], 'malformed_argument_parse': parse_error,
                'bad_call_executed': False},
            'SDK_recoverable_error_then_adapter_crash_confirmed': True,
            'both_original_writers_quiescent': True, 'unique_stopped_tree_locked_before_score': True,
            'candidate_tree_sha256': lock['tree_sha256'], 'candidate_patch': item['patch'],
            'scoring': {'receipt': SOURCES[str(score_path.resolve())], 'tests': tests,
                'patch_successfully_applied': True, 'infra_failure': False, 'resolved': False},
            'interpretation': interpretation, 'original_result': original_refs['original_result'],
            'controller_result': original_refs['controller_result'], 'recovery_result': item['result'],
            'candidate_lock': item['lock'], 'final_provider_response': original_refs['final_provider_response'],
            'SDK_rejection_and_crash_events': event_refs,
            'new_scoring_required_for_this_existing_code_endpoint': False,
            'new_model_calls_required_for_this_existing_code_endpoint': False})
    assert {row['slot_index'] for row in cases} == {7244, 7251}
    summary = {'version': VERSION, 'observed_utc': datetime.now(timezone.utc).isoformat(),
        'passed': True, 'cases': cases,
        'immediate_disposition': {
            'existing_supplemental_code_endpoints': {'known_failed': 2, 'unknown': 0},
            'original_generation_endpoints': {'technical_unknown_retained': 2},
            'repeat_existing_model_or_score_jobs': [],
            'REF_strict_overall_counts_unchanged': {'passed': 33, 'failed': 13, 'unknown': 4},
            'REF_supplemental_code_view': {'passed': 33, 'failed': 15, 'unstarted_Requests': 2},
            'old_score_or_usage_rows_modified': False},
        'repair_status': {
            'root_cause': 'Project rejected-tool-call history adapter reparses malformed provider JSON after a genuine SDK rejection; the SDK itself had already produced a recoverable tool error.',
            'existing_fix_evidence': SOURCES[str((ROOT / 'artifacts/software-benchmark-v114/rejected-history-controls-r1/summary.json').resolve())],
            'fix_invariants': repair_control['invariants'],
            'old_run_hot_patch_or_continuation_performed': False,
            'new_SDK_controls_repeated_in_this_audit': False},
        'conditional_new_attempts_if_a_normal_repaired_generation_endpoint_is_required': [
            {'original_slot_index': row['slot_index'], 'instance_id': row['instance_id'],
             'new_attempts': 1, 'method': 'fresh original baseline and empty conversation under explicitly frozen repaired REF',
             'same_budget_candidate_tokens': 5_000_000, 'needs_new_seed_and_identity': True,
             'reuse_stopped_tree_or_feedback': False, 'claim_exact_resume': False,
             'replace_original_status': False, 'status': 'recommendation_only_not_started_or_allocated'}
            for row in cases],
        'measurement_limits': [
            'The existing trustworthy stopped code can be classified as failed without another score. This is not the original normal terminal-code endpoint.',
            'Do not execute the malformed rejected action, replay the old conversation or relabel the old generation as normally completed.',
            'Do not reselect a candidate after seeing official failures. Any new model attempts are separate experimental results and keep prior costs.',
            'Large old source snapshots and archives were not re-extracted or rehashed; the prior validated recovery and round-trip evidence is reused. This audit verifies small metadata, original rejection events, the exact locked patch and its scoring identity.'
        ], 'new_API_calls': 0, 'new_model_calls': 0, 'new_Docker_operations': 0,
        'new_scoring_calls': 0, 'old_files_changed': False}
    read_bytes(__file__)
    OUT.mkdir(parents=True, exist_ok=False)
    for filename, value in (('summary.json', summary), ('sources.json', {'version': VERSION, 'sources': list(SOURCES.values())})):
        with (OUT / filename).open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps({'summary': str(OUT / 'summary.json'), 'known_stopped_code_failures': 2,
        'original_generation_unknowns_retained': 2, 'new_model_or_scoring_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
