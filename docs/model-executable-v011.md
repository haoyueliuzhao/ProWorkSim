# v0.11 模型工作接口、固定episode与可执行项目群

依据[审计](reference/model-executable-audit.md)，实施分阶段见[计划](model-executable-v011-plan.md)。软件版本0.11.0；WorldCore业务格式仍沿用v0.9。新模块使用已有权限、采用、版本、工作和问题关系，未建立第二套世界事实。

## 模型与执行分界

场景role.policy可选model，config声明后端、模型标识、任务、协议、采样参数、重试及四类预算。ModelPolicy只接收StaffRuntime提供的真实角色上下文。所有业务读写、提交和采用仍由公开端口实际执行。模型没有WorldCore实例、隐藏评价答案、控制器事件表或其他角色memory。

每次模型调用与run_id、role、opportunity_id、model_call_id关联；每个HTTP attempt保存实际请求、返回、HTTP状态、usage和耗时。模型提出动作后另有model_action_link关联实际世界tool_call及request_key。服务返回不等于工具已执行。角色实际对话由适配器追加，模型不重写memory；上下文不自动摘要或裁剪，达到边界明确停止。

模型服务超时/限流、格式错误、真实工具拒绝、世界实现错误分别保留。仅按固定表对传输重试，同一request每个attempt留痕；有效但错误的动作不重采样。usage缺失保留缺失，并按请求预留占用预算、停止后续请求，不补造实际token。

| 协议 | 合同 |
| --- | --- |
| native_tools | 真实公开工具加staff_wait/staff_done控制工具。超过一个tool_call整次拒绝并保存全部原文，不取第一条执行 |
| single_decision_json | 公开工具定义在角色user消息中原样提供。只接受一个JSON对象：kind/action/arguments三键，或kind/reason两键；无原生tool调用。真实动作返回以明确public_tool_result消息追加 |

single_decision_json中的控制对象准确形式为`{"kind":"wait","reason":"..."}`或`{"kind":"done","reason":"..."}`。JSON模式不接受数组、多动作、重复键、额外字段或原生调用，不根据近似字段猜测意图。done只是模型停止声明，后续不再请求该模型；同事可继续，制度与质量独立判断。wait不推进世界时钟，真实wait工具才产生时间行动。

