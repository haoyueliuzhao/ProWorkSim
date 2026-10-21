# v054 MATCH/PROJECT 双会话 owner 实现 r1

本修订新增独立 `software_benchmark_interleaved_owner_v054`，没有修改原 `CalibrationActor.generate_native`、采样、上下文、输出上限、MatchBridge、FormalOwnerService 或 r3/r5 资源代码。实现阶段的代码与控制均留在 `/tmp/v054-interleave-mp-r1`，由主代理统一集成和冻结；本文不表示新服务已上线或已通过真实 GPU 交错资格。

## 模型与会话

一个 resident 只加载一次原始模型。启动时建立两个真实 CalibrationActor facade，model/tokenizer/torch/既有 head_execution 共享，窗口、输出路径、身份字典和 guard 独立。构造只使用原 loader 的七个 raw policy 字段，随后要求完整身份和 inference profile 与原 owner 相同；不再次加载权重、装 hooks、启用 adapter 或更换 generator。

`session_protocol=mp-interleave-v1`、`maximum_sessions=2` 同时出现在 resident/session identity。每个会话有自己的 socket、RPC sequence、claim、原 slot/seed、FormalOwnerService、MatchBridge/ledger、condenser 账本和 Torch RNG 副本。原工作树和 Agent 生命周期仍由各自运行器管理。全局 formal episode 上限由队列原授权约束，这个 owner 不自行增加正式任务。

只有一个专用 FIFO 线程执行完整原 `FormalOwnerService.dispatch`。begin/reseed、count、生成、finish 都进入该执行器。每次安装该会话的私有 Torch CPU/可见 CUDA RNG，调用原 service，再保存后续随机流并恢复 resident 的 parked RNG。finish 仍执行原 finish/guard；它恢复的是该会话的初始 parked 状态，不覆写另一会话保存的 RNG 副本。原 generator 没有加 wrapper 或替换；锁在外部编排层。

## 两阶段轮值与原时间门

客户端是新 `InterleavedOwnerClient`，旧 OwnerClient 不改。普通 `.call(op, **args)` 内部依次执行 reserve、等待 grant、commit；PROJECT 外层计费可使用 `with client.turn('project_complete', request=...):`，取得不执行模型的 grant 后，再调用同一参数的 `.call` 提交。

每个 ticket 固定完整原 operation/arguments、request_id、session claim 和原绝对 deadline。每会话最多一个 queued/dispatched 请求；已用 request_id 保留小 tombstone，不允许重放。生成类 ticket 的排队截止为 `min(original_deadline-615, enqueue+45)`，只有至少保留原 600 秒生成加 15 秒收尾余量时才可派发；grant 最长保留 5 秒，过期 commit 不执行。begin/count/finish 不套用 615 秒生成门，仍服从其原有效 deadline。

排队不暂停或重置原 660 秒请求/6,000 秒 episode 时钟。客户端读取原 guard 的 request_deadline 与 hard deadline。已开始执行后，剩余期限不足或回包不完整仍按未知处理；15 秒是调度保留余量，不是对所有 GPU/codec/存储故障都能及时闭合的保证。

queued/granted ticket 可以原子取消。服务保存完整未派发回执，包含 dispatched=false、generation_calls=0、usage_unknown=false、original_operation、request_id、session_claim、ticket_id、queued_seconds、原期限，以及 MATCH 当时的完整 ledger。客户端逐一核对本次 ticket/request/operation/claim，并核回执内容与其文件 SHA/字节数。不能因请求 ID 非空就接受另一条回执。随后抛出独立 BaseException `InterleaveNotDispatched`，由新的外层预算接缝处理；不自动重试。

真正派发之后不再返回零生成取消证明。尤其 PROJECT 在本地 mark_dispatched 后才发现 grant 过期时，外层仍须保守处理该计费边界，不能把原已派发标记悄悄倒退。原 exact count 对象带整对象 SHA，因此 count 返回体保持原样；交错证据放在独立 RPC envelope/turn 文件，生成返回只在原 body/usage 之外增加证据。

## 关闭、取消与长期内存

