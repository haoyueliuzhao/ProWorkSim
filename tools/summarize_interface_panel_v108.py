"""Report the v108 manager while retaining v106 scoring and v105 task accounting."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location('v106_metrics_source',
    Path(__file__).with_name('summarize_interface_panel_v106.py'))
previous = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(previous)
PANEL, BATCH = previous.PANEL, previous.BATCH


def run(panel_path=PANEL, batch=BATCH, output=None):
    panel = previous.read(panel_path)
    candidates = [batch/'api-coordinator-v108'/name for name in ('progress.json', 'run-summary.json')]
    present = [path for path in candidates if path.exists()]
    latest = max(present, key=lambda path: path.stat().st_mtime_ns) if present else None
    coordinator = previous.read(latest) if latest else {}
    calls, snapshot = previous.ledger_snapshot(batch/'api-ledger.sqlite')
    summary, rows = previous.analyze(panel, calls, snapshot, batch, coordinator)
    summary.update(version='v108-original-43-plus-57-panel-summary-r1',
        panel=previous.ref(panel_path), coordinator_source=previous.ref(latest) if latest else None,
        official_scoring_and_usage_validation_source=previous.ref(previous.__file__),
        previous_lifecycle_history_overwritten=False)
    output = output or batch/'reporting-v108'
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary.json', summary), ('per-task.json', rows)]:
        path = output/name
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(path)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel', type=Path, default=PANEL)
    parser.add_argument('--batch-root', type=Path, default=BATCH)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.panel, args.batch_root, args.output), ensure_ascii=False))
