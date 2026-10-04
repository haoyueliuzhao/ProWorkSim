# v0.30 O1与中型代码模型：冻结选型协议

本轮依据[用户新审计](../reference/audit-v029-next-v030.md)，先解决共同载体的工作、修复与可微更新资格。v0.29保持8/8闭合、完整有效0/8、无支持和零分配更新的原结论。本轮不重复旧sqlparse八槽，也不以旧0/8作为新模型的同协议参照。

## 1. 范围与结束条件

本轮固定三个运行组合：当前项目9B端点、SWE-Next-14B、Devstral-Small-2507。后两者为唯一新增模型；不下载Small 2、普通Coder或其他回退候选，不根据工作低分追加模型。技术资格与开发工作分开；未通过必要资格的臂终止，其他臂独立继续。

本轮最多36条正式筛选经历（6个开发案例×2个seed×3模型），另每模型至多4次独立原生技术诊断生成、1次诊断更新及1个更新后单调用WorldCore片段。后三项只作技术资格，不并入36条工作成绩，更不是额外项目或算法收益。

筛选结束后按预先规则选择一个可训练组合；全部不合格则明确结束本批。研究下一步是以选定组合产生新的O1当前策略支持，再开展B/G-raw/I-P，不能将本轮开发经历改成训练材料。本轮不自动启动尚未冻结的贡献试训/独立确认清单，不以旧M=8机械外推下一窗。

## 2. 固定候选与数值profile

| 运行组合 | 权重身份 | 项目初始化 |
|---|---|---|
| 当前9B参照 | Qwen/Qwen3.5-9B `c202236235762e1c871ad0ccb60c8ee5ba337b9a` | 严格恢复v025-r1完整actor/critic 3/3端点 |
| SWE-Next-14B | TIGER-Lab/SWE-Next-14B `5d9484d6b0e20786629fccf6de9f190f5fb5ebc7` | 官方权重，加新的项目LoRA/critic/两个optimizer，0/0 |
| Devstral-Small-2507 | mistralai/Devstral-Small-2507 `bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39` | 官方BF16权重，加新的项目LoRA/critic/两个optimizer，0/0 |

