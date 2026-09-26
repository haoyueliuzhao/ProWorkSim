# v0.14 公开返回呈现：固定成果检视与完整合同检索

本次把“公开返回如何呈现”从角色工具权限中独立声明。`WorkInterface(variant="v14", presentation="full_v14")` 与 `presentation="compact_v14"` 使用同一套 `work-interface-v0.14` 工具定义、参数和权限；唯一区别是 `submit` 与默认 `inspect_submission` 的返回呈现。上下文上限、角色提示、抽样、权重和任务条件必须由实验协议另行锁定，不能把增加上下文的效果归于此投影。

v0.14 的 implementer 与 reviewer 均公开 `inspect_submission`，使提交者也能通过真实、受权限校验的调用取回完整固定合同；这不授予 review/approve 权限。两呈现臂的新工具集完全相同。旧 `variant="v13"` 和 `legacy` 的工具定义不公开新增 `include_contract` 参数，v0.13 implementer 的工具列表仍不包含 inspect。正式对照不是声称 v0.13 原工具字节不变；它是在同一新 schema 下比较完整和简明返回。

## 保留和省略的内容

`inspect_submission(work_id, submission_id)` 仍执行真实 WorldCore 动作：检查该固定提交与每个固定产物的访问权限。Core 保存完整原始提交为 operation receipt，不改变采用、不判断正确性、不选取适用业务依据。检视不是读取文件；知识状态中不会因为检视而增加文件读取记录。

`submit` 和默认 `inspect_submission` 使用同一简明投影，保留以下内容：

- 原 submission ID、requirement version、artifact_versions、提交者和提交时间、适用性、失效状态及审阅记录。
- 固定合同中的目标、工作所有者、审批政策、凭证要求、交付文件/内容结构、期间和复核合同。
- 每项固定 adoption 的 alias、object/version、requirement version、policy、target version 和其他未明确省略的字段。
- 真实 command ID、逻辑时间、提交标识等原 envelope；没有缩短或改写这些标识。

重复的完整 `requirement_snapshot` 不默认全部展开；公开的 `requirement_snapshot_complete=false` 和 `read_full_inspection` 明确提示这只是摘要。完整原固定合同，包括原 `public_format`、`online_scope` 和历史要求，均可通过真实的 `inspect_submission(work_id, submission_id, include_contract=true)` 取得。该次调用仍受相同 Core 权限校验，返回原始完整检视结果。简明 adoption 不展开 history 和冗余位置/作者/时间元数据，这些同样可通过完整检视取得。

简明返回明确指出以 `artifact_versions` 中固定引用调用 `read_version`。没有把 workspace 的当前版本当成固定提交版本，也没有自动替模型选用其中某个文件或提供 SQL。文件正文与实际查询结果不作截断：`read_alias`、`read_version`、`sql_query`、`sql_build` 及其他工具返回保持完整。所有错误返回保持原样。

观察保持此前 v0.13 对项目安装元数据的选择，其余公共字段全部保留；两新呈现臂的观察相同。开发 CPU 集成曾发现删除 instance/branch ID 会触发 StaffRuntime 的绑定拒绝，现已保留，未改变 runtime 的绑定规则。本实现主要减少提交/检视中重复展开的完整合同，不声称解决了全部长上下文问题。

## 原返回、公开返回与实际模型输入

每次 `WorkInterface.call` 的辅助审计文件 `public-projections/<role>/call-N.json` 保存完整原返回、完整实际公开返回、两侧 SHA256/字节数、action、arguments、profile 和投影理由。每次观察也保存完整原观察与选择后观察，不只保留其 hash。

标准 `capture_port` 位于 WorkInterface 外层，独立捕获模型真实获得的工具列表、观察和工具返回。StaffRuntime 记录同一公开返回；ModelPolicy 的实际 native tool message 原样序列化该返回。MemberView 从实际请求恢复输入，不从原始 receipt 或 sidecar 补出被省略的内容。`latest_observation` 删除旧观察也不会使摘要引用失效：没有使用“过去某条观察里的相同字段”作为隐式完整合同，完整合同只能从显式的公开检索调用取得。

WorldCore receipt 原始内容与简明返回不同，因此原有 `receipt.public_result == public_response` 检查改为统一的 `response_matches_receipt`。该函数仍接受逐字相同的原返回；对简明返回则核对：

1. 受支持的 projection 版本、正式 v0.14 role profile 和工具。
2. 实际 Core receipt 的 contract 和 request digest；digest 精确绑定 actor、project、tool、arguments 和 interface profile。
3. 对完整原 receipt 使用冻结纯函数重新投影后的整个公共响应，逐字段相等。

它不采用“忽略若干不认识字段”的比较方式。改变引用、投影 SHA、工具、参数、项目、profile 或版本都会拒绝。raw/public sidecar 便于人工复核，不能替代实际 commit、捕获和请求证据。

任务评价继续分别要求检视与文件读取；简明检视没有获得任何额外读取信用。真实读取的全文与引用不受投影影响；目标模型后续消费仍须由实际 request 中存在对应公开 tool message 来证明。原始 Core 数据或审计 sidecar 里的内容不能作为模型已消费的证据。

## 有限核验与解释边界

`tests/test_work_presentation_v014.py` 以真实准备世界、真实 WorldCore 命令和显式模拟的模型响应检查：同 schema 对照、完整检视入口、精确固定版本、真实读取原文、篡改拒绝、原/公开文件保存、native 输入、独立捕获、MemberView 与任务奖励；另在完整与简明呈现下分别执行真实正确实现、提交及完整合同回读，确认逐份固定合同保真和奖励均为 1。模拟 transport 不具备真实生成 token，因此不冒充可训练模型经历。

2026-09-26 的单例 CPU 序列化测量：`development-w0-review` 的原始检视为 7,399 字节，简明公开返回为 4,241 字节，比值 0.5732。它只是该案例序列化的字节减少；不是 token 节约比例、上下文可操作性或能力提升结论。模型层面的呈现及上下文对照由单独冻结的 E0 协议和报告给出。
