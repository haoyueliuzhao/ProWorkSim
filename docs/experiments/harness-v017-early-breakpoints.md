# H1早期工作断点：8段已闭合native片段

观察时间：2026-09-27T02:04:53.027518+00:00。

范围仅为两模型首个native窗口的slot 0–3，各两个实现和两个复核，均为repeat 0。它们是正在进行的H1里的既有8段闭合记录，**不是新增8个样本，不是全H1结果，不含SDK对照，也不构成完整模型排名**。没有运行模型、SQL、评价器或正确SQL参考计算，没有改变提示、环境、输出或评分。

下列每条观察绑定R（原rollout/已存评价）、X（完整实际经历）、T（runtime终态）文件及SHA；完整路径、JSON pointer和SHA也逐项保存在[结构化证据](harness-v017-early-breakpoints.json)。大段原生成、SQL和提示只通过引用保存。

| 观测 | 模型 | 任务 | 原奖励/完整责任 | 已存工作断点 | 证据 |
|---|---|---|---|---|---|
| E1 | qwen35-9b | uci-harness-f0-implement | 0.2 / False | 第6次决策的build发生CatalogException（data.customers对应schema不存在）；第10次build执行success，此时角色剩余决策为0。已存correct_actual_build=false，无submit；现有逐build记录未保存具体业务差异，不能据此补算或断言金额哪里错。 | R1 / X1 / T1 |
| E2 | qwen35-9b | uci-harness-f1-implement | 1.0 / True | 第6次build已有独立正确构建信用；第7次submit成功并取得完整责任R=1。之后继续读取消息/固定提交，第10次机会因上下文上限停止。这个后续停止没有抹掉已完成的固定交付。 | R2 / X2 / T2 |
| E3 | qwen35-9b | uci-harness-f2-review | 0.25 / False | 取得复核依据后，第6次生成到输出上限；下一次生成登记了一个blocking issue，没有approve。既有独立评价对原固定提交记录为pass，correct_review_decision仍false。issue被世界登记不等于质疑成立；本分析不重算其数值主张。随后出现上下文上限停止。 | R3 / X3 / T3 |
| E4 | qwen35-9b | uci-harness-f3-review | 0.25 / False | 取得复核依据后，第6和7次生成均到输出上限，达到连续格式错误门槛停止。没有approve或raise_issue实际调用。 | R4 / X4 / T4 |
| E5 | qwen38-27b | uci-harness-f0-implement | 0.2 / False | 实际做了两次build：第7次被受限执行器以allowlist:not拒绝，第9次为TIMESTAMP/VARCHAR比较的BinderException。第10次再次修改代码，但闭合前没有新的build或submit。R=.2来自确切输入读取，不是没有尝试SQL。 | R5 / X5 / T5 |
| E6 | qwen38-27b | uci-harness-f1-implement | 0.2 / False | 第7次build同样被受限执行器以allowlist:not拒绝；第9次build执行success，第10次preflight结构通过。已存correct_actual_build=false、没有submit；preflight明确不评价业务数值。原记录未保存该未提交build的逐项业务差异，不能补判其具体计算错误。 | R6 / X6 / T6 |
| E7 | qwen38-27b | uci-harness-f2-review | 0.25 / False | 取得复核依据后，尝试读取一个未共享版本遭拒；第8次选择staff_done，reason以“Approving.”结束，但没有approve调用。既有独立评价记录原提交pass，正式复核未完成；工作人员结束和正式批准必须分开。 | R7 / X7 / T7 |
| E8 | qwen38-27b | uci-harness-f3-review | 0.25 / False | 第2次多调用被整体拒绝；后来尝试raise_issue，但其locator不存在于精确版本，世界拒绝登记。另有未共享版本读取拒绝，没有approve/decide_issue。既有固定提交内容评价为content_failure，但缺少有效正式复核行动，最终达到角色决策上限。 | R8 / X8 / T8 |

## 多调用反馈到达与后续动作

27B在E5、E6、E8分别生成2、3、5个原生调用，被同一“至多一个调用”规则整体拒绝，三次均没有世界动作。对应公开反馈在同角色下一次实际request、owner的actual_prompt_messages和rendered_prompt中逐项相同。随后三次生成均改为一个read_version调用、finish_reason为tool_calls。这里只陈述时序和实际输入匹配，**不证明反馈导致了改正，更不证明后续业务工作成功**。证据为X5/X6/X8的format-feedback与下一model-attempt，加下表owner原提示文件。

9B的E3下一次生成从输出截断转为单个raise_issue；E4下一次仍截断，随后到连续错误上限。这同样只能说明输出与执行的实际次序，不能以“已收到反馈”等同于“充分利用反馈”。证据X3/X4、T3/T4。

## allowlist:not的解释边界

E5/E6的首个build错误来自**受限执行器拒绝**，并不自动说明业务SQL错误。两段实际提交SQL局部存在：

- E5：`NOT (LOWER(TRIM(r.InvoiceNo)) LIKE 'c%')`，证据X5 sequence66的write_object参数。
- E6：`NOT (UPPER(InvoiceNo) LIKE 'C%')`，证据X6 sequence66的write_object参数。

[冻结执行器第132行](/data1/zhuxinrui/projects/ProWorkSim/runs/frozen-v017-h1/src/proworksim/domains/executable_project.py:132)用标识符后跟左括号识别候选函数，再检查函数集合；not未列入该集合。因此，guard将NOT(...)识别为函数是一种有源码和原SQL局部支持的候选解释。没有独立重放guard或SQL来验证该解释，也没有证明这些SQL满足业务合同。源码SHA256：`fc3d039c914af24882fb761fcffce500162a78baba02186f2a64ad41db53d4e3`。

