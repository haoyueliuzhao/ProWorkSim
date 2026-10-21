# v054 MATCH/PROJECT 双会话客户端与准入修订 r1

本修订仅改变同一常驻 MATCH/PROJECT 模型的会话容量与生命周期控制。每个已准入常驻模型允许最多两个独立任务会话；实际数值请求仍由服务器逐请求串行执行。REF 保留单会话。任务、seed、工具、采样、上下文、输出限制及每回合 token/时间预算没有在这些客户端文件中修改。

## 部署和会话绑定

新部署必须在 declaration、source spec、service-ready 与实际 owner identity 四处一致声明 `session_protocol="mp-interleave-v1"` 和 `maximum_sessions=2`。缺少该显式协议的历史部署只能占用一个会话。服务工厂将协议同步固定到 owner admission、service spec 和 model-service，并在验证阶段再次核对。

每个双会话部署以原 `session_lock_path` 派生 `.slot-0` 和 `.slot-1` 两把宿主 flock。获得本地槽后，客户端把对应 `session_slot` 传给 owner，且要求 acquire 返回同一槽、claim、协议和容量。第三个会话无法获得锁时在 formal claim 之前返回资源等待。不会为每个会话重新获取或卸载物理 GPU 常驻租约。

`available_residents` 保留 resident ID 为键，并增加 `session_capacity` 和 `active_claims`。健康判断核对活动 claim 对应的独占槽、可用槽补集，以及至多一个绑定的 dispatched ticket。已存在一个任务的双会话常驻模型仍可向调度器报告另一个空槽；这不意味着两个数值生成同时运行。

## 逐会话关闭和故障边界

正常 release 必须证明本 claim 已静默、没有本 claim 的 in-flight 请求、队列已移除、原学习/RNG guard 已闭合、该会话 RNG 已关闭、旧 socket 已移除且模型对象仍驻留。不再要求整个 resident 全局空闲，另一会话可以正在执行。

已有 r9 关闭修复继续保留。release 后的行政错误先验证保存的 release 与当前 session 文件及 claim 精确绑定，再确认当前 owner 中该 claim 已关闭；另一 claim 的 queued/dispatched 状态不构成该会话的未关闭证据，因此不会因此暂停整卡。

没有合法 release 时，双会话客户端请求 owner 的 `abort_session`。只有 owner 明确证明该 claim 没有 dispatched 工作、已移除自身队列并终止自身会话，客户端才记录局部失败并保持另一会话运行。该记录不会把失败任务重分类为成功，也不会授权重新生成该题。

若本 claim 已 dispatched 且共享状态未知，或管理通信无法取得可信取消证据，则封闭共享派发并按原绑定的 resident 身份暂停其进程组。暂停不代表已经提交的 GPU kernel 被即时取消，未知费用仍保留未知。客户端不自动恢复或重试数值请求。

原 660 秒请求边界不由此补丁延长。排队截止时间、未 dispatched 票据回执及 outer ledger 的映射由配套 owner/runner 修订提供；本客户端不会把排队取消伪装成已执行的生成，也不自行重发。

## 新 pool 的准入

新 policy 版本为 `v054-resident-pool-policy-v2-interleaved`。保留原 8 个 resident 上限与显存门，单个新 resident 的准备调用上限为 6；`inherit_modes=["REF"]`，旧 MATCH/PROJECT 常驻进程仅可作为原数值模板，不能被假定已支持交错。

新的 MATCH/PROJECT 注册使用 `kind="new_interleaved_model_device"` 和 `v054-match-resident-spec-v3`。`interleaving_check_receipt` 与 `check_receipt` 必须指向同一份实际控制回执。该回执必须绑定部署、准备授权、实际 owner 身份及物理 GPU，报告 6 次生成、4 个完成会话、零未结请求、同一个 resident PID/模型、独立会话、逐请求 FIFO 串行，以及三次对应输出/token trace/RNG transition 同值。旧版仅有顺序两会话的准备证据不能通过本门。

新 pool 使用独立根目录和策略，保留旧事件链引用；没有放宽旧链中仅允许完整 REF 闭合后退休的规则。

## 本分支的必要 CPU 控制

新增一项综合 CPU 控制使用真实 flock 与程序化管理端，验证双槽/第三槽拒绝、B 派发期间 A 的正常 release、A 释放后行政故障不暂停 B、未派发会话故障隔离、已派发未知的共享故障处理、REF 单槽，以及拒绝旧两调用凭据冒充新交错准入。

控制最终通过，pytest 用时 0.13 秒。首次执行只在测试夹具的临时模块 ROOT 与项目策略路径不一致处失败，修正夹具路径后重新运行同一项通过；没有执行旧 GPU 控制或重复容量测试。模型调用、GPU 加载、正式 claim 都为零。准入 JSON 在该 CPU 控制中是显式合成材料，因此该结果不证明真实 GPU 交错数值等价，也不构成正式运行授权或准入；真实六请求控制仍须由配套流程完成。
