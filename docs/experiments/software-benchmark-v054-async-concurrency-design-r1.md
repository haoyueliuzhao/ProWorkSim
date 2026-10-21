# v054 异步与并发：同卡独立回合交错设计 r1

**状态：设计，未上线、未准入。** 本文整理 MATCH/PROJECT 与 REF 的只读分析，不改变当前 r8 的运行源码、服务、预算或在途任务。没有为本次文档新增模型请求、GPU 探针、CPU 控制、正式 claim 或官方评分。

当前已上线的是跨卡动态 pool、CPU 环境预准备和最多两个官方评分 worker。符合原显存门的 GPU 0–7 可以进入 pool，全局最多八个正式 episode；这不表示当前已有八张卡满足门槛或全部参与运行。**一个 resident 当前仍只接收一个 episode。** 本文提出的“同一 resident 上两个独立 episode 交错”尚未实现，不能描述为现有能力。

当前部署分别见 [动态常驻监控器](software-benchmark-v054-dynamic-provisioner-r1.md) 和 [CPU 环境预准备](software-benchmark-v054-cpu-prewarm-r1.md)。环境预准备是提前建立公开仓库运行模板，既不运行正式题目，也不代替 Agent 的公开测试反馈。

## 1. 可以并发什么，不能提前返回什么

候选方案是在一份常驻模型权重上保留最多两个完全独立的 episode，GPU 每次仍只执行一个完整生成请求。A 的 CPU 工具或公开测试等待时，B 可以生成；A 自己的 `run_tests` 仍需等待真实结果后才向同一 Agent 返回。每题仍只有一个 Agent，独立工作树、history、seed、预算、公开测试、交付与评分身份，不能交换两题的消息、补丁或反馈。

这与给同一 Agent 增加后台公测工具不同。本文不改变工具 schema、反馈时点、测试 argv、结束语义或项目受管权限；不提前返回“已开始”代替测试结果，也不省略结果反馈。不同 episode 的 CPU 公测可以重叠，各自仍受原 4 CPU/16 GiB/16,384 PID 及测试超时约束。

官方隐藏评分已经在候选锁定、生成结束后异步运行，最多两个 grader。它不参与 Agent 求解反馈，与上述必须等待的公开测试是不同阶段；不能把现有评分异步误报成 Agent 公测已经异步化。

同卡交错只能利用已有生成间隙，不能增加该卡串行生成的算力。它需要新的会话、调度、账单与闭合协议；不是把并发数改为 2 就完成，也不能保证吞吐倍增。

## 2. 原始证据和观察范围

两份原始设计及引用清单保留在：

- MATCH/PROJECT：`/tmp/proworksim-v054-shared-owner-design-r1/design.md`，SHA256 `d33238ef2f11530768fc453cc78f175cecf1445d8eed6e07a994b1f661443572`；同目录 `manifest.json` 记录实际读取的 11 个源码文件身份。
- REF：`/tmp/v054-ref-interleaving-design-r1/design.md`，SHA256 `d8c0c0ca8cba7c3c350ab6a2bdc1ba9860df508beddb9f442e0e9b482b192ddf`；同目录 `manifest.json` 记录设计及只读时序文件身份。
- REF 时序原件：`/tmp/v054-ref-interleaving-design-r1/readonly-timing.json`，SHA256 `e0948d69111f0f45d7b78d82d5ee414cdfd627c0b9bb716a9ce955f590131da5`。这是本机只读分析资产，不是新增实验或模型回执。

REF 时序原件记录 13 个已闭合 episode、302 对 request/response 文件时间戳。来源包括 `runs/software-benchmark-v054/formal-queue-r1/slots/3/preclaim-1/episode`、`slots/5/preclaim-2/episode`、后续原队列槽以及 `slots/1415/preclaim-1/episode`；完整逐题路径在原件的 `records[].episode`。该样本包含不同先前运行 revision，不是单一新配置的受控比较。

| 已观察量 | 数值 | 能表示什么 |
|---|---:|---|
| 成对请求响应窗口之和 | 1,623.43 秒 | 包含 HTTP、准备、生成、序列化和持久化，不能直接称为纯 GPU 时间 |
| 请求窗口之间的间隔之和 | 161.24 秒 | 包含工具、SDK 和精确计数，不能直接称为可全部重叠的 CPU 时间 |
| 每题首请求至末响应窗口之和 | 1,784.68 秒 | 未覆盖全部 episode 首尾准备和清理 |
| 间隔占上述窗口比例 | 约 9.03% | 仅这 13 题、这段窗口的文件时间戳观察 |
| 各题间隔比例范围 | 约 1.61%–15.67% | 有任务差异，不能把均值视为全部 REF 的固定特性 |
| 最大单个请求间隔 | 4.35 秒 | 本样本未出现 PROJECT 长公测那种数百秒的请求外间隔 |

