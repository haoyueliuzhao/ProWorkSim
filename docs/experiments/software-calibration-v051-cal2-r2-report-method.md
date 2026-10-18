# CAL2 r2唯一合并、环境有效性与费用口径

本轮报告器为`scripts/software_calibration_v051_cal2_r2_report.py`。它不修改原报告器或任何run，先要求r2宿主进入`complete`或`paused`终态且worker区间全部闭合，才读取新槽。运行中不汇总为终态；未开始槽保留not_started，不填业务失败。原首阶段JSON直接复用，不重新评分、分词、测量或读取旧模型轨迹来推算结果。

## 两种视图与唯一库存

逻辑面板一直是六题×R/P/U的18行。新r2只绑定原14未开始行及独立准入的boltons-1/R零生成首次曝光例外。原boltons-1/P、boltons-1/U、boltons-2/P已有模型经历，永久排除，保留其原末树代码未知；不能用原raw固定交付0代替代码评分，也不能补验或重采。

历史层另存原4条technical_unknown，完整保留原R装载后、循环前的零生成失败。r2中同一R的首次真实模型曝光映射原逻辑行，并不删除旧技术尝试，也不增加第19个独立题/条件样本。JSON的`original_entered_history`和`zero_generation_R_history`明确保存两层。原R已经发生的装载worker费用继续保留。

新r2行按原task、seed、预算及顺序绑定，重复、替换已暴露旧槽或改变预算均拒绝。原三条未知和新行合并后，完整六题P−R、U−P代码及Q点估计必须保持null；已知配对可以单列，但不得改用已知子集充当完整主效应。R的项目固定交付始终N/A。

## 独立环境有效性覆盖层

`artifacts/software-calibration-v051/cal2-r2-first-execution-audit/report.json`提供独立只读证据，SHA256为`81820c7b2e3fd9df70e282d5cd1f842eab42e5564f29fd573aff800d0b8d50c6`。其精确影响范围是boltons-1/R、boltons-2/R和boltons-2/U：socket fixture把`socket.socket`替换为函数，导致原asyncio/ssl路径的类继承失败，影响原P2P测试。这是测试环境缺陷，不是模型生产代码失败或成绩阈值。

报告逐项核对audit的worker报告引用及末树runner引用与本次新记录相同，再将这三行严格`R_code`、`Q_terminal`置为未知。原执行器`raw_R_code=0`、`raw_Q_terminal=0.9927184466019418`仍保留，并存`pre_environment_overlay`。全部原r2绑定行另存`r2_rows_before_environment_overlay`。这一层不回写runtime结果、host判定、源文件或原评分。

boltons-2/U原`submitted=false`、`R_joint=0`来自“No fixed delivery”，该观察不因代码端点失效而删除；不推测修复环境后会否提交。R固定交付仍N/A。覆盖层只影响明确声明的代码端点，不扩展到其他任务、固定交付或生成费用。

## 生成费用与评分有效性独立

原首阶段报告的`complete_actual_tokens=null`保留在`stages[0].billing`，不修改原JSON。新的`generation_fee_evidence`使用已准入零生成R审计及其余22个完整、无inflight的native usage，独立证明原实际生成量227,876 token。该证明不使原代码评分变已知，也不删除原R失败或费用。

r2费用从每个实际native attempt的prepared/started/complete原件绑定，重复引用只计一次。有已知完整usage且无未结算请求时，测试环境未知不应使费用未知；反之，缺回包、费用源未决或不确定预约仍使完整实际费用为null。已知小计、预约上界与完整实际费用分别列示。

worker按每个唯一闭合attempt目录计一次，原R装载区间、原其他worker和r2新增worker都保留；不加嵌套生成、CPU测试或评分时长。CAL1只可独立附列。后继r3若获准运行七条未开始库存，应把本阶段合并报告作为单一前阶段费用来源，再加r3费用，不能再次加原首阶段227,876 token或413.1480391025543秒。

## 本次一次终态生成的结果

[阶段JSON](software-calibration-v051-cal2-r2-stage.json)的SHA256为`b4f0a9875230efd7ef7c44f93e440aaa3f3ba77449f8e394689301c8884a48d7`；[阶段Markdown](software-calibration-v051-cal2-r2-stage.md)为同次只读渲染。r2原宿主`paused`，8条complete、7条not_started。独立环境覆盖后，唯一18逻辑行是5条closed、6条technical_unknown、7条not_started；原首阶段4条技术未知历史仍单独保留。

| 费用来源 | 完整回包 | 独立已知实际token | worker秒 |
|---|---:|---:|---:|
| 原首阶段，含零生成R历史成本 | 22 | 227,876 | 413.1480391025543 |
| r2 | 253 | 2,676,767 | 3,429.4393272399902 |
| 唯一合计 | 275 | 2,904,643 | 3,842.5873663425446 |

本次无不确定预约，独立完整实际生成费用为2,904,643 token。合计worker为1.0673853795395958小时。严格完整六题P−R、U−P点估计均为null，未决界限保留。七条未开始为parse-2/U及xmltodict两题的R/P/U；不因其未运行而列为失败。

阶段报告顶层`version=software-calibration-v051-cal2-r2-unique-report-v1`；`root`、`plan`、`supervisor`、`host_status=paused`绑定r2正式终态，`rows`是唯一18行。历史状态在`stages`及`historical_host_statuses`，原初阶段report仅作历史来源，便于独立r3准入检查精确七条未开库存。

## 必要控制与边界

只新增三个纯CPU报告合同：18逻辑槽/R双历史层/三原未知及独立费用；暂停时七条未开与禁止重采、禁止把运行中宿主当终态；环境覆盖不改raw或原固定交付0、不污染已知生成费用。三个控制一次通过（0.07秒），新脚本和新测试范围Ruff通过；未重跑旧报告控制、原仓库pytest、原CPU资格、SDK或tokenizer。机器凭据为`artifacts/software-calibration-v051/cal2-r2-report-controls/result.json`。

在root确认宿主正式ended后，仅执行一次：

```bash
PYTHONPATH=src:. .venv/bin/python -m scripts.software_calibration_v051_cal2_r2_report \
  --original-report docs/experiments/software-calibration-v051-cal2-initial-stage.json \
  --r2-root runs/software-calibration-v051-cal2-r2 \
  --environment-audit artifacts/software-calibration-v051/cal2-r2-first-execution-audit/report.json \
  --output-prefix docs/experiments/software-calibration-v051-cal2-r2-stage
```

阶段版不覆盖。后继r3正式终态须另输出final并复用此阶段来源，不能把旧层重新计费或重新评分。本报告没有新增模型、真实测试、评分、分词、GPU、参数或反向调用，不读取HOLD任务，不释放或启动任何后继库存。
