ProWorkSim 后续实现建议（审计后草案）
依据：提交 631f1ce75e273efea223614baca65d226cf0575a 与 2026-09-22 实现说明。本文件是设计建议，不是已完成实现、冻结实验或运行授权。
0. 推进判断
保留当前可执行世界、版本存储、真实工具、独立验证、规则可行性见证和角色隔离。不要推倒重写，也不要先扩展成大量自由对话角色。
先修复三个影响数据选择的契约缺陷，然后把目前固定的两个工作阶段变成可组合的项目结构，最后在稳定协议上进行真实目标模型训练。
可以并行做训练适配冒烟，但该冒烟只证明接口，不用于宣布学习收益，也不消费当前有已知准入缺陷的数据作为正式正例。
1. v0.1.2：修复已声明机制的契约
PR-1：可见要求与独立评价统一
新增 contracts.py 中的 CitationRequirement / EvidenceRequirement。保存可用来源、版本规则、允许位置、必需组合关系（all_of / any_of）。
- 当前 memo 的公开契约是披露收入或经营利润率位置二选一；保留该契约的兼容修复应使二者均被接受。
- short 的模型股价与指定披露 EPS 是同时必须出现的精确位置，不能随 memo 修复而放宽。
- 编译器据同一个结构化要求渲染可见指南；评价器从结构化要求读取检查配置。
- 共用“要求定义”，不把参考答案或隐藏判定结果暴露给工作者；参考数值仍独立实现。
- 为旧 world 记录其原 contract / evaluator；重新评价保存新版本，不覆盖旧结果。若加强要求而不是修复已有不一致，应建立新的任务契约版本。
回归：收入单引、利润率单引均通过；错版本、错来源、无效字段、只引用模型不能通过；short 的精确来源约束不变。
PR-2：依赖声明与实际产物绑定一致
明确区分：
1. 工作者声明的输入依赖。
2. 工具观测到的读取历史（读过不等于用于成果）。
3. 评价确认的必要依赖。
对 model 验证适用 financials；对 memo 验证 financials 和本次提交 model。memo 正文的 source_versions 与版本元数据中相应必需依赖必须一致。
缺失、旧版或自相矛盾声明仍可作为合法的错误工作被保存；reviewer 可报告问题，独立评价不得标为完整正确。不要自动把所有读过的文件加成“真实使用来源”。
Store.put 对 newly written artifact 的 freshness 应根据依赖状态计算，或在暂时无法确定时标为 unknown；不能只因写入了文件就无条件证明其已更新。至少区分 current / stale / unknown。
回归：
- 正文正确、dependencies=[]：不得成为独立有效交付。
- 正文 v2、metadata v1：不得通过。
- 修正为正确依赖后通过；上游变化后依赖成果标记陈旧但字节不被自动修改。
- 引用旧版本的历史产物仍可读取；后续变化不得重写历史已批准版本。
- 无关上游变化不应使所有产物无差别失效（在引入字段级规则后验证）。
PR-3：修复受限公式语义
保留受限公式计算器，不要求实现全部 Excel。将 Tokenizer 输出编译到受限表达式树，显式处理百分号后缀、括号、幂与算术优先级。
用外部固定数值/显式括号等价式作为 oracle，而不是调用同一个坏解析器生成测试期待值。
回归：=2/50%=4；=10%^2≈0.01；现有标准算术、绝对引用、跨表引用、ROUND 边界不回退；不支持的函数明确报错；错误公式仍能保存为工作者错误，不能成为静默正确值。
PR-4：最小审计工件与调用记录
不要求生产审计平台。每次 run 产生小型 manifest：
run_id, code_commit, schema_version, contract_version, evaluator_version, spreadsheet_engine_version, actor_policy_versions, world_seed, lineage_id, generation_spec, budget, stop_reason。
API 记录区分逻辑调用与底层 attempt；记录失败/重试/超时/成功与已知 usage，不估造不可得的账单 token。
_finish_tools 的已完成判断按本次 call 与 tool_call_id 组合，而不是整个历史里的裸 tool_call_id；此项为静态审阅发现的补强建议，不属于本包已动态复现的三个缺陷。
公开摘要与原始 traces 分别保留。敏感密钥不进入 manifest。精确历史复核需要原始 trace，不能靠重新运行 API 代替。
v0.1.2 验收
原项目测试和上述回归通过；12 配置机制矩阵保持原有边界；新旧评价分开保存；三类已知反例不再违反契约。修复不必扩大角色数量、任务类别或引入数据库。
2. v0.2：从固定脚本转为可组合工作流空间
首要对象
当前 design(seed, delivery, information) 主要抽样数值，work_item 与 _drain_events 固定 work-1/work-2 和 current/future。下一版应让结构成为数据，而不是继续向这些分支加入更多 if。
建议增加以下对象，先用 dataclass/JSON，无需分布式服务：
对象	最小字段	责任
ProjectTemplate	template_id, domain_contract, node_templates, artifact_roles	定义业务过程族
WorkflowSpec	nodes, work_dependencies, event_rules, terminal_conditions	定义具体工作网络
WorkNode	node_id, owner_role, preconditions, goal, deliverable_roles, acceptance_contract	实例化工作义务
EventRule	trigger, guards, allowed_effects, requirement_patch	定义资料/要求/行动如何推进项目
ArtifactContract	artifact_role, required_input_roles, period/unit rules, semantic checks	使校验不固定在 model/memo 名称
LayoutMap	semantic_field -> artifact/sheet/cell or JSON location	分离业务语义与表格位置
InformationPolicy	role, visible objects, release timing, clarification channels	定义局部信息与授权