若额外假设请求窗口耗时不变、这些间隔全部可被填满、交接清理成本为零，以上局部窗口的算术比例约为 1.10×。**这不是已实现收益，不是整个 REF 的吞吐上界，也不支持 2× 承诺。** 文件时间戳不是 GPU kernel profiler；任务组成、先前 revision、首尾成本及清理开销均限制外推。

这 13 份 ledger 均已知完整、无 inflight，结束原因是 `full_input_and_output_reservation_insufficient`。每题末尾多出的一个无 response 的 request 文件，来自“先写 request evidence、再做 reserve”的原实现；文件本身不证明发生过 GPU dispatch。因此不能把这些尾文件算成 13 次失败生成。时序只统计实际成对文件，保留上述说明。

## 3. 所有组共同需要的新边界

常驻进程继续独占物理 UUID lease，权重不在回合间卸载。最多两个会话名额分别绑定 claim、原 slot/seed、宿主 PID/start_ticks、随机 session token/nonce、请求序号与独立费用引用；每会话最多一个等待或执行中的生成请求。

GPU 请求使用受信 FIFO 轮值，不按任务得分、预估成功率或补丁表现选择。一次原始生成完整结束才轮转，不做 token 中途抢占、不把两题合成 batch、不改原模型/采样/上下文/输出上限。CPU 公测期间不持有 GPU 轮值。

正常结束 A 必须只证明 A 自己的请求、账本、工具 writer 和候选生命周期已闭合，不再要求整个 resident 空闲。若 B 正在生成，A 的正常 release 不能 pause、abort 或 SIGSTOP B。新回执必须使用会话级语义，例如 `session_quiescent=true`、`own_inflight=0`，另记其他会话是否活动，不能让旧的“全 resident quiescent”字段误导候选锁。

旧 `ResidentSession` 的整题 flock、queue 的每 resident 忙闲位、owner/Gate 的单 active、sentinel 的全服务 poison 都需要共同版本化。只放宽其中一个门，会留下错误结束证明或使 A 的 watchdog 停掉 B。

## 4. MATCH/PROJECT：共享权重，隔离原始 owner 状态

现有 `CalibrationActor` 的 `phase/window_id/busy/output/used_window_ids` 属于单个 actor，Torch CPU/CUDA RNG 却属于进程。`generate_native` 会执行 `model.eval()`、清除共享 `model._cache` 并写调用记录；原 `finish_evaluation_guard` 直接恢复整个进程的 Torch RNG。因此两个线程同时调用当前 owner 不可行。

MATCH 还明确要求真实 `CalibrationActor` 类型，以及 `generate_native.__func__` 就是原始方法。不能用普通代理伪装 owner，也不能替换该 generator 方法加锁。最小候选实现是两个真实 actor facade 共享已有 model、tokenizer、torch 和 head_execution，由外部唯一计算线程执行各自原 `FormalOwnerService.dispatch`。

每个 facade 的窗口、输出路径、identity/recipe/inference profile 字典、snapshot、RPC 序号、MatchBridge 和 ledger 独立。SDK、Γ1、world、history、工作区和 CPU scope 继续在每题自己的运行器中；condenser 仍与自己那一题的 Agent 共用原账本。不能浅复制整个 owner `__dict__`，否则会共享可变列表和状态。

创建 facade 不调用 `load_actor`、`from_pretrained` 或 `model.to`，不复制权重、不再次安装 head hooks。原 `HeadExecution` 的计数器/类型集合是共享诊断，若需要逐请求计数则在唯一计算线程内记录差值。r3/r5 allocator 资格与显存预约仍只有一份；原 `native_cache_context` 每次完整进入/退出，不能同时进入两个 context。

构造器还存在身份派生细节：直接传 `old.freeze_identity()` 会把已有 `policy_version` 再纳入 hash。应精确使用原 raw loader 的七个 policy 字段：base_manifest、base_revision、model_path、raw_release、trained_adapter_loaded、checkpoint、adapter_sha256；其中 raw=true、trained_adapter=false、checkpoint/adapter=null。构造后完整 `freeze_identity()`、contract、inference profile、布局必须与原 owner 同值，否则拒绝。

### RNG 的最小组合

记常驻空闲 RNG 为 P，两会话连续随机流为 RA、RB。只有唯一计算线程可以读写它们。

