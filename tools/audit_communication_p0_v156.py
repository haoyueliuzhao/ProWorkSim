"""Read retained zero-model controls and build a conservative P0 gate report.

No model, container, download, scorer, or training is invoked. Local fragment
counts are estimates and are never allocated proportionally from API usage.
"""
from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from proworksim import software_input_provenance_v156 as provenance
from proworksim.software_collaboration_observation_v141 import load_official_content_counter

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def collect_requests(folder, counter, tokenizer_id):
    records, estimates, costs = [], [], Counter()
    peer_estimate = retrieval_estimate = duplicate_estimate = sender_estimate = 0
    seen = set()
    paths = list(Path(folder).glob('*/provenance.json'))
    paths.sort(key=lambda p: read(p)['identity']['request_id'])
    for manifest in paths:
        directory = manifest.parent
        value = read(manifest)
        built = provenance.BuiltRequest((directory/'payload.json').read_bytes(), value)
        response = read(directory/'response.json')
        capture = {'request_id': value['identity']['request_id'],
                   'payload': ref(directory/'payload.json'), 'manifest': ref(manifest),
                   'exclusive_capture': True}
        records.append({'request': built, 'response': response, 'capture': capture})
        estimate = provenance.estimate_fragment_tokens(built, counter, tokenizer_id=tokenizer_id)
        estimates.append(estimate)
        span_by_id = {s['occurrence_id']: s for s in value['spans']}
        member, episode = value['identity']['member_id'], value['identity']['episode_id']
        for piece in estimate['pieces']:
            span = span_by_id[piece['occurrence_id']]
            source = span['source']
            count = piece['estimated_tokens']
            if source is None:
                continue
            parents = source.get('parent_source_ids', [])
            if source['category'] == 'Peer-message' or (
                    source['category'] == 'Retrieved' and source['origin_member_id'] != member
                    and any(':world-message:' in p for p in parents)):
                peer_estimate += count
            if source['category'] == 'Retrieved':
                retrieval_estimate += count
            material = next((p for p in parents if ':file-material:' in p), None)
            key = (episode, member, material or source['source_id'], span['payload_slice_sha256'])
            if key in seen:
                duplicate_estimate += count
            seen.add(key)
        usage = response.get('usage')
        if usage is not None:
            for name in ('input_tokens', 'output_tokens', 'total_tokens'):
                costs[name] += usage[name]
        original = directory/'response-original.json'
        if original.exists():
            body = read(original)
            for choice in body.get('choices', []):
                for call in choice.get('message', {}).get('tool_calls') or []:
                    function = call.get('function', {})
                    if function.get('name') == 'send_message':
                        try:
                            sent = json.loads(function['arguments'])['body']
                        except (KeyError, ValueError, TypeError):
                            continue
                        if isinstance(sent, str):
                            sender_estimate += counter(sent)
    groups = Counter()
    for estimate in estimates:
        groups.update(estimate['estimated_by_primary_category'])
    known = sum(groups.values())
    unknown = sum(e['unattributed_fragment_tokens_estimate'] for e in estimates)
    wire_bytes = sum(r['request'].manifest['payload_bytes'] for r in records)
    semantic_bytes = sum(r['request'].manifest['semantic_payload_bytes'] for r in records)
    semantic_known = sum(r['request'].manifest['semantic_attributed_payload_bytes'] for r in records)
    return records, estimates, {
        'requests': len(records), 'wire_bytes': wire_bytes,
        'semantic_payload_bytes': semantic_bytes, 'semantic_attributed_bytes': semantic_known,
        'semantic_byte_coverage': semantic_known/semantic_bytes if semantic_bytes else None,
        'local_estimated_source_coverage': known/(known+unknown) if known+unknown else None,
        'local_estimated_by_primary_category': dict(groups),
        'unattributed_fragment_tokens_estimate': unknown,
        'authoritative_scripted_usage': dict(costs),
        'analytical_subaccounts_NOT_added_to_team_total': {
            'known_direct_peer_and_message_pull_fragment_tokens_estimate': peer_estimate,
            'retrieved_fragment_tokens_estimate': retrieval_estimate,
            'repeated_source_fragment_tokens_estimate': duplicate_estimate,
            'sender_send_message_body_tokens_estimate': sender_estimate,
            'peer_origin_inside_mixed_summaries_or_composite_code': 'unidentified_not_proportionally_allocated',
            'duplicate_measure': 'episode+consumer+source_or_exact_file_material+literal_fragment_hash',
            'duplicate_is_automatically_waste': False},
        'local_token_estimates_are_not_API_token_decomposition': True,
        'source_records': [r['capture'] for r in records]}


