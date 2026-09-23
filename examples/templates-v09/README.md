# v0.9 两模板公开接口示例

这些配置是有限合成资料。两个项目可以分别装载，也可以在同一个世界中运行。此目录演示各自交付，不自动建立项目之间的资料依赖；跨模板发布联动需另外声明分享、采用和维护规则。

在仓库根目录运行，目标目录应不存在：

```bash
.venv/bin/proworksim world-create runs/templates-v09-demo/world --spec examples/templates-v09/world.json
.venv/bin/proworksim project-load runs/templates-v09-demo/world examples/templates-v09/reconciliation.json --actor operator
.venv/bin/proworksim project-load runs/templates-v09-demo/world examples/templates-v09/report.json --actor operator
.venv/bin/proworksim world-tools runs/templates-v09-demo/world --actor analyst --project FINANCE
.venv/bin/python examples/templates-v09/run_workers.py runs/templates-v09-demo/world --output runs/templates-v09-demo/public-transcript.json
```

`run_workers.py` 将可信会话封装成仅有 `tools / observe / call` 的端口。核对策略从公开任务发现三份来源并逐项采用、读取、生成和提交；报告策略从公开观察取得对象身份，采用声明的固定版本，生成有限正文，然后由审阅策略读取实际固定提交。首次正确交付没有强制返工。脚本保存实际观察、参数和工具返回，不读取评价器答案，不硬编码对象 ID。

重复演示请使用新的世界目录和输出文件。该脚本是一次性示例，不是任意步骤中断后的恢复策略。它不会把已有 pending 交付或任意环境状态自动重置。

如只运行财务模板，装载 `reconciliation.json`，复制 `ports.json` 为新文件并只保留 `finance_worker`；运行时用 `--ports 新文件`。如只运行报告模板，装载 `report.json`，保留 `report_author` 和 `report_reviewer`。端口配置为实际身份与项目绑定，不是角色扮演文字。

最小 Python 调用也可以直接使用实现中的策略：

```python
from proworksim.workers.reconciliation import ReconciliationWorker
from proworksim.workers.research_review import PublicReportWorker

# public_port 是仅提供 tools() / observe() / call(...) 的对象。
finance = ReconciliationWorker(public_port, split=True)
result = finance.run()  # 从公开观察选择未完成核对工作。

# 报告策略的 source_data 要求先按公开合同建立该工作的采用绑定。
author = PublicReportWorker(report_author_port)
data, dependencies = author.prepare(work_id, style="compact")
submission = author.deliver(work_id, data, dependencies, split=True)
reviewer = PublicReportWorker(report_reviewer_port)
findings = reviewer.review(work_id, submission["submission_id"])
```

示例中的核对工作允许明确交付真实冲突和未知；它不会把“材料不足”改写为零。报告正文仅支持合同声明的两类有限句式，背景文字的专业充分性不评价。正式接受、有限内容正确性、模型能力分别解释。进一步的状态及合同说明见 [设计说明](../../docs/template-expansion-v09.md)。
