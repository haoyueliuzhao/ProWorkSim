# v051 CAL2最终唯一合并

本报告以原r1+r2阶段合并为单一前阶段来源，只增加r3原七条库存。大段原记录仍在原件，各行以path、SHA及JSON位置追溯，未重复嵌入或重新生成45MB阶段报告。

原3条真实P/U轨迹代码未知、原R零生成失败历史及r2三条受socket环境故障影响的严格代码未知均保留。旧raw得分不是有效业务失败；boltons-2/U的无固定提交R_joint=0保持。原四历史尝试和R双历史层未删除。

## 原18槽指标与费用

宿主终态`complete`；槽状态`{'technical_unknown': 6, 'closed': 12}`。固定18槽全部来源闭合：`False`。报告只读取原件，不新增模型、评分、分词或更新。

R为原始mini-SWE单agent，P为原始模型的ProWorkSim S1，U为S_star actor4/4的同一S1。三条件均用同一project数值路径、独立fresh resident和原任务初态；R_code比较各自最终工作树。P/U的R_joint只衡量固定交付，R对此不适用，不能填0。

## 末树代码正确性：来源绑定

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| R | 4/6 | null | [0.0, 0.3333333333333333] |
| P | 4/6 | null | [0.0, 0.3333333333333333] |
| U | 4/6 | null | [0.3333333333333333, 0.6666666666666666] |
| P_minus_R | paired/6 | null | [-0.3333333333333333, 0.3333333333333333] |
| U_minus_P | paired/6 | null | [0.0, 0.6666666666666666] |

## 末树代码正确性：原记录

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| R | 6/6 | 0.000000 | [0.0, 0.0] |
| P | 4/6 | null | [0.0, 0.3333333333333333] |
| U | 5/6 | null | [0.3333333333333333, 0.5] |
| P_minus_R | paired/6 | null | [0.0, 0.3333333333333333] |
| U_minus_P | paired/6 | null | [0.0, 0.5] |

## 完整原测试观察分数：来源绑定

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| R | 4/6 | null | [0.5196712018140589, 0.8530045351473922] |
| P | 4/6 | null | [0.5230725623582767, 0.85640589569161] |
| U | 4/6 | null | [0.5425170068027211, 0.8758503401360543] |
| P_minus_R | paired/6 | null | [-0.32993197278911546, 0.33673469387755106] |
| U_minus_P | paired/6 | null | [-0.3138888888888889, 0.35277777777777763] |

## 固定交付：仅P/U

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| P | 4/6 | null | [0.0, 0.3333333333333333] |
| U | 5/6 | null | [0.3333333333333333, 0.5] |
| R | N/A | N/A | N/A |
| U_minus_P | paired/6 | null | [0.0, 0.5] |

每题等权，不按原测试数量、成功、提交或提前终止筛选。任一相关未知使完整均值或配对差保持null；界限只是未知结果在[0,1]内的范围。原结果与来源绑定口径并列，原非空值不因缺证被删除。

## 完整18槽与原测试观察

