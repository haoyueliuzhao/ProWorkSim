"""Archive the five recovery attempts and a separately labelled logical-slot view."""

import argparse
import copy
from pathlib import Path
import signal
import time

from proworksim.storage import read_json
from scripts import recover_collaboration_carrier_v026 as recovery
from scripts import report_collaboration_carrier_v026 as reporting
from scripts.evaluate_work_v022 import reference, write


def save(report, stem, prefix=''):
    write(stem.with_suffix('.json'), report)
    stem.with_suffix('.md').write_text(prefix+reporting.markdown(report))


def finish(plan_path, root, output):
    error = None
    try:
        recovery.run(plan_path, root)
    except BaseException as caught:
        error = {'type': type(caught).__name__, 'message': str(caught)}
    report = reporting.load_run(root, require_terminal=True)
    report['recovery_supervisor_error'] = error
    report['scope'] = 'Five predeclared recovery attempts only; the original interruption remains archived.'
    save(report, output/'collaboration-v026-c1-r3', '# 资源恢复：5次独立尝试\n\n原中断与未启动状态在R2报告中保留；本文件只记录预声明恢复尝试。\n\n')
    plan = read_json(plan_path)
    parent_root = Path(plan['parent_run'])
    guard_root = Path(plan['parent_resource_controller'])
    while time.time()<plan['wall_deadline_at']:
        parent = read_json(parent_root/'supervisor.json')
        guard = read_json(guard_root/'state.json')
        if parent.get('status') in reporting.TERMINAL and guard.get('phase') in {'complete', 'failed'}:
            break
        time.sleep(5)
    else:
        raise RuntimeError('Recovery report saved; parent archive did not close before final deadline')
    base, catalog, parent, workers, episodes, sources = reporting.load_run(parent_root, require_terminal=True, include_inputs=True)
    _, _, child, child_workers, child_episodes, child_sources = reporting.load_run(root, require_terminal=True, include_inputs=True)
    original = reporting.summarize(base, catalog, parent, workers, episodes, sources=sources)
    joined_workers = {'original-'+k:v for k,v in workers.items()} | {'recovery-'+k:v for k,v in child_workers.items()}
    joined_episodes = copy.deepcopy(episodes)
    for slot in plan['slots']:
        joined_episodes[slot['slot_id']] = child_episodes[slot['slot_id']]
    derived = {**parent, 'ended_at': max(parent['ended_at'], child['ended_at'])}
    result = reporting.summarize(base, catalog, derived, joined_workers, joined_episodes,
              sources={'original': sources, 'recovery': child_sources, 'recovery_plan': reference(plan_path)})
    result.update(run_status='recovered_descriptive_view', terminal=True,
                  scope='Derived sixteen-logical-slot description after the declared resource recovery. Original interrupted attempt is retained and this does not replace the original primary archive.',
                  original_attempt_result=original['overall'], recovery_attempt_result=report['overall'],
                  retry_of_interrupted_slot=plan['slots'][0]['slot_id'],
                  actual_started_attempts=(16-original['overall']['not_started'])+(5-report['overall']['not_started']))
    save(result, output/'collaboration-v026-c1-recovered',
         '# 资源恢复后的16个逻辑槽描述性汇总\n\n本表按事前声明的5个恢复槽合并结果，不覆盖R2原始报告。原中断仍是一次未知尝试；恢复属于新尝试，全部成本计入。不能将此表伪称为无中断的原16次运行。\n\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    finish(args.plan.resolve(), args.run_root.resolve(), args.output.resolve())
