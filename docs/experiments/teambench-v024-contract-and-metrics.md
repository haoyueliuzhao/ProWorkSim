# v0.24 D2：公开缺失数值规则与验证指标窄修订

本轮只完成适配层修订、必要 CPU 控制和三项定向测试。真实外部模型 episode、参数更新、API 调用、GPU 秒数均为 **0**。原 v0.23 六例的源、分数、标签和报告不修改；旧种子 20261001–20261003 已属开发材料。内部 v0.24 的 GPU 预算不分配给外测；未来外测建议为三个新种子、三个预定 checkpoint 共九例，当前没有生成这些种子、加载模型、加入队列或启动外部评价。

## 公开规则及审计文字的一处方向纠正

审计建议延续 generator，却把缺失排序写成“在普通数值之前”。固定 generator 第 184–188 行实际将 `MISSING` 的排序数值置为 −1，键为 `(-score, name)`；固定 grader 使用相同键。因此，数值降序下 **MISSING 在正常 0–100 之后**。本次依据可执行来源明确这一方向，没有把 generator 或 grader 改成缺失优先。

新版公开补充合同逐字投递给 Executor，Verifier 和其 input-only 计算副本也读取相同补充：缺失数值保留并填为 `MISSING`；缺失免于普通 0–100 范围过滤；排序视为 −1，位于普通数值之后；同值继续按 `name` 升序。准备动作有明确程序归属，不给模型新增交接信用。原 generator 产出的 `workspace`、expected 和旧 spec 都保留，新的 episode 只在自己的材料复制区追加公开条款；准备记录保留原 spec 与新 spec 的 SHA。

CPU 人工表的实际顺序为 `100/High → 0/Zero → MISSING/Alpha → MISSING/Zulu`。八个固定内容谓词全通过；把两条缺失行移到数值前，只触发 `sort_order_wrong`；删掉缺失行，只触发 `wrong_row_count`。这同时见证范围豁免和缺失间同值排序，不是新模型成绩。

## 指标及最终声明绑定

| 字段 | v0.24 定义 |
|---|---|
| `verification_attempted` | episode 是否实际发起过 `verify_submission`，包含参数被拒的尝试 |
| `verification_execution_succeeded` | 任意一次验证程序 returncode 为 0 且未超时；不要求最终声明 |
| `verification_table_valid` | 任意一次返回结构合法的四列表格；不是业务正确 |
| `verification_matches_submission` | 任意合法返回表是否逐格等于固定提交；没有合法表时为 null |
| `verification_content_correct` | 任意合法返回表是否通过已有八个独立内容谓词；未获得可检查表时为 null |
| `final_attestation_supported` | 最终声明确实绑定当前固定提交和所引用的成功验证；读取完整、被审工作区未改变，且所引用表通过内容谓词，pass/fail 与逐格相等/不等对应 |

前五个字段是 **曾经发生** 的事实；最后一个只看最终引用的那一次。报告同时保存尝试次数、成功次数、逐次验证、最终 verification ID 和 `final_attestation_computation_succeeded`。先成功、再失败、最终引用失败的程序作 pass，不会借用更早的成功记录变成受支持的最终声明。

`verification_content_correct` 明确限定为固定 grader 的八个表格谓词：列、行数、去重、范围、缺失替换、重复 ID 获胜值、排序和部门纠正。它不是完整的所有单元格 oracle，不验证任意数据上的通用 pipeline，也不证明两岗位思维独立。没有新定义、扩张或回溯重判既有 grader 分数。

## 内容检查不开放 oracle 或写权限

控制器只接受 SHA 为 `8b0a417ea3f810cfa07e376b80b869d479bf574305aef67c62903a738a9a096b` 的既有修订 grader，从其源码逐字提取并核对八个 Python 内容检查块。返回表写成控制器临时 CSV，随后运行这些已固定程序；每次检查程序源码也记 SHA。这里不运行 `clean.py`，因而不为验证内容判断额外重跑 actor。

