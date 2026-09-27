# v0.19 独立 episode 双副本采集设计

日期：2026-09-27。本文记录独立世界双副本的实现边界。采集器和单次子进程已实现，真实 CPU 子进程＋WorldCore 控制已通过，模型返回为明确的人工 fixture。**本文不作为真实 GPU 加速比或学习数值准入的证据**；真实模型控制与部署状态以实验报告为准。

## 实施判断

同一窗口的独立工作世界可以在两组 GPU 上同时运行。每个世界仍只有一个写者，其内部角色、工具、外部时钟和决策预算继续串行。共享学习器只在全部预定槽闭合后执行原来的至多一次更新。这个方式可以利用模型层切分之外的设备；两副本对采集时间的理论收益上限是 2 倍，实际收益受任务长短、第二份权重加载、同步和资源竞争限制，不能承诺整轮快 2 倍。

不宜直接使用 `multiprocessing.Pool.map(collect_window, slot_chunks)`。当前 `harness_collection.collect_window` 为输入的整窗生成一个 `declaration`，其中 `gamma_identity.fixed_slot_cases` 与全部预定种子进入指纹。分片独立调用会产生不同 Γ，且各片重新从 `slot-0` 开始命名。当前 `CandidateActor` 构造还会建立 actor/critic optimizer；直接加载第二个 SharedActor 不是“只读副本”的实现。

建议分两个有界门槛：先完成双副本的真实零更新采集和概率核验，再完成一窗并行采集→唯一共享更新→刷新副本→新窗口真实交互。前者通过不能自动声称后者成立。不得用双 optimizer 的本地更新、最终平均参数或只复制 `policy_version` 文字代替共享学习器。

## 固定资源计划

| 模型 | 主进程采集兼唯一学习器 | 只读采集副本 | 条件 |
|---|---|---|---|
| 9B | 2 张卡 | 另 2 张卡 | 两进程均保持原逻辑 2 卡切分和相同数值 profile |
| 27B | 4 张卡 | 另 4 张卡 | 占用 8 卡；四项目进程不能同时占据第二组 |

物理 GPU UUID、空闲量、利用率与并行其他项目进程写入资源证据；不会改动或终止其他项目。每副本减少切分卡数、改变 dtype、算子或 context budget 都是独立数值配置变更，需要另外验证，不能隐含在“并行”中。9B 也不把“有 8 卡”解释为自动开 4 个副本，首版只支持最多 2 个，限制故障面和数据归并复杂度。

固定分配在采集前根据全窗原始 slot 顺序产生，不看 reward 或耗时动态调度。两个 rank 内各自仍按原顺序执行分到的槽。分配公式可用 `rank = (global_slot_index + 1 - slot_count) % 2`，使全窗最后一个槽总在 rank 0 的主进程。这样在每槽重新设定原种子的前提下，主进程的最终采样 RNG 来自逻辑上最后的槽，避免仅因分片令保存的训练 RNG 取决于哪个副本先结束。所有 CPU/GPU 操作是否实际保持这一性质须通过测试，不只依赖公式。

资源不满足时只等待预声明的两组，不在已有一部分样本后自动改为串行、改 GPU 切分、增加副本或另找一个种子补样。若在正式采集前决定采用串行，应冻结不同执行协议并记录尚未开始采样的阶段边界。

## 最小实现边界

实现提取现有单槽操作并增加并行 collector，不改变单世界内核：

1. `prepare_slot(owner, window_spec, row, global_index, output)`：沿用原模板构建、WorkInterface、native/SDK runtime 和公开场景；准备的 world/runtime 留在实际负责该槽的进程，不 pickle 运行中的世界或 SDK Conversation。
2. `declare_prepared_window(...)`：主进程接收所有槽的准备说明，按原索引组成一次完整 `declare_window`，写出唯一声明并作为启动屏障。每个说明保留初始业务状态、成员、实际 policy config 和 slot 绑定。所有进程核对声明的 actor、Γ、slot 和本地准备结果后才可调用模型。
3. `run_prepared_slot(owner, prepared, declaration)`：复用原 `begin_episode → run_fragment → finish_episode → export_online_rollout`；保留真实 model-call 和独立 capture，不把摘要当作原始记录。
4. 主进程先启动第二副本的固定任务，再串行执行自己的任务，最后等待、读取结果。主进程不会同一时间用两个线程调用自己的 model。GPU 子进程使用新的 Python 解释器/`spawn`，不对已初始化 CUDA 的主进程使用 `fork`。
5. `merge_slot_results` 仅按完整声明排序结果，拒绝重复、额外、错误 actor/Γ/slot；缺失的原槽成为明确 unknown entry。`diagnose_window` 仍在完整声明上执行一次。`run_online_windows` 现有 slot 顺序检查与分母规则保持生效。

