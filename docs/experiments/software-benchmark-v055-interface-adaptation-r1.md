# v055 DeepSeek 六条件接口适配与必要控制

本文记录接口实现和准入准备，不报告模型的 SWE-bench 成绩。三种接口各增加思考与非思考条件，使用官方 `deepseek-flash`，与仍在运行的 v054 本地模型队列分别保存。本文涉及的新代码均为 v055 文件；不修改 v054 已冻结文件。

## 实际调用与工具边界

REF、MATCH 继续使用固定 OpenHands SDK 1.49.6 的原生 Agent、默认系统说明、Terminal/FileEditor/TaskTracker、Think/Finish，以及原有 condenser。正式控制器通过 v054 `NativeToolRPC` 调用隔离 Actor 中的原生工具，模型提供者改为可信控制器内的官方直连客户端。Agent 与 condenser 共用同一逐题账本和请求上限；condenser 不获得工具。

PROJECT 使用真实 S1 World、受管工具、唯一稳定成员与真实 SDK worker。保留文件读取/分页/修改、新增/删除/重命名、公开测试、固定和正式提交等能力；没有增加不受管 bash、浏览器或网络搜索入口。原始问题、初始仓库和最终候选锁定、官方评分由独立宿主运行器负责。当前实现不是把 PROJECT 换成原生 Agent。

DeepSeek 只接收现有本地 `function` schema。模型响应中的工具只由本地执行器处理，没有服务器搜索工具、MCP 或插件。真实 Actor 网络隔离与公共/隐藏材料隔离由 v055 宿主运行器沿用原边界；API 凭据只在可信控制器读取。模型 API 直接连接官方主机，不走本地 LLM 服务或反向代理，也不依赖环境 proxy 配置。

## 模型推理与历史

思考模式显式发送 `thinking.type=enabled` 和 `reasoning_effort=high`，省略该模式不支持的 temperature。非思考显式 disabled，REF temperature=0.6、MATCH/PROJECT=0.7；不发送无效的 top_p/top_k、seed、parallel_tool_calls 等字段。这里不声称 DeepSeek 与原 Qwen 的采样分布相同。预定 seed 仅保留为实验身份，API 不支持该 seed，不能称为可复现的提供者随机种子。

原生 SDK 可能省略 reasoning_content，或规范化 function.arguments 的空白。适配器保存真正收到的 assistant 消息；根据原始 tool-call IDs 和解析后的参数核对，再恢复原消息的 reasoning_content。缺少原始思考内容或动作参数发生变化时停止，不合成思考文本。PROJECT 继续保留原 SDK 的 assistant 原件机制，并通过同一适配器再次核对。每题、每条件拥有不同且在题内稳定的 user_id，用于避免跨条件共享会话/KVCache 身份。

## 上下文与计量边界

目标资源限制继续区分 REF 输入 98,304 / 输出 32,768，MATCH/PROJECT 输入 16,384 / 输出 2,048。输出上限包含思考 token。逐题总输入+输出上限 500,000，全部模型请求 128，Agent 决定 128；condenser 也消耗同一题请求/token 预算。真实消耗来自官方响应 usage；reasoning_tokens 是 completion_tokens 的子集，不二次累加。

远程 API 不提供本地推理 token_trace，不能沿用旧代码中的“实际输入/输出 IDs”断言或伪造 token IDs。新接口支持显式可插拔计数器。正式候选使用官方 `deepseek-recipe==0.2.0`、V4.1 编码和 1017 tokenizer，保留本地编码计数，再加事先固定的 128 token 工程余量。该方法属于本地官方编码加工程余量，不冒称服务器签发的精确 count；响应 usage 仍是实际用量依据。真实 API 中性准入另行比较 actual prompt 与 local+128，未通过时不能冒称上下文完全匹配。

UTF-8 字节估算只保留为显式后备工程工具，正式控制器在没有已配置计数器时于模型调用前拒绝。不能将较大的 schema 字节数直接冒充实际 token 数，导致整批 PROJECT 初态无效拒绝。

PROJECT 复用 Γ1 的普通反馈生命周期、静态去重、同输入字段引用，以及只去除较早完整工具轮次的容量选择；最新反馈不任意截断。改变的是“已实际呈现”的证据类型：使用精确发送请求、响应及已结算 API usage，不声称获得本地 token IDs。团队账本明确标记 `reported_api_usage`，与旧 `reported_actual_trace` 区分。任何实际 usage 超过冻结预留时保留响应、费用和异常；不自动补一次请求。

