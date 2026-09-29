# v0.25 新材料与程序路线分项准入

**允许启动预模型冻结的 A 成员配置研究；不宣称全部四种工作路线获准。**A 的主动交接和绑定请求交接均有完整实际路线。B 自检修复有完整路线，B 有据反馈修复在本次尝试中未能通过固定上下文预算。本轮可重配置成员顺序因此固定为 A 实现者、A 提供者；B 的八条真实采样仍进入基础 RL，所有 B 成员强制 Q=B，不因后来的模型成绩或偶然多方法出现而临时开放。

全部记录是 **CPU 程序见证**。运行真实 WorldCore、原角色权限与机会、native parser、v24 确定标识、compact、官方 Qwen tokenizer 和真实上下文拒绝规则。没有目标模型生成、GPU、API、参数更新或教师训练标签。规则路线不计入当前策略支持池。

## 新来源与固定使用边界

先排除 v0.15/v0.16/v0.22/v0.23/v0.24 已用的 138 名客户、414 张发票和 1315 个原始行，再按 `SHA256(collaboration-v025:CustomerID)` 选择 32 名新客户，连续配对成 16 份材料。每份保留两名客户各自两张完整普通发票和一张完整冲销发票；每张发票至多三行。新材料共 96 张完整发票、205 个原始行。所有数值、描述和来源行保留。

材料划分在模型采样前固定：

| 用途 | 唯一材料 | 情境与预定槽 |
|---|---:|---|
| 当前支持窗 | 2 | 精确 A、错计数 B，各 8 重复，A/B 交错，共 16 槽 |
| 贡献开发 | 6 | 2A、2B（正确／错计数）、2维护（改变／保持），各 1 次 |
| 独立确认 | 6 | 同结构的新情境，每个 2 seed，共 12 槽／策略 |
| 后继交互 | 2 | 新 A、新错计数 B，各 1 次／策略 |

`registry()` 导出 `training_cases`、`training_window`、`development_cases/slots`、`confirmation_cases/slots`、`continuation_cases/slots`、`all_cases`。唯一支持窗口为 `v025-window-1`。各阶段 seed 分别固定于 `202610020000`、`202610021000`、`202610022000`、`202610023000` 起的互不重叠区间，实际清单见 catalog；重复槽带 `case_id/task/seed/sampling_seed/repeat_index`。开发与确认按 A/B/维护交错。

仍然只有一个 UCI Online Retail 来源家族。实体／原始行不重叠不等于新来源泛化或语义去污染。旧轨迹不进入新支持池。

## 保持的工作条件

终局工作合同、固定材料评价、权限、角色机会、native compact、数值与模型配置不变。A 机会为提供者 6、实现者 16；B/维护为实现者 24、复核者 28。上下文容量 16384，固定保留 2048 输出，实际 prompt 上限 14336。`runtime` 继续直接使用 `deterministic_work_v024`，没有另造 harness。

方法标签仅存在于研究目录和 CPU 控制参数，不进入真实工作人员任务文本或其观察。程序只能依据各角色实际观察和已读返回选择动作。A 两种路径以及 B 两次最终路径尝试的准备业务状态 hash 分别相等；实际 world/episode/storage 身份独立。

## 分项结果

| 范围 | 结果 | 可支持的声明 |
|---|---|---|
| 同一训练 A：主动交接 | 完整职责通过，R=1 | 实际交接、消费、采用、正确构建及固定交付在原预算可行 |
| 同一训练 A：绑定请求交接 | 完整职责通过，R=1 | 真实 request_id 对应交接，后续实际消费及交付在原预算可行 |
| 同一最终训练 B：实现者自检修复 | 完整职责通过，R=1 | 当前错误初稿自检、撤回、正确新产物与独立核准可行 |
| 同一最终训练 B：有据反馈修复 | **未获完整路线资格** | 保留实际有据 issue 和后续尝试；不能称完整反馈修复已容纳 |
| 其他 14 份材料的合法职责路线 | 14/14 完整通过 | 各自至少存在一条程序可行路径 |

总计 **17 条合格程序路径覆盖全部 16 份材料**；这不等于全部材料都具有两种合格方法。合格路线所需业务动作最大 prompt 为 **14007 token**，加 2048 输出共 16055。另有 **12 次**真实上下文拒绝发生在相应业务已经完整完成后的额外 `staff_done`；这些拒绝不执行动作、不隐藏、不算模型失败／成功数据，也不保证任意模型路线可完成。