1. begin A 时先确认进程 RNG 为 P，再运行原 begin/capture/reseed，保存得到的 RA，随后恢复 P。B 用自己的 seed 产生 RB。两个 facade 可同时 collecting，但不能同时 generating。
2. 执行 A 请求前安装 RA；执行原 service/resource context 和原 generator，完整记录返回/usage 后保存新的 RA。确认本请求 KV 清理并在边界同步本进程 CUDA，再恢复 P，才允许 B 进入。不能每次重新 `manual_seed(seed)`，那会重置同题连续采样流。
3. finish A 时安装最终 RA，调用原 `finish_evaluation` 和 `finish_evaluation_guard(snapshot_A)`。原 guard 恢复 P；记录 A 的 collection/restored RNG hash，确认 RB 副本未变，只关闭 A。B 的窗口仍可继续。
4. 异常时保存实际 dispatch/epoch/费用状态。恢复 P 不等于证明 CUDA 错误后的共享模型可信；共享状态不明时必须 poison resident，不能继续 B 或自动重采。

第一版可把完整 `child.dispatch`，包括 count/prepare/codec，放在同一计算线程，减少 tokenizer 和 resource wrapper 的并发面。这样仍保留部分短 CPU 尾部空隙，但不在首次修订同时增加另一个优化变量。

原 guard 的证明范围是 actor 身份、冻结布局、无梯度/优化器/更新、适配器状态及 Torch RNG，不是对全部 9B 权重或全部共享 buffer 重新逐字节 hash。RNG 作用域为 Torch CPU 和当前唯一可见 CUDA device；不能因此先承诺所有 HF/算子都严格确定或全部任务输出逐 token 不变。

## 5. REF：独立会话表与引擎轮值

REF 仍保持固定原 vLLM 0.32.0、一个原始模型 resident、`--max-num-seqs 1`、prefix cache 禁用、131,072 总上下文、98,304 输入、32,768 输出和原采样/逐题 seed。不把第二个请求送入 vLLM 内部排队，更不启用同时解码或抢占；外部轮值确保每次交接时引擎能真正为空。

当前 `RefSessionGate` 只有一个 active/global HTTP inflight，acquire/release 使用整引擎 `pause_generation(mode=wait, clear_cache=True)` 和 `reset_prefix_cache`；poison 的 mode=abort 会影响整个 scheduler。这些全局操作不能原样放到双会话的任意一个 release 中。

并行只读审查已安装源码得到：`AsyncLLM.abort` 支持 request_id；pause 的 wait/abort 作用于整个 scheduler；gpu_model_runner 对显式 seed 的新请求建立独立 Torch generator。完成请求的缓存释放仍可能包含异步步骤，不能仅凭完整 HTTP 回复就宣称交接状态已清理。

建议新增容量为 2 的 episode 会话表和一把 GPU 请求轮值。每题独立准备完整输入、精确计数；轮到自己后重新核验 claim、存活、seed、预算及时间门，再执行原完整 prompt+32,768 预约并转发一次非流式请求。受信侧绑定唯一 request ID，保留官方添加 `chatcmpl-` 后的完整身份，防止跨题混用响应或取消目标。

仍持有轮值、且没有其他请求进入引擎时，取得完整 usage，再执行 pause/wait+clear_cache、unfinished=0、reset_prefix_cache；保存 cleanup receipt 后才让另一题生成。首版每请求都清理，比仅在 claim 切换时清理更直接。独立源码审查发现官方 pause 内部包含约 20 ms 等待，但真实完整清理成本尚未测量，不能把它当作固定总开销。

正常响应应等 usage 与 cleanup 都明确后才交还对应客户端，避免它已继续工具执行后才发现上次清理未知。“无跨题 KV”指无可参与下一请求计算的前题 KV/SSM/prefix 状态，不声称物理显存字节全部抹零。prefix caching=false 本身也不能替代完整清理证据。

A 正常 release 只封禁 A 的 token、取消它尚未派发的 ticket，并确认其账本与最后一次 cleanup 完整；此时即使 B 正在生成，也不调用 pause/reset/abort/SIGSTOP。只有全部会话退出、请求队列空或共享服务发生故障时才执行整个 resident 的最终 drain。

## 6. 排队计时、费用和故障范围

**排队仍计入时间，不能暂停、重置或延长原时钟。** 原每题 500,000 token、128 次总模型尝试/128 次决策、5,400 秒软门/6,000 秒硬门保持；CPU 工具、公测、tokenize、轮值等待和清理都计入 episode 墙钟。每题只允许一个实际 Agent；另一题不能代为推理、测试或交付。

当前 MATCH/PROJECT 宿主请求门为 660 秒，原生成上限 600 秒；REF 宿主门 1,860 秒、HTTP 原超时 1,800 秒。在原 guard 内等待轮值可能耗尽请求或 episode 剩余时间。这是执行机会的变化，必须记录 queued_seconds、generation_seconds、tool/test_seconds、cleanup_seconds，不能声称保持同 seed 就等于原串行 episode 的完整执行条件。

