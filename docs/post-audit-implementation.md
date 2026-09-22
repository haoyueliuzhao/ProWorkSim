# 审计后修订：契约修复与有限结构空间

本轮依据 [审计结论](reference/audit-v0.1.md) 和 [后续建议](reference/post-audit-plan.md) 修订。保留实际文件、版本、权限、事件、规则角色和独立数值参照；优先修复错误准入，再增加有限结构。未扩展为完整金融系统，也未引入环境角色共同学习。

## 1. 已复现问题与修复

修订前运行 `scripts/audit_counterexamples.py`，通过公开工具复现：合法利润率单引被拒绝、空/旧依赖被接受，以及 `=2/50%` 与 `=10%^2` 分别错误地计算为 0.0004 和 0.001。

- `contracts.py` 的 `CitationRequirement` 同时配置公开指南和评价。memo 保留收入/利润率二选一；short 的模型股价位置和指定披露 EPS 仍需同时出现。新布局只改变真实位置，不放宽语义约束。
- `ArtifactContract` 指明必要来源。评价核对 memo 正文和版本元数据的必要绑定，读取历史仍只表示访问行为。错误声明允许落盘，但不能获完整通过。
- `freshness.py` 按必要依赖和声明依赖计算 `current / stale / unknown`，缺边为 unknown、旧版本为 stale；已批准历史版本不重写。下游只更新标记，实际内容由工作人员修改。
- `formula.py` 将 openpyxl token 解析为显式 AST，包含前缀、后缀百分号、二元运算、引用、函数和括号。采用 negation → percent → exponent → multiplication/division → addition/subtraction，二元同级左结合；没有扩大完整 Excel 函数范围。优先级依据 [Microsoft 官方说明](https://support.microsoft.com/en-gb/excel/the-order-in-which-excel-performs-operations-in-formulas)。数值测试使用固定外部期望，不以同一解析器生成答案。

旧数据按 `finance-v0.1.2` 复核，保留原始契约推断来源及旧评价。新工作规格使用 schema 0.2、`operating-toy-v0.2` 契约/评价；0.1 读取支持仅用于复核及有限旧模板恢复，不支配新结构的设计。

## 2. 结构成为规格

`WorkflowSpec / WorkNode / EventRule` 记录工作节点、依赖、发布组、版本与受约束事件。`workflow.py` 激活前置义务已接受的节点；`events.py` 执行白名单材料变化。内核只调用通用工作流入口，不再直接创建 `work-2` 的财务变化。

| topology | 工作与产物关系 |
| --- | --- |
| chain | 复现模型→备忘录的两阶段更新 |
| fork | 模型工作接受后，memo 和 note 两项工作分别可执行；两者接受后发布下一阶段 |
| selective | 第一阶段产生模型、备忘录、情景说明；第二阶段仅修改 brief 的受众要求，产生 note 更新义务，model/memo 必须保留版本 |
| coordination | 链式产物与实时负责人澄清；可行性实验可故意漏改一次 memo，审阅只响应实际错误 |

选择性更新当前以**产物级依赖**实现，尚未声称支持同一工作簿任意字段级语义影响分析。note 依赖 model/brief，memo 依赖 model/financials，因此 brief 变化只使 note 失效。这是实质分叉和更新范围变化，并非更换公司名称。

`LayoutMap` 和 XLSX renderer 支持标准与移动布局。输入/输出的表名、列与行位置变化；指南、公式、工具层见证和验证定位随同映射。独立参考数值仍由 `financial_result` 计算，不复用生成器公式求值结果作为答案。

```bash
.venv/bin/proworksim build runs/fork --seed 211 --topology fork --layout shifted
.venv/bin/proworksim run runs/fork --provider baseline
.venv/bin/proworksim evaluate runs/fork
```

也可通过 `build --workflow-spec <json>` 替换工作网络。测试中仅扩展 JSON 规格就增加了第三次 brief 修改及 note 义务，没有改变内核。当前模板的 artifact roles 仍限制为已有领域对象，不能称为任意专业世界生成器。

## 3. 调用与经历记录

每次真实模型运行保存 manifest：run ID、Git commit、dirty 标记和源码哈希、schema/contract/evaluator/表格引擎版本、固定角色策略、完整合成规格、预算、停止原因和初始快照。

模型逻辑调用在请求前持久化。DeepSeek 每次底层 HTTP attempt 单独记录成功、错误、超时、重试序号及可得 usage；失败请求未返回 token 时保持 null，不估造账单。工具完成以本次 call 中的 tool_call_id 记录，不会因另一次响应复用 ID 而跳过操作。

`episode.json` 分开记录 `artifact_valid / business_accepted / explanation_assessed / trajectory_supervision_status`，明确 `professional_gold=false`。SFT 使用适用的新评价版本；历史错误和其他角色消息不作为正向目标。课程按 episode/work item 的最终评价聚合，避免一次工作的反复提交重复扩大失败权重。

项目另外记录 source_family、template、topology、layout、role_information、scenario。它们用于审计结构覆盖；当前来源划分仍按 seed 谱系，尚未建立足以宣称未见结构泛化的正式训练/保留集。

## 4. 实验协议

1. 修订前后运行同一组审计反例。
2. 对原 v0.1 的 43 次实际调用和不可变文件做复制品重评，保存旧评分，不重新采样；比较原 37 条 SFT 的准入变化。
3. 保留十二配置机制矩阵，并增加四种拓扑×两种布局×两个种子的结构矩阵。
4. 在新布局上做小规模真实模型可行性实验。
5. 对同一第一阶段产生的第二阶段快照分支，保留历史上下文与清空上下文；材料、时钟、工作、邮件和可见知识状态完全匹配。该对照只测上下文继承，不能代表连续项目训练的全部价值，也不是 short/file/continuous 的因果比较。

```bash
.venv/bin/python scripts/audit_counterexamples.py runs/audit-reproduce
.venv/bin/python scripts/regrade_history.py runs/live-v0.1 runs/regrade-reproduce --old-exports runs/exports-v0.1
.venv/bin/python scripts/experiment_v02.py mechanism runs/structure-reproduce --seeds 211 223
.venv/bin/python scripts/experiment_v02.py live runs/live-structure-reproduce --seeds 313
.venv/bin/python scripts/experiment_v02.py paired runs/paired-reproduce --seeds 317 331 --max-turns 60
```

完整结果、失败和解释边界将单独记录在实验报告中。低样本可行性实验不提供显著性或学习收益结论。

## 5. 本地训练适配

`training.py` 使用本地 Qwen tokenizer 的真实 chat template，显式将 API 的工具参数字符串转换成对象。保留实际正文和工具历史；不把 Teacher 的 reasoning_content 转成另一个模型的隐藏思考格式。只监督最后一个已准入的模型输出，token offset 划分掩码，超长样本拒绝而不静默截断。

冻结目标为：episode 等权、episode 内 call 等权、每个 call 内监督 token 平均交叉熵。首轮最多每个 episode 两条，属于链路冒烟的小样本上限。Teacher 来源保持为 DeepSeek；没有将其伪称为 Qwen 自生成经验。

`scripts/train_smoke.py` 实际执行 LoRA backward、优化、保存、重载及回到同一工具接口。是否每一步通过以实验记录为准；提供代码不等于闭环已成功。RL 仍为 interchange-only。

本地共享 Qwen 模型目录只用于读取，适配器保存到本项目 runs 子目录。共享 GPU 会与其他项目争用资源；用户提出该问题后，本项目暂停新的 GPU 运行，继续 CPU/API 实验。后续训练需遵循用户确认的资源安排。
