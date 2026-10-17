# v050 最终方法与完整状态证据

这是最终报告的方法附录。全部信息来自已保存的原生运行/逐槽/collection guard与JSON凭据，本次没有加载checkpoint张量或增加前向、反向、验收。

## 本人目标与原分母

实际新材料包含643条Γ1 native input（8,793,409输入token）及175,532个本人输出token；上下文不是本人目标。48条成员轨迹均保留，actor按48T、critic按48K归一，拒绝决定不计入K。各成员的输出与调用分母如下。

| 槽 | 成员 | T本人输出 | K生成决定 | 48T | 48K |
| --- | --- | --- | --- | --- | --- |
| org50-train-LA-r01 | member_001 | 2090 | 7 | 100320 | 336 |
| org50-train-LA-r01 | member_002 | 1854 | 7 | 88992 | 336 |
| org50-train-LA-r02 | member_001 | 3035 | 14 | 145680 | 672 |
| org50-train-LA-r02 | member_002 | 2250 | 10 | 108000 | 480 |
| org50-train-LA-r03 | member_001 | 3389 | 15 | 162672 | 720 |
| org50-train-LA-r03 | member_002 | 3155 | 10 | 151440 | 480 |
| org50-train-LA-r04 | member_001 | 2136 | 7 | 102528 | 336 |
| org50-train-LA-r04 | member_002 | 2201 | 7 | 105648 | 336 |
| org50-train-LA-r05 | member_001 | 2731 | 8 | 131088 | 384 |
| org50-train-LA-r05 | member_002 | 3343 | 13 | 160464 | 624 |
| org50-train-LA-r06 | member_001 | 2858 | 9 | 137184 | 432 |
| org50-train-LA-r06 | member_002 | 4272 | 13 | 205056 | 624 |
| org50-train-LA-r07 | member_001 | 2163 | 8 | 103824 | 384 |
| org50-train-LA-r07 | member_002 | 2569 | 10 | 123312 | 480 |
| org50-train-LA-r08 | member_001 | 2114 | 13 | 101472 | 624 |
| org50-train-LA-r08 | member_002 | 2595 | 10 | 124560 | 480 |
| org50-train-LA-r09 | member_001 | 2735 | 8 | 131280 | 384 |
| org50-train-LA-r09 | member_002 | 3828 | 11 | 183744 | 528 |
| org50-train-LA-r10 | member_001 | 6934 | 22 | 332832 | 1056 |
| org50-train-LA-r10 | member_002 | 2668 | 9 | 128064 | 432 |
| org50-train-LA-r11 | member_001 | 3184 | 10 | 152832 | 480 |
| org50-train-LA-r11 | member_002 | 11876 | 25 | 570048 | 1200 |
| org50-train-LA-r12 | member_001 | 9009 | 23 | 432432 | 1104 |
| org50-train-LA-r12 | member_002 | 2438 | 12 | 117024 | 576 |
| org50-train-LB-r01 | member_001 | 4073 | 17 | 195504 | 816 |
| org50-train-LB-r01 | member_002 | 4149 | 18 | 199152 | 864 |
| org50-train-LB-r02 | member_001 | 2091 | 10 | 100368 | 480 |
| org50-train-LB-r02 | member_002 | 9447 | 25 | 453456 | 1200 |
| org50-train-LB-r03 | member_001 | 3375 | 12 | 162000 | 576 |
| org50-train-LB-r03 | member_002 | 3251 | 16 | 156048 | 768 |
| org50-train-LB-r04 | member_001 | 4307 | 12 | 206736 | 576 |
| org50-train-LB-r04 | member_002 | 7311 | 19 | 350928 | 912 |
| org50-train-LB-r05 | member_001 | 5276 | 18 | 253248 | 864 |
| org50-train-LB-r05 | member_002 | 3666 | 12 | 175968 | 576 |
| org50-train-LB-r06 | member_001 | 2456 | 11 | 117888 | 528 |
| org50-train-LB-r06 | member_002 | 4815 | 15 | 231120 | 720 |
| org50-train-LB-r07 | member_001 | 2916 | 15 | 139968 | 720 |
| org50-train-LB-r07 | member_002 | 2314 | 14 | 111072 | 672 |
| org50-train-LB-r08 | member_001 | 2680 | 12 | 128640 | 576 |
| org50-train-LB-r08 | member_002 | 2509 | 17 | 120432 | 816 |
| org50-train-LB-r09 | member_001 | 3361 | 17 | 161328 | 816 |
| org50-train-LB-r09 | member_002 | 2757 | 15 | 132336 | 720 |
| org50-train-LB-r10 | member_001 | 2861 | 16 | 137328 | 768 |
| org50-train-LB-r10 | member_002 | 2133 | 10 | 102384 | 480 |
| org50-train-LB-r11 | member_001 | 2765 | 11 | 132720 | 528 |
| org50-train-LB-r11 | member_002 | 4186 | 20 | 200928 | 960 |
| org50-train-LB-r12 | member_001 | 3579 | 17 | 171792 | 816 |
| org50-train-LB-r12 | member_002 | 3827 | 13 | 183696 | 624 |

## 更新与critic

原H=1函数和prepare_window code object保持同值，完整recipe、函数摘要、实际输入/目标和恢复声明见机器报告的update_method及provenance.branches。三分支的643个旧critic值、优势和reward逐项相同，actor组成变化不扩展到critic。

原报告中的zero-initialized措辞是历史模板；实际继承的4/4 critic已有非零值，不能解释为本轮重置。共有121条负优势和522条正优势，没有只保留成功材料。

现有collection-guard中的最终critic摘要为 `6c8798957f3a6a06fc46cf1354bda01e585763d46c6377fbdc6d54a1fbcdc80a`；critic Adam摘要为 `845bac005760936b72e849639a6fd728e6ecde94db6f9f41c1e40fe41e0b5fa4`，三分支完全同值。actor及其Adam分别不同。守卫摘要相等是既有运行时证据，本报告没有重做逐元素张量比较。

## 完整状态摘要

S*来自v049 B4/4，完整state_tensor_digest为`ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39`。common-restore3/3只是模型构造中间步骤，实际更新前loaded-state明确恢复S*4/4。

| 分支 | 最终actor SHA256 | 完整state_tensor_digest | 重载精确 |
| --- | --- | --- | --- |
| B | 18f5fd7d61330aef9210965909d42b33944131fa94abc27c8846ca057317d465 | d68647eaac7bb17b1ba742e15253c90011f2b7d6092352b427849b60b10f8742 | true |
| Q+ | 7a76e93826a90052c400505bc407a30f9ff067e99fd1d1537e5d551678e69207 | 837d5c24208b27934b11597d587e65e0fe75c38873107d77996da872c45ab35e | true |
| Q− | 52dc58b5419c101b66045a7030c81b8ea0db1842ab3330a00a45563aa13e4995 | 7819339078757a64e3b1d91bb9ebcea0944921d3862b46f481455f79e347d6db | true |

## 计算计数的范围

成功分支各1288次wrapper前向和643条逐决定反向；整个窗口还包括旧失败尝试。总计算及下界/上界见主报告和costs.json。生成token只计算实际1527次生成调用，不将训练重复读取本人输出折成新生成费用。

## 报告复核

本次构建执行36项确定性报告一致性断言；另有来源审阅503项JSON比较。二者属于只读分析，不增加pytest或模型资格数量。复现此文档构建可从仓库根执行 `.venv/bin/python docs/experiments/software-learning-v050-final-evidence/build-final-report.py`，它仅消费同目录保存的分析JSON；原件提取脚本亦保存在证据目录，执行它们需要对应runs原件。
