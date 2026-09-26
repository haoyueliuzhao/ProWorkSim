# v0.15 已选模型的固定后续执行器

`scripts/run_learning_pilot_v015.py` 接收**已经完成的显式模型选择**，执行固定 N0 → N1 和软件评价序列。它不读取分数排序、不选择候选、不修改任务份额，不在失败后重采或替换 checkpoint。模型选择仍由完整 S1 审阅及单独 selection 记录负责。

## 输入与冻结

入口：

```bash
python -m scripts.run_learning_pilot_v015 \
  --config <explicit-config.json> --output <new-executor-directory>
```

必须从 config 指定的干净 frozen source checkout 运行，Git HEAD 与完整 `source_commit` 相同。config 字段如下；路径可相对 project，两个 Python 路径保留 venv symlink，不解析成宿主基础解释器。

```json
{
  "project": "/absolute/project",
  "source": "/absolute/frozen-checkout",
  "source_commit": "full-frozen-commit-sha",
  "python": "/absolute/model-env/bin/python",
  "launcher_python": "/absolute/project/.venv/bin/python",
  "launcher": "/absolute/project/runs/v015-launch/launcher.py",
  "environment": {},
  "model_path": "/absolute/public-model",
  "weight_manifest": "/absolute/public-model/proworksim-manifest.json",
  "selected_screen_protocol": "/absolute/frozen-selected-screen.json",
  "selection_record": "/absolute/selection.json",
  "physical_gpus": {"mc": [0], "rtg": [1]},
  "poll_seconds": 30,
  "budget_safety_factor": 1.25
}
```

selection 必须为 `status="selected"`，且 `selected.candidate_id` 与 screen 的 condition ID 相同、`selected.screen_protocol.sha256` 与实参协议原始字节一致。执行器不重算 rank。外层条件 `qwen35-9b` / `qwen38-27b` 分别映射原生 profile 的 `qwen3.5-9b` / `qwen3.8-27b`；9B 每个 lane 1 卡，27B 每个 lane 3 卡，两个集合互斥。已显式选择的历史7B条件仍按其登记的 legacy runtime/单卡执行，不会自动回退到它。

环境不可覆盖 `CUDA_VISIBLE_DEVICES` 或 `PYTHONPATH`。source commit、launcher、选择记录、选中协议及权重清单 SHA 保存在 scheduler；每次新阶段启动前复核。生成的协议另保存 SHA，不能在等待期间改掉任务/预算。整个 output 以及协议目录必须新建；存在目录时拒绝覆盖。

## 六个固定阶段

| 阶段 | GPU lane | 预定 episode | 起点与依赖 |
|---|---|---:|---|
| bridge（N0） | mc | 32 训练 | 独立 fresh base；2×16 新在线窗口 |
| software-initial | rtg | 3 评价 | N1 seed 的独立 fresh base；可与 N0 并行 |
| pilot-mc | mc | 64 训练＋40 评价 | N0 门通过且资源预算先写入；fresh base |
| pilot-rtg | rtg | 64 训练＋20 评价 | 同上；fresh base；共同初始评价不重复计数 |
| software-mc-final | mc | 3 评价 | MC 的 N1 全部计划完成后，还原其最后计划 checkpoint |
| software-rtg-final | rtg | 3 评价 | RTG 的 N1 全部计划完成后，还原其最后计划 checkpoint |

协议调用已有 `build_learning_pilot_v015` 和 `build_software_eval_v015` 生成，保留各自 seed、case、deadline 与分布。共 **32 N0＋188 N1＋9 软件评价=229 个预定 episode**。N1 两条首次启动前共同等待 bridge 和 software-initial 的原进程退出，使两 lane 同时可用于初始化核对；不能占着一 lane 提前加载后因另一 lane 尚忙而耗尽核对时限。已明确退出的软件失败不阻塞 N1；软件成绩不决定训练准入。若进程身份/占用未知，则不能声称两条件能够建立共同初态，两条 N1 保持未执行。

两个 N1 协议在写盘前声明 `shared_initialization`，目录为 `<output>/initialization`，participant 分别 mc/rtg、participants 固定 `[mc,rtg]`、timeout 1800秒。由 online runner 的独立初始化 helper 保存并比较真实学习态指纹；这里只声明与调度，不用同seed冒充actor/critic/两optimizer张量相同。bridge和软件评价不加入barrier。

N0 准入必须同时满足：原始进程退出 0、online run complete、精确 2 个 16 例窗口、32 个 episode 实际闭合、初始 actor/critic step 为 0、没有恢复外部 checkpoint、两窗各真实记载 1 次 actor 和 critic 更新、总计各2次。每窗实际 behavior 和 gradient 概率报告须覆盖所有 admitted decisions，`passed=true` 且记录的 max/mean 差异分别不超过原 **0.02/0.002**。退出0、自报“完成”或仅一窗更新都不足以放行。

