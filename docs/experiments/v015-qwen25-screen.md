# v0.15：Qwen2.5-7B 的36例 UCI 开发筛选

**36例全部闭合且回报可评价，完整责任完成0/36；平均R为0.113889。**部分工作已经发生：15例真实依据送达、3例实现责任中的完整输入读取、2例短复核中的完整证据读取，以及1条采用义务修复后实际执行。它们仍没有形成独立正确实现或有据复核，不能把部分进展表述为完整成果，也不应把0 complete解释为36例完全没有实际工作。

本记录只读原始结果与动作，不运行模型、世界、SQL或奖励评价。基础汇总为 `runs/learning-v015-baseline-final/report.json`；逐例 task/fact/repeat、原始分项、动作序号、固定版本及证据路径/SHA见 [JSON](v015-qwen25-screen.json)。首6例沿用已有52个回执一致性抽查，不再次遍历核验全部回执。

## 协议与分母

冻结源码 `b86edae8839c332c961aeb511d433cdfba4949d2`。这是原 Qwen2.5-7B-Instruct 共享初始化、FP32/highest、2048输出上限/16384上下文、temperature 0.7 下的纯评价，12个UCI development情境各3个固定采样seed。所有角色共享相同有效参数。这里的3次重复是同一初始策略的采样重复，不是3个训练种子。

36个episode均为 known，record=36 true，V=36 false；无未启动或unknown槽。actor/critic各0更新，原评价guard记录学习张量/优化器/step不变、RNG精确恢复。本轮不测学习收益，也不比较其他候选优劣。

## 每项责任与事实重复

全部单元格都是原R，所有行的 complete 均为0/3。

| 责任 | fact | repeat 0 | repeat 1 | repeat 2 | 平均R |
|---|---:|---:|---:|---:|---:|
| implement | 0 | 0 | 0 | 0.2 | 0.066667 |
| implement | 1 | 0.2 | 0 | 0 | 0.066667 |
| implement | 2 | 0 | 0 | 0.2 | 0.066667 |
| review | 0 | 0 | 0 | 0 | 0 |
| review | 1 | 0.25 | 0 | 0 | 0.083333 |
| review | 2 | 0.25 | 0 | 0 | 0.083333 |
| pair | 0 | 0 | 0.2 | 0.2 | 0.133333 |
| pair | 1 | 0.2 | 0.2 | 0.2 | 0.2 |
| pair | 2 | 0.2 | 0.2 | 0.2 | 0.2 |
| chain | 0 | 0.2 | 0 | 0.2 | 0.133333 |
| chain | 1 | 0.2 | 0.2 | 0.2 | 0.2 |
| chain | 2 | 0.2 | 0 | 0.2 | 0.133333 |

按责任合计，implement/review/pair/chain各9例，平均R分别为0.066667、0.055556、0.177778、0.155556。总R=4.1；16例R=0、18例R=0.2、2例R=0.25。

| 原终局分项 | 达成 / 适用episode | 对总R的贡献 |
|---|---:|---:|
| 实现责任完整读取精确输入 | 3/9 | 0.6 |
| 独立正确实际构建（implement、pair） | 0/18 | 0 |
| 独立正确固定提交（implement、pair、chain） | 0/27 | 0 |
| 短复核完整读取独立证据 | 2/9 | 0.5 |
| 正确且有据的复核决定（review、chain） | 0/18 | 0 |
| 本轮真实适用basis送达（pair、chain） | 15/18 | 3.0 |

分项分母按原责任合同；chain没有单独的正确build奖励项，不将未设该项的9例补成“build评分为零”。

## 读取、修改、执行之间的差别

在有implementer的27例中，13例实际读取适用basis，11例实际读取data。7次 `sql_build` 成功返回SQL执行结果：全部使用当时实际current code，但都是原 `code@v1`；其中6次把basis列为真实输入，5次构建请求确实保留了此前basis读取返回。原程序没有实现basis政策，因此来源被加载、依据出现在输入上下文，不等于已经用于正确的业务逻辑。

实际有12次写code：10次改变code内容，2次只是原程序原样复制。10次改变又分为：

- 5次写入裸 `sql` 或 `queries` 容器，包含SQL文本，但不符合公开执行器的 `models/tests/config` 程序结构。
- 5次把声称的结果表直接写入code；其中若干使用并不存在于这批真实客户中的 `A123`。

没有一次形成不同的、合法打包到models中的SQL并成功执行。旧通用诊断的 `models_projection_changed` 在删除models时也会为true，所以本报告特意保留其技术含义，并单列上述实际写入类型，避免称为“10次有效SQL修订”。另有3例手写result，不能替代真实SQL产物。总共2次实际submit均未达独立正确固定成果。

