# v051 CAL2只读终态报告方法

本文件冻结报告口径，不宣称CAL2已经运行或完成，也不释放HOLD。报告器为`python -m scripts.software_calibration_v051_cal2_report`。它只使用JSON、原生成回包、原测试结果和宿主终态，不调用模型、tokenizer、pytest、源码评分器或旧测量器。原记录和既有报告不覆盖。

## 固定面板与指标

面板保持三个仓库各两题，共六题×R/P/U，18个原槽；缺失或未开始的行仍保留。R是原始mini-SWE单agent，P是原始模型的ProWorkSim S1，U是保留S_star actor4/4的同一S1。三条件使用相同project数值路径、同题seed和独立fresh resident。报告不打开HOLD任务材料或重新加载模型参数。

`R_code`比较每个条件的末树代码正确性。R先保存原始候选，再以冻结规则恢复只读测试、配置及支持文件，保留合法生产修改、删除和新增helper；原树与权威评分树的SHA分别绑定。P/U使用事前声明的末树端点，合法同树固定交付验收复用，报告不再执行一次评分。

`R_joint`只用于P/U，描述最后固定交付及流程要求。R没有该项目端点，显示N/A，不计为0，也不计作需要补齐的未知。行政时间删失下，已知`R_joint`继续保留，`R_token`可为null，两者不互换。末树`R_code=1`不自动推出已有固定交付。

`Q_terminal`是该题已观察通过节点数除以完整原测试节点数。各题在总体中等权，不按测试数量加权。源码归因成立的collection失败可能使`R_code=0`；未执行节点明确列为not-run，其未证明通过部分只降低保守观察分数，不宣称节点主体已经执行并失败。报告另列已观察passed/failed/error/skipped、未运行节点清单和全节点结果界限。宿主、隔离、测试来源或runner未决则保持未知。

每个端点分列原记录值与严格来源绑定值。缺失终态guard、原生费用、episode身份、测试来源或机械测量时，不删除原值；严格口径相应为null。R/P/U均值固定除以六题；完整均值或P−R、U−P要求相关六对全已知，否则点估计null并给出[0,1]未知值导致的界限。界限不是置信区间，也不是将未知填0后的成绩。

## 来源与停止

只接受`complete`或`paused`的已闭合宿主以及所有worker已闭合区间。验证封存plan、原18行身份、slot started/closed、唯一worker attempt、报告引用、实际原生actor身份与project路径、S_star来源、终态只读与RNGguard、冻结机械测量结果及末树原测试证据。报告复用既有测量判定，不重新执行其历史反馈/拒绝证明。

P/U执行前拒绝来自`measurement.stop_assessment.local_resource_rejections`的精确理由：`context_capacity`、`team_budget`、`member_fixed_budget`。这些计数是已绑定终止证明，不把反馈重复呈现数当调用数。若测量未决或有完整性问题，拒绝数保持未知而非0。R读取自身带SHA的preexecution拒绝原件；它的字段与P/U分开保存。

安全的已绑定context/预算终止不因R低而变成故障；行政soft截止、真实执行fault、费用未决和身份/来源未决分列。原停止名和原始回执保留，不按结果追加、替换或重采。

## 唯一费用

费用来源是每个resident的`calls/*-{prepared,started,complete,fault}.json`。每个实际native attempt只算一次，framework重复引用不再收费。只有完整且绑定一致的实际usage进入已知token小计；已开始但缺完整合法回包保留其最大预约，预约金额缺失时另标未知，完整实际费用保持null。prepared但没有started不是实际生成。已知费用小计0不能被解释为费用完整已知0。

worker驻留费用按每个唯一attempt目录的闭合区间计一次，包括预装载失败、装载、生成、测试、测量及收尾；不再叠加内嵌生成或测试时长。CAL1费用不进入CAL2主表，只有显式`--cal1-report`才作为独立附列引用。报告不会读取旧CAL1槽重新计费。

R的最多128次原生bash行动与P/U至多32次项目公开测试并非相同交互机会；R/P的工具、界面与交付要求不同，因此P−R不能唯一归因于某一组件。三仓库六个人工合成缺陷也不构成自然issue总体样本。U−P仅描述本面板保留actor差异，无新增训练，不外推一般协作或学习收益。

## 必要CPU控制与终态命令

仅新增三个纯CPU控制：六题等权/未知界限/N/A和行政删失端点区分；R与P/U两种collection记录中not-run和完整分母一致；唯一native费用、未派发请求、未知预约和错误回包。三个控制通过，旧CAL1十一项及实际runner、SDK、tokenizer控制未重跑。另执行新文件范围Ruff。对应机器凭据位于`artifacts/software-calibration-v051/cal2-report-controls/result.json`。

CAL2真实root尚未启动时不生成虚构终态报告。待宿主闭合后，由root运行一次：

```bash
PYTHONPATH=src:. .venv/bin/python -m scripts.software_calibration_v051_cal2_report \
  --root runs/software-calibration-v051-cal2 \
  --output-prefix docs/experiments/software-calibration-v051-cal2-final \
  --cal1-report docs/experiments/software-calibration-v051-cal1-final.json
```

输出目标已存在即拒绝覆盖。报告只产生新的JSON与Markdown，不修改run或进行阶段准入。当前准备阶段实际模型、评分、分词、GPU、参数和反向调用均为0；真实18槽终态数据仍待后续执行。
