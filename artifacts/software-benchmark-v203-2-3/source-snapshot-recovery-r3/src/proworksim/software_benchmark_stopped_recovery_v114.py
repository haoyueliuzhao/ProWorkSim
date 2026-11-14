"""Lock the only archived stopped worktree as a separate supplemental endpoint.

The original generation remains technical_unknown. This never constructs a
missing tool action, reruns a model, selects a patch by score, or edits old files.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_episode_v066 import archive_bundle, controller_ref
from .software_benchmark_native_artifact_v054 import _native_tree
from .software_benchmark_snapshot_recovery_v061 import export_utf8_patch

ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT/'runs/software-benchmark-v111/aligned-interface-r1'
OUTPUT = ROOT/'runs/software-benchmark-v114/stopped-code-recovery-r1'
VERSION = 'v114-unique-stopped-worktree-supplemental-recovery-r1'
ENDPOINT = 'recovered_stopped_code'
TASKS = {7244: 'matplotlib__matplotlib-22865', 7251: 'pydata__xarray-4687'}
ERRORS = {7244: 'Invalid control character', 7251: 'Unterminated string'}


def stream_reference(path):
    path = Path(path).resolve()
    count, digest = 0, hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024**2):
            count += len(chunk)
            digest.update(chunk)
    return {'path': str(path), 'sha256': digest.hexdigest(), 'bytes': count}


def read_ref(ref):
    return json.loads(checked(ref).read_bytes())


def rejected_action_evidence(folder, response):
    conversations = list((folder/'controller-output/native-conversation').iterdir())
    if len(conversations) != 1:
        raise ValueError('The final rejected call requires one original conversation')
    paths = sorted((conversations[0]/'events').glob('event-*.json'))[-3:]
    if len(paths) != 3:
        raise ValueError('The original action/error/crash tail is incomplete')
    refs = [reference(path) for path in paths]
    action, error, crash = [read_ref(ref) for ref in refs]
    call = response['choices'][0]['message']['tool_calls'][0]
    if (action.get('kind') != 'ActionEvent' or action.get('action') is not None
            or action.get('tool_call_id') != call['id'] or action.get('tool_name') != call['function']['name']
            or action.get('llm_response_id') != response['id']
            or error.get('kind') != 'AgentErrorEvent' or error.get('tool_call_id') != call['id']
            or error.get('tool_name') != call['function']['name']
            or not error.get('error', '').startswith('Error validating tool')
            or crash.get('kind') != 'ConversationErrorEvent'):
        raise ValueError('The final malformed call is not proven rejected without an action')
    rpc = folder/'controller-output/native-rpc-raw.jsonl'
    with rpc.open() as stream:
        last = None
        for line in stream:
            if line.strip():
                last = line
    value = json.loads(last)['response']['observation'] if last is not None else {}
    if value.get('timeout') is not False or type(value.get('exit_code')) is not int:
        raise ValueError('The last actual native command did not return a complete result')
    return {'final_action_error_crash_events': refs, 'actual_rpc': reference(rpc),
            'bad_tool_call_id': call['id'], 'bad_call_had_no_action': True,
            'last_actual_command_exit_code': value['exit_code'], 'bad_action_replayed': False}


def validate_records(index, row, result, child, interrupted, writers, quiet, baseline_provenance):
    """Only a frozen, fully stopped original attempt can supply this endpoint."""
    if (index not in TASKS or row.get('instance_id') != TASKS[index] or row.get('slot_index') != index
            or row.get('arm') != 'REF' or result.get('status') != 'technical_unknown'
            or result.get('candidate_lock') is not None or result.get('failure_scope') != 'local'
            or result.get('batch_stop_required') is not False
            or result.get('model_bridge_thread_finished') is not True
            or any(result.get(key) != row.get(key) for key in
                   ('slot_id', 'instance_id', 'configuration', 'condition_id', 'arm', 'seed'))
            or child.get('slot_id') != row['slot_id'] or child.get('status') != 'technical_unknown'
            or child.get('hidden_feedback_received') is not False):
        raise ValueError('Only these original unclosed REF attempts can supply a supplemental tree')
    if (child.get('error', {}).get('type') != 'ConversationRunError'
            or ERRORS[index] not in child.get('error', {}).get('message', '')
            or 'software_benchmark_deepseek_interfaces_v055.py' not in child.get('traceback', '')
            or '_canonical_call' not in child.get('traceback', '')):
        raise ValueError('The original failure is not the audited malformed-history crash')
    for ledger in (result.get('ledger', {}), child.get('ledger', {})):
        if (ledger.get('inflight') is not None or ledger.get('uncertain_reserved_tokens') != 0
                or ledger.get('complete_actual_tokens') != ledger.get('known_actual_tokens')
                or type(ledger.get('known_actual_tokens')) is not int
                or not 0 < ledger['known_actual_tokens'] <= 5_000_000
                or not ledger.get('calls') or ledger.get('attempts') != len(ledger['calls'])):
            raise ValueError('A stopped-worktree recovery cannot erase uncertain model usage')
    if any(result['ledger'][key] != child['ledger'][key] for key in
           ('attempts', 'decisions', 'known_actual_tokens', 'complete_actual_tokens')):
        raise ValueError('Host and original controller accounting disagree')
    if (writers.get('all_quiet') is not True or writers.get('errors') != []
            or writers.get('create_result_unknown_roles') != []
            or interrupted.get('writer_quiescence') != writers
            or interrupted.get('official_final_candidate') is not False
            or interrupted.get('scoring_authorized_by_this_record') is not False
            or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or quiet.get('all_owned_objects_removed') is not True
            or quiet.get('retained_objects') != [] or quiet.get('create_result_unknown') is not False):
        raise ValueError('The original intermediate archive needs complete writer and cleanup proof')
    stopped = writers.get('writers', [])
    if (len(stopped) != 2 or {value['role'] for value in stopped} != {'actor', 'controller'}
            or any(value.get('state', {}).get('Running') is not False
                   or value['state'].get('Pid') != 0 or value['state'].get('Status') != 'exited'
                   or value.get('claim') != quiet['claims'][value['role']] for value in stopped)):
        raise ValueError('Both original namespace writers must be stopped under the same claims')
    archive = interrupted['archive']
    actor = next(value for value in stopped if value['role'] == 'actor')
    before = baseline_provenance.get('archive', {})
    if (archive.get('role') != 'actor' or archive.get('container_path') != '/testbed'
            or archive.get('container_id') != actor['container_id']
            or archive.get('container_claim') != actor['claim']
            or archive.get('owned_volume_claim') != quiet['claims']['volume']
            or any(before.get(key) != archive.get(key) for key in
                   ('container_id', 'container_claim', 'owned_volume_claim', 'container_path'))):
        raise ValueError('The sole interrupted archive must belong to the same original baseline actor')
    return True


def recover(index):
    if os.getuid() == 0 or os.geteuid() == 0 or index not in TASKS:
        raise PermissionError('Only ordinary-user offline recovery of the two declared snapshots is allowed')
    folder, output = BATCH/'episodes'/str(index), OUTPUT/str(index)
    if output.exists():
        raise FileExistsError('A supplemental candidate has already been selected; never overwrite or reselect it')
    plan_ref = reference(BATCH/'execution-plan-v113.json')
    rows = [row for row in read_ref(plan_ref)['rows'] if row['slot_index'] == index]
    if len(rows) != 1:
        raise ValueError('The original immutable panel row is missing')
    row = rows[0]
    refs = {name: reference(folder/path) for name, path in {
        'original_result': 'result.json', 'writer_quiescence': 'writer-quiescence.json',
        'quiescence': 'quiescence.json', 'baseline_provenance': 'baseline-snapshot-provenance.json'}.items()}
    result = read_ref(refs['original_result'])
    refs.update(controller_result=result['controller_result'], interrupted=result['interrupted_worktree'])
    child, interrupted = read_ref(refs['controller_result']), read_ref(refs['interrupted'])
    writers, quiet, provenance = (read_ref(refs[name]) for name in
                                   ('writer_quiescence', 'quiescence', 'baseline_provenance'))
    validate_records(index, row, result, child, interrupted, writers, quiet, provenance)
    archive = interrupted['archive']['archive']
    if Path(archive['path']).resolve() != (folder/'interrupted-worktree.tar').resolve():
        raise ValueError('The recovery cannot substitute another workspace/archive')
    if (stream_reference(archive['path']) != archive
            or interrupted['archive']['stream_sha256'] != archive['sha256']
            or interrupted['archive']['bytes'] != archive['bytes']):
        raise ValueError('The uniquely stopped archive no longer matches its original stream receipt')
    baseline_ref = provenance['snapshot']
    if Path(baseline_ref['path']).resolve() != (folder/'baseline-snapshot.json').resolve():
        raise ValueError('The recovery baseline changed')
    baseline = read_ref(baseline_ref)
    if baseline.get('truncated') is not False or _native_tree(baseline) != baseline.get('tree'):
        raise ValueError('The original baseline is incomplete or internally inconsistent')
    last = child['ledger']['calls'][-1]
    last_response = controller_ref(last['response'], folder/'controller-output')
    raw = read_ref(last_response)
    calls = raw['choices'][0]['message'].get('tool_calls', [])
    if len(calls) != 1:
        raise ValueError('The audited final rejected response must contain one original tool call')
    try:
        json.loads(calls[0]['function']['arguments'])
    except json.JSONDecodeError:
        pass
    else:
        raise ValueError('The final malformed arguments no longer match the audited failure')
    rejection = rejected_action_evidence(folder, raw)
    refs.update(stopped_archive=archive, baseline=baseline_ref, final_provider_response=last_response)
    # The old record stays non-final. This new selection has one fixed rule and
    # never consults score results, hidden tests, candidate alternatives or tools.
    candidate = archive_bundle(archive['path'], gitlinks=baseline.get('gitlinks', []))
    output.mkdir(parents=True, exist_ok=False)
    source = write_new(output/'recovery-source.json', {
        'version': VERSION, 'slot': row, 'plan': plan_ref, 'original_evidence': refs,
        'source_module': reference(__file__), 'original_generation_status': 'technical_unknown',
        'original_official_final_candidate': False, 'endpoint': ENDPOINT,
        'selection_rule': 'The sole complete original archive after both namespace writers stopped',
        'model_calls': 0, 'tool_calls': 0, 'scoring_calls': 0,
        'original_bad_tool_call_executed': False, 'old_result_changed': False,
        'rejected_action_evidence': rejection})
    candidate_ref = write_new(output/'candidate-bundle.json', candidate)
    patch = export_utf8_patch(baseline, candidate, output/'candidate.patch', policy=candidate['file_policy'])
    if patch['candidate_tree_sha256'] != candidate['tree']['tree_sha256']:
        raise ValueError('The exported candidate differs from the sole stopped tree')
    lock = write_new(output/'lock.json', {
        'version': VERSION, 'endpoint': ENDPOINT, 'slot': row, 'baseline': baseline_ref,
        'candidate': candidate_ref, 'patch_receipt': patch, 'tree_sha256': candidate['tree']['tree_sha256'],
        'quiescence': refs['writer_quiescence'], 'recovery_source': source,
        'lock_before_grading': True, 'candidate_selection_after_scoring': False,
        'original_generation_status': 'technical_unknown', 'replaces_original_endpoint': False,
        'model_calls': 0, 'tool_calls': 0, 'grading_calls': 0})
    return write_new(output/'recovery-result.json', {
        'version': VERSION, 'status': 'supplemental_candidate_locked', 'endpoint': ENDPOINT,
        'slot_id': row['slot_id'], 'instance_id': row['instance_id'], 'slot_index': index,
        'condition_id': row['condition_id'], 'configuration': row['configuration'],
        'candidate_lock': lock, 'patch': patch['patch'], 'source': source,
        'original_result': refs['original_result'], 'original_generation_status': 'technical_unknown',
        'replaces_original_endpoint': False, 'model_resampling': False, 'bad_action_replayed': False,
        'model_calls': 0, 'scoring_calls': 0, 'round_trip_verified': True,
        'candidate_tree_sha256': candidate['tree']['tree_sha256'],
        'actual_original_tokens': child['ledger']['known_actual_tokens']})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot-index', type=int, choices=sorted(TASKS), required=True)
    args = parser.parse_args()
    print(json.dumps(recover(args.slot_index), ensure_ascii=False))
