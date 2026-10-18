# v052 原12槽终态报告方法

新增`scripts/software_bridge_v052_report.py`，版本`software-bridge-v052-final-v1`。本报告器独立于已经封存的模型运行源，不修改OH adapter、受管collector、测试入口或旧v051模块。这里只完成代码和一项纯CPU分母控制，尚未对真实root生成报告。

## 输入、原分母与正式端点

报告器只接受终态`complete`或`paused`的`runs/software-bridge-v052`，读取其plan、supervisor、各slot的started/closed及所绑定worker report；可引用interruption。固定库存必须是原boltons/parse/xmltodict各两题×OH_ref/PS1，恰好12个不同槽，不能删未开、缺证或成绩不佳的题。

R_code及Q_task_terminal分别按六题等权，条件差为PS1−OH_ref。只有该均值或配对差需要的全部值已知才给点估计，否则为null并保留[0,1]未知值导出的界限。界限不是置信区间，不对未知填0或按测试数量加权。原已验证`bounded`函数只作为数值库复用；两条件配对逻辑在新脚本中独立适配，不能误用旧四状态面板。

PS1的R_joint/Q_joint单独报告。OH_ref没有项目固定交付合同，因此其joint端点与joint条件差明确`applicable=false`、mean/bounds/denominator均null；不是0，也不计为六个技术未知。

每槽先保存四个raw字段，然后独立判断正式绑定。正式值要求原host state为complete，started的row/plan/attempt、closed的report引用和continue decision、report的row/source_plan均一致；worker report status为closed，verdict和measurement都continue，actor guard及四项episode guard全true，native accounting全部started已结算且无完整性错误。OH必须保持joint不适用，PS1须保持内部P映射与固定交付身份。缺guard、fault或未开保持未知；安全context/预算结束但代码0且证据齐备可以是正式已知结果，代码成功不是门槛。

对某个端点缺失的字段不推算：例如完整性闭合但Q_task_terminal未给出，该Q端点仍null。原raw非空值不因正式缺证删除。

## 紧凑证据与费用

只复制必要标量：每槽usage、native账单计数、stop/boundary的标量、角色映射、guard布尔值、公开终态测试计数、末树观察数、相同身份验收复用和唯一候选ref。完整SDK历史、native响应、calls列表、测试stdout/全部node正文和大accounting结构不嵌入最终JSON；通过原worker report的path/SHA/bytes及JSON pointer追溯。

host_final_test_executions已是该槽固定交付加未复用终态测试的总数；terminal.new_test_executions只为分项，不再次相加。相同树/完整评价身份复用的原权威回执另存引用。collection缺节点按原评分语义记未观察/not-run，不能冒称已经执行失败。

生成费用只使用本轮supervisor.ledger一次，不重新遍历resident/calls，也不逐slot重复相加已汇总费用。known actual、不确定预约、ledger和complete actual分列；源缺字段保持null。旧v051费用和剩余预算不加入。

worker区间从supervisor.states全部attempts按output身份去重，每段只计一次，包括纯pre-model资源尝试。GPU index从`gpu.index`读取，缺少时看`binding.gpu_index`，没有凭据则null。缺秒数时给已知秒数小计和缺失区间数，完整worker秒数/小时为null；不填0。generation、scoring、model和phase耗时均不再加入worker驻留。

## 唯一新控制

`tests/test_software_bridge_report_v052.py`只有一项纯控制：固定12/6及PS1−OH方向；完整代码0的安全context样本仍已知；原raw成功但缺终态guard时正式null；未开始也null；完整均值/差缺值时保持null；OH joint不适用不填0；缺行直接拒绝。首次1 passed（0.06秒），scoped Ruff通过。没有重跑旧数值控制、SDK、tokenizer、模型、三态来源资格或候选测试。

证据见`artifacts/software-bridge-v052/report-controls/summary.json`。这项纯控制不冒称完整真实宿主来源已经验证，真实报告仍要在宿主终态后由root调用。

## 终态后命令，当前未执行

```bash
PYTHONPATH=src:. .venv/bin/python -m scripts.software_bridge_v052_report \
  --root runs/software-bridge-v052 \
  --output docs/experiments/software-bridge-v052-final.json \
  --markdown docs/experiments/software-bridge-v052-final.md
```

JSON和可选Markdown输出都必须是新路径；已存在任何输出即拒绝，不覆盖原件。报告生成不评分、不采样、不改源，也不放行后继。六个开发任务和三库只能支持有限桥接描述，不能据此称总体等效、完整默认OpenHands产品复现或新独立HOLD结果。