| 槽 | 原R_code | 绑定R_code | 原Q_terminal | 绑定Q_terminal | R_joint | 行政删失 | 测试已观察/总数 | 未运行 | 状态 |
|---|---:|---:|---:|---:|---:|---|---|---:|---|
| v051-cal2-boltons-1-R | 0 | null | 0.992718 | null | N/A | False | 412/412 | 0 | technical_unknown |
| v051-cal2-boltons-1-P | null | null | null | null | null | False | 0/412 | 412 | technical_unknown |
| v051-cal2-boltons-1-U | null | null | null | null | null | False | 0/412 | 412 | technical_unknown |
| v051-cal2-boltons-2-P | null | null | null | null | null | False | 0/412 | 412 | technical_unknown |
| v051-cal2-boltons-2-U | 0 | null | 0.992718 | null | 0 | False | 412/412 | 0 | technical_unknown |
| v051-cal2-boltons-2-R | 0 | null | 0.992718 | null | N/A | False | 412/412 | 0 | technical_unknown |
| v051-cal2-parse-1-U | 0 | 0 | 0.663265 | 0.663265 | 0 | False | 98/98 | 0 | closed |
| v051-cal2-parse-1-R | 0 | 0 | 0.642857 | 0.642857 | N/A | False | 98/98 | 0 | closed |
| v051-cal2-parse-1-P | 0 | 0 | 0.663265 | 0.663265 | 0 | False | 98/98 | 0 | closed |
| v051-cal2-parse-2-R | 0 | 0 | 0.591837 | 0.591837 | N/A | False | 98/98 | 0 | closed |
| v051-cal2-parse-2-P | 0 | 0 | 0.591837 | 0.591837 | 0 | False | 98/98 | 0 | closed |
| v051-cal2-parse-2-U | 0 | 0 | 0.591837 | 0.591837 | 0 | False | 98/98 | 0 | closed |
| v051-cal2-xmltodict-1-P | 0 | 0 | 0.933333 | 0.933333 | 0 | False | 60/60 | 0 | closed |
| v051-cal2-xmltodict-1-U | 1 | 1 | 1.000000 | 1.000000 | 1 | False | 60/60 | 0 | closed |
| v051-cal2-xmltodict-1-R | 0 | 0 | 0.933333 | 0.933333 | N/A | False | 60/60 | 0 | closed |
| v051-cal2-xmltodict-2-U | 1 | 1 | 1.000000 | 1.000000 | 1 | False | 60/60 | 0 | closed |
| v051-cal2-xmltodict-2-R | 0 | 0 | 0.950000 | 0.950000 | N/A | False | 60/60 | 0 | closed |
| v051-cal2-xmltodict-2-P | 0 | 0 | 0.950000 | 0.950000 | 0 | False | 60/60 | 0 | closed |

Q_terminal的分母固定为完整原测试集合。源码归因成立的collection失败可使R_code=0；未运行节点列为not-run，不能说这些节点执行后失败。此时已观察通过数/完整分母是保守观察分数，逐槽还列出缺节点及全节点结果界限。runner、权限或来源故障保留未知。

## 费用、停止与资源

CAL2实际已知 **4661175 token**，不确定预约 **0 token**，预约金额本身未知的请求0个；完整实际费用`4661175`。实际开始430次、完整回包430次；已准备但未派发0次。预约不是已知收费。

worker唯一19个区间，共6212.898455秒（1.725805小时）。装载、生成、测试与闭合已包含在内，不加嵌套时长。CAL1费用只在可选附列中给出，未加入CAL2费用。

逐槽JSON保留context与预算执行前拒绝原件、宿主测量判定、原停止和中断回执。安全预算/context终止不自动变成技术未知；真实fault、费用/副作用或worker绑定未决不能填0。行政soft截止保留joint-policy观察；P/U的R_token在实际删失时保持null，不冒称纯token估计。

## 解释范围

只有三个公开仓库的六个人工合成缺陷任务；不是外部真实自然issue总体。R允许最多128次原生bash行动，P/U至多32次项目公开测试，界面、可用动作和交付流程不同，P−R并非单一组件的因果分离。末树代码正确性与固定交付不能互换。U−P仅描述本固定面板上的保留actor差异；没有新训练，不从有限任务推广一般协作、通用能力或训练收益。没有读取HOLD任务，也不自动启动下一阶段。

来源/测量未决：`[{"kind": "historical_preserved_issues", "source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/docs/experiments/software-calibration-v051-cal2-r2-stage.json", "bytes": 45031062, "sha256": "b4f0a9875230efd7ef7c44f93e440aaa3f3ba77449f8e394689301c8884a48d7"}, "json_pointer": "/integrity_issues"}]`。

完整六题P−R与U−P点估计仍null；不能用已知子集、raw固定交付0或环境失效raw代码0补全未知。费用独立于代码评分有效性，前阶段原227,876token已包含在r1+r2单一小计内，不再另加。本报告不启动HOLD或任何后继，来源/初始输入资格仍须独立准入。