现有计费器在实际网络/owner 调用前 reserve。不能把额外排队直接藏进已预约的 HTTP/RPC，随后将“尚未生成的排队超时”与“已生成但回包丢失”混为一类。需要显式 ticket admission：轮值等待有界且仍在原受信时间门内，实际转发时才进入生成预约；所有已发生的模型尝试/决策按真实状态记录。新增“未派发调度期限”必须有 server 侧唯一请求身份和未 dispatch 的证据，不能冒充现有正常边界白名单、不能用自动重试补救。

本文不采用将 660/1,860 秒在拿到轮值后重新起算的方案。若将来另行讨论这种语义，也必须单独冻结并说明条件变化，不能作为当前设计的隐含实现。保留原时钟会使后一题可用推理机会减少的风险仍存在，这也是本方案尚不能标记 formal-ready 的原因。

| 故障或结束情况 | 最小处理原则 |
|---|---|
| A 在 CPU 公测期间自己的宿主失败，且已证无 A 的数值调用在途或排队 | 停止 A 的 writer、关闭 A 的会话并保留技术状态；正常生成的 B 不因 A 的常规清理被无条件停止 |
| A 的 ticket 尚未派发，取消有明确证明 | 原样保留零新增生成的取消回执，不迟到执行、不自动重排 |
| A 已派发但 usage/输出/取消或清理未知 | 未知费用保持未知；停止新的 GPU 轮值，必要时 poison 共享 resident，不能把损失填成普通模型错误 |
| 原支持的正常预算/context 边界且账本完整 | 只闭合该会话，不误升级为整服务故障 |
| 引擎或 GPU/共享状态损坏 | 共享故障，双会话不提供物理隔离；受影响已进入槽分别保留状态，不自动重采 |

REF 的精确 request_id abort 只能针对被记录的当前请求，不能使用无范围 abort 代替取消；即使 abort 返回也不自动证明 usage 与清理完整。MP 原生 generation 无安全 token 中途切换设计，不能通过杀一个 Python 线程假定模型已恢复可信状态。旧 sentinel 的全服务 poison/SIGSTOP 调用点必须同时修订，否则新 Gate 或 facade 本身隔离并不足够。

全局正式 episode 上限仍为八个。同一 resident 的第二个会话占用第二个全局名额，不因 GPU 数不增加就额外突破上限。两个会话各自带来 CPU、内存和工作树成本；宿主资源、临时 rootfs 清理、最多两个 grader 和一个预准备 worker 的预算需纳入部署准入。

## 7. 最小后续验证与上线边界

本文没有执行下列拟议控制，也不构成自动启动许可。只有进入后续独立修订时才做覆盖新增行为的必要验证，不重复现有完整容量、旧三组 CPU 链路或正式题。

MP 可先用一次 CPU 合成组合控制覆盖 FIFO、单生成在途、私有 ledger/window/output/RNG、A 等待公测时 B 可运行、A finish 不改变 B、stale socket、queued cancellation、未知已执行调用导致 shared poison。时间门用可控时钟，不做长时间 sleep。随后如单独获准，可用最多六个短合成请求比较隔离基线 `A1,A2` 与 `B1` 和交错 `A1,B1,A2`；A=MATCH、B=PROJECT，A2 可覆盖 condenser 共账本。原输入/模板/seed/2,048 输出上限保持，全部准备成本单列。

REF 可用一组假引擎 CPU 状态控制覆盖两个独立 token、FIFO、等待期限、A 正常关闭时 B 不被暂停、精确取消、cleanup 与费用隔离，再用独立准备许可下少量真实交错请求核对同 PID、不同 seed、独立 ledger、每轮清理、无重载。原 max_num_seqs、上下文和输出参数不变，不重复完整 98,304 输入容量控制；先前“串行两个会话”的回执不能直接充当“同时存在两个会话”的准入。

MP 实际控制需保留完整 input IDs、各会话 RNG before/after、output IDs、chosen-token trace、usage、调用顺序、原 guard 与关闭证据；若结果不同，不自动归咎 RNG、不重采到一致、不临时放宽容差。有限控制通过也不认证全部 500 题轨迹等同。REF 实际控制还需证明请求身份、usage 和空引擎清理的对应关系，不能只看 HTTP 200。

实现至少涉及新 owner/Gate、会话容量、queue 路由、ticket 与计费/时钟接缝、release proof、sentinel/watchdog 和冻结身份；不同时改公测 API、评分器、训练或模型数值路径。当前 r8 在途服务不能靠修改磁盘源码热升级。若以后实施，需在相关回合闭合后由独立新 source seal/服务身份交接，旧回合不重跑，结果按 revision 分层报告。

本次只新增本文档。已上线的跨卡 pool 和预准备按其原协议继续运行；同卡双 episode 交错仍是待验证设计。