验证工具对模型仍只返回原有 execution、stdout、表格结构与同固定提交的相等关系。控制器的 expected 内容、内容检查结果及谓词失败信息均不进入角色工具回执或后续模型请求。终局报告才附加 controller-only 内容结果。已有终局 artifact grader 仍按 v0.22 路径，在隔离中重跑提交程序一次，保留与固定输出的再现检查；这与“验证返回表的内容检查不重跑 actor”是不同过程。

未修改 Landlock/seccomp 配置、input-only 工具合同或被审工作区只读权限。两个故意写 `data/output/clean.csv` 的验证控制仍被拒绝；没有把 PermissionError 变成成功，也没有重复整套 OS 隔离矩阵。

## 已完成 CPU 控制

命令：`.venv/bin/python -m scripts.teambench_model_v024 --output runs/teambench-v024-cpu-controls`。五个程序 episode 都使用旧开发 seed 0，是明确标注的程序控制，非模型交互、非训练材料、非外部新评分。实际调用既有隔离工具和固定 grader；原开发材料的全部文件 SHA 前后一致。

| 程序控制 | 曾成功执行 / 合法表 | 与提交一致 | 内容谓词通过 | 最终声明受支持 | 完整联合职责 |
|---|---|---|---|---|---|
| 正确实现与正确验证并 pass | 是 / 是 | 是 | 是 | 是 | 是 |
| 成功验证但没有最终声明 | 是 / 是 | 是 | 是 | 否 | 否 |
| 提交与验证都遗漏同一缺失数值行 | 是 / 是 | 是 | 否 | 否 | 否 |
| 写 input-only 输出路径被拒后声明 pass | 否 / 否 | null | null | 否 | 否 |
| 先成功，后一次写操作失败，最终引用失败 check 作 pass | 是 / 是 | 是 | 是（此前 check） | 否 | 否 |

共六次实际 verify：四次成功且返回合法表，两次按原权限拒绝；四张合法表中三张通过内容谓词，一张共同漏行失败。五个声明控制均符合预声明预期；额外人工表控制的正确/错序/漏行三张表也符合预期。控制器指标没有进入模型可见回执。

定向测试：`.venv/bin/python -m pytest -q tests/test_teambench_model_v024.py`，**3 passed in 2.30s**。其中一个显式 fake transport 控制走真实 `ModelPolicy`、角色端口和隔离程序，验证新增公开规则真实进入消息且私有内容检查不进入消息；fake transport 不计真实模型调用。首次测试中两项通过、一项仅因把 JSON 编码消息当原始换行字符串匹配而失败；修正测试同时识别原始/JSON 编码表示后通过，未因这次测试失败改变模型合同或评分。上述三个新文件的 Ruff 检查通过。

## 未启动的九例外测建议

[声明文件](../../examples/id-vtdo-v24/external-d2-proposal.json) 预留生成 seed `20261101/20261102/20261103`，三个采样 seed 在三 endpoint 固定复用。endpoint 为共同新初态、MC 两窗终态、Handoff-RTG 两窗终态。九例在内部 54 例之外，仍只有同一家族的一个来源，不能称为完整官方 benchmark。

当前 `automatic_launch=false`、`current_gpu_budget_seconds=0`、`status=proposed_not_started`。实际执行前须有单独外测预算/启动决定、三个 checkpoint 身份绑定和足以覆盖完整评价的监督计划。此文件不沿用 v0.23 的剩余额度，也不会自动启动队列。

代码：[新适配层](../../src/proworksim/teambench_model_v024.py)、[CPU 控制](../../scripts/teambench_model_v024.py)、[定向测试](../../tests/test_teambench_model_v024.py)。机器摘要：[JSON](teambench-v024-contract-and-metrics.json)。原始 CPU 记录：[report.json](../../runs/teambench-v024-cpu-controls/report.json)。