A 的两个完整路线来自同一准备状态：一个主动发送合法已读依据，另一个先由实现者真实请求、由提供者读取请求并将交接绑定其 `request_id`。两者均执行实际数据／依据读取、采用、SQL 构建和新固定交付。它们不是因措辞、读顺序或不同初稿拆成的类别。

B 反馈程序以实际 reviewer 读取和 inspect 形成有效 issue；实现者在实际模型请求中的 `observation.issues` 读取该 issue 后才撤回。后继设计包含改代码、新 build、新 submit、绑定新 SID 的 response、reviewer 读取新固定材料及 response 后决定 `accept_fix` 并核准。尝试没有走完该链，任何已准备好的程序分支均不替代实际成功证据。程序没有修改角色权限或省略问题处理义务。

## 保留的失败与最小准备表示调整

本轮在目标模型采样前做过五次 B 反馈程序尝试，均保留原文件：

1. `runs/retail-work-v025-initial`：原程序在 submit 前 prompt 14457 超限；下一角色因预期的新 submit 不存在而出现后继 fixture 错误。
2. `runs/retail-work-v025-feedback-short`：删去非必需 `read_messages`、缩短程序文本。所写 SQL 使用 `USING`，被既有 SQL allowlist 拒绝；同时后继请求超上下文。未放宽 SQL 执行器。
3. `runs/retail-work-v025-feedback-direct`：改为合法 `ON`，响应使用实际已读 data 并绑定新 SID，减少非必需回读与等待，仍超限。
4. `runs/retail-work-v025-compact-preparation`：对新的训练 B 初稿做经预模型批准的最小等义紧凑表示。该 B 的自检修复复验通过；反馈仍超限。
5. `runs/retail-work-v025-feedback-alias`：对于已 inspect、且观察确认仍为同一当前版本的对象，程序使用较短的合法 `read_alias`，省去可选 read `work_id`；读取的实际对象／版本不变。最终仍在 submit 后的必要后继决定达到约 **14513** prompt，超过 14336，后续 response/decide/approve 未完成。

这些是 CPU 开发失败，不能计作目标模型成绩；其中 SQL 执行错误与随后 fixture 断言都保留。没有下调输出预留、扩大上下文、合并对象／版本、删去证据或绕过工具调用。

最终训练 B 显式包含：

- `prepared_code_variant = compact-sql-v025-r1`；
- 新 `case_id = retail-v25-4273bbfbaa657a8c`；
- 初稿 JSON 由 **1160 字节缩为 847 字节**；独立序列化代码用官方 tokenizer 从 **335 token 缩为 259 token**，这不是完整 prompt 的缩减量；
- 删除非业务说明，缩短等义 SQL；保留 `unique_customer` 测试与 `COUNT(DISTINCT InvoiceNo)+1` 唯一预定错误；
- 原版与最终版实际准备执行的错误结果表逐值相同。最终版自检路径被原独立完整谓词判定成功，错误准备／修后正确均由实际记录支撑。

该改动只作用于新的训练 B。数据切片、来源池、其他 15 个 case、任务目标、工具、权限、调度和预算保持。旧 case 的文件不重写，其身份不再冒充最终训练 B。最终两种 B 尝试均从该相同新初态运行。

## 冻结边界与复现

机器可读结果为 `retail-work-v025-qualification.json`：

```json
{
  "can_start_A_only_study": true,
  "all_required_routes_passed": false,
  "full_four_method_qualification": false
}
```

“未获资格”不是证明所有可能 B 反馈路线都不可能完成；只是本轮没有取得所需完整见证，因此预先冻结为 A-only 配置候选。B 仍按真实完整有效性与方法 Mapper 记录，不改回报、不删除可信失败，也不把 B 权重质量转给 A 或成功样例。若本次 16 条真实采样没有 A 可重配块，必须按总协议的支持不足出口处理，不能引用这些程序路线凑出模型支持。

必要核验为 1 项新目录／来源／固定份额测试，以及上述实际程序路线与准备产品比较；Ruff 通过。未重跑函数式学习路径诊断或梯度验收。

```bash
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src runs/v016-sdk/resident-venv/bin/python \
  -m scripts.retail_work_controls_v025 --output NEW_DIRECTORY \
  --tokenizer runs/assets/models/Qwen3.5-9B-c20223623576

.venv/bin/python -m scripts.retail_work_qualification_v025 \
  --output NEW_QUALIFICATION_JSON
```

全路线控制 CLI 会如实包含未合格的 B 反馈路线并返回失败；只读 qualification 则根据已冻结的分项范围判定能否启动 A-only 研究。两种返回值含义不同，没有将完整路线失败改写为全部通过。