官方DeepSeek支持[JSON模式](https://api-docs.deepseek.com/guides/json_mode/)及[工具调用](https://api-docs.deepseek.com/api/create-chat-completion/)。本地Qwen服务按相同公开JSON协议生成，但没有宣称提供受约束JSON解码。旧native试跑的多调用失败单独保留，不被新协议结果覆盖。

## 模型身份、预算与本地服务

商业API请求名、响应model、system_fingerprint与调用时间分别保存；返回别名不证明权重不可变。当前DeepSeek名称/峰值单价核实自[官方价格表](https://api-docs.deepseek.com/quick_start/pricing/)，GET /models原返回也保留。按峰值单价报告保守估计，不冒充账户实际账单；未知usage占用单列。

Qwen后端为本地固定目录的Qwen2.5-7B-Instruct，原始权重只读，记录文件摘要与声明revision。HTTP服务仅绑定loopback，使用已有独立训练venv的Transformers/PyTorch；本项目请求明确绕过环境的外部HTTP代理。原项目进程和权重不修改，共享GPU占用在每段实验前后采样；快照不是资源预留，也不能据此断言其他作业吞吐未变。

服务记录真实未padding的input token IDs、生成output IDs、mask及从实际采样logits取得的chosen-token log-probabilities；不由最终文字重新分词冒充采样记录。温度在唯一处理器中应用，top_p=1/top_k=0/repetition_penalty=1，基准generation_config和有效覆盖项均记录。多个EOS按模型配置处理，batch padding不计入实际生成。Greedy请求不伪称有随机策略行为概率。共享随机流及batch顺序记录，不宣称逐episode种子可精确重放。

## 固定历史episode与当前进度

每次staff-run在行动前写独立EpisodeManifest，结束后固定起止状态副本、全部已提交文件版本字节、原始经历区间、预声明责任work/node、末时具体submission和产物、模型/场景配置及终止原因。副本为独立字节，不是指向未来可变文件的硬链接。

声明work_node时沿末时maintenance_head及真实工作替换选择当前义务；接受过的前项单列历史，不能因is_current同时为true而重复评分。续行创建新的episode并指向parent，前段预算截断和未完成记录不变。只支持完整行动返回后的边界，不增加任意进程崩溃恢复保证。

- episode-assess读取封闭episode及可读结束快照，即使当前世界后来成功或被移走也不改变历史结果。
- world-assess独立查询当前世界。不能拿它给旧模型episode补成功。
- 评价责任范围在运行开始固定，历史评价spec只能声明该范围内的目标/过程要求，不能改选后来的提交。

原条件诊断按规范work_item_id筛选；不往基础记录增加冗余work_id字段。

## 奖励独立于诊断

RewardSpec是显式版本化的旁路：固定历史内容/独立目标、必要过程门槛和可选实际工具成本映射为奖励。原制度、质量、来源、未知及故障分项保持不变；没有默认总体成功标签。

完成可评目标可得1；可观察的真实失败和不提交工作为0；评价故障、不可读取的依据、外部未知目标及模型服务重试耗尽等导致不可评的故障没有可训练奖励，eligible=false、reward=null。模型格式错误不能因没成功而过滤。已存在的好交付或同版本重复提交/发布不产生新episode信用。批准、消息、关闭问题、反复提交数量不产生正奖励。

未履行已公开的来源采用义务，与外部来源未知分别诊断；显式required_source_adoption过程门槛可确认这种已发生的违规，正文仍保持未评，不能把未知正文说成计算错误。历史pilot若当时没有完整公开说明，后补说明不倒填到其责任中。

最小策略梯度验证只在真实token、历史奖励和奖励反例验收成立后进行。商业API经历不能更新供应商模型；首决策LoRA验证也不等于完整多轮Agentic RL或学习收益。三组研究对照及144次公开项目主批另行计划。

## 公开可执行项目

固定官方jaffle_shop_duckdb的虚构客户、订单、支付种子与源码来源。新增组织流程是研究设计，不声称官方仓库提供了完整企业协作、PR或CI。

P0发布整理数据；P1实际SQL产生经营指标；P2进行客户分析并提供公开粒度要求；P3实际查询汇合P1/P2结果。可用初始接口允许两项目启动；粒度变更通过正式发布和有版本作用域的问题反馈引发后继工作，不设置双方最终完成相互等待。

SQL源/配置保存在受管JSON对象，sql_build投影成实际.sql文件并创建独立DuckDB执行；sql_query真实查询当前角色可读材料。结果含表、真实测试结果/错误和源码文件，连同trusted execution_provenance形成新的世界版本；提交必须绑定实际执行的代码版本。复制一个看似成功的结果JSON不具有执行证明。编辑项目自测不改变独立业务验证要求。

能力仅允许有界SELECT/CTE及声明函数；禁止外部文件/网络、安装扩展、宿主shell和任意路径，子进程清除宿主密钥环境。CPU、墙钟、DB内存和输出行数受限，不静默截断结果。物理临时DB是派生文件，权威记录为可重建的确切输入、SQL和逻辑表版本；不宣称原样保存.db字节或运行完整dbt。

## 公开格式补齐

规则策略此前在Python中编码了报告两种句式和核对输出形状，模型公开合同没有完整呈现这些字段约束。本版把不含数值答案的语法、schema、来源引用和未知值约定放进各角色可读的requirements.public_format；submit/adopt工具说明也明确现有接口合同。它们不含正确交付、具体问题清单或事件计划，不替模型选择下一业务动作。

第一批pilot发生在这些说明补齐之前，保留其原观察和结果；随后冻结的开发批明确使用新公开合同，不把前后结果混成同条件比较。

## 第二冻结的显式上下文与准备起点

模型适配器v0.11.2新增context_policy，默认full_history；latest_observation只从HTTP请求去掉早期已登记的公开观察消息，保留当前任务/工具/观察、全部实际assistant和工具返回。memory和归档仍保留原消息。每次调用与attempt记录原消息索引及哈希、保留/移除理由、完整/实际请求摘要；无登记旧历史不猜测删除。上下文选择改变了接口条件，单列诊断，不能用它回写旧episode。

Scenario executed_prefix可声明roles行动子集；模型角色尚未获得机会，既有实例/角色绑定不切换。work.phase=published要求实际接受和公开交付兑现。CLI及模型实验驱动在真实前缀完成后才打开目标episode；前缀检查点和原经历保持，预算及CPU工作不隐去。

sql_query读取当前work已采用的精确来源；跨项目来源没有采用时不猜其他版本。本地查询仍受项目权限和声明输出限制。原API中的查询拒绝及修复后共享v2/私有v3的真实对照分别保留。

发布起点的补充限制：published谓词仅适用于明确声明public_delivery.publish的工作，同时核验真实发布。没有发布义务的已接受工作不因此自动成为published；这种配置在场景验收时明确拒绝。
