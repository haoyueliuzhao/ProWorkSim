# v0.23 外部 D2 六例：失败归因与评分解释边界

本页是结束后的只读核查，不新增模型调用、grader 重跑、隔离控制或评分修订。检查对象为 `runs/domain-v023/external_{initial,final}/actual/external/seed2026100{1,2,3}/` 的实际 actions、verification、OS execution、模型请求及冻结 adapter。三对种子的完整联合职责均为 0；这支持“本次指定 D2 变体未观察到完整职责提升”，不支持通用外部能力结论。

## 真实复核动作与最终声明必须分开

原始六例 `responsibility.verifier_computation_executed` 均为 false，但**不能据此写成六例均没有成功计算**。[冻结 adapter](../../runs/frozen-v023/src/proworksim/teambench_model_v023.py) 第 273–277 行先按最终 attestation 的 verification ID 选择 `check`，再计算此字段；因此它实际表示“最终声明引用了成功且返回合法表格的验证”。这是分项字段命名与可观察事实不完全对应的问题。原始结果不修改，本报告补充逐次动作口径。

| 端点／种子 | 实际 verify 次数 | 实际计算结果 | 最终职责断点 |
|---|---:|---|---|
| 初态 20261001 | 5 | 两次未闭合三引号 SyntaxError；两次写输出文件被拒；check-4 成功返回合法 JSON，逐格等于固定提交 | 成功后未 attest，达到角色生成预算；不能记为“无成功计算” |
| 初态 20261002 | 4 | 一次 `TypeError: unhashable type: 'list'`；三次写输出文件被拒 | 引用失败的 check-3 声明 pass，无实际成功计算支持 |
| 初态 20261003 | 1 | 写输出文件被拒 | 随后两次连续输出达到 2048 token 上限，按冻结格式边界停止，未 attest |
| 终态 20261001 | 0 | Executor 未显式提交，Verifier 未激活 | Executor 耗尽角色生成预算；grader 重跑产物不能替代固定交付 |
| 终态 20261002 | 2 | 两次写输出文件被拒 | 引用失败的 check-1 声明 pass，并将其称作 environmental issue，无实际成功计算支持 |
| 终态 20261003 | 1 | 写输出文件被拒 | 随后两次连续输出达到 2048 token 上限，按冻结格式边界停止，未 attest |

共 13 次 verify：9 次 PermissionError、2 次 SyntaxError、1 次 TypeError、1 次成功。成功证据为 [初态 001 的 verification-4.json](../../runs/domain-v023/external_initial/actual/external/seed20261001/verification-4.json)，其 `execution_succeeded`、`valid_expected_table`、`submitted_table_equal` 均为 true；对应源程序与工具回执保存在同目录 `actions.json`。该成功证明程序执行并与固定提交相等，**不证明其表格符合全部业务规则，也不证明两岗位推理独立**；本例双方都遗漏同一缺失数值行。

五个已提交 episode 均完整读取固定 code/input/output/spec，固定 workspace 未变且 grader 重跑逐字节重现提交输出。最终受有效计算支持的声明为初态 0/3、终态 0/3；任意成功表格计算则为初态 1/3、终态 0/3。两者不能混用。

## PermissionError 的实际原因

9 次错误均发生在模型程序以 `"w"` 模式打开 `data/output/clean.csv`；未发现读取已声明 input、spec 或以 stdout 返回 JSON 的合法路径遭错误拒绝。被冻结的公开工具说明明确要求：`input-only isolated copy`，并且 `Print exactly JSON {"columns":[strings],"rows":[[strings]]}`；Verifier 岗位合同也说明提交 output 不可读。实际模型请求中保留了同一说明，例如 [终态 002 的原始 model_attempt](../../runs/domain-v023/external_final/actual/external/seed20261002/model-calls/verifier/b3983d0b623dd5298f61259125511222f88de10f27f8ad40158f896659e5274a.json)。

实际代码却复用了会写结果 CSV 的 pipeline 路线。这与已公开的 input-only／stdout 表格合同不符，现有证据不支持把这些 PermissionError 归为“环境错误使合法验证失败”。初态 001 改成内存计算并 `json.dumps` 后实际成功，也提供了同一模型试验中的可行路径。既有 [CPU 准入](teambench-v023-model-adapter.md) 的正确控制亦通过，但它是 fake transport 控制，不计为真实模型成绩。以上判断只覆盖这 13 次调用，不构成任意程序和完整工具说明的充分性证明。

## 0.9 是有限 artifact 检查率，不是固定交付成功率

六例 grader 均通过 9/10 项 artifact predicates；加入仅检查 `pass` 声明的第 11 项后，初末 seed 002 为 10/11（原始 rounded partial score 0.91），其余四例为 9/11（0.82）。所以“0.9”应标为分解后的 artifact 检查率。原修订 grader 对实际验证执行／独立性不评分，本适配器另行要求显式固定提交、材料读取、有效计算支持的声明及重跑一致性。尤其终态 001 没有提交，仍可在评分复制区得到 9/10；不能据此补记模型交付成功。

六例唯一 artifact failure 均为 `wrong_row_count`。只读比较 input、固定产物／grading-copy 产物和 trusted expected：

| 种子 | grader 期望行数 | 两端实际行数 | 两端均遗漏的空数值输入行 |
|---|---:|---:|---|
| 20261001 | 32 | 31 | id 21，Sofia，rating 为空 |
| 20261002 | 22 | 21 | id 21，Kenji，rating 为空 |
| 20261003 | 29 | 28 | id 26，Ugo，score 为空 |

这一失败同时暴露了上游公开语义的解释边界。公开 [seed 001 spec](../../runs/domain-v023/external_initial/actual/external/seed20261001/roles-world/roles/verifier/private/spec.md) 写道：`Any cell with empty string or "N/A" must be replaced with "MISSING"`，以及 `rating must be between 0 and 100 inclusive`。它未明确写出缺失数值对 range 的豁免、以及 MISSING 的排序位置。与之相比，[实际归档 generator](../../runs/domain-v023/external_initial/actual/external/assets/reviewed/generators/gen_d2_data_quality.py) 第 153–166 行明确保留空数值行，第 168–172 行填 MISSING，第 184–188 行将其排序数值设为 -1。原始 buggy code 保留空值也提供了线索，但不等于公开规范已完整表述这些规则。

因此，本页保留预声明 grader 的原分数与 failure modes，不事后把行数失败改为通过；同时也不将该缺失值语义解释问题简化为通用业务能力失败。原始 `wrong_approval` 标记受该 artifact 判定影响，应连同此限制阅读；“引用失败计算作 pass 的声明缺少工具证据支持”则可由动作记录独立确认。六例完整职责为 0 还分别有未交付、未声明或未绑定成功验证等独立缺项，不依赖只把缺失数值行判错。三对同一合成来源种子不足以估计广泛迁移、显著性或学习效果大小。
