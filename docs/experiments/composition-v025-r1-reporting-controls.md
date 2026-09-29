# v0.25 R1 只读终态报告与自动归档

本页记录新报告入口的有限 CPU 验证，不是 R1 模型结果。原 v0.25 报告、分数、已失败更新和获授权预算修订都保留；R1 使用新的 run、source、监督与预算，输出独立的 `composition-pilot-v025-r1.md/json`。

`report_composition_recovery_v025.py` 从新冻结 plan 读取 `original_run`、原 supervisor/report/plan/support-complete 的 SHA 引用，以及恢复 binding。它核对原窗口确实是没有可重配块的16条原始经历、283个 admitted 决定，并核对原终态报告与原监督账本的成本一致。原轮共 **49415.01438975334 GPU 秒（13.726393 GPU 小时）**，包括原支持采集和中断训练；R1重新加载、失败或重算的占用另外计费，然后给出累计成本，原预算余额不延用。

恢复证明逐项保留原冻结源码的未步进判据，以及实际 `shared-before.pt` 恢复的 actor、critic、两个 optimizer 和 CPU/CUDA RNG。报告只核对引用字节和已保存的完整状态 digest，不加载 tensor、不检查已消失模型的实时权重。恢复目标是原更新前的 shared-before 状态，而非较早的采样前 origin；原266次部分反向不作为可继续的梯度 checkpoint，283个决定全部重新计算。实际新 admission/composition-admission 的字节还须与原件一致，实际283行 loss 的组成权重须均为1。

完整 R1 路径为一次 F0 更新（actor/critic 累计从2到3）、12个原本未执行的确认 slot 和2个新后继 slot。原16条经历只增加一次重复训练消费，**R1新采样训练经历为0，新增世界 episode 最多14**。报告分别统计实际闭合 manifest 边界与可信业务评价；闭合但 guard 未通过的 episode 仍是发生过的新交互，其结果保留未知，不能把“未知”改成零，也不能把“未执行”写成失败。

确认使用实际 v0.25 canonical preparation、原 case/seed、当前恢复后 checkpoint 身份、assessment SHA 与 evaluation guard。新的 reader 明确检查 `canonical-keys-v025-all-original-business-fields-and-immutable-file-bytes`，不误用 v0.24 报告辅助函数的版本限定。A新交付、B正确初稿核准、B错误计数修复、维护变化/不变分项呈现。

**所有 R1 报告中的配置主点估计与参数学习收益保持 null。**原窗口没有可重配块、没有配置分支，也没有这些确认情境的更新前配对观测。即使恢复更新成功并有确认完成案例，也只能描述恢复后 F0 的工作结果，不是 ID-VTDO 组成增量或参数改善证据。

新预算为 **91800秒＝25.5 GPU小时**：train_base 20小时、confirm_base 4.5小时、next_base 1小时；单更新任务最多18小时、整体 wall 最多48小时，单实例、无自动再次恢复。执行终止但协议未完成时报告 `closed_incomplete`；仍有声明阶段未结束时只给 snapshot。现阶段未预报真实结果。

CPU验证命令：

```bash
.venv/bin/python -m pytest -q tests/test_report_composition_recovery_v025.py
```

两项有限 fixture 覆盖：原失败费用与新失败费用相加；重复16次消费不计作新采样；原文件全部字节不变；未闭合更新的保存计数不能当终态步数；v0.25确认版本绑定正确；已知失败与未知guard分离；两条已闭合新 episode 不因其中一条结果未知而少计采样。结果 **2 passed**，相关三文件 Ruff 检查通过。

终态入口：

```bash
.venv/bin/python -m scripts.report_composition_recovery_v025 \
  --run runs/domain-v025-r1 \
  --output-json docs/experiments/composition-pilot-v025-r1.json \
  --output-md docs/experiments/composition-pilot-v025-r1.md \
  --require-terminal
```

`scripts/archive_composition_recovery_v025.py` 在监督器终止后调用同一入口，严格只接受上面两份新的固定路径。它拒绝覆写原两报告、任何已存在输出或两个原始 run 目录。按项目授权仅暂存、提交、推送这两份新结果；归档失败记录独立保留在新 run 的 `archive-status.json`，不改写模型运行记录。