若 N0 不满足条件，两个 N1 和对应 software-final 均记为依赖未满足，不启动、不补采。N1 完成要求进程/计划窗口/实际闭合数一致；某个条件中止，只保留该条件已发生的工作，另一条件继续。software-final 入口继续执行独立的载入前绑定核验，拒绝未完成 N1、早期/开发最优或其他来源 checkpoint。

## 启动、恢复与不重试

复用已测 launcher 的真实命令、stdout、退出码和每15秒 GPU/进程/host资源采样；复用 candidate queue 的原子 JSON、路径和 `/proc` 身份读取工具。每个子 launcher 以 `start_new_session=True` 启动。先持久写 `launch_intent`，再 Popen；一旦出现 intent，该阶段绝不会再启动第二次。observer 被中断或退出不会给任何子进程发信号。

`--resume` 必须使用完全相同的 config/source/选定输入：**已有 attempt 只观察，不重跑；从未产生 launch_intent 的预定后继，可在原门通过后首次启动。**保存的 launcher/child PID、command、start_ticks 必须一致；首次绑定子进程时还核对其父进程为原存活 launcher。观察到 PID 复用时不采用新 PID。已不存在的进程允许60秒完成记录写入宽限，之后缺少退出证据则为 outcome_unknown，不凭结果文件推断 exit0。

原进程身份或 lane 占用不确定时，不在该 lane 启动替代进程；另一 lane 可继续。这里的边界是六个固定任务、有限 episode/决策、一次启动与无重采，不是承诺所有合法长训练在固定墙钟内结束，也不通过 observer 擅自终止仍匹配的运行进程。

## 资源预算及只读输出

N0 门通过后，**先于任意 N1 启动**写 `resource-budget.json` 并保存其路径与 SHA。之后每次使用已有预算都核对 scheduler 中保存的路径和原始字节 SHA；不匹配即停止 N1 启动，即使修改后 JSON 仍能正常解析。记录真实32例的 launcher观测进程时长、设备数、设备分配和 device-seconds。N1 规划公式为：

`N0 elapsed / 32 × 188 × safety_factor`；分配设备时长再乘每任务实际声明设备数。

软件若初始3例已完整结束，使用 `software initial elapsed / 3 × 9 × safety_factor`；否则明确使用 `N0 elapsed / 32 × 9 × safety_factor` 作为**跨来源规划占位估计**。后者不能承诺代码工作的实际成本；不会因后来轨迹不同偷偷重写初始预算。原始资源日志始终保存，可另行计算真实总成本。

N0含加载、CPU/I/O、训练和观测开销；N1评价/软件轨迹的成本可不同。设备分配时长不是 GPU kernel time、FLOPs 或并行墙钟，采样峰值也不能保证捕获真实峰值/约束未来显存。launcher 对所有GPU及进程采样，保留共享服务器上的资源竞争证据，不终止其他项目。

稳定输出路径：

- `scheduler.json`：六阶段状态、实际命令、PID/起始tick、门判定和退出记录。
- `protocols/`：全部固定协议；`uci-study.json` 与 `software-study.json` 分开。UCI manifest 的 baseline_references 只引用一次 MC 的共同初始 development/locked 两窗供 RTG 对照，不重复计样本；引用声明本身不验证复用，必须查看实际共同初态核对记录。
- `launch/*.launch.json`、`*.log`、`*.resources.jsonl`：复用 launcher 的持久原始记录。
- `runs/<stage>/`：各阶段原始运行目录与完整失败记录。
- `resource-budget.json`：N0后、N1前的冻结规划估计。
- `initialization/*.json`：由在线入口生成的真实共同初态核对记录，最终只读报告包含原文件路径/SHA/内容。
- `study-report.json`：只读取已保存 protocol/manifest/report/launcher，列明闭合、未启动和开放项，不加载模型/tensor、不重新执行判分、不把缺失奖励补成0。完成或observer异常/分离时生成；每次还实际调用已有 learning_report_v015.build_report/write_report，在唯一 `readonly-uci-<time_ns>/` 新目录生成分项工作统计。路径和成功状态写回 study-report；若缺少原始证据或汇总发生异常，保存明确 readonly_error 和原因，保留原闭合/缺失计数，不重跑模型或重新判分。软件保持独立。

必要 CPU fixtures 以假 Popen/PID 和保存的 JSON 测试：完整依赖顺序与预算写入先于N1；可见成功flag与超阈值记录矛盾时拒绝；恢复不重跑旧attempt但首次启动未尝试后继；PID复用保留未知；软件失败不阻止另一条件；无selected记录则拒绝。没有在这些检查中启动 GPU、模型或参数更新。
