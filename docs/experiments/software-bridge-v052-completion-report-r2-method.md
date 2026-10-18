# v0.52 r2 合并报告适配：原十二槽与 r1 零模型启动成本

新增 [software_bridge_v052_completion_report_r2.py](../../scripts/software_bridge_v052_completion_report_r2.py)，原 [completion_report.py](../../scripts/software_bridge_v052_completion_report.py) 及其首次通过的控制保持不变。本适配不复制或重写统计计算；通过私有 `FunctionType` 绑定原 `read_continuation` 的 `RESUME_VERSION` 为 `software-openhands-bridge-resume-r2-v0.52`，原 `summarize` 仅替换该读取入口。原九行保留、原三行替换、正式/原始指标、十二/六分母和未知界限全部复用原纯函数。

## r2 来源与零模型阶段

唯一新模型根为 `runs/software-bridge-v052-resume-r2`。它仍必须绑定首阶段 report/plan/supervisor、原十二行与原三个未开始槽身份，并在 complete/paused、ended_at 存在且所有 worker attempt 结束之后才允许实际报告。r2 plan 的 `supporting_references.resume_r1_zero_model_failure` 必须绑定不可变审计 SHA `bd8ac03925f41c352290e974ec2d89fbba7f66c3522899043c5481e5e679685a`：[r1 zero-entry audit](../../artifacts/software-bridge-v052/resume-r1-zero-entry-audit.json)。

r1 的三个 worker 在原 `worker` 首个 `frozen(root)` 操作失败，未创建 slot-start、task、resident/calls、prepared 或 episode；其 ledger 实际调用、完整调用、token、预约和更新均为 0。审计中三个真实区间分别为 5.018754005432129、5.019733667373657、5.018822431564331 秒，总计 **15.057310104370117 秒**。这些是启动失败的操作成本，不增加科学样本、模型曝光或模型账单。

适配器逐字段要求审计的零账本、未进入槽/装载/生成、具体缺席路径与三段实际 worker 区间，不接受仅凭 `passed=true` 或总账本为 0 的“零模型”声明。审计完整文件另以 SHA 绑定，区间总和必须精确等于上述封存值。

## 合并方式与限制

先用原报告器计算“首阶段九行 + r2 原三行”的唯一十二槽。随后只增加一个 `zero_model_bootstrap_only` stage，保留 r1 原零账本和三段 worker 成本；其 `scientific_rows_added` 与 `model_ledger_added` 都为 0。总 worker 时间再加 15.057310104370117 秒一次，旧第一阶段、r1 bootstrap、r2 的 attempt-output 绝对路径必须互异；任何重复或二次加入 bootstrap 均拒绝。

顶层行、模型账本及统计不因 bootstrap 改变。原四个中断结果保持 null，原 157 完整/158 开始、已知 1,795,219 token 与不确定 14,512 token 只计一次，然后只加 r2 的真实模型账本。原不确定费用不被启动修复消除，完整实际 token 成本仍为 null。科学分母仍是十二槽、每条件六题，不变成十五或十八槽；没有未用预算转移、旧槽重采或评分补验。

## 控制与实际报告命令

只新增一个纯控制，使用合成报告与零入口审计结构，覆盖：bootstrap 有时间成本但零科学行/零模型费用、原行/统计/未知账本保持、二次加入或跨阶段重复 attempt 拒绝、伪零预约/slot-start/装载或缺席路径拒绝。原 completion-report 控制和任何旧控制不重跑；不执行真实合并，不调用模型、业务测试或 tokenizer。

根代理确认 r2 终态后才可执行，输出文件必须为新文件：

```bash
.venv/bin/python -m scripts.software_bridge_v052_completion_report_r2 \
  --first-stage docs/experiments/software-bridge-v052-final.json \
  --root runs/software-bridge-v052-resume-r2 \
  --output docs/experiments/software-bridge-v052-completion-final-r2.json \
  --markdown docs/experiments/software-bridge-v052-completion-final-r2.md
```

该命令只读取首阶段封存标量、r1 审计及 r2 已绑定报告，不遍历旧模型调用或重建工作区。原报告、已绑定源码/控制及运行原件均不改写。
