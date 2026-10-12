# v049 原库存：r1 只读归因修订与接续报告

原5槽与新3训练槽合并为唯一原8槽，开发仍为原三个分支各4单位，合计原20槽。原unknown解释、原停止、R与全部费用保留；r1解释修订不算策略收益。
旧阶段GPU worker秒 2162.429730653763；新阶段 32796.446522951126；合计 34958.87625360489。原S0仅在旧阶段计一次的新复用凭据：True。
保留原5槽生成：119次/1617987token；新阶段：None次/Nonetoken。旧生成不再额外加到20槽合计。

原运行状态：`closed_with_unknowns`。固定库存20槽，状态：`{'closed': 9, 'technical_unknown': 1, 'not_started': 2, 'conditional_not_applicable': 8}`。
实际费用已知部分 3363861 token；完整实际费用 None；完整实际调用 None。
本窗口两阶段GPU worker合计小时：9.710798959334692（含S0、采集、学习、开发；不重复加嵌套时长）。

## 更新后配对开发

F使用正式R_joint；每分支原4单位全部已知才计算均值。行政关闭的R_token/Q_token仍保留null。

| 分支 | 状态 | F | Q | 完整回合token |
|---|---|---:|---:|---:|
| B | {'closed': 1, 'technical_unknown': 1, 'not_started': 2} | None | None | None |
| Q_plus | {'conditional_not_applicable': 4} | None | None | 0 |
| Q_minus | {'conditional_not_applicable': 4} | None | None | 0 |

Q+−B：None；Q−−B：None；epsilon：None；有限差分：None。
二元F分辨率为0.25。未更新状态没有开发执行，不能推断B相对训练前收益；零差不是精确C=0。

## 原20槽库存

| 槽 | 阶段/分支 | 状态 | R_joint | Q_joint | 行政删失 | 完整token | 已知token |
|---|---|---|---:|---:|---|---:|---:|
| org49-train-LA-r1 | training/S0 | closed | 1 | 1.0 | False | 182504 | 182504 |
| org49-train-LA-r2 | training/S0 | closed | 1 | 1.0 | False | 493282 | 493282 |
| org49-train-LA-r3 | training/S0 | closed | 1 | 1.0 | False | 196209 | 196209 |
| org49-train-LA-r4 | training/S0 | closed | 1 | 1.0 | False | 448905 | 448905 |
| org49-train-LB-r1 | training/S0 | closed | 1 | 1.0 | False | 495438 | 495438 |
| org49-train-LB-r2 | training/S0 | closed | 1 | 1.0 | False | 250554 | 250554 |
| org49-train-LB-r3 | training/S0 | closed | 1 | 1.0 | False | 270431 | 270431 |
| org49-train-LB-r4 | training/S0 | closed | 1 | 1.0 | False | 495265 | 495265 |
| org49-dev-DA-s1-B | development/B | closed | 1 | 1.0 | False | 491926 | 491926 |
| org49-dev-DA-s2-B | development/B | technical_unknown | None | None | None | None | 39347 |
| org49-dev-DB-s1-B | development/B | not_started | None | None | None | 0 | 0 |
| org49-dev-DB-s2-B | development/B | not_started | None | None | None | 0 | 0 |
| org49-dev-DA-s1-Q_plus | development/Q_plus | conditional_not_applicable | None | None | None | 0 | 0 |
| org49-dev-DA-s2-Q_plus | development/Q_plus | conditional_not_applicable | None | None | None | 0 | 0 |
| org49-dev-DB-s1-Q_plus | development/Q_plus | conditional_not_applicable | None | None | None | 0 | 0 |
| org49-dev-DB-s2-Q_plus | development/Q_plus | conditional_not_applicable | None | None | None | 0 | 0 |
| org49-dev-DA-s1-Q_minus | development/Q_minus | conditional_not_applicable | None | None | None | 0 | 0 |
| org49-dev-DA-s2-Q_minus | development/Q_minus | conditional_not_applicable | None | None | None | 0 | 0 |
| org49-dev-DB-s1-Q_minus | development/Q_minus | conditional_not_applicable | None | None | None | 0 | 0 |
| org49-dev-DB-s2-Q_minus | development/Q_minus | conditional_not_applicable | None | None | None | 0 | 0 |

## 学习剂量与完整状态

| 分支 | 更新状态 | actor步 | critic步 | 完整反向决定 | actor梯度norm | actor与B同值 |
|---|---|---:|---:|---:|---:|---|
| B | updated | 1 | 1 | 206 | 0.050031084567308426 | None |
| Q_plus | None | 0 | 0 | 0 | None | None |
| Q_minus | None | 0 | 0 | 0 | None | None |

前向、反向、optimizer、支持观察、完整原材料规模和保存恢复凭据详见JSON中的updates/consumption及原文件引用。这里未加载checkpoint张量比较critic/Adam，不把参数摘要比较写成额外模型实验。

## 真实支持

| root/member | M | 实际重复 | 基础轨迹 | n支持 | v | 类数量/计数 | b |
|---|---:|---:|---:|---:|---:|---|---|
| LA/member_001 | 4 | 4 | 4 | 3 | 0.75 | 1/{'local_lineage_delivery': 3} | {'local_lineage_delivery': 1.0} |
| LA/member_002 | 4 | 4 | 4 | 3 | 0.75 | 1/{'local_lineage_delivery': 3} | {'local_lineage_delivery': 1.0} |
| LB/member_001 | 4 | 4 | 4 | 3 | 0.75 | 1/{'local_lineage_delivery': 3} | {'local_lineage_delivery': 1.0} |
| LB/member_002 | 4 | 4 | 4 | 3 | 0.75 | 1/{'local_lineage_delivery': 3} | {'local_lineage_delivery': 1.0} |

各成员原优势、mask、未映射/缺证原因及梯度方向检查保存在JSON。可信失败、未提交与残余材料不按成功筛掉；缺失槽不转移质量。原工作采用链只作Mapper事实，不能直接解释为正Contribution或一般协作收益。

## 记录边界

机械判断：`{'continue': 9}`；读原件时发现的问题数：0。
本报告只读同一v049原库存的旧/新阶段，不运行模型、tokenizer、世界或验收；原5槽成本仅计一次，不加其它旧实验成本。未开始与条件不适用均保留，未知结果和完整费用保持null。完整JSON包含所有源文件引用、worker成本、recipe/S0身份、配对逐单位差及未决记录。

原件与新解释逐槽对照保存在JSON的original_interpretation/record_interpretation_receipt；原阶段及r1阶段源码身份、旧停止凭据和物化来源单列。训练前未更新开发基线仍缺席，完整critic/Adam张量比较未执行。
