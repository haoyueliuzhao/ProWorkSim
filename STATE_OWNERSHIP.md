# 状态归属与重算（v0.9）

| 字段或对象 | 归属 | 权威与修改规则 |
| --- | --- | --- |
| artifacts.versions 的身份、字节哈希、来源与已签发 credential | B | 文件版本创建／正式确认；已提交版本不得改写 |
| current_version 与实际文件镜像 | B 指针／文件物化 | 原子状态决定正式指针；镜像只由同一版本字节恢复 |
| attestations | B | 有配置权力的 Confirm；评价器、正文主张或缓存不能创造 |
| work 定义、requirements、replacements | B | 初始编译与明确 ReviseRequirement；保留旧义务 |
| submissions 的固定字段、review、withdrawal、invalidation | B | 实际提交、制度决定和修订后果；重算不改决定 |
| work.artifact_edits | B | 真实文件编辑事件；不能由缓存的 in_progress 反向猜测 |
| condition 定义、绑定／撤除／信息到达／response_received 历史 | B | 实际行动与接收事件；不以 PASS/FAIL 缓存充当事实 |
| raw_condition_responses | B/O | 原始响应、接收时间／序号和不可由调用者覆盖的接收时事实快照 |
| work.status/blocker/blocker_ids/applicability | P | 由 current_work_view 写回；不是第二套解释权 |
| condition.status/unavailable_providers/resolution_ref/response_checks | P | 由 condition_view 写回 |
| blockers、condition_responses | P | 单向兼容／展示投影，不反向决定条件是否满足 |
| freshness 与按工作适用关系 | P | 由声明来源、正式凭据和工作上下文计算，不修改内容 |
| pending_submission_id / submission_state / enabled_actions | P 查询结果 | 待审、条件、前驱与角色维度分别判断；不保存第二套事实 |
| state_revision / operation_commits | Q | 命令与环境事件分别提交；结果与正式效果写在同一快照 |
| events / event_history | Q/B | 真实队列与已处理事件；同 tick 按入队顺序，重复事件不重复效果 |
| event_attempts | Q/O | 失败或提交后交付异常的持久诊断，关联已知提交前缀，不算第二次正式效果 |
| messages、interactions、读取与模型上下文 | O/B | 已实际提供或发生的记录，不由新版投影改写 |
| evaluations / verified_dependencies | 世界外证据 | 独立版本化评价；不替工作人员改产物或删除错误批准 |

## 新增多项目状态

| 字段或对象 | 归属 | 权威与修改规则 |
| --- | --- | --- |
| world_id、actors、applications | B | 可信零项目世界规格；项目包不得重建人员或升级世界权力 |
| world_status | Q | 运行／暂停的显式世界操作；idle 是活动项目集合的观察结果 |
| projects、project_history | B | 包装载和显式完成／归档；历史保持，不等于删除世界 |
| workspaces / world_workspace | B | 别名指向世界对象；对象 ID 与文件名分离，别名不能越权 |
| organization.grants | B | 项目包的明确 project/work/object 作用域；无上下文不能借项目权力执行世界动作 |
| shares | B | 精确版本和接收主体的显式授权；后续发布授权须有 follow_updates |
| adoptions[work_id::alias] / adoption.history | B | 精确工作/需求/项目/别名绑定，及声明政策和实际采用版本；显式 adopt_version 保存前后引用，修订后新项独立采用 |
| adoption_view | P | 当前目标和已采用版的关系；不会更新交付文件或自动创建批准 |
| episodes | Q/O | 本次观察范围的起止项目和修订号；结束不删除项目、事件或人员阅读历史 |
| artifact.storage_path | B/物化位置 | 仅受控 artifacts 子目录；镜像恢复不将同名文件混为同一对象 |


E1 的缓存操作仅使用 `core.projections.projection_paths` 明确列出的两个视图缓存。它不删除正式提交、历史消息、版本指针或签发登记，也不声称清除了全部可能存在的缓存。纯函数不产生新文件、消息、批准或阅读收据。

`rebuild_projections` 可以覆写 P，不能把条件 status 和 blocker status 两份缓存互相校正。缺少原始回应等必要事实应报明确错误；缺少适用确认则不可评，不借用隐藏规格补目标。

当前模型基于可信检查点、定义与原始事实快照，不保证从任意历史日志重建全部状态。新格式不能通过删掉正式登记或 journal 自动降级为旧格式。旧格式不做隐式迁移。

## v0.7 工作能力与发布

| 字段或对象 | 归属 | 权威与修改规则 |
| --- | --- | --- |
| applications | B/固定配置 | files/spreadsheets 的实际工具注册与准入，未知能力拒绝 |
| artifact.kind、不可变 JSON/XLSX 字节 | B | 真实能力创建/编辑；错误公式与缓存也属于历史字节 |
| world/project.publication_policy | B/固定政策 | explicit 或 implicit_write；不追补历史 release |
| releases | B | 精确版本、发布人、时间和目标项目/源工作范围，追加保持 |
| shares | B | 同/跨项目精确授权，ACL OR 合法分享；发布不自动授予全版本 readers |
| adoption_view.target_version | P | fixed 为固定版，current_published 从发布范围查询；无发布时不可评 |
| submission.adoption_snapshot | B | 固定采用及提交时目标，受不可变提交扩展保护；后来发布不改历史判据 |
| project.information_routes | B/环境政策 | 合法包声明的真实初始材料、提供者与延迟/不可得规则，执行时仍核对作用域 |
| worker transcript | O/外部记录 | 调用当时工具定义、观察、请求和返回；不从最终状态回填 |
| content evaluation/read_set | 世界外证据 | 固定提交与输入版本/哈希、实际值/错误；不删除正式批准 |