主进程与副本可通过项目目录中的原子 JSON 和小型 tensor 文件交换控制消息，不必新增 HTTP 模型服务或调度平台。模型调用仍在各自 resident 进程内真实执行，原 `transport_kind=resident_direct` 可以保留；控制 IPC、进程 ID、物理设备和副本 rank 分别记录。元数据中新增明确的 `collection_execution` 版本与固定分配表，使新的 Γ 区分于串行采集。

现有目录继续使用主采集根下的 `slot-{global_index}`。每槽只能由所属 rank 写入；全窗 `declaration/progress/support/summary` 只能由主进程写入。只读副本自己的 `resident/calls`、种子、同步和退出记录在独立 rank 目录；合并器保留并引用原字节，不能搬动后重写 rollout 的路径或哈希。副本应输出原生 entry JSON 及不可变内容引用，由主进程加载为既有 `prepare_window` 所需结构。

## 只有一个学习器

首版需要真正的 `SamplingReplica`：可以共享 CandidateActor 的原生提示、解析、采样和 token 记录代码，但构造不得建立 critic、optimizer，接口不得提供 `update_window` 或全学习器 checkpoint restore。

每窗 barrier 前，唯一学习器导出只包含以下内容的只读 actor 快照：

- 全部实际 LoRA tensor 名称、shape、dtype 和值，不能只有哈希。
- `policy_revision`、严格 actor identity、base manifest、完整有效 inference profile 与源代码绑定。
- snapshot 文件字节哈希和 tensor 内容哈希。

第二副本只在 idle 边界复制 adapter 值；自己的 tensor digest、完整 actor identity 与主进程完全相同后返回 readiness。基座 manifest、逻辑 device map、依赖版本、停止规则、原生解析、temperature、采样变换和任何启用的缓存/快速内核配置也必须相同。物理 GPU 不同单独记录，不篡改 inference profile 来伪装相同。

进入窗口后所有副本只读。所有预定槽结束、未完成请求清空、副本封闭本窗并报告实际 adapter digest 后，主进程才调用一次原 `update_window`。主进程进行全部概率复算、actor/critic backward 和 optimizer step；第二副本此时禁止采样。更新后，下一窗加载新快照并完成同样的 identity barrier，旧窗口 transport 不能复用。

首版每窗口启动一次子进程，在 barrier 前加载只读快照；子进程结束后主进程才可更新。每次冷加载耗时单独记录。后续可以考虑常驻，但本轮不实现复杂的跨窗 IPC。采样 token/cache state 不跨 policy 更新。adapter 同步失败停止整个新窗口，不用陈旧副本先采再补身份。副本生命周期也不能调用现有 `SharedActor.restore_checkpoint`，因为它会恢复 optimizer、critic 与 RNG，且会把“副本状态”变成第二套学习器。

## 原种子、评价 guard 与 own-token 学习目标

每个槽沿用原 `sampling_seed`，开始真实工作前在所属进程调用相同 reseed。槽内成员、工具回合、采样顺序保持原定义。每副本同一时刻只执行一槽，避免一个进程内共享 Torch 全局 RNG 被两个 episode 交错消耗。主 rank 执行全窗最后的槽，窗口后仍按原逻辑保存/恢复它的 RNG；不合并两个独立随机流，不拿最快完成槽的 RNG 当作全局状态。

