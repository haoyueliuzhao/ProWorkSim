# v054：REF 参考配置与 MATCH 数值、资源对齐草案

记录日期：2026-10-20。状态：**proposed / 待冻结，仅供审阅，不是运行准入或新增模型回合授权**。本配置调研只查阅官方资料和已有本地源码，没有加载模型、启动 GPU、执行能力测试、下载大文件或搜索配置。用户随后授权的 PROJECT 文件接口修复及实际SDK构造检查单独记录在[修复说明](software-benchmark-v054-file-repair.md)，不表示本文件的 REF/MATCH 已实现。

目标任务集为 SWE-bench Verified 官方 `test` 完整 500 题。REF、MATCH、PROJECT 各对同一题运行一次；模型始终为原始 `Qwen/Qwen3.5-9B`，不挂训练 adapter、不训练。题单、官方镜像修复身份、环境、最终候选与评分合同由主方案另外冻结；不能把 v053 的 SWE-smith 环境资格移作 Verified 资格。

## 1. 当前能支持的外部参考结论

本次查阅的 Qwen3.5-9B 官方模型卡给出了模型、推理模式、采样与服务部署建议，但其 9B 结果表中没有 SWE-bench Verified 项，也没有给出“该 9B 模型 + 明确 OpenHands commit + 工具 + 提示模板 + 采样 + 预算 + 500 题结果”的完整复现包。官方 OpenHands 提供通用 SDK、preset 和 SWE-bench 执行文档，本次没有找到与原始 9B 对应的完整公开 benchmark 配置。因此，本文件不能将 REF 命名为“官方 9B SWE-bench 复现”，也不能借用 27B、35B、397B、Coder 或训练衍生模型的设置及分数代替 9B。[固定 revision 的官方模型卡](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)、[OpenHands benchmark 说明](https://github.com/OpenHands/benchmarks)、[官方 SWE-bench 使用说明](https://github.com/OpenHands/benchmarks/blob/main/benchmarks/swebench/README.md)。

“本次没有找到”是限定于所查资料的结论，不是对所有公开材料作穷尽性证明。Qwen 原 `QwenLM/Qwen3.5` GitHub 地址本次已重定向到 `Qwen3.8`，不能把该浮动入口当前内容视作 3.5-9B 的固定来源。另一个容易误用的来源是 vLLM 的 Qwen3.5/3.6 recipe：当前页主要展示大规模 MoE 的部署，不是本服务器上 9B 的实测资源证明。[Qwen GitHub 入口](https://github.com/QwenLM/Qwen3.5)、[vLLM 官方 recipe](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html)。

REF 的准确名称应为：**依据官方组件与模型使用建议，预先提出的原始 9B 外部参考配置**。它是一个待冻结候选，既不是论文分数复现，也不是通过多配置试跑挑出的最佳结果。

## 2. 三臂关系不能改写

| 项目 | REF | MATCH | PROJECT |
| --- | --- | --- | --- |
| 控制流 | 固定官方 OpenHands Agent / Conversation | 与 REF 完全相同的官方控制流 | 项目真实受管 S1 |
| 工具、工具描述、执行方式 | 下文固定的原生工具组合 | **与 REF 相同** | 保持真实项目工具；不补 bash |
| system 模板、题面呈现规则 | REF 的固定模板 | **与 REF 相同** | 项目原有规则 |
| 历史管理 | 固定官方 condenser 算法与配置 | **与 REF 相同** | 项目原有投影、历史管理和反馈 |
| 推理配置 | 本文件单一参考候选 | 匹配 PROJECT 的推理设置与可匹配资源限制 | 项目冻结推理配置 |
| 用途 | 外部参考能力 | 将外部 Agent 放入项目推理与资源条件 | 项目实际运行状态 |

MATCH **不得**为方便接入而改成 PROJECT 等价工具、换成两工具 mini preset、换项目历史裁剪，或把 PROJECT 新增 bash 后再声称能力相同。REF→MATCH 是推理与资源配置迁移的整体差异；MATCH→PROJECT 是实际 Agent 系统差异，包含其工具、提示、历史和执行机制，不能自动解释为某一个单独模块的因果效应。

同一历史管理算法不意味着生成后的历史内容、摘要次数或终止点相同。例如，相同 condenser 使用 Agent 的有效输入容量作为触发上界时，MATCH 的短窗口会更早触发；应将此列为容量变化诱发的行为差异，不能热改其算法补偿成绩。

## 3. SDK 1.49.6 的原生组合与现有 v053 接口差别

本地已固定 SDK / tools 版本 `1.49.6`，来源 commit 为 `fcc102a697874d54a357e36004e02c95040dbdc0`。本次只读了该 checkout 的 preset、Agent 和 condenser 源码，没有重新安装。固定源码中的 `get_default_tools` 包含 Terminal、FileEditor、TaskTracker；browser 默认开启、sub-agent 默认关闭。Agent 的内建工具是 Finish 和 Think。`get_default_agent` 还配置默认 condenser；该工厂的摘要配置为 `max_size=80`、`keep_first=4`，不应误用摘要类本身另设的字段默认值。[官方 Hello World](https://docs.openhands.dev/sdk/guides/hello-world)、[固定 preset 来源](https://github.com/OpenHands/software-agent-sdk/blob/fcc102a697874d54a357e36004e02c95040dbdc0/openhands-tools/openhands/tools/preset/default.py)、[固定 Agent 来源](https://github.com/OpenHands/software-agent-sdk/blob/fcc102a697874d54a357e36004e02c95040dbdc0/openhands-sdk/openhands/sdk/agent/base.py)、[固定 condenser 来源](https://github.com/OpenHands/software-agent-sdk/blob/fcc102a697874d54a357e36004e02c95040dbdc0/openhands-sdk/openhands/sdk/context/condenser/llm_summarizing_condenser.py)。

现有 [v053 native 模块](../../src/proworksim/software_panel_native_v053.py) 与 [v052 参照说明](software-bridge-v052-openhands-reference.md) 的真实状态是：

- 使用官方 Agent / Conversation 控制流，但只暴露 Terminal 和 Finish；不含 FileEditor、TaskTracker、Think、Browser、MCP 或 delegate，且 `condenser=None`。
- Terminal 工厂来自官方，但执行器和描述改为每命令新建非交互 bash，`cd/export` 与后台任务不跨调用保留，普通命令限制为 1—60 秒。它不是官方持久交互终端行为。
- 模型经过项目 provider；BF16 主干、FP32 输出头、项目 attention 和 FP32 采样。这里的“native”指原生控制流及真实模型请求，不等于标准外部推理引擎。
- 共享渲染器会追加 `XML_SINGLE_CALL_HINT`；v053 bridge 还显式拒绝 terminal/finish 以外的工具。

因此，**现有 v053 collector 不能直接改名成为 v054 MATCH**。后续如进入实现阶段，应新建独立适配接缝，共享 PROJECT 所需数值层，但不向 REF/MATCH 插入项目提示、不限制成两工具、不替换原生终端、不进行项目历史投影。数值请求的标准 tool-call 解析、reasoning 字段和多工具回包语义要与 REF 对齐。现在没有实施这一接缝，也没有证明其已通过。

上文几个固定 commit 的网页读取本次出现缓存未命中；对该版本的具体判断来自已保存 checkout 的只读源码。在线当前文档仅用于理解接口，不能冒充旧版本源码已逐字联网重新取得。

SDK进程须在导入前设置 `LITELLM_LOCAL_MODEL_COST_MAP=True`，使用随已安装包提供的模型价格表，避免初始化自动刷新远端价格表。PROJECT真实构造控制在该设置下已通过，网络尝试和模型调用均为0，见[构造凭据](software-benchmark-v054-sdk-construction-r3.json)。这项通用启动设置不改变Agent工具、推理参数或token计量；REF/MATCH的实际运行接入仍待实现。

## 4. 唯一 REF 候选

候选标识暂定 `REF-P1`。以下参数是为了形成一个具体可审阅方案而预先提出的单一选择；未运行、未按任务得分筛选。每项最终值及来源还须写进不可变运行配置。

| 项目 | REF-P1 提议 |
| --- | --- |
| 模型 | `Qwen/Qwen3.5-9B`，revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`；沿用已验证完整文件，禁止 adapter、量化替换和权重微调 |
| 服务实现 | 官方 vLLM OpenAI-compatible 服务；确切 release/commit、依赖和容器或 wheel SHA 待冻结，不使用浮动 `latest` |
| 数值 | BF16 模型计算配置，保留引擎自身正常累加实现；不挂项目 FP32 head / attention / sampler 补丁；不启用量化、MTP 或 speculative decoding |
| 模型用途 | 只接收文本；不加载视觉路径参与任务；不使用图像工具 |
| 模式 | `enable_thinking=true`；reasoning parser 为 `qwen3`；工具解析选择该固定引擎的 `qwen3_coder` |
| 采样 | temperature `0.6`、top-p `0.95`、top-k `20`、min-p `0`、presence penalty `0`、repetition penalty `1` |
| 容量 | 输入加输出总窗口 `131,072 tokens`；每次最多输出 `32,768 tokens`，有效输入上限相应为 `98,304` |
| Agent | SDK / tools `1.49.6` 与上述 commit；官方 Agent / Conversation；仅一个 Agent |
| 工具 | 原生 Terminal、FileEditor、TaskTracker，加内建 Finish、Think；browser=false、sub-agents=false、MCP为空；没有外部 critic / verifier |
| system 与工具描述 | 固定该 SDK 的 system 模板（`cli_mode=false`）、所列工具的原始描述及唯一 Verified 题面后缀；不加载个人 SOUL、宿主 AGENTS、用户插件或任务外技能 |
| 终端执行 | 官方持久终端语义，运行于每题独立环境；REF/MATCH 使用相同 executor、工具限制和容器工作路径 |
| 历史管理 | 官方 `LLMSummarizingCondenser`，`max_size=80`、`keep_first=4`、`max_tokens=None`；额外明确 `hard_context_reset_max_retries=1`，避免隐含的失败后多次摘要重试 |
| 摘要模型 | 同一原始 9B、同臂推理设置；属于单 Agent 的历史压缩，不是第二个解题 Agent；调用和 token 全部计入同题账本 |
| 调用与总 token | 每题至多 128 次 Agent 决定、128 次实际模型 attempt、500,000 输入加输出 token；摘要、解析失败和任何其他实际模型调用均占该上限 |
| 时间 | 每题 5,400 秒后不开始新模型请求；6,000 秒硬终止；REF 单次模型调用提议 1,800 秒、外层请求守卫 1,860 秒；不得突破剩余 episode 时间 |
| 重试与缓存 | SDK / HTTP 自动模型重试设为 0；无跨题 prefix cache；每题独立初态和固定 seed；不从前一题继承摘要或补丁 |
| 候选 | 仅终态生产树，最终评分之前唯一锁定；无 critic 选择、多候选择优或评分后重导出 |

其中 thinking coding 采样组合和长输出建议来自模型卡；将这组通用 coding 建议用于 Verified，是本方案选择，**不是官方 SWE-bench 设置声明**。模型卡给出的原生容量为 262,144；这里选择 131,072，是其建议的至少 128K 区间内较小的单候选，明确不声称复现 262K 原始默认设置。它也不是 v053 的 18,432 窗口。[Qwen 官方模型卡的部署与 Best Practices](https://huggingface.co/Qwen/Qwen3.5-9B#best-practices)。

原模型卡内“非思考 reasoning”的两处参数列表存在不一致；本候选没有采用这一分支，不混合不同小节拼出一个所谓官方参数组。Browser 关闭、上述预算和摘要重试上限都是本实验限制，所以也不能把 REF-P1 称为“所有 OpenHands 产品的默认 preset”。

reasoning 历史须另外冻结实际传输字段：该固定 Qwen chat template 会按最近真实 user 消息位置决定如何重渲染先前 reasoning；现有文件没有读取 `preserve_thinking` 这一开关。不能仅写 `preserve_thinking=true/false` 就宣称历史行为已受控。REF 必须保留服务端实际 reasoning 回包和 SDK 接收记录，并以真实请求捕获证明下一请求是否按模板回传；MATCH 的算法和序列化接口与 REF 相同，但禁用 thinking 后不生成新 reasoning。该接缝现在未验证，不据此启动正式任务。

## 5. MATCH 与 PROJECT 的数值、资源对齐清单

下表以当前项目推理合同作为拟匹配对象，不表示 v054 运行已冻结。REF/MATCH 的工具、system 与历史管理按上一节保持相同；它们不能因接入困难被替换为 PROJECT 工具。

| 维度 | REF-P1 | MATCH / PROJECT 拟共同设置 |
| --- | --- | --- |
| 模型文件 | 相同固定原始 9B | 相同固定原始 9B |
| 推理模式 | thinking | 非 thinking；如实记录模板是否消费历史开关 |
| temperature / top-p / top-k | `0.6 / 0.95 / 20` | `0.7 / 1 / 0` |
| repetition penalty | `1` | `1` |
| presence / min-p | `0 / 0` | 当前 provider 没有额外该类变换；须冻结“无变换”语义，不能让外部服务默认值介入 |
| 总窗口 / 最大输出 | `131072 / 32768` | `18432 / 2048`；完整 prompt 至多 `16384` |
| 权重计算路径 | vLLM 常规 BF16 路径 | 现有 BF16 主干 + FP32 lm_head；无 adapter |
| attention | 固定外部引擎实现 | 项目 `sdpa_bf16_explicit_kv_v020` |
| sampling 实现 | 固定外部引擎实现 | 既有 FP32 sampling transform；温度和 top-k/top-p 只施加一次 |
| 文本终止 | 由固定模型配置、模板及引擎 parser 声明 | EOS `[248044,248046]`，pad `248044`；必须证明未被 SDK 默认 stop 覆盖 |
| 单次模型时间 | 提议 1800 秒 / 1860 秒外守卫 | provider 600 秒 / host 660 秒外守卫 |
| 每题总预算 | 提议 500000 token / 128 实际调用 | 同为 500000 token / 128 实际调用，128 Agent 决定另计 |
| 总体并发 | 与其他臂共用全局最多 4 resident，单卡单 resident | 同一全局上限，不按每臂分别开 4 个 |
| GPU /种子 | 相同允许的物理卡集合，预定 per-task seed | 同样规则；相同 seed 不保证不同引擎生成相同序列 |
| 工具测试、CPU与I/O | 原生工具执行方式 | MATCH 保持 REF；PROJECT 保持 S1；实际 CPU 秒数、工具次数及反馈字节另报 |

MATCH 若要真正匹配 PROJECT 的数值实现，必须共享其冻结模型加载、attention、输出头和采样变换，而非只在 vLLM API 写下相同 temperature 就称数值相同。REF→MATCH 因而同时包含推理引擎/内核、思考模式、采样、窗口、输出和资源限制的改变；这些是整体配置差异，不能独立归因于某个字段。若最终只对齐可表达的 API 参数，必须降低表述为“参数匹配、数值 backend 未匹配”，并保留这个限制。

同样，现有数值渲染器追加的 `XML_SINGLE_CALL_HINT` 不是采样参数。MATCH 不得为了复用它而改变与 REF 相同的 system 模板；PROJECT 若保持其原提示，该差异属于 MATCH→PROJECT 的实际系统区别。需要一个不注入提示的数值入口，而不是改写旧冻结源码或谎称已有 collector 已具备该能力。

模型调用上限也不能冒充工具机会相同。PROJECT 若继续保留 S1 的独立公开测试次数上限，而原生 Terminal 允许一般测试命令，这两种计数不能直接等同；应记录不可匹配项和实际测试/工具分布。不能给 MATCH 偷加 `bridge_run_tests` 专用工具、替换终端或缩减 FileEditor/Think 来制造表面一致。

### GPU 准入不能只按“9B”标签复用

现有 [v053 资源模块](../../src/proworksim/software_panel_resources_v053.py) 实际筛选 A100/A800、总显存至少 `81,920 MiB`、空闲至少 `46,080 MiB`；复用缓存目标为 `min(72 GiB, free−1 GiB)`，最低 `44 GiB`。它还核对物理序号与 UUID，要求 native allocator。这是项目现有数值路径的资源策略，不是 vLLM 128K 配置已通过的证明。

REF-P1 提议单卡 TP=1、单序列、vLLM 显存比例 0.80、禁跨题 prefix cache，初步硬等待门为同级 80 GiB 卡空闲不少于 `65 GiB`。这个门由 0.80×80 GiB 再留 1 GiB 空闲算得，是计划值；没有进行实际 vLLM 内存资格验证，不能宣称它已经足够容纳目标窗口。正式实现前应按一次固定配置的真实容量准备结果确认，不够就暂停并另版修订，不能自动改成量化、缩窗口、换 sampler 或借用他人显存。

REF 使用外部引擎自己的 KV/状态内存管理，不叠加项目 r3/r5 的大块缓存预约。MATCH/PROJECT 的可匹配显存与设备准入规则一致；它们实际 CPU、GPU 时间和显存峰值仍应记录，不能把“同 token 预算”写成“同算力成本”。目前未新增占位、GPU轮询、模型服务或显存诊断。

## 6. 预算预约与实际费用的统一口径

每次请求都先取得该臂实际 chat template 渲染的完整输入 token 数 `I`，在生成前预约 `I + O_max`，并检查上下文与本题剩余余额。REF 的 `O_max=32768`，MATCH/PROJECT 的 `O_max=2048`；不同预约粒度会影响接近预算末尾时能否再调用，属于预定配置差异。不能在成绩较差时临时缩小输出预约以增加调用次数。

完成后结算实际 `I + O_actual`；输出包含 reasoning、工具调用文本和普通内容。输入要计算每次实际重发的历史及工具 schema，不能只数新增消息或最后答案。任何 SDK condenser 调用、格式错误、被解析器拒绝的完整生成都计费。prefix cache 即使减少物理计算，也不能让重复输入在“逻辑输入 token 预算”中消失；缓存命中和物理成本可以另报。

未知 usage、timeout、断线和进程中断不能按零 token 结算。保留已确认实际量以及未决预约，暂停未启动库存；没有精确可审计恢复包时不自动重采已进入模型的任务。只有模型入口前、有证明的纯资源等待才可重排，并且不改变题目、seed、配置或计分分母。

“128 决定”不等于“128 次所有模型调用”：默认摘要可在一次 Agent 迭代之外调用模型。需要独立 `agent_decisions`、`all_model_attempts`、`condenser_attempts` 与各自 actual token 计数。所有生成共享该题的 128 次实际调用和 500000 token 上限，不能给摘要另开未计费通道。

## 7. 新方案的上限与既有授权分开

| 部分 | 任务×预定运行 | 每回合输入＋输出 token 上限 | 总 token 上限 | 全部实际模型 attempt 上限 |
| --- | --- | --- | --- | --- |
| MATCH | 500×1 | 500,000 | 250,000,000 | 64,000 |
| PROJECT | 500×1 | 500,000 | 250,000,000 | 64,000 |
| MATCH＋PROJECT | 1,000 回合 | — | **500,000,000** | **128,000** |
| REF-P1 候选，单列 | 500×1 | 500,000 | **250,000,000** | **64,000** |
| 若未来三臂均获准实施 | 1,500 回合 | — | **750,000,000** | **192,000** |

这些是上限，不是预计消耗，更不包括环境构建、数据传输、CPU测试、GPU驻留与准备成本。按每题 6000 秒硬界相加，每臂为 833.3 个 episode 槽小时；这不是实际 GPU 小时，也不含等待或准备，不能据此给出完成日期。

新计划的 5 亿 MATCH＋PROJECT 预算、单列的 2.5 亿 REF 候选预算均不能沿用 v053 的 1.4 亿上限。当前用户要求只是修订可审阅方案；本文件的数字不构成执行授权，不启动 1500 回合，也不以“资格试验”名义消费新模型回合。

## 8. 正式冻结前的最小缺口

以下是后续方案必须补齐的具体字段，不是现在要求运行测试：

1. vLLM 确切代码/包/镜像身份及实际数值、parser、chat-template SHA；SDK 1.49.6 若继续采用，冻结其全部真实导入来源。模型文件已有凭据可复用，不重复 hash 19 GB 权重。
2. REF/MATCH 共同的完整工具 schema、system/题面模板、condenser 参数、原生持久终端执行与 timeout；MATCH 无项目提示注入的数值接缝。PROJECT S1 单Agent合同单列，不能补 bash。
3. 使用实际 tokenizer 的初态容量及合成协议请求控制；对 reasoning/tool-call round trip、摘要独立 usage、跨引擎参数含义做有限接口核验。不跑完整500题作配置搜索，不新增模型资格回合。
4. 每题 seed、三臂调度顺序及其固定规则，必要的设备/容量计划；不能因早期分数或某仓库困难而换配置、删题或只完成容易子集。
5. Verified 官方完整 500 行身份、修复后镜像、最终官方评分版本及每题未知处理，由主方案另行形成独立资格清单。最终结果的分母保留 500，资源/基础设施未知单列。

在这些项仍未冻结时，报告应使用“REF-P1 proposed、MATCH 待实现、PROJECT 方案待冻结”，不能使用“原生标准参照已复现”“数值完全一致已验证”或“实验已启动”等措辞。