def audit(sdk_summary, output, junit):
    sdk = read(sdk_summary)
    normal = next(c for c in sdk['controls'] if not c['exception_control'])
    exceptional = next(c for c in sdk['controls'] if c['exception_control'])
    manifest = ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    counter, tokenizer = load_official_content_counter(manifest, manifest_sha256=ref(manifest)['sha256'])
    cached = lru_cache(maxsize=65536)(counter)
    records, estimates, sources = collect_requests(normal['source_capture_directory'], cached, tokenizer['tokenizer_id'])
    ledger_path = Path(normal['source_capture_directory']).parent/'model-ledger/ledger.json'
    ledger = read(ledger_path)
    entries = [{'request_id': row['request_id'], 'status': 'settled', 'usage': row['usage']}
               for row in ledger['calls']]
    reconciled = provenance.reconcile_ledgers([r['response'] for r in records], entries)
    tree = ET.parse(junit)
    cases = tree.findall('.//testcase')
    failures = tree.findall('.//failure') + tree.findall('.//error')
    tests_pass = bool(cases) and not failures
    obs = normal['observation']
    gates = provenance.evaluate_g0(records, estimates, reconciled, other_gates={
        'G0-4': tests_pass and not obs['runtime_measurement_errors'] and
                  exceptional['observation']['completion_status'] == 'partial',
        'G0-5': tests_pass and sdk['passed'],
        'G0-6': tests_pass and sdk['passed']})
    sources['attributions'] = estimates
    write(output/'source-coverage.json', sources)
    write(output/'usage-reconciliation.json', reconciled)
    summary = {
        'version': 'v156-communication-pilot-p0-admission-r1',
        'status': 'P0_controls_complete_precision_gate_not_admitted',
        'P1_started': False, 'model_API_calls': 0, 'training_steps': 0,
        'P1_cash_budget_authorized': False, 'P1_start_authorized': False,
        'CPU_controls': {'cases': len(cases), 'failures': len(failures), 'passed': tests_pass,
                         'junit': ref(junit)},
        'actual_SDK_scripted_control': {'normal_requests': normal['scripted_requests'],
            'condenser_requests': normal['scripted_summaries'],
            'captured': normal['source_capture_completed'], 'pending': normal['source_capture_pending'],
            'observer_errors': obs['runtime_measurement_errors'],
            'test_states': obs['public_tests'], 'reviews': obs['review'],
            'source_presentations': obs['source_presentations'],
            'exception_control': {'requests': exceptional['scripted_requests'],
                'status': exceptional['observation']['completion_status'],
                'coverage': exceptional['observation']['coverage']},
            'other_observer_channels_not_declared_globally_complete':
                [k for k,v in obs['coverage'].items() if not v],
            'scope': 'CPU script through real SDK; no capability result or real provider token evidence'},
        'gates': gates,
        'cost_authority': 'Physical provider ledger, not logical observer or sum of analytic subaccounts',
        'no_provider_exact_source_claim': True,
        'remaining_experiment_gates': ['provider-compatible exact attribution evidence or explicit protocol revision',
            'independent gate review', 'P1 frozen native communication/budget/scorer deployment binding',
            'new P1 cash budget and explicit launch confirmation'],
        'references': {'SDK': ref(sdk_summary), 'SDK_ledger': ref(ledger_path),
            'tokenizer': ref(manifest), 'tokenizer_real_request_audit': ref(ROOT/'artifacts/software-benchmark-v156/tokenizer-audit-r1/summary.json'),
            'panel': ref(ROOT/'artifacts/software-benchmark-v156/communication-design-r1/approved-panel.json'),
            'source_coverage': ref(output/'source-coverage.json'),
            'usage_reconciliation': ref(output/'usage-reconciliation.json')},
    }
    write(output/'summary.json', summary)
    print(json.dumps({'status': summary['status'], 'CPU_cases': len(cases),
        'source_byte_coverage': sources['semantic_byte_coverage'],
        'local_token_estimate_coverage': sources['local_estimated_source_coverage'],
        'gates': gates['gates'], 'P1_started': False}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-summary', type=Path, default=ROOT/'artifacts/software-benchmark-v156/observer-sdk-r4/summary.json')
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/software-benchmark-v156/p0-admission-r1')
    parser.add_argument('--junit', type=Path, default=ROOT/'artifacts/software-benchmark-v156/p0-cpu-controls-r1/junit.xml')
    args = parser.parse_args()
    audit(args.sdk_summary, args.output, args.junit)