新架构不继承9B的LoRA或optimizer。当前9B包含过去项目更新，新候选包含不同公开后训练；因此这是运行组合选型，不是参数规模或某一后训练方法的因果比较。模型卡外部基准数字不换算为本项目能力，来源、许可与有限重合检查见[候选研究](../research/software-model-candidates-v030.md)。官方依据：[Devstral模型卡](https://huggingface.co/mistralai/Devstral-Small-2507)、[SWE-Next模型卡](https://huggingface.co/TIGER-Lab/SWE-Next-14B)。

三臂固定单张A100 80GB、temperature=0.7、top_p=1、top_k=0、repetition penalty=1、输出上限2048、上下文上限16384。保持原概率门max absolute error≤0.02、mean absolute error≤0.002。主干BF16、冻结输出头FP32、LoRA及其计算FP32；关闭ambient autocast和TF32，LoRA r=8/alpha=16/dropout=0，仅q_proj/v_proj。9B仅其完整注意力层匹配，两个密集模型则每层匹配，因此实际可训练参数和模块清单必须分别报告。

9B继续原已验证函数式学习路径。两个新密集模型使用原SharedActor和原完整序列selected-logprob路径，明确高效SDPA和输出头计算，不靠截断上下文或删错误token取得概率一致。实际加载核验全部分片、架构、EOS、LoRA模块、dtype/device及未加载/多余tensor；禁止CPU/disk offload或悄悄改精度。

## 3. 原生格式与真实token证据

SWE-Next使用其固定官方Qwen2模板及JSON `<tool_call>`；当前9B保留XML function/parameter格式。实际下载的Devstral `tekken.json`声明 **v13**，官方mistral-common 1.7.0实际选择InstructTokenizerV13，其助手工具串为`[TOOL_CALLS]name[ARGS]{argument_object}</s>`；不根据模型名误套旧v7数组格式。

Mistral输入直接使用官方`encode_chat_completion`产生的token IDs；带特殊控制标记的可读render只作审计，不经另一个tokenizer重新编码。Qwen同样保存真实模板输入和采样输出。完整原请求、选中上下文、实际IDs、行为logprobs、模型身份和边界原件均保存。只加公开的一次单工具语法说明，不提供任务答案或隐藏参考实现。多工具/不合法格式按原有界规则保留与拒绝，不改原始输出取得成功。

三臂的公共SDK选择策略固定为`first_and_latest_observation_last4_tool_rounds`：保留首个和最新真实observation、至多四个完整工具轮。Mistral官方v13不接受SDK实际产生的`tool → user`序列，故仅其原生编码层把后续真实user装入tool envelope，分别完整保存`original_tool_message`和`subsequent_user_messages`，并记录来源索引与hash；不制造助手或工具结果，不删观察、错误回执或已采样token。原始SDK request仍独立保存。此前阻断及修订后18/18组合、72次CPU往返、24次真实错误回流见[原生模板资格](software-native-templates-v030.md)。这属于公开记录的载体格式适配，不能据此作纯模型规模因果比较。

mistral-common和SentencePiece安装在独立`runs/v030-runtime-deps`，不修改原9B环境。实际使用的依赖版本、权重下载完整SHA与加载前未变的size/mtime分别记录；不会把下载占位文件或预分配逻辑大小当作完整权重。

## 4. O1任务形成与测试覆盖

环境只给共同根目标、代码、公共合同、兼容要求、权限与资源边界，初始任务表为空。成员自行创建、修订、领取任务、转交责任和安排依赖。固定两个稳定启动身份，不增加经理或动态扩员；前四单执行者案例只启用A，另一个身份不可接受责任。

任务修订有版本，依赖绑定当时版本，固定patch记载当时任务scope/owner/dependency快照；旧patch不会自动完成新修订任务。模型可以集中完成，也可以拆分协作。任务数、消息数或两人都改代码不是成功条件，也不进入选型排名。

run_tests分别呈现上游回归、公开正常路径、成员自测及未测试部分；公共正常例由公开合同派生，与隐藏独立输入分离。修复类初始执行真实有缺陷代码，提供标为controller-forced的失败反馈。这不是模型自主发现错误，也不是自动替模型修复。

固定提交要求当前版本真实测试和固定patch，但不强制测试必须绿色；失败仍可形成可评提交。提交回执仅保存版本，不代表独立通过。独立验收保持父进程执行，模型不能看到隐藏参考/评分文件；公开通过不能替代完整根目标验收。

## 5. 六个开发案例与用途隔离

这六个实质不同合同均复用已固定MIT Marshmallow 4.3.1源码（commit `c7b559a1fa3aba57ca6dba0ab336841c5038a782`），是**一仓库六合同**，不是六独立项目或官方六道SWE题。新派生需求、初始实现、公开检查、隐藏检查与参考/坏控制各自固定hash，见[开发池说明](../../examples/software-sources-v030/README.md)。

| 类别 | 案例 | 启动成员 | 主要观察 |
|---|---|---|---|
| API正常路径 | nested load/import | A | 返回对象与嵌套消费关系 |
| API正常路径 | datetime/attribute serialization | A | 类型、字段映射和正常输出 |
| 真实失败修复 | pre_load many envelope | A | 实际错误后修改、重测、固定 |
| 真实失败修复 | nested validation error handling | A | 保留并处理真实错误路径 |
| O1共同根目标 | batch ledger import/canonical amounts/report | A/B | 自主任务形成、责任与集成 |
| O1共同根目标 | settings partial overlay/redacted export | A/B | 自主分解、依赖与完整根目标 |

每模型使用同两seed `202610040701/202610040702`，顺序为seed外层、固定case顺序内层。单执行者每槽64次决策，双成员每人64次；每模型至多1024次正式工作调用，三模型共3072次，技术资格另最多15次调用。

全部标为`model_interface_development`，optimizer、贡献开发、独立确认资格均false；删除附加标签也不能把其转成训练材料。schema贡献开发、TextFSM独立确认以及当前sqlparse训练材料均不参与挑模型。本仓库曾用于旧9B冻结开发交互，但未用于项目参数训练；不将这种历史暴露描述为陌生仓库。

## 6. 推理、训练和容量资格分别判定

权重加载成功不是资格完成。各模型完整共同状态在诊断前保存，诊断后严格恢复，正式筛选使用原共同状态；不让诊断优化改变候选工作比较。

原生技术控制固定四次生成：短请求读取真实note；真实读回及约8192-token代码返回后的事实记录；控制器真实missing-file异常及约10240-token输入后的继续；约14336-token输入加180独立函数写出要求的2048输出上限压力请求。长fixture是独立技术材料，不取自六个开发案例。强制初始异常有真实执行回执，明确不归为模型动作。

前3次验证正常多轮接口和真实反馈继续；第4次可能自然达到输出上限或形成未闭合工具串，全部原始token仍进入概率与有梯度数值检查。不得强制minimum generation、改EOS、重写概率、裁尾重判或补采到够长。

四条原始trace全部通过原概率门后才允许一次聚合技术更新：复用原PPO token surrogate、原optimizer与clip，使用明确声明的恒定正诊断信号及技术critic目标，保留全部输入/输出与梯度依赖。这不是软件业务reward、开发任务训练或算法收益；目的是核对真实参数变化、两个optimizer状态、完整checkpoint保存/重载和新身份回流。任何概率失败均零步，保持真实失败。

更新后执行一个新身份的单调用WorldCore片段，核对实际响应身份、窗口及无旧缓存；不要求这个1次调用片段完成软件任务，也不纳入36条成绩。最后完整恢复共同actor/critic/两个optimizer/RNG用于正式筛选。

训练接口资格与近16K容量证据分开记录：后者要求真实压力序列输入+输出≥15360且完整反传成功，否则记`capacity_not_demonstrated`，不以短生成外推。总training_ready同时要求接口、概率、更新、重载、新身份回流及该容量证据。实际每条长度、更新耗时与显存峰值单列；资格不能保证任意未来窗口的成本或消除长输出显存风险。

## 7. 事前选型规则

只有推理和training_ready均通过的臂才进入正式开发筛选。进入后预定12槽全部执行并保留成功、可信失败、未映射（如适用）及技术未知；不根据中途工作低分提前换模型或追加seed。

模型成为可选组合需满足：12槽全部有已知完整验收；API、修复、O1三个类别各至少2/4通过。排名依次按O1完整成功数、修复完整成功数、API完整成功数、两个seed都通过的案例数、更少SDK格式错误、更少实际worker GPU秒，最后固定候选顺序打破完全相同的平局。

三个类别分别报告，不给一个混淆单执行者与团队任务的总成功率。不得按消息数量、形成多少任务、方法类别数或可见“合作感”选模型。全部不合格则本批结束；选择后，参数模型、harness和数值profile整体冻结。筛选差值属于载体组合差异，不代表ID-VTDO增量。

## 8. 资源、成本和异常

用户已撤销的累计GPU/worker时长、统一墙钟和队列截止均保持None。每模型至多一个owner，最多3个并行，GPU0–7均可用；空闲A100需≥78000MiB free、利用率≤5%、无其他compute进程且稳定60秒。下载未complete的臂只CPU等待，不占GPU；不终止其他任务。

单worker RSS≤64GiB；实验原件上限128GiB、卷预留20GiB；loading900秒、单episode2400秒、boundary600秒、单资格inference900秒；qualification update没有统一时间帽，但持续资源监控。记录下载、排队、装载、技术更新、冻结工作和报告的实际成本，不从旧9B收集1.783 GPU小时推断新24B训练耗时。

两个新候选只下载一份官方Transformers分片集合，不下载Devstral的重复consolidated权重。ModelScope仅在固定revision、每分片SHA/size与HF完全一致时作传输来源，最后完整下载SHA必须验证。HTTP原前缀、重试/改传输原因与实际range进度保留，不能用预分配文件大小宣传下载完成。

旧27B清理按用户明确授权完成，见[清理记录](../operations/model-27b-cleanup-2026-10-04.md)。保留旧模型身份元数据、9B基座与检查点和所有实验原件；已删除权重的目录明确标为不可加载。

## 9. 与分配主线的对齐

新增[一阶分配修订](../design/experience-allocation-v030.md)恢复可见理论条款中的对数N、显式历史锚及覆盖锚，并区分不接语义类别/图的G-raw、读取类别先验但类内独立的G-lift辅助对照、类别共享I-P。旧v027/v029线性N、q0=b变体和旧结果保持。

当前本地只有新审计与较早详细理论可见条款，未取得完整V1.3原文。该实现仅声明已核对的一阶部分；跨窗口历史转移、贡献预测、真实配对试训、图结构共享和O3动态成员仍分别需要独立实现/实验证据。本轮选型不调用配置器，也不声称已完成完整理论或取得分配收益。

下一项配置实验必须在选定同一模型/完整学习起点下新采O1材料，按新开发产出和精度要求冻结重复数与最低频数，保持失败残余与原分母；C来自更新后的真实贡献开发，独立确认不回流。G-raw公平一般基线及全部试训成本先登记，不能靠删原始经历或删方向压低一般基线预算。
