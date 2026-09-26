# v0.15 候选筛选与在线 pilot 的只读报告

`scripts/learning_report_v015.py` 汇总 S1 能力筛选、N0 数值桥接和 N1 在线 pilot 的**原始已存结果**。它不加载模型或检查点张量，不执行世界、SQL、优化器或奖励评价；报告中的回报、`completed`、分项得分、record/V 和方法分类来自运行时原记录。它只验证闭合 experience 的保存哈希并统计真实 token ID 长度，不重新分词或复算概率。

## 输入与入口

```json
{
  "jobs": [
    {
      "name": "screen-candidate-a",
      "protocol": "examples/learning-v15/screen-candidate-a.json",
      "run": "runs/screen-candidate-a",
      "condition": "candidate-a",
      "candidate_id": "candidate-a",
      "launch": "runs/v015-launch/screen-candidate-a"
    }
  ],
  "baseline_references": []
}
```

`protocol` 相对 `--source`，`run` 与可选 `launch` 相对 `--project`；绝对路径也可用。运行继续使用既有 `online/window-i/collection/slot-j` 布局。`launch` 是 `.launch.json/.resources.jsonl/.log` 前缀。manifest 可以保留其他登记元数据，完整 `declared_job` 写入结果。

窗口用显式 `mode=online|evaluate`、`stage=screen|bridge|pilot`、`phase`、`node` 标记用途；按窗口→协议→job 继承，**不从窗口名称猜测阶段**。slot 提供 `case_id`，可显式添加 `task`、`fact_id`/`fact_position`、`repeat`、`sampling_seed`、`family`、`pool`；已闭合 episode 的原 `online_case` 用作回退，最后才从已知 case ID 解析事实编号和来源。支持 handoff/implement/review/pair/chain。repeat 未声明时记录“同窗口同 case 的出现顺序”及这个来源，不伪称真实随机种子编号。

```bash
.venv/bin/python -m scripts.learning_report_v015 \
  --manifest examples/learning-v15/study.json \
  --project /data1/zhuxinrui/projects/ProWorkSim \
  --source /absolute/frozen/source \
  --output runs/v015-readonly-new
```

Python 入口为 `build_report(manifest, project_root=..., source_root=...)` 和 `write_report(report, output)`。输出必须是新目录；已存在目录直接拒绝，避免覆盖原报告。生成完整 `report.json` 与简短 `report.md`。

## 计数规则

- 所有计划槽位逐一列出，区分 closed_known、closed_unknown、open、interrupted_open、not_started。只有准备世界而没有 episode 开始，不算 started。中断原因保留原 runner/window/interruption 信息。
- `R=.2` 的读取或交接不算责任完成。筛选主指标只统计 `stage=screen` 下 implement+review 原记录 `completed=true`，同时按任务、事实和 repeat 完整展开；不按回报阈值重定义成功。
- unknown/open/not_started 不补零。当任何独立计划测量未知时，完整计划的奖励均值和完成率为 null；仍列已测分母、已测回报和完成次数。分项 score、achieved 独立呈现。
- 闭合 measurement 以原 manifest SHA 标识；同一原记录重复引用只计一次。相同 raw run 不得作为两个 job 重复登记；共享初始 baseline 放 `baseline_references`，该字段不增加 episode/token/step，也不自行认证复用合法性。
- `actor_optimizer_steps/critic_optimizer_steps` 才是窗口增量。评价窗口增量记0，并保留其实际记录字段、累计 totals 与 guard；评价报告若声称新增 step，列为不一致。不能累加评价中的累计 step。
- before/after actor、collection identity、初始 checkpoint 元数据、评价 guard、恢复状态与未知 update 窗口都保留。guard 缺失、未确认或保存的前后学习状态摘要不同分别显式可见。
- b 不跨 θ、窗口、情境或候选混合。原 support 各窗口及各成员的 M/n/b、方法自由度单独保存；跨 episode 方法标签频数只是描述统计，不是新的经验分布或 ID‑VTDO 准入判断。
- token trace 长度从真实 finished model_attempt 读取，每响应仅一次，和 reported usage 分开列；如二者冲突直接记录。没有 trace 不重建。上下文拒绝、调用状态、工具回执、成员统计及资源参考保留；resident direct 不当作网络 HTTP。

## 验证范围

4项纯 JSON fixture 测试覆盖：未运行不等于零、局部奖励不等于完成、pair及重复事实展开、不同 θ 下 b 不合并、评价累计步数不增加真实 step、原 token trace 长度、baseline 引用不重复计数、输出不可覆盖、闭合经验被修改时报错，以及重复 raw run 登记拒绝。Ruff 通过。

另对历史 `learning-v014-capacity-high12` 做了一次只读输入适配检查：4个实际闭合例、actor/critic 各1增量、41次真实生成、250,612 输入 token /3,367 输出 token，与其原记录一致，未发现汇总一致性问题。该历史读取不是 v0.15 新模型运行或数值验证，不补入 v0.15 实验样本。原输出位于 `runs/learning-report-v015-controls/report/`。
