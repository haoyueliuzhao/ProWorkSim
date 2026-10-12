# v049 r1 原库存续接宿主 CPU 控制

本次只新增续接宿主、监督包装和 10 项有限 CPU 控制；10 不同用例 / 10 次执行全部通过，相关三个文件 Ruff 通过。未执行模型、GPU 任务、真实 tokenizer、世界动作或私有验收。初次 9 项通过后，只执行新增的第 10 项 host 干运行控制；没有重复整套或旧模型资格。

原批次 `software-learning-v049` 已终态，保留其 supervisor、停止文件、原 5 槽结果与旧训练导出。一次只读库存核查确认：

| 项目 | 原件值 |
|---|---:|
| 已闭合原槽 | LA r1/r2/r3；LB r1/r2 |
| 唯一未开槽 | LA r4；LB r3/r4 |
| 决定 / 实际调用 | 122 / 119 |
| 输入 / 输出 token | 1,586,240 / 31,747 |
| 实际总 token | 1,617,987 |
| 成员测试 | 14 |
| 原 worker GPU 秒（含 S0） | 2162.429730653763 |
| 不转移的原未用 token | 882,013 |

所有原 961 个已冻结文件均同字节，包括旧运行器、世界、Γ1、工具、数值代码及其原协议依赖。新读取适配、宿主和测试为新增文件，另行冻结；不通过修改原模型可见源码恢复后续槽。

新 root 直接引用原 S0/checkpoint 与 declaration，不复制旧实验数据，不创建新 S0 资格。监督器把原 S0 标注为 `complete` 且 `attempted=false`、`original_complete_state_reused=true`、本阶段 GPU 秒为 0；它不被重新启动。采集 worker 保留 `collect-LA/LB` 名字，但只执行从原目录实际闭合状态派生的原剩余 3 槽，seed、先手和根顺序不变。任何已准备但未闭合目录、旧 update/development 尝试或原 worker 未退出都会阻止准备续接计划。

新采集仅保存原 row、capture 和机械回执，并用原 `finish_evaluation` 所需的最小 slot/reward 元数据关闭冻结 owner 窗口。训练导出延后到 B 前一次执行：原 5＋新 3 的八个目录按原 declaration 顺序组成唯一 `source-registry.json`；每个槽只产生一次正式派生 entry，所有原始文件留在原位置。Q 分支消费封存后的同一 `entries.json` SHA，不重新物化。CPU 的旧原件诊断与此后正式八槽物化是不同活动，不能说整个工程只读取了旧原件一次。

新 host 的所有学习读取入口来自 `software_learning_v049r1`，支持统计使用 `software_allocation_v049r1`，避免其内部 `bind_rollout` 再落回旧 member reader。原 H1 更新和方向算法保持原实现；实际 native input/tokenizer/probability 核验仍按真实学习桥接执行。registry 只包含训练八槽，不扫描与 Q 并行执行的开发目录。

新调用预算最多为 3 采集＋12 条件开发＝15 槽、7,500,000 token、1920 决定/attempt、480 成员测试；加原已消费上界为 9,117,987 token、2042 决定、2039 attempt、494 测试。原 20 槽/10M 设计上界保留，旧费用只计一次，剩余额度不转移。Q 分支原有支持条件和不追加规则不变。

接口：

```text
python -m scripts.software_learning_resume_v049r1 prepare \
  --run-root NEW --original-root ORIGINAL --controls R1_CPU_CONTROLS_JSON
python -m scripts.software_learning_resume_v049r1 supervise --run-root NEW
```

`prepare` 必须在 root 完成整合、提交全部新增实现及 CPU 准入后运行。本子任务没有执行 prepare、supervise 或任何 worker，也未提交代码。机器回执及实际原件引用保存在同名 JSON。
