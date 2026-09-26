# v0.14 首次正式 high 精度研究：原工作行为的只读诊断

本诊断读取六个已停止运行的原始事件、闭合快照、真实工具回执和已保存奖励，不再执行 SQL、模型、奖励或 V 评价。**144 个训练 episode 与 120 个初始评价 episode 已闭合；后续 480 个预声明槽位保持 unknown。没有最终锁定评价，以下不是完整学习曲线，也不是 MC 与 RTG 的收益比较。**

完整逐事件证据位于 `runs/v014-study-high-work-diagnostics/episodes-v2.json`；提交的机器摘要为 [v014-study-high-work-summary.json](v014-study-high-work-summary.json)，按条件、seed、window、模式和任务保留分母及原分项。每条诊断首先核对原 manifest、experience、起止 state 的 SHA256，随后核对 tool_call 与 end snapshot 的实际 command receipt，包括 compact 呈现的确定性映射。未闭合、缺失或损坏证据不计成零回报。

## 观察到的工作行为

训练池每类 36 例，初始评价每类 30 例。这里的“改 SQL”仅指实际已保存 code 版本的模型名称/SQL 文本变化，已与只改文件元数据、只手写 result 分开；它不表示业务正确。

| 责任与事实 | 实际训练经历 | 初始评价经历 |
|---|---:|---:|
| implement：当前成员实际读取适用 basis | 14/36 | 14/30 |
| implement：实际修改 SQL 文本 | 18/36 | 16/30 |
| implement：实际执行本 episode 修改后的 SQL 版本 | 10/36 | 11/30 |
| implement：原正确 build / 正确固定提交分项 | 0/36、0/36 | 0/30、0/30 |
| review：读取固定提交 code 版本 | 12/36 | 4/30 |
| review：读取固定提交 result 版本 | 15/36 | 14/30 |
| review：读取适用独立 audit_basis | 0/36 | 3/30 |
| review：原有据复核分项 | 0/36 | 0/30 |
| chain：实现成员实际读取适用 basis | 15/36 | 14/30 |
| chain：实际修改 SQL 文本 | 3/36 | 3/30 |
| chain：原正确提交 / 有据复核分项 | 0/36、0/36 | 0/30、0/30 |

66 个 implement 中有 9 例原 R=0.2，其余 57 例为 0；这些 0.2 来自原输入读取条款，不能解释成已完成正确 SQL 工作。66 个 review 的原 R 全为 0；训练与评价分别有 6 例实际读到了与当时固定提交不匹配的版本。正确版本读取、独立依据读取和完整有据判断是不同事实。

66 个 chain 中有 43 例保留了原交接成果 R=0.2，23 例为 0，尚无原正确固定提交或有据复核成果。模型确实存在改代码、执行修改版本及局部恢复，不能将这些统称为“只会调用工具”；但同样不能用这些动作替代未出现的独立业务成果。

## 错误后是否修复了具体义务

脚本不把换工具或后续 `ok=true` 记作恢复。对于缺 adoption，它要求：

1. 后续成员实际请求包含原错误对应的完整 `model_tool_result.message`。
2. 同一工作、同一缺失 alias 出现真实成功 adoption，保存确切 object/version。
3. 更晚同一工作发生成功 SQL 执行，其不可变执行 provenance 确实使用了该 object/version。

这只证明指定前置义务得到恢复，不表示其他输入齐全、SQL 业务正确或反馈是模型内部选择的因果原因。对于执行错误，只有实际改变 code 内容、并用该确切 code 版本重新成功执行才记执行恢复；手写 result 不替代 code 修改。

正式样本中，12 个训练 chain episode 出现 14 个不同的具体义务恢复，3 个初始评价 chain episode 出现 3 个。共有 19 条先前失败能与这些恢复匹配；同一恢复覆盖多次失败时，恢复数已去重。所有这些 episode 的原终局合同仍单列，**没有把局部修复重评分为完整交付。**

作为独立的已有记录控制，新 E0 `compact12 / window-0 / slot-2` 显示事件 51 报缺 data adoption，事件 120 实际采用 data v1，事件 153 的真实执行 provenance 使用 data v1。它仍缺 basis 且原 R=0.2，诊断只记 data 前置义务恢复。旧 v0.13 的手写 result 后执行 code v1、读取 code v1 而固定提交为 v2、读 basis 后仍未 adopt 三类已知行为均被新脚本按原序列识别，未修改旧结果。

## 验证与复现

7 项离线 fixture 通过，覆盖确切 adoption 引用、实际反馈消费、手写 result 与 code 修改区别、SQL 文本与元数据变化区别，以及未闭合/缺失 episode 的 unknown 处理。另对 4 条已存在的实际模型记录作只读断言；这些检查没有新模型或 SQL 运行。Ruff 对新增两脚本与测试通过。

原始实际记录控制保存在 `runs/v014-study-high-work-diagnostics/actual-record-controls.json`。脚本不将早期动作倒填成“当时已知正确”，业务正确性仅引用原终局 component；当前事实关系与原终局质量始终分开。

在新输出路径复现逐 episode 诊断：

```bash
.venv/bin/python scripts/learning_work_diagnostics_v014.py \
  --run runs/learning-v014-mc-seed0 --run runs/learning-v014-mc-seed1 \
  --run runs/learning-v014-mc-seed2 --run runs/learning-v014-rtg-seed0 \
  --run runs/learning-v014-rtg-seed1 --run runs/learning-v014-rtg-seed2 \
  --output /tmp/proworksim-v014-work-reproduction.json
.venv/bin/python scripts/learning_work_summary_v014.py \
  --diagnostics /tmp/proworksim-v014-work-reproduction.json \
  --output /tmp/proworksim-v014-work-summary-reproduction.json
```

这些计数描述提前停止研究中的真实行为瓶颈。训练窗口存活数量不同，且尚未到达预定开发 2/4 或最终锁定节点，不能把这里混合的训练与初始评价样本解释为可重复学习提升、算法优劣或迁移收益。