人民币预算由共享 CNY SQLite 账本独立执行。旧 PROJECT 内部 USD 字段为兼容内部账本结构而保持零费率，不是免费运行声明，也不是预算授权依据。全局预算对每次请求按提供者最大输入和输出上限做保守预约，结算后按 cache hit/miss 与完整输出收敛。未能确认是否计费的请求保留预约；不会自动重试。

## 必要 CPU 与真实 SDK 控制

控制使用合成仓库，不读取正式题或参考补丁。六条件各两轮程序响应，共 12 次程序响应，真实模型/API 费用为 0、网络尝试 0、GPU 访问 0。

| 条件 | 原始控制位置 | 实际工具流程 | 官方本地编码两轮输入（加余量前） |
|---|---|---|---|
| REF 非思考 | interface-control-r1 | think → finish | 7,435 / 7,492 |
| REF 思考 | interface-control-r1 | think → finish | 7,458 / 7,520 |
| MATCH 非思考 | interface-control-r1 | think → finish | 7,435 / 7,492 |
| MATCH 思考 | interface-control-r1 | think → finish | 7,458 / 7,520 |
| PROJECT 非思考 | interface-control-r2 | read_file → staff_done | 5,976 / 8,021 |
| PROJECT 思考 | interface-control-r3 | read_file → staff_done | 6,002 / 8,052 |

各条件续接均保留原 reasoning_content，输入保留五个原生工具或 33 个真实受管工具，不加入搜索。每组程序 usage 为 2,060 token，仅为夹具值；不能计为真实模型 token。

保留的控制失败：r1 在四个原生条件完成后，PROJECT 构造因旧元数据检查要求 API key 变量名而失败，未发 PROJECT 请求。修复为声明变量标识后，r2 完成 PROJECT 非思考真实 SDK 两轮；脚本末尾误将 staff_done 算作业务动作而断言失败。原完整事件记录证明业务动作 1、机会 2、正常生命周期闭合、两笔 API usage 完整。对此仅做原件只读重物化，没有重复生成。r3 只执行尚未开始的 PROJECT 思考条件。组合核查保存于 `runs/software-benchmark-v055/interface-control-combined-r1.json`，保留旧失败回执并明确新证据来源。

另有三个纯 CPU 故障控制通过：原思考历史恢复与参数篡改拒绝；全局预算在派发前停止记为零次实际请求；网络结果不确定时保留一次请求及未结算预约。禁止未知工具的检查也覆盖 web_search 拒绝。Ruff 对新增接口、控制器和检查脚本通过。

## 真实 API 中性准入计划

`neutral-qualification-plan-r1.json` 预先固定六条件，各至多两次真实请求，总至多 12 次；费用属于用户原 2,000 元总预算。脚本不读取正式评测题。保留真实完整工具 schema，但在 SDK 执行前，只允许预定的 harmless fixture 动作到达实际执行器：原生 think→finish，PROJECT 仅读取 fixture.py→staff_done。任何偏离、截断、异常或计量超界都记为资格失败，不补抽成功样本。单条件目录原子创建，不能复用重跑；第三次请求在网络派发前阻断。

固定最大输出仍为正式组的 32,768 或 2,048；短提示不等于收窄模型输出上限。按最大提供者输入保守预约计算，全部 12 请求的累计最坏预约为 26.345472 元，实际费用以同一全局账本收敛。该数字不是预计必然消耗，也不增加预算。

## 真实准入执行结果（2026-10-22 00:00 CST）

六条件按同一冻结计划一次并发执行，全部通过，各恰好两次请求，总 12 次真实 API 请求；无重试、无替代条件、无正式题或 GPU 调用。实际 SDK 原生 think→finish 与 PROJECT read_file→staff_done 均完成，PROJECT 的 staff_done 属于生命周期结束，不计为第二个业务动作。所有子进程已经退出。