短复核9例中，7例读到固定code、7例读到固定result、7例读到适用audit；这些读取不一定同时满足完整决策证据。3次真实approve中，2次证据不完整，1次虽然证据齐全却批准了错误金额的固定产物。完整读取不自动给正确判断信用。

## 错误重试与实际恢复

539次真实工具调用中，269次外层调用ok、270次拒绝；另外9次 `sql_build` 虽外层ok，内部却为execution_error。因此按“拒绝或SQL执行失败”统计为279次，不把工具包装层的ok当SQL成功。

有87个“收到反馈后，同成员下一次实际工具调用仍为相同工具及参数”的转移；155个下一次调用改变了工具或参数，其中69个外层调用ok。后者只是操作变化或接受，不能统一称为有效修复。

对明确“缺少本work采用”的反馈，找到3次真实绑定恢复：

- **chain-f0-repeat0，slot9**：seq213/261拒绝缺basis采用；seq309真实adopt；seq333实际build使用该精确basis并执行成功。但仍运行原code，没有正确完整交付。这是1条可验证的“具体义务修复→实际执行”。
- **chain-f0-repeat2，slot11**：seq186缺basis；seq240实际adopt，此后没有使用该绑定的build，不能补称执行恢复。
- **pair-f1-repeat0，slot18**：seq111缺basis；seq134实际adopt；seq150起6次build都使用了该绑定，但code中写的是结果表，持续报 `Code declares only models/tests/config`。修好了采用绑定，仍未修好程序。

最常见拒绝包括：非收件人或向自己发manual request（88次）、read_alias访问未分享精确版本（44次）、handoff的provider/work lineage不符（33次）、build缺basis采用（21次）。这些是本协议下实际行动与权限/状态契约不符的记录，不能据错误标签推断模型在所有其他接口下也缺乏相应能力。

## 可核对的具体例子

序号均为当前episode原始联合事件sequence；准备动作不计入本轮。完整SHA在JSON的 `evidence_examples` 中，下列为experience SHA前12位。

| 例子 | 实际观察 | 证据路径（相对运行根） | SHA前缀 |
|---|---|---|---|
| implement-f0-r0，slot0 | seq8读audit遭拒，seq20起反复请求错误audit路由；合法basis起初可见 | `online/window-0/collection/slot-0/episode/experience.json` | `a7874e4c8d85` |
| implement-f0-r2，slot2 | seq8读data、32读basis、44运行code@v1、56固定提交；得读取0.2，内容失败 | `online/window-0/collection/slot-2/episode/experience.json` | `b7889e1c10a5` |
| chain-f0-r0，slot9 | 缺basis采用→真实修复→执行；完整成果仍未成立 | `online/window-0/collection/slot-9/episode/experience.json` | `22775455fe0d` |
| review-f1-r0，slot15 | 读固定result、audit、data、code并inspect，取得0.25；没有有效判断 | `online/window-0/collection/slot-15/episode/experience.json` | `207d24421882` |
| pair-f1-r0，slot18 | basis采用恢复后，结果表误写code导致重复内部执行失败 | `online/window-0/collection/slot-18/episode/experience.json` | `796c3834ebfa` |
| review-f2-r0，slot27 | seq8/32/56/93读result/audit/data/code，68inspect，105批准错误金额；仅得读取0.25 | `online/window-0/collection/slot-27/episode/experience.json` | `962b6518458f` |

运行根为 `runs/learning-v015-screen-qwen25-7b/`。这里复用了保存的评价与终局分项，未根据这些例子修改任务、提示、评分或重新评价。

## 成本与解释范围

GPU7单进程耗时5619.6254秒，约1.5610 GPU进程小时；共享GPU资源记录保留，这不是纯硬件计算时间。571次resident direct尝试，569次返回生成；真实生成消耗3,975,985输入token和37,785输出token，共4,013,770。2次上下文上限拒绝发生在生成之前；其预算保留量不追加为实际生成token。实际网络HTTP=0，更新=0。

方法标签有13条proactive_handoff、1条requested_handoff，其余22条无映射；标签不等于方法支持。原单窗口12个情境记录、21个成员块的b全部为空，组成自由度均为0，未执行ID‑VTDO。各情境M=3是本次筛选预算，不跨权重或其他实验拼接支持。

这个结果支持保留旧7B作为明确协议下的有限工作基线：可以取得资料、完成部分交接，并出现针对真实错误的局部状态修复；实现与复核尚未产出合同要求的完整成果。它不支持学习收益、其他模型排名或独立来源泛化结论。UCI的三个fact是同来源、按客户隔离的开发素材，仍属于模型选择资源。