本轮H1保持冻结；H2后继也已单独冻结，不临时扩大SQL支持或回填旧成绩。执行器限制与模型工作选择需要分别记录，不能把修环境的影响混入学习收益。

## 证据索引（完整SHA256）

- R1：[team-rollout.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-0/team-rollout.json)；`a9827dabde2cdcf19df63b5b748c19b849dfb0fd4d8f84b79e5daba95de0715b`。
- X1：[experience.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-0/episode/experience.json)；`e17c03a47a5eb3451c0fb79320c9aebdbc1b2b744b94aed61534fe5b9fee1a33`。
- T1：[runtime.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-0/runtime.json)；`c69d796166b895fac985968efc1f8af07e1dd71bd9d54545dea03f6ed8f8cc9e`。
- R2：[team-rollout.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-1/team-rollout.json)；`10e711c2da1cedb32bca0b4dda83470d80701ac023c7a33b22cd925c4660db41`。
- X2：[experience.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-1/episode/experience.json)；`14c5bfc5eec15c73a003ec9f57d2f5a6d936198cac2d671245506e59bdc6c976`。
- T2：[runtime.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-1/runtime.json)；`46b628f37ef1987ad41d4a5711d1d999baa714a4efe900fcd1121fad1177b0bb`。
- R3：[team-rollout.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-2/team-rollout.json)；`e8ef73f4b6825a59603b3a8a9c6c750d5faa5db3edb10044f56f71f1dc0173bb`。
- X3：[experience.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-2/episode/experience.json)；`f93a1426b6b33a6c2893a4fcf9745315cc74433ded950c6cf9f30bb44a16dfd8`。
- T3：[runtime.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-2/runtime.json)；`527a8b1e6c47ee0f609f3d18124f6487f98bfee00c72fe40798c4bd8849961ec`。
- R4：[team-rollout.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-3/team-rollout.json)；`7b4d98f6bcbdeb920cf9fb50cd0bcda0b1b3011064415c473eeb2593ebdf39ba`。
- X4：[experience.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-3/episode/experience.json)；`c5334222de313d7769bacf8833af7c32b5d0c9bf0a828cab9ce60fffeb68a1f7`。
- T4：[runtime.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen35-9b/online/window-0/collection/slot-3/runtime.json)；`5c073e58ab0c264649d7121d17cb6894bbbd48bc49c64bc408e35e62c52b9b4a`。
- R5：[team-rollout.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-0/team-rollout.json)；`01b8479252261467515676ca3749d885f69f52dbfffa8026563437088be0f460`。
- X5：[experience.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-0/episode/experience.json)；`c3bc5df737e19feb28cac892af80f049e3c7b4cc7d8a4451fc5569463090b4af`。
- T5：[runtime.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-0/runtime.json)；`e076324f9e0f1f0c26f8ef3ef9c16f31b94547df4af8c8f175d39a1a0cabae38`。
- E5多调用后提示：[resident_e0ef97d1e65e493cb131289880fa657a.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/resident/calls/resident_e0ef97d1e65e493cb131289880fa657a.json)；`256911dd32c8ba0bc4653e082e839b994b0baf85f2fa52cc9d3c4076153cf2be`；下一调用 `model-c4331cb092caad6d88c983e9`。
- R6：[team-rollout.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-1/team-rollout.json)；`26960b6040658c025efc1d7f447c8caca64189ec65aa1d03409181a597c0d2d9`。
- X6：[experience.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-1/episode/experience.json)；`6d89b88e57769e6ddf06eee210d373601a8236231a9baf694cc28e5fd9306b93`。
- T6：[runtime.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-1/runtime.json)；`184cce0d82337d604eadc22cb0be88b37880d0e552677c79d02cccff5bad9df9`。
- E6多调用后提示：[resident_c62ebec352ae46eba6ffb263beb9a5d9.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/resident/calls/resident_c62ebec352ae46eba6ffb263beb9a5d9.json)；`1fc473405c94e312fda8427fb9dff39eb8b33c619c35167b4274cb96f48b3ef9`；下一调用 `model-bc7a0ed08d11adedd294c801`。
- R7：[team-rollout.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-2/team-rollout.json)；`330e0a6a1800c07558a12ba06e242a4c163654613117c41b9f64d3da6f10f8e7`。
- X7：[experience.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-2/episode/experience.json)；`453dba3231ed37c148b9041d549a9df0dc7b009f805d6f652baa4da0020ccfae`。
- T7：[runtime.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-2/runtime.json)；`90b45566ab040317cf2841c273c38a8760056d353d7965613a40e697e0a61638`。
- R8：[team-rollout.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-3/team-rollout.json)；`08bea6d415e1d68207c8f44b2ffd2ababc6dd21acb5009824b70b0ad3a9e8b11`。
- X8：[experience.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-3/episode/experience.json)；`09100b66f90af686830915b4ca2418fe7f5124c9bd585276d426d99407b6c2e6`。
- T8：[runtime.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/online/window-0/collection/slot-3/runtime.json)；`3d95bfe1d7c9f14661d44bf0d80e23ea1411428defcea41ca658675bfe492673`。
- E8多调用后提示：[resident_dbd1d529f0ac4853bb3a577b433e0b93.json](/data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-h1-qwen38-27b/resident/calls/resident_dbd1d529f0ac4853bb3a577b433e0b93.json)；`fe6d30a3a5b1db529a7060f10e32be8d3684f37862f2d74e3ac6303520ae23c5`；下一调用 `model-2ec4b12641dca09fb4a5a572`。

该片段没有覆盖后续重复、SDK或完整团队工作。行为原因保持未知，不使用“模型忘记了”等未经证实的解释。