代码边界：
- kernel.py 保留身份、工具和持久化动作，不依赖特定第二轮财务事实。
- workflow.py 维护节点状态，消费已提交事件，实例化新增义务。
- events.py 注册受约束事件处理器；不允许生成器任意执行后台代码。
- domain/operating_toy.py 保留现有算术领域，明确它不是规范金融建模知识。
- renderers/xlsx.py 与 renderers/json.py 按 LayoutMap 建文件。
- validation.py 根据 ArtifactContract 定位对象，不到处写死 B2/B6 和 work-2。
保留当前模板为 legacy adapter。迁移后的它应保持原来的可见目标、输入与预期结果。
第一批结构，不追求无限组合
1. 链式更新：披露 -> 模型 -> 备忘录；复现当前行为。
2. 分叉同步：一个模型影响备忘录和情景说明，两个产物需要各自绑定对应输入。
3. 选择性失效：某变更只影响其中一个成果；学会判断应更新什么，不是全部重写。
4. 信息协调与实际返工：口径存在缺口或版本冲突，通过有权限角色确认；审阅仅依据实际交付提出问题，正确成果直接结束。
工作节点的存在条件、输出依赖、信息持有者是结构变化；企业名称、种子、目录顺序是表面变化，不混用统计。
每个结构要有工具层可行性见证，但见证不充当训练后的目标模型或唯一合法执行路线。
角色迭代
保留固定 manager/reviewer 作为可解释基线。先抽象 StaffPolicy 的观察与动作接口，再单独引入语言模型表达层。
角色可以改变沟通表述，不能自行创设事实、授权或隐藏评分要求。正式审批仍通过受权限保护的明确动作。第一轮训练不要同时优化环境工作人员与目标模型。
v0.2 验收
新增一个结构主要修改规格/模板，而非环境内核；相同业务语义更换布局后仍可正确求解；依赖链或角色信息变化会改变所需工作；无关文本变化不改变答案；没有必然返工剧情。
3. v0.3：材料划分与可靠经历产品
独立性与覆盖
保留 seed 衍生 lineage 分组，新增 source_family_id, template_id, topology_id, layout_id, role_information_id, scenario_id。同一项目分支和改写不得跨组。
至少区分：
- 同结构、新来源/参数的实例保留集。
- 未见结构组合保留集。
- 新布局/信息位置的迁移集。
这些评价集衡量不同泛化，不合并成一个“新种子泛化”结论。当前 synthetic seed 分组是防同实例泄漏，不证明结构隔离。
经验记录
增加 EpisodeRecord：初始快照、任务与需求版本、policy_version、模型调用 IDs、真实动作、所有提交结果、最终 outcome 与停止原因。
把 artifact_valid、business_accepted、explanation_assessed、trajectory_supervision_status 分开；全局 passed 不能让未评专业质量悄悄变成金标。
监督对象仍可采用经过验证的成功区间，但要明确它是 outcome-conditioned 候选。历史错误作为上下文、不是正向目标；纯文本合法输出与工具输出分开记录；测试夹具、规则见证不成为模型正例。
对首个正式数据包执行真实目标 tokenizer 渲染、长度检查、消息/工具角色转换、token-level loss mask 和最小 loss/backward；不能把 JSONL 数量当成已可训练。
观测压缩
每轮全量 observe 逐次附加会扩大上下文。可改为全量起始观察+增量事件/版本通知，并按需取 work item、邮件与表格范围。
这是运行框架变更，需要版本化并对照；保留模型实际收到的输入，不事后改写历史请求。是否节省 token 及是否影响成功率需要测量，不能直接用单个样例估计通用收益。
4. 参数训练接入：先验证小闭环，再比较算法
不要让 DeepSeek API 返回的模型名等同于可更新本地权重。选择一个具备训练权限与本地权重的目标模型，分别定义 ModelBackend 与 TrainerBackend。
先完成一次真实参数更新、checkpoint 保存、重新加载，并在相同环境接口执行。这个结果只叫训练链路通过。
首轮数据可来自目标模型自己执行得到的有效区间；若成功支持不足，独立记录少量指导/Teacher 路径，不能伪装成目标模型自行探索成功。
暂缺精确行为概率和原始 token 路径时，继续将 RL 导出标为 interchange-only。严格 on-policy 训练需要已知 policy_version、采样参数、真实 token/logprob 与后端契约。
对一次项目拆成多个模型调用的情形，显式冻结 project/episode/call/token 的加权规则，避免长项目仅因调用多就意外放大权重。不要把原 API reasoning 字段自动映射成另一个模型的隐藏思考格式。
5. 效果研究与外层课程
当前 short/file/continuous 同时改变工作数、备忘录要求、交互轮数；不能用这三个条件直接估计“连续项目训练”的因果效果。
构造 matched scenario：同一来源、相同两阶段目标、相同交付物和工具。连续条件继承真实第一阶段状态；独立条件使用匹配且预先定义的第二阶段起点。明确比较的是状态继承、上下文继承还是二者组合，不能同时更换多个未说明因素。
开发阶段比较静态配额与失败定向配额，再研究结构化控制器。历史失败只有在环境与评价有效、版本适用的情况下才进入控制器；按 episode/任务分母聚合，避免重试多的个案反复放大。
环境生成和控制器探索的成本都计入预算。测试集不反馈课程；效果尺度依据希望检测的增益、项目聚类和训练种子差异事先设计，不以四五个案例作为充分样本量。
最终实施顺序
1. 修复 F1/F2/F3，保留有限机制基线。
2. 把工作网络、产物契约和布局映射从固定业务代码中提取。
3. 建立少量真实结构变化及独立谱系/结构保留集。
4. 打通一次真实目标模型参数训练，明确候选监督与未评项。
5. 比较连续/独立与静态/反馈课程；之后再考虑角色模型共训与更复杂金融领域。
“没有完整 GUI”“没有分布式事务”“没有所有角色一起训练”不构成当前阶段的阻断。每一步以本轮具体研究声明所需的最小证据验收。
