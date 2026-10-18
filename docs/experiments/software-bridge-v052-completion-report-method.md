# v0.52 原十二槽接续合并报告方法

本报告器只读汇总原库存，不执行评分、模型、tokenizer 或业务测试，不恢复任何中断回合。旧 `software-bridge-v052-final.json` 的名称虽然含 final，仍作为首阶段原件保留，固定 SHA 为 `5a5f6efb564de1615819fe002d61715a1e235265781a55d0bffc1e21cfb38335`。新结果另存，不覆盖旧 JSON、MD、host 或原运行文件。

## 库存与来源

第一阶段五个 closed 和四个 technical_unknown 行完整保留，包括 raw、正式端点、guard/来源、费用口径及缺证记录。唯一可替换的是原 `v052-cal2-xmltodict-1-PS1`、`v052-cal2-xmltodict-2-PS1`、`v052-cal2-xmltodict-2-OH_ref` 三个 not_started 行；最终仍为十二个逻辑槽、六题、每条件六行，不拼成十五条样本。boltons2-PS1、parse1-PS1、parse2-PS1、xmltodict1-OH_ref 四个中断槽不重采、不补评分，正式端点继续 null。

新根为 `runs/software-bridge-v052-resume-r1`。报告器要求接续 plan 的 `predecessor_references` 精确绑定首阶段 report、plan 和 supervisor；`original_rows` 完全等于原 plan 的十二行，`rows` 只能是上述原三行且顺序、seed、先手等字段不变。新 supervisor 必须绑定新 plan，states 仅三槽，状态为 complete 或 paused，具有 ended_at，所有 attempt 已结束。旧、新 plan 分别验证，不把新三行套入旧十二行的入口门。

新三行读取复用旧报告器的 `formal_outcomes`、`compact_report`、`metrics_for`、`worker_intervals` 纯契约。只有新槽的 started→report→closed→plan、宿主 complete、continue verdict/measurement、native 结算及 actor/RNG 等 guard 都闭合时才给正式值；缺失或失配保留 null。旧九行不重新调用这些门，不因补充账单而修改旧正式评分，也不遍历旧 native 输入或 SDK trajectory。

## 费用与分母

旧封存标量只计一次：158 started、157 complete、已知实际 1,795,219 token、不确定预约 14,512 token、账本 1,809,731 token，唯一 worker 总时长 2683.403012275696 秒。只加新根三槽 ledger 及唯一完整 worker intervals，两个 stage 单列原标量和来源；同一 attempt 路径跨阶段重复出现即拒绝，嵌套 native/test/phase 时长不叠加。装载前资源尝试的已有 worker 时间仍保留。

旧不确定预约不转换为已知实际，不因新阶段正常完成而清零，整体 complete_actual_tokens 仍为 null。账单完整与业务评分已知分别处理。整体十二行均值、各条件六行均值与六题配对差只有相应分母全部已知才输出点值，否则输出 null 与未知值取 [0,1] 所得界限；这些界限不是置信区间。OH 的固定交付端点保持不适用。

旧模型/资格费用和未用预算不转入新库存，无更新。新三槽独立上限 1,500,000 token、384 决定、384 attempt、两个 PS1 共 64 次公开测试。报告器的 `new_model_calls/new_scoring_calls/new_tokenizer_calls` 都指报告操作本身，为 0；真实模型费用来自分阶段原 ledger。

## 必要控制与执行

只增加一个 pure control，同时覆盖仅替换原三槽、排除旧九槽、禁止给旧四 unknown 填值、禁止额外行或改 seed、费用只加一次、重复 worker interval 拒绝、旧 14,512 不确定预约和 null 完整费用保持。它使用合成字典，不读取实际报告或调用模型/测试引擎；原报告控制不重跑。

当前仅实现和执行这一个纯控制，实际合并需根代理确认新阶段终态后才运行，输出路径必须不存在：

```bash
.venv/bin/python -m scripts.software_bridge_v052_completion_report \
  --first-stage docs/experiments/software-bridge-v052-final.json \
  --root runs/software-bridge-v052-resume-r1 \
  --output docs/experiments/software-bridge-v052-completion-final.json \
  --markdown docs/experiments/software-bridge-v052-completion-final.md
```

报告实现：[software_bridge_v052_completion_report.py](../../scripts/software_bridge_v052_completion_report.py)。原件不修改，生成报告不增加实验、重评分或恢复授权。
