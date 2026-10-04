"""Read the finite v030 candidate ledger without inventing unstarted scores."""

import argparse
from pathlib import Path
import time

from proworksim.storage import read_json
from scripts.run_ne_v021 import read, reference, write

VERSION = 'software-model-selection-report-v0.30'


def report(run_root, output_dir):
    root, output = Path(run_root).resolve(), Path(output_dir).resolve()
    plan, supervisor = read_json(root / 'plan.json'), read_json(root / 'supervisor.json')
    selection = read(root / 'selection.json')
    candidates = {}
    for name in plan['candidates']:
        actual = root / name / 'actual'
        worker = read(actual / 'report.json') or {}
        qualification = read(actual / 'qualification/report.json') or worker.get('qualification') or {}
        rows = worker.get('rows', [])
        progress = read(actual / 'progress.json')
        if progress is not None and len(progress) > len(rows):
            rows = progress
        byslot = {row['slot_id']: row for row in rows}
        outcomes = []
        for slot in plan['inventories'][name]:
            row = byslot.get(slot['slot_id'])
            folder = actual / slot['slot_id'] / 'slot-0'
            outcomes.append({**slot, 'status': row.get('status') if row else 'not_started_or_not_closed',
                             'R': row.get('R') if row else None,
                             'complete_work': row.get('complete_work') if row else None,
                             'record': row, 'assessment': read(folder / 'assessment.json'),
                             'trajectory_directory': str(folder)})
        resident = read(actual / 'resident/owner.json')
        candidates[name] = {'state': supervisor['states'][name], 'worker': worker,
                            'qualification': qualification, 'outcomes': outcomes,
                            'actual_model_profile': resident.get('inference_profile') if resident else None,
                            'model_download': read(plan['download_manifests'][name]) if name in plan['download_manifests'] else None,
                            'common': read(actual / 'common.json')}
    value = {'version': VERSION, 'generated_at': time.time(), 'run_root': str(root),
             'plan': plan, 'plan_reference': reference(root / 'plan.json'), 'supervisor': supervisor,
             'selection': selection, 'candidates': candidates,
             'allocation_experiment_started': False,
             'scope': 'Three runtime combinations, six development contracts from one repository. Technical probes and frozen work are separate; unstarted or unknown results are not zero. No ID-VTDO effect estimate.'}
    output.mkdir(parents=True, exist_ok=True)
    write(output / 'software-model-selection-v030.json', value)
    text = ['# v0.30 O1与代码模型选型运行记录', '',
            f'运行状态：`{supervisor["status"]}`。执行源码：`{plan["source"]["code_commit"]}`。',
            f'原始记录：`{root}`。', '',
            '本轮固定当前9B、SWE-Next-14B、Devstral-Small-2507。仅本项目新派生的Marshmallow六个开发合同参与模型选型；不是六个独立仓库。schema贡献开发和TextFSM独立确认没有参与选择。',
            '最多36条筛选经历，另有每模型4次原生诊断、至多1次诊断参数更新与1个新身份单调用片段；技术控制不算工作成绩。', '',
            '## 推理与训练资格', '',
            '| 组合 | Worker状态 | 推理资格 | 更新接入 | 近16K容量 | 完整恢复 | 已记录筛选槽 |',
            '|---|---|---|---|---|---|---:|']
    for name, candidate in candidates.items():
        q = candidate['qualification']
        recorded = sum(row['record'] is not None for row in candidate['outcomes'])
        text.append(f'| {name} | {candidate["state"]["status"]} | {q.get("inference_ready")} | {q.get("training_integration_ready")} | {q.get("near_16k_capacity_demonstrated")} | {q.get("common_restored_exactly")} | {recorded}/12 |')
    text += ['', '`None`表示当前尚无该资格结果。必须通过原概率门、真实完整反传/一步更新、checkpoint重载、新身份回流和容量条件后，才进入冻结开发筛选。诊断正信号不称业务奖励；诊断后完整恢复原共同状态。', '',
             '## 冻结开发逐槽结果', '', '| 案例/seed | 当前9B | SWE-Next-14B | Devstral-Small-2507 |', '|---|---|---|---|']
    for index, slot in enumerate(plan['inventories'][plan['candidates'][0]]):
        cells = []
        for name in plan['candidates']:
            row = candidates[name]['outcomes'][index]
            cells.append(str(row['R']) if row['status'] == 'closed' else row['status'])
        text.append('| ' + slot['case_id'] + ' / ' + str(slot['sampling_seed']) + ' | ' + ' | '.join(cells) + ' |')
    text += ['', 'R=1需完整独立交付验收；公开回归绿色、任务创建、发送消息或固定提交本身均不等于通过。单执行者API/修复与双成员O1分别评价，未启动不补零。', '', '## 分类与选择', '']
    if selection:
        text += [f'预定规则结果：`{selection["status"]}`；选定组合：`{selection["selected_candidate"]}`。', '',
                 '| 组合 | API：成功/已知 | 修复：成功/已知 | O1：成功/已知 | 两seed均过案例 | 可选 |', '|---|---:|---:|---:|---:|---|']
        for name, row in selection['candidate_results'].items():
            values = row['categories']
            cells = [str(values[c]['successful_complete_deliveries']) + '/' + str(values[c]['known'])
                     for c in ('api_normal_path', 'repair_after_real_failure', 'o1_root_goal')]
            text.append('| ' + name + ' | ' + ' | '.join(cells) + f' | {row["cases_passing_both_seeds"]} | {row["selection_eligible"]} |')
    else:
        text.append('三个预定候选尚未全部终结，尚未进行最终选择。')
    text += ['', '每类别均预定4次，只有12槽全部已知且三个类别各至少2/4完整通过才可入选。排名依次采用O1、修复、API完整通过数、双seed一致性、格式错误、更低实际worker成本与固定候选顺序。技术失败不触发自动替换模型。', '',
             '## 实际成本与边界', '',
             '| 组合 | 结束worker GPU小时 | 诊断actor/critic步数 | 正式筛选优化器步数 |', '|---|---:|---|---:|']
    for name, candidate in candidates.items():
        update = candidate['qualification'].get('update') or {}
        text.append(f'| {name} | {candidate["state"].get("elapsed_gpu_seconds", 0)/3600:.6f} | {update.get("actor_optimizer_steps", 0)}/{update.get("critic_optimizer_steps", 0)} | {candidate["worker"].get("screening_optimizer_steps", 0)} |')
    text += ['', f'已结束worker累计GPU小时：{supervisor.get("worker_gpu_seconds", 0)/3600:.6f}；运行中worker已用：{supervisor.get("running_gpu_seconds", 0)/3600:.6f}。下载/排队未分配GPU，不与worker GPU小时混算。',
             '逐条真实输入输出长度、行为与梯度概率门、技术更新耗时/显存以及失败原因，见配套JSON中的qualification和原始目录。',
             '本轮没有B/G-raw/I-P贡献试训、正式分配或锁定集确认；候选绝对工作变化不代表经验分配增量。一阶公式CPU控制也不代表已完成完整V1.3或跨窗口算法。',
             '全部成功、失败、技术未知和未启动保留。报告只读取当前记录，不重试模型、改变门槛或补采。', '']
    (output / 'software-model-selection-v030.md').write_text('\n'.join(text))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(report(args.run_root, args.output_dir)['supervisor']['status'])


if __name__ == '__main__':
    main()
