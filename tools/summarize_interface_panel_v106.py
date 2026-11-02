"""Read the v106 deployment lifecycle with the unchanged v105 panel and ledger."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace

_spec = importlib.util.spec_from_file_location('v105_metrics_source',
    Path(__file__).with_name('summarize_interface_panel_v105.py'))
_previous = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_previous)
_namespace = clone_namespace(_previous)
read, ref, bound = _previous.read, _previous.ref, _previous.bound
PANEL, BATCH = _previous.PANEL, _previous.BATCH
ledger_snapshot = _previous.ledger_snapshot


def official_score(folder, row):
    paths = {name: folder / (name + '.json') for name in ('request', 'receipt', 'completion', 'quiescence')}
    if not paths['receipt'].exists():
        return {'resolved': None, 'state': 'not_scored'}
    receipt = read(paths['receipt'])
    if receipt.get('status') != 'official_report':
        return {'resolved': None, 'state': 'technical_unknown', 'receipt': ref(paths['receipt'])}
    if not all(p.exists() for p in paths.values()):
        return {'resolved': None, 'state': 'awaiting_scoring_closeout', 'receipt': ref(paths['receipt'])}
    request, completed, quiet = (read(paths[k]) for k in ('request', 'completion', 'quiescence'))
    identity = bound(receipt['identity'])
    report = receipt['official_result'][1][row['instance_id']]
    candidate = bound(request['candidate_lock'])
    empty = candidate.get('patch_receipt', {}).get('patch', {}).get('bytes') == 0
    if (any(receipt.get(k) != row[k] for k in ('slot_id', 'instance_id', 'condition_id'))
            or any(request.get(k) != row[k] for k in ('slot_id', 'instance_id'))
            or identity.get('condition_id') != row['condition_id']
            or identity.get('request') != ref(paths['request'])
            or any(identity.get(k) != request.get(k) for k in ('slot_id', 'configuration', 'candidate_lock', 'plan', 'scorer_manifest'))
            or type(receipt.get('resolved')) is not bool or report.get('resolved') is not receipt['resolved']
            or report.get('infra_failure', False)
            or not (report.get('patch_successfully_applied') is True or empty and receipt['resolved'] is False)
            or receipt.get('candidate_changed') is not False or receipt.get('actor_feedback') is not False):
        raise ValueError('Score is not bound to this exact candidate and planned attempt')
    if (completed.get('returncode') != 0 or quiet.get('quiescent') is not True
            or quiet.get('cleanup_errors') != [] or quiet.get('create_result_unknown') is not False):
        return {'resolved': None, 'state': 'awaiting_scoring_closeout', 'receipt': ref(paths['receipt'])}
    return {'resolved': receipt['resolved'], 'state': 'resolved' if receipt['resolved'] else 'unresolved',
            'receipt': ref(paths['receipt']), 'candidate_lock': request['candidate_lock']}


_namespace['official_score'] = official_score
analyze = _namespace['analyze']


def run(panel_path=PANEL, batch=BATCH, output=None):
    panel = read(panel_path)
    candidates = [batch / 'api-coordinator-v106' / name for name in ('progress.json', 'run-summary.json')]
    present = [p for p in candidates if p.exists()]
    latest = max(present, key=lambda p: p.stat().st_mtime_ns) if present else None
    coordinator = read(latest) if latest else {}
    calls, snapshot = ledger_snapshot(batch / 'api-ledger.sqlite')
    summary, rows = analyze(panel, calls, snapshot, batch, coordinator)
    summary.update(version='v106-unchanged-panel-ledger-deployment-summary-r1',
                   panel=ref(panel_path), coordinator_source=ref(latest) if latest else None,
                   original_v105_diagnostic_history_overwritten=False)
    output = output or batch / 'reporting-v106'
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary.json', summary), ('per-task.json', rows)]:
        path = output / name
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(path)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel', type=Path, default=PANEL)
    parser.add_argument('--batch-root', type=Path, default=BATCH)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.panel, args.batch_root, args.output), ensure_ascii=False))
