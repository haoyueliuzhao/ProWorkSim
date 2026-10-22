"""Archive only 261 declared closed historical text files, preserving r1 codec.

The frozen candidate file contains project-relative exact paths. Each admitted
path has a closed supervisor, no current execution reference and no observed
same-user process use. Gzip content readback precedes raw removal; the original
historical outcomes and reference hashes retain their meaning after restore.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import importlib.util
import json
import os
from pathlib import Path
import shutil
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT / 'runs/history-text-archive-v055-r2'
VERSION = 'v055-closed-history-text-lossless-archive-r2'
CANDIDATES = ROOT / 'artifacts/software-benchmark-v055/history-text-archive-r2/candidates.json'
CANDIDATES_SHA = '3543694f4a8f234bfea9716be7b1ccc87a1ee99b10c724d106641e935f2c9855'
CODEC = ROOT / 'tools/archive_v050_history_r1.py'
spec = importlib.util.spec_from_file_location('_history_r1_codec_private', CODEC)
codec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codec)
SELECTED = []


def candidates():
    if codec.digest_path(CANDIDATES)['sha256'] != CANDIDATES_SHA:
        raise ValueError('Fixed historical candidate list changed')
    value = json.loads(CANDIDATES.read_bytes())
    paths = [ROOT / p for p in value['paths']]
    if len(paths) != len(set(paths)) or len(paths) != 261:
        raise ValueError('Only the fixed 261 distinct paths are in scope')
    for path in paths:
        if not path.is_relative_to(ROOT / 'runs') or '..' in path.parts:
            raise ValueError('Candidate escaped the project historical tree')
        if path.name not in {'runtime.json', 'experience.json', 'experience.jsonl', 'entries.json', 'admission.json'}:
            raise ValueError('Candidate is not a declared historical text')
    return paths


def process_use(paths):
    roots = {str(ROOT / 'runs' / p.relative_to(ROOT / 'runs').parts[0]) for p in paths}
    targets = set(map(str, paths))
    matches, denied = [], 0
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            command = (entry / 'cmdline').read_bytes()
            for root in roots:
                if root.encode() in command:
                    matches.append({'pid': int(entry.name), 'kind': 'command_root', 'root': root})
            for fd in (entry / 'fd').iterdir():
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if target in targets:
                    matches.append({'pid': int(entry.name), 'kind': 'open_candidate', 'path': target})
        except OSError:
            denied += 1
    return {'matches': matches, 'same_uid_proc_denied': denied,
            'scope': 'same_uid_observable_proc_plus_sealed_supervisor_closure_not_universal_other_user_proof'}


def require_quiet():
    result = process_use(SELECTED)
    if result['matches']:
        raise RuntimeError('A selected historical path may be in use: ' + json.dumps(result['matches']))
    return result


def current_seeds():
    old = json.loads((ROOT / 'runs/software-benchmark-v054/formal-queue-r1/state.json').read_bytes())
    new = json.loads((ROOT / 'runs/software-benchmark-v055/queue-r1/state.json').read_bytes())
    return {
        'qwen': {k: old[k] for k in ('bindings', 'kernel_router', 'resource_recovery',
                 'resource_planning_revision', 'ref_handoff_host', 'three_volume_host') if k in old},
        'deepseek': {k: new[k] for k in ('plan', 'active_host_revision', 'native_solver_activation',
                     'all_arm_budget_activation') if k in new},
    }


def strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, str):
        yield value


def reference_audit(paths):
    """Walk explicit current metadata references, never whole filesystem/data."""
    seeds = current_seeds()
    pending = deque()
    targets = set(map(str, paths))
    seen, inspected, hits, exclusions = set(), [], set(), []
    def enqueue(value):
        for text in strings(value):
            if text.startswith(str(ROOT) + '/'):
                path = Path(text)
            elif text.startswith(('runs/', 'artifacts/', 'src/', 'tools/', 'config/')):
                path = ROOT / text
            else:
                continue
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            # Check ancestors too: a current dependency on an old directory is a use.
            for target in targets:
                if key == target or target.startswith(key.rstrip('/') + '/'):
                    hits.add(target)
            if path.suffix == '.json':
                pending.append(path)

    enqueue(seeds)
    peak_pending_paths = len(pending)
    while pending:
        path = pending.popleft()
        key = str(path)
        if not path.is_file():
            continue
        relative = str(path.relative_to(ROOT))
        if (any(part in path.parts for part in ('workers', 'slots', 'rootfs', 'episode', 'model', 'models', 'checkpoints'))
                or path.name in ('public-tasks.json', 'trusted-evaluation.json')
                or relative.startswith(('runs/software-learning-', 'runs/software-organization-'))):
            exclusions.append({'path': key, 'reason': 'model_task_or_historical_payload_not_host_metadata'})
            continue
        if path.stat().st_size > 16 * 1024**2:
            exclusions.append({'path': key, 'reason': 'over_16MiB_host_metadata_bound'})
            continue
        try:
            body = path.read_bytes()
            parsed = json.loads(body)
        except (OSError, ValueError) as error:
            exclusions.append({'path': key, 'reason': 'unreadable_or_not_json', 'error': type(error).__name__})
            continue
        inspected.append(key)
        enqueue(parsed)
        peak_pending_paths = max(peak_pending_paths, len(pending))
        del body, parsed
    return {'version': VERSION + '-current-reference-audit', 'created_unix': time.time(),
            'current_seeds': seeds, 'queue_exhausted': True, 'inspected_metadata_count': len(inspected),
            'distinct_reference_count': len(seen), 'candidate_matches': sorted(hits),
            'inspected_paths': inspected, 'excluded_paths': exclusions,
            'pending_queue_payload': 'deduplicated_paths_only_not_parsed_documents',
            'peak_pending_paths': peak_pending_paths,
            'exclusions_by_reason': dict(Counter(row['reason'] for row in exclusions)),
            'model_or_environment_payload_read': False}


def fingerprint():
    paths = candidates()
    OUT.mkdir(exist_ok=False)
    audit = reference_audit(paths)
    audit_ref = codec.put(OUT / 'current-reference-audit.json', audit)
    use = process_use(paths)
    rejected, rows, supervisors = [], [], {}
    hits = set(audit['candidate_matches'])
    for path in paths:
        reason = None
        root = ROOT / 'runs' / path.relative_to(ROOT / 'runs').parts[0]
        if str(path) in hits:
            reason = 'referenced_by_current_execution_metadata'
        elif any(row.get('path') == str(path) or row.get('root') == str(root) for row in use['matches']):
            reason = 'observed_process_use'
        try:
            if reason is not None:
                raise ValueError(reason)
            if root not in supervisors:
                p = root / 'supervisor.json'
                value = json.loads(p.read_bytes())
                if value.get('status') not in ('complete', 'closed_with_unknowns') or not value.get('ended_at'):
                    raise ValueError('missing_closed_supervisor')
                supervisors[root] = {'reference': codec.digest_path(p), 'status': value['status'], 'ended_at': value['ended_at']}
            before = codec.identity(path)
            if path.with_name(path.name + '.archive.json').exists():
                raise ValueError('prior_archive_marker_exists')
            ref = codec.digest_path(path)
            if codec.identity(path) != before:
                raise ValueError('candidate_changed_during_fingerprint')
            rows.append({'original': ref, 'identity': before, 'supervisor': supervisors[root]})
        except (ValueError, OSError) as error:
            rejected.append({'path': str(path), 'reason': str(error), 'type': type(error).__name__})
    groups = {}
    for row in rows:
        groups.setdefault(row['original']['sha256'], []).append(row['original']['path'])
    return codec.put(OUT / 'plan.json', {'version': VERSION, 'created_unix': time.time(),
        'source': codec.digest_path(__file__), 'codec_source': codec.digest_path(CODEC),
        'candidate_manifest': codec.digest_path(CANDIDATES), 'candidate_count': len(paths),
        'current_reference_audit': audit_ref, 'same_user_process_observation': use,
        'allowlist': rows, 'excluded_candidates': rejected, 'content_groups': groups,
        'codec': 'gzip', 'compression_level': 1, 'default_restore_root': str(OUT / 'restored'),
        'remove_raw_only_after_full_decompression_sha256_verification': True,
        'historical_results_unchanged': True,
        'required_resources': {'CPUQuota': '200%', 'MemoryMax': '2G', 'IOWeight': 10, 'Nice': 10,
                               'IOSchedulingClass': 'idle'}})


def configure(plan_ref):
    global SELECTED
    plan = codec.load_ref(plan_ref)
    if (plan['version'] != VERSION or plan['source'] != codec.digest_path(__file__)
            or plan['codec_source'] != codec.digest_path(CODEC)
            or plan['candidate_manifest'] != codec.digest_path(CANDIDATES)):
        raise ValueError('Archive source, codec or frozen candidate manifest changed')
    allowed = set(candidates())
    SELECTED = [Path(row['original']['path']) for row in plan['allowlist']]
    if len(SELECTED) != len(set(SELECTED)) or not set(SELECTED) <= allowed:
        raise ValueError('Plan escaped the fixed candidate set')
    codec.ROOT, codec.OUT, codec.VERSION = ROOT, OUT, VERSION
    codec.ALLOWLIST, codec.no_candidate_process_use = SELECTED, require_quiet
    codec.__file__ = __file__  # Private module only; markers name the r2 restore entry.
    return plan


def archive(plan_ref):
    plan = configure(plan_ref)
    audit = codec.load_ref(plan['current_reference_audit'])
    if not audit['queue_exhausted'] or current_seeds() != audit['current_seeds']:
        raise ValueError('Current execution revision changed after reference exclusion')
    # A small worst-case archive allocation cannot consume the experiment reserve.
    if shutil.disk_usage(OUT).free < sum(row['identity']['allocated_bytes'] for row in plan['allowlist']) + 128 * 1024**3:
        raise ValueError('Preserve at least 128 GiB while creating historical archives')
    result_ref = codec.archive(plan_ref)
    result = codec.load_ref(result_ref)
    compressed_allocated = sum(Path(row['archive']['path']).stat().st_blocks * 512 for row in result['objects'])
    return codec.put(OUT / 'summary.json', {'version': VERSION, 'plan': plan_ref, 'result': result_ref,
        'finished_unix': time.time(), 'candidate_count': plan['candidate_count'],
        'archived_paths': len(result['removed_paths']), 'excluded_candidates': plan['excluded_candidates'],
        'failures': result['failures'], 'unique_archive_objects': len(result['objects']),
        'source_allocated_bytes': result['released_raw_allocated_bytes'],
        'compressed_allocated_bytes': compressed_allocated,
        'net_payload_reclaimed_bytes': result['released_raw_allocated_bytes'] - compressed_allocated,
        'small_sidecar_and_receipt_bytes_not_subtracted': True, 'real_model_calls': 0,
        'historical_outcomes_changed': False, 'old_r1_sources_and_archives_changed': False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='operation', required=True)
    subs.add_parser('fingerprint')
    for operation in ('archive', 'restore'):
        p = subs.add_parser(operation)
        p.add_argument('--plan', type=Path, required=True)
        p.add_argument('--sha256', required=True)
        if operation == 'restore':
            p.add_argument('--destination')
            p.add_argument('--original-paths', action='store_true')
            p.add_argument('--path')
    args = parser.parse_args()
    if args.operation == 'fingerprint':
        print(json.dumps(fingerprint()))
        return
    ref = codec.digest_path(args.plan)
    if ref['sha256'] != args.sha256:
        raise ValueError('Plan seal changed')
    if args.operation == 'archive':
        print(json.dumps(archive(ref)))
    else:
        configure(ref)
        codec.restore(ref, destination=args.destination, original_paths=args.original_paths, selected=args.path)


if __name__ == '__main__':
    main()