评价窗口仍调用主学习器的 `capture_evaluation_state` 与 `finish_evaluation_guard`，检查 actor、critic、两 optimizer、步数及历史标志不变，恢复主进程 CPU/所有可见 CUDA RNG。guard 的原语义是**学习器** RNG 与学习状态，不应扩大声称“整个多进程世界所有随机源均已恢复”。副本没有学习状态；其 RNG 只服务带固定 seed 的本次 episode，下槽会重新 reseed。副本也须给出窗口前后 actor tensor 不变、无 optimizer 构造与无更新入口的运行证据。仅主 guard 通过不能证明副本无改权重，必须分别查验。

SDK 和 native 的 policy identity 都应在 `prepare_slot` 时绑定真实快照；响应中的 `actor_identity/system_fingerprint/online_window_id` 继续由实际采样 owner 生成。原始输入 IDs、输出 IDs、实际 logits 得到的 behavior logprobs、EOS 检查和原始响应继续完整保存。不能将其他槽 token、重新分词文本或主进程重算出的 logprob 写成副本的 behavior evidence。

主学习器沿用 `prepare_window` 的逐决策身份/窗口检查与固定分母。它对来自两个 rank 的真实 own-token target 按原槽顺序执行 `learning_logprobs`，继续使用原概率容差；副本间数值不一致必须真实触发 mismatch。跨 GPU 的相同 seed/profile 不足以证明逐 token 绝对相同，控制实验应报告实际差异及是否通过原门，而不是预先承诺完全相等。优化不增加 learner forward，正式训练仍执行原来的必要概率门。

## 故障与未知槽

每个固定 slot 只有一次 launch intent。已知格式失败按既有评价合同记录，不能借并行重新生成；有记录但无法评价、服务错误、进程丢失、缺失 token 或 actor 不一致保留各自原证据和 unknown 原因。主进程不得省略这些槽、用 0 替换、调低分母、补采或将其他槽结果搬过来。

若副本异常退出，已完整闭合且证据核验通过的槽保留；该副本未完成和尚未开始的槽逐个标记实际状态，仍纳入原槽总数。另一个进程可以完成自己原已分配槽，但不能接管丢失槽。对“完整当前 actor 证据不足”如何停止后继阶段沿用现有准入门；并行 collector 不自行新设奖励门。

第二副本 GPU OOM、资源竞争和独立世界故障分别记录。不得因一组卡拥塞换组重跑同一 slot。启动前失败与采样后失败应分开，保留未开始次数；正式协议是否允许一次资源等待由启动计划明确，不解释为样本重试。

## 最小必要核验与工作量边界

这是比前缀缓存更大的采集器改造，不是将一个循环改成线程池。预计改动面为：槽准备/运行拆分、只读 actor snapshot/replica、2 进程 collector、协议/启动器接入、归并与故障控制及文档。独立准备全部世界和合并仍为 CPU 工作，初版无须并发单世界写者、RPC 模型队列或分布式 optimizer。

必要核验只覆盖新增失效面：

1. CPU 控制：两 worker 完成顺序颠倒仍输出原槽顺序；一槽格式失败、一个 worker 死亡、一个错 actor/Γ、一个重复结果不造成删槽或补样；任何模型采样不能早于唯一 declaration barrier。
2. RNG 控制：相同原 seed 的槽不受其他进程的完成顺序影响；评价 guard 确实恢复主学习器；固定最后槽分配的保存状态如实记录。只读 replica 无 optimizer，无调用更新的通道。
3. 小型真实 GPU 控制：预声明少量固定请求/episode，在两组同规格设备上取得真实 IDs 和 behavior logprobs；主学习器重算两个 rank 的全部目标，沿用原数值容差。报告加载时间、采集时间、实际峰值显存和资源竞争；控制不加入正式业务成绩。
4. 共享更新控制：一个小窗来自两个 rank 的 target 共同参与唯一 optimizer 更新；随后两个 rank 都加载同一个新 identity，重新与世界交互；旧 transport 被拒绝。没有非零学习信号时如实记录未更新，不为通过控制改奖励或重采。

真实 GPU 门槛未完成前，CPU 控制不能视为模型训练准入。实际部署若发生在未启动的 pilot 前，须按阶段边界冻结新 source、Γ、collector/runtime/资源配置，初始和最终评价使用相同配置。正在运行或已闭合的 H1 不切换、不重演补成绩；已开始窗口不能中途转换并行。


## 更窄替代：仅初始与最终评价分片

