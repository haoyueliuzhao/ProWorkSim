"""Read original v029 artifacts; never infer model success from a queue or CPU test."""

import argparse
from pathlib import Path
import time

from proworksim.storage import read_json
from scripts.run_ne_v021 import read, reference, write

VERSION = 'software-allocation-report-v0.29'


def outcomes(folder):
    rows = []
    spec = read(folder / 'window-spec.json') or {}
    for index, slot in enumerate(spec.get('slots', [])):
        root = folder / f'slot-{index}'
        entry = read(root / 'entry.json')
        assessment = read(root / 'assessment.json')
        mapping = read(root / 'mapping.json')
        rows.append({**slot, 'status': ('closed' if entry['reward']['eligible'] else 'technical_unknown')
                     if entry else 'not_closed', 'reward': entry.get('reward') if entry else None,
                     'assessment': assessment, 'mapping': mapping,
                     'original_trajectory_directory': str(root),
                     'entry_reference': reference(root / 'entry.json') if entry else None})
    return rows


def report(run_root, output_dir):
    root, output = Path(run_root).resolve(), Path(output_dir).resolve()
    plan, supervisor = read_json(root / 'plan.json'), read_json(root / 'supervisor.json')
    support = root / 'support/actual'
    gate = read(support / 'support-gate.json')
    allocation = read(support / 'allocation-plan.json')
    selection = read(root / 'selection.json')
    workers = {}
    for name, state in supervisor['states'].items():
        actual = root / name / 'actual'
        workers[name] = {'state': state, 'report': read(actual / 'report.json'),
                         'update': read(actual / 'update/report.json'),
                         'training_consumption': read(actual / 'update/software-consumption.json'),
                         'development_receipt': read(actual / 'development-receipt.json'),
                         'confirmation': outcomes(actual / 'confirmation'),
                         'successor': outcomes(actual / 'successor'),
                         'development': outcomes(actual / 'development')}
    summary = {'version': VERSION, 'generated_at': time.time(), 'run_root': str(root),
               'plan_reference': reference(root / 'plan.json'), 'plan': plan, 'supervisor': supervisor,
               'support': outcomes(support / 'collection'), 'support_gate': gate,
               'allocation_plan': allocation, 'selection': selection, 'workers': workers,
               'scope': 'One training task, one contribution-development task, one independent confirmation task. Repeated seeds are not independent projects. CPU controls, real work and parameter-update effects remain separate.'}
    means = {}
    for method in ('B', 'G', 'I'):
        rows = workers.get('formal-' + method, {}).get('confirmation', [])
        if len(rows) == 4 and all(row['reward'] and row['reward']['eligible'] for row in rows):
            means[method] = sum(row['reward']['reward'] for row in rows) / 4
    summary['independent_confirmation'] = {'means': means, 'I_minus_B': means['I'] - means['B']
        if {'I', 'B'} <= means.keys() else None, 'I_minus_G': means['I'] - means['G']
        if {'I', 'G'} <= means.keys() else None, 'independent_project_count': 1}
    output.mkdir(parents=True, exist_ok=True)
    write(output / 'software-allocation-v029.json', summary)
    text = [
        '# v0.29 新来源经验分配实验记录', '',
        f'- 运行状态：`{supervisor["status"]}`；当前阶段：`{supervisor["stage"]}`。',
        f'- 固定源码：`{plan["source"]["code_commit"]}`；原始目录：`{root}`。',
        '- 三个来源用途固定：sqlparse训练、schema贡献开发、TextFSM独立确认。',
        '- 首窗8槽同一精确情境、同一参数版本、member_a先手、最低类频数2。保留所有失败、未映射与技术未知。',
        '- 没有可配置支持时停止，不补采、不改分母、不追加无对照基础更新。',
        '', '## 当前策略原始窗口', '',
        '| 槽位 | 状态 | R | 路线 |', '|---|---|---:|---|',
    ]
    by_id = {row['slot_id']: row for row in summary['support']}
    for slot in plan['inventories']['support']:
        row = by_id.get(slot['slot_id'], {})
        reward, mapping = row.get('reward') or {}, row.get('mapping') or {}
        text.append(f'| {slot["slot_id"]} | {row.get("status", "not_started")} | {reward.get("reward")} | {mapping.get("class_id", mapping.get("status", "—"))} |')
    if gate:
        text += ['', f'支持门状态：`{gate["status"]}`。选定成员块：`{gate.get("eligible_blocks", [])}`。', '',
                 '| 成员 | M | n_z | n+ | v | b |', '|---|---:|---|---:|---:|---|']
        for value in (gate.get('supports_by_xi') or {}).values():
            for member, block in value['blocks'].items():
                text.append(f'| {member} | {block["M"]} | {block["n_by_class"]} | {block["n_positive"]} | {block["v"]} | {block["b"]} |')
    text += ['', '## 实际更新与工作执行', '',
             '| Worker | 状态 | GPU小时 | actor/critic新步数 |', '|---|---|---:|---|']
    for name, value in workers.items():
        state, result = value['state'], value['report'] or {}
        text.append(f'| {name} | {state["status"]} | {state.get("elapsed_gpu_seconds", 0)/3600:.6f} | {result.get("new_actor_steps", 0)}/{result.get("new_critic_steps", 0)} |')
    text += ['', f'已结束worker累计GPU小时：{supervisor.get("worker_gpu_seconds", 0)/3600:.6f}；'
             f'尚在运行worker已用GPU小时：{supervisor.get("running_gpu_seconds", 0)/3600:.6f}。',
             '该账含模型装载、训练、冻结执行与worker边界；没有另建显存预留进程。单次训练耗时与峰值见JSON中training_consumption。', '',
             '## 独立确认与结论边界', '',
             f'TextFSM各方法均值：`{means}`；I−B：`{summary["independent_confirmation"]["I_minus_B"]}`；'
             f'I−G：`{summary["independent_confirmation"]["I_minus_G"]}`。',
             '缺少完整4次已知验收时不计算该方法均值。每方法4个seed仍为同一个任务，不能解释为12个独立项目或广泛软件泛化。',
             '完整交付、独立API、选定回归和consumer实际调用观察，以及后继sqlparse原件，逐槽保存在配套JSON。',
             '配置权重变化或候选试训完成本身不证明分配有效；若所有schema结果相同，应归因于零可辨识贡献方向及覆盖/基础锚项，不能称为发现高价值经验。',
             'CPU机制资格、真实模型工作结果、真实参数训练收益分别记录；队列状态不是实验效果。', '']
    (output / 'software-allocation-v029.md').write_text('\n'.join(text))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    result = report(args.run_root, args.output_dir)
    print(result['supervisor']['status'])


if __name__ == '__main__':
    main()