| 条件 | 实际输入 token | 实际输出 token（包含思考） | 响应报告思考 token | 两轮 server count − local count |
|---|---:|---:|---:|---|
| REF 非思考 | 15,102 | 118 | 不单列 | −14 / −14 |
| REF 思考 | 15,149 | 122 | 0 | −14 / −14 |
| MATCH 非思考 | 15,102 | 119 | 不单列 | −14 / −14 |
| MATCH 思考 | 15,150 | 126 | 4 | −14 / −14 |
| PROJECT 非思考 | 14,377 | 134 | 不单列 | +56 / +56 |
| PROJECT 思考 | 14,486 | 146 | 57 | +56 / +56 |

合计实际输入加输出 90,131 token。共享账本结算上界为 **0.05128168 元**，用户 2,000 元预算剩余 **1,999.94871832 元**；未结算预约、未知收费预约均为 0。该金额为当前保守账本值，不冒称已取得提供者正式账单。

所有实际输入均满足事先固定的 local+128 预留，原始 reasoning_content 在工具续接时保留；其中部分思考条件返回空思考串、报告 0 reasoning token，仍保留原始空串，不编造思考。这证明本次中性两轮接口通路和局部计量准入通过，不证明任意后续历史/工具 schema 的服务器计数必然与本地完全一致，也不构成 SWE-bench 能力结果。响应 model 均为 `deepseek-flash`，观察到的 system_fingerprint 为 `e72d3c7f663d3e1383b00b3884cb4501`；这是观察值，不是可由用户锁定的权重哈希。

完整汇总为 `runs/software-benchmark-v055/neutral-qualification-summary-r1.json`（SHA256 `b2f9b6cd63d5387be3de10f6c589b719fe4943d85192e260f58293791bd8b7ee`）；计划、启动前源码哈希、CA 哈希、命令、原始请求/响应和 SDK 事件分别保留。正式启动和运行性能以主实验报告为准。

全局预算派发前拒绝也另做了一个真实 PROJECT SDK 机会控制：决定消费 1、实际模型尝试 0、实际 token 0、保留预约 0，正常结束为 model_budget_exhausted，未误归执行完整性失败。准备夹具首版因缺少显式公开测试回调，在世界组装前被拒绝；修正夹具后只执行了一个上述 SDK 机会，没有付费请求。

## 后续异常退避与资格复用

用户随后要求中途异常不要阻塞流水线，异常集合留待最后处理。直连客户端据此将一般 API/网络故障的共享保护改为有界冷却，不自动重试已经派发的原请求；认证、余额和账本完整性等硬停止仍单独处理。

接口仅修订网络派发前的等待分支：收到 `ConcurrencyBusy` 时，即使全局在途数为 0，也根据 `admission_wait_seconds` 等待冷却。一次等待不超过 5 秒，且不越过本题软期限；等待只再次检查预约资格，不重新发送已经进入服务的请求。软期限到达仍未派发时，记录 `soft_deadline_during_provider_admission_wait`，实际请求/token 为 0，不把冷却误记为人民币预算耗尽。硬停止不等待；预算不足仅在其他在途结算可能释放预约时等待。

仅对上述新分支执行三个纯 CPU 控制，分别覆盖零在途冷却后首次派发、冷却达到软期限、硬停止立即结束，全部通过，Ruff 通过。新增真实 API 请求为 0。此前六组 12 请求的真实 SDK/API 成功路径及计价原件保持；正常请求路径未改变，因此复用已有资格，没有重复付费准入。这里不声称最终源码与首次准入源码逐字节相同：首次启动源码哈希、后续修订源码哈希及窄 CPU 证据分别保留。

小证据归档位于 `artifacts/software-benchmark-v055/interfaces-r1/`。原 `manifest.json` 及原 15 份回执不改写，新增 `admission-wait-control-r1.json` 通过 `manifest-supplement-cooldown-r1.json` 独立引用。

## 已知解释边界

1. 官方模型别名与响应 fingerprint 可记录，但无法像本地权重一样锁定文件哈希；API 不支持本方案的随机 seed。逐题配对仍成立，同 seed 不构成提供者随机轨迹相同的证据。
2. 官方本地编码加 128 token 余量只在已披露的中性请求中通过实际 usage 核对，不是任意任务历史的精确服务器计数证明。后续超界须保留为计量/执行异常，不能藏入普通模型错误。
3. 思考模式的输出上限包含思考 token，MATCH/PROJECT 的 2,048 上限可能显著限制可交付输出。六条件测的是已冻结接口与资源配置下的结果，不能将组间差值直接解释为纯接口效应或原始模型的无条件能力差异。