确定性 XLSX 序列化只规范 ZIP 和文档时间元数据，不删除公式、数值或错误。恢复比较使用真实提交字节，不通过评价重算来“修复”历史错误。


## v0.8 持续工作

| 字段或对象 | 归属 | 权威与修改规则 |
| --- | --- | --- |
| project.maintenance_rules | B/固定政策 | 项目包装载时校验来源、稳定工作节点、阶段、后果及范围授权 |
| maintenance_impacts | B | 实际发布后独立事件提交的捕获上下文和后果，按 release/project/rule/node 去重 |
| project.maintenance_heads | B | 指向当前维护谱系头；后继创建时推进，普通修订仍由 work_replacements 追踪 |
| work.previous_obligation_id / maintenance_trigger | B | 后继工作与已接受前项及真实发布的关系；前项不被自动替代或撤销 |
| knowledge.read_artifacts 的 work/requirement | O/B | 调用者显式传入且经过校验的精确工作读取；泛化读取不推断为某项工作进度 |
| artifact_edits 的 work/requirement | B | 本人实际编辑并声明工作上下文；output_ready 仅表示这类编辑发生，不证明质量或完成意图 |
| information_routes.availability_revision / information_updates | B | 合法提供者的公开可得性修改与追加历史；不凭修改直接满足条件 |
| request.route_revision / work_item_id / requirement_version | B | 请求时冻结的路线与工作上下文；新请求可以撤除旧未满足条件，原始回应不删除 |
| continuous worker checkpoint | 世界外 Q/O | 已完成步骤之间显式保存的公共进度、命令序号和原始轨迹，不是内核事实或任意崩溃恢复证明 |


## v0.9 版本定位的问题与处理

| 字段或对象 | 归属 | 权威与修改规则 |
| --- | --- | --- |
| issues | B | 有范围review权且实际已读精确提交的主体提出；固定work/req/submission/ref/locator，创建时记录是否适用于当前待审工作 |
| issue_responses | B/O | 责任人实际回应，一对一关联问题与真实提交；正文及证据不自动构成真值 |
| issue_decisions | B | 有权review主体对确切回应的处理事实；accept_fix/accept_rebuttal/keep_open，记录对应submission与全局序号 |
| issue_views | P/公开查询 | 从不可变问题与决定折叠status、applicability、blocks_approval；不写回第二套status权威 |
| work.outstanding_issue_ids | P/公开查询 | 批准条件，区别于资料获取条件；阻止approve而不阻止修复重新提交 |
| rejection事实及分类 | O | 运行时保留type/message和显式原因/类别/调用上下文；未知保持unknown，不按文本猜归因 |
| 财务记录/报告章节/claim | B/版本化文件内容 | 属于领域对象的实际JSON字节，不升级成通用世界的固定字段；错误也可成为真实提交 |

后续版本不覆盖旧问题定位或决定的证据。新版本如何满足专业内容由领域独立评价；一次review处理决定不证明未来所有版本正确。


## v0.10 世界外运行与评价

| 记录 | 归属与边界 |
| --- | --- |
| scenario规格/manifest/前缀记录 | 世界外可信部署元数据；部署/事件只走公开动作，前缀是实际执行，不冒充背景历史 |
| worker memory/last_action/last_result/cursor | 世界外策略运行进度；每角色独立，完整动作返回后checkpoint；需验证世界/实例/分支/策略身份 |
| experience事件 | 当时实际接口和控制器返回的外部记录；不从最终状态重建观察，不供另一角色充当私有上下文 |
| episode assessment | 只读评价证据；制度、内容、独立目标、过程、不完备和运行问题分开，无总成功分数 |
| 公共instance_id/branch_id | 既有世界身份的只读投影；不改变存储事实或授予权限 |

Episode停止不删除world/project/work或其他项目。世界可以仍有未完成工作而本次声明的观察范围已到达boundary_reached。

## v0.11 模型、历史边界和SQL执行

| 记录 | 归属与修改边界 |
| --- | --- |
| 模型request/attempt/response/usage | 世界外O；实际HTTP与角色机会绑定，未知用量不补造，模型提议不算世界执行 |
| adapter messages/context_selection | 世界外Q/O；保存完整真实对话，请求筛选单列索引及哈希，不事后改写经历 |
| EpisodeManifest及start/end版本副本 | 世界外只读证据；固定职责/提交/经历区间，副本不成为新的世界权威，未来live状态不能回填 |
| RewardSpec与奖励 | 世界外显式训练合同；不覆盖制度或内容评价，未知/实现故障保持无可训练奖励 |
| SQL/config及实际输出 | 世界版本化B；通过公开写入/构建工具产生，不把临时数据库变成第二权威存储 |
| version.execution_provenance | 实际SQL执行边界写入的版本元数据；普通write_object不能伪造此元数据，提交须对应实际代码及源版本 |
| 临时.sql与DuckDB | 受限执行的派生文件；权威是已提交SQL、输入引用和逻辑结果，不承诺物理DB字节恢复 |

模型权重、LoRA与训练概率在世界之外，商业API调用不是参数更新。原始token/mask来自实际生成，不能从最终文本补造。策略停机、episode结束、机构接受、独立质量和奖励资格分别记录。