release 只验证当前会话已完成原 finish/guard、账本关闭、无自身 queued/dispatched，并移除自己的 socket。回执使用 session_quiescent、own_inflight、session_rng_closed 等新字段，允许另一会话仍在运行。普通关闭不要求整 resident idle，也不停止另一题。

未派发会话的 abort 先原子禁止新请求并取消其 queued ticket；如已进入窗口，原 finish/guard 清理排入同一个 FIFO，不创建额外数值线程。槽位在清理结束前保持占用。若本会话已 dispatched 或共享状态不明，则 shared poison，保留显存/lease，不自动复用；这不是模型正常失败分类。

abort 是幂等的：hostwatch、sentinel 和宿主异常同时报告同一 claim，只创建一次取消证明和一次清理，后续返回同一证明；已正常关闭的 claim 返回已有关闭证明。正常 release 正在完成时的 abort 不重复删除状态。返回 cleanup_pending 只在确实排入 guard 清理时为 true。

正常 release 与 aborted cleanup 完成后，在同一 metadata lock 内删除该 claim 已结 ticket 的原请求、生成返回和 token trace，并先清除队列中对应取消项。只保留小 request/claim 防重放集合与关闭引用，磁盘原件不删除。未知运行中的证据不被当作已结数据回收。这样避免长时间常驻后在内存累计整个评测的 prompts 和 outputs。

## 准备许可

实际 GPU 准备使用独立 `v054-resident-interleave-control-v1` 许可：四个 synthetic session（两 MATCH、两 PROJECT），两次 MATCH window 各两调用，PROJECT 各一调用，总最多六次。许可固定每个 session 的 request label/body、usage_id 和 seed；A1 是 Agent、A2 是 condenser、B1 是 PROJECT。许可的 8,192 输入、2,048 输出和 61,440 总 token 只是本次合成请求授权边界，不降低原模型 18,432 上下文或正式合同。owner 在准备请求派发前核对固定 request/usage 和实际输入计数。

本次实现未执行这些 GPU 请求；真实原始 facade 构造、Torch RNG 和权重同一性须由随后独立六请求控制证明，不能用下述 Python RNG fixture 代替。

## 已执行的必要 CPU 控制

1. 综合控制：`/tmp/v054-il-cpu-r2/receipt.json`，SHA256 `8d8146b37b938f8a47e5e996c43af49ebfee8660e5f0aaef9be3e9b99c1c8fb9`。程序化字符 tokenizer/Python RNG，覆盖基线 A1/A2/B1 与 A1/B1/A2 交错同值、Agent/condenser 两 attempt 一 decision、私有连续 RNG、finish A 不改 B、过期/余量不足零派发、finish 不受 615 秒门、局部 abort 不停另一生成，以及已派发故障 shared poison。最大同时程序化生成为 1。首次尝试仅因沙箱拒绝 Unix bind 而在进入前失败；获准本地 socket 后完成同一控制，没有重复 GPU 或正式任务。
2. 联调发现的生命周期增量控制：`/tmp/v054-il-lifecycle-r1/receipt.json`，SHA256 `4a2bc11c999b5664ab20755349acbf820353240dc5cbc153a5d13dffc2972af2`。只补请求 payload 回收/队列清理、小 tombstone 拒重放、两观察者同时 abort 的幂等和 cleanup 完成；没有重跑原综合基线。
3. 回执绑定增量控制：`/tmp/v054-il-ticket-binding-r1.json`，SHA256 `3c6a98a8661bc87f7b7045ace77ddd2cd38cb3cce5f4c1a99fc4184a3075a803`。复用已保存取消原件，拒绝错误 ticket、request、operation、claim，以及 hash 正确但属于另一 request 的回执；没有新 socket 连接或生成。

这些回执保留各自执行时的源码 SHA，后续生命周期/绑定修订未回写先前记录。最终源码身份见本次 manifest；不把早期 CPU 回执冒充最终真实 GPU 准入。全部 CPU 控制的真实模型、GPU 加载、实际 tokenizer、正式 claim 和隐藏评分次数为零。静态 Ruff 已通过；没有重复原容量或历史三组全链路控制。