另一可行方案是训练 64 例完全沿用单 owner，只有初始/最终各 27 例用两份 resident 评价子协议。两端固定相同的 case/seed 分片，各子 run 保存独立声明与实际评价 guard，不把它们的轨迹用于 actor/critic 更新。它可不实现跨窗只读 replica 常驻和训练轨迹归并，但仍不能通过拼接 JSON 冒充原单 resident 评价。

具体要求是：父 run 在空闲边界持有实际检查点；初始端绑定初始检查点，最终端绑定固定训练结束检查点。子 run 恢复同一精确 actor/base/profile，并以纯 evaluate 模式运行。若复用现有 SharedActor，子 run 会构造且恢复 dormant optimizer，应如实标注，并用自己的实际 guard 证明 optimizer 与 critic 未变化、step 增量为零；不能写成“没有构造第二个 optimizer”。父 run 的 guard 只覆盖父学习器，报告需另外明确核验每个子 run 的 identity、纯评价、源代码不变、完整 guard 和原槽一一映射。

子声明可以保留各片真实 Γ；父报告保存全局槽到子 run/局部槽的精确内容引用，两端执行相同分片协议。不能将子声明改写为全窗声明，也不能复制一个子 run 的 `learning_unchanged=true` 作为所有进程的结论。子准入须校验完整父协议、预定 checkpoint、固定分片和全窗口 mode=evaluate，不用一个未注册 stage 绕过现有 H2 准入。失败槽仍保留，另一子 run 不接管、不补样。

代码走读发现当前 H2 准入严格重建整个协议，学习报告器通过 `collection/slot-{index}` 找证据，后续支持密度准入要求原主 run 的六窗完整记录。因此窄方案仍需至少覆盖子协议/准入、父 collector 或运行包装、真实证据归并、报告器/启动器四个连接点，不能只替换启动命令。评价轨迹不参加训练是它比全窗并行简单的主要原因。

在“每例成本相同、两组并行无额外开销”的理想估算中，54 个评价槽可节省 27 个槽的串行时间；整个 118 例 pilot 相当于 91 个串行槽，采集加速上限约 1.30 倍、时间减少约 22.9%。实际任务时长不同，基座加载、训练反向与共享 GPU 竞争会进一步改变收益，不能作为实测承诺。它不是整个 pilot 快两倍的方案。

该纯评价替代方案仅完成可行性评估，没有新增执行分支。本轮按用户明确要求继续实现前述全窗口双副本，并保持唯一学习器；这使训练采集的 64 例也可并行，而不是只优化 54 个评价槽。


## 当前实现及证据位置

- `src/proworksim/harness_collection.py` 提取 `prepare_slot`、`run_prepared_slot`、`collection_declaration`、`finish_collection`，原串行入口仍调用相同生命周期。
- `src/proworksim/harness_parallel_v019.py` 实现固定两组 GPU、全声明 barrier、全局槽归并和子进程结束门；`scripts/sampling_replica_v019.py` 在新解释器中加载只读 owner 并执行自己原分配槽。
- 每个世界仍写在完整采集根的 `slot-{global_index}`；所属进程写 `parallel-result.json`，仅引用该槽真实 `team-rollout.json` 和 `mapping.json` 字节。父进程逐条使用原 `bind_rollout` 核对声明、actor、成员、映射及奖励。
- `collection/parallel/report.json` 与 `summary.json.parallel_execution` 保存真实父/子身份及 source guard、零更新证据、子进程退出状态、固定分配、snapshot/准备/采集实际耗时、子原调用文件引用与资源字段。只读子模型冷加载耗时单列。
- 子进程缺失 final guard 或异常退出时，父进程先保留全部固定槽，包括已完成真结果和缺失槽 unknown，再抛出错误阻止更新；不重启、不接管、不换 seed。barrier 前加载或身份失败时没有任何模型采样，并单独留下全预定槽和阶段错误。
- `tests/test_harness_parallel_v019.py` 使用真实子进程及真实 WorldCore、明确人工模型返回，验证完整 Γ、原 seed/slot 顺序、原 own-token 与固定学习分母、错误 slot 绑定、子崩溃及 wrong-actor-before-barrier；CPU fixture 不建立 CUDA context，也不证明 GPU 数值相同。
