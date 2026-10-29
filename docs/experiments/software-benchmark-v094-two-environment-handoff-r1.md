**v093 两项实际环境失败后的零模型交接（v094）**

本次与 v092 的失败不同：v093 首个 PROJECT（physical6044）和 REF（physical6045）已经实际创建环境，合计 **4 个容器、2 个专用卷**。模型 FIFO 桥初始化仍引用原 v066 六千槽授权，拒绝带 `:recovery-v089-r1` 后缀的恢复逻辑身份，随后停止。原日志为 `Episode outside the fixed six thousand paired runs`；不能把这一错误简化为模型失败或仅仅修改物理编号就算修复了桥接。

两个环境均已停止并完整清理：actor/controller/volume 的原 claim 和释放凭据一致，writer 静止，模型桥线程结束，quiescent=true，无残留对象、清理错误或未知创建结果。controller 压缩归档和中间工作树原件保留。两个 `host-api-counts` 目录为空，model_calls=0、model_dispatch_started=false；controller 只生成了 ready 文件。44 个恢复逻辑身份在 requests、response_observations、provider_protocol_events 三张 API 账表中仍均为零。

启动健康门只允许这两个接口样本先进入，失败后保护了其余42项：physical6046–6087 没有 episode 或 actor/controller/volume/评分 claim，尚未消费。新交接仅将 **6044→6088、6045→6089**；其余42项保留原物理编号和配置引用。预算端仍使用 v089 canonical6000–6043 注册表，同44个逻辑 slot_id、recovery_attempt=1、任务、seed、模型和条件均不变。本次不新增模型尝试或 token 额度，也不修改原失败结果或费用。

环境开销必须累加，不能复用上一轮“零 Docker 创建”的结论。迄今这44个恢复模型尝试实际产生4容器/2卷的失败环境开销；若修订后完整执行44项，原完整环境上界155容器/44卷需计入这笔开销，累计为159容器/46卷，评分任务数量不增加。上述数量是环境创建累计上界，不是并发数；模型尝试仍44、累计输入＋输出上界仍2.2亿，人民币总账仍1,700元。

完整映射、逐对象创建/释放、零请求与未消费证据已封存在[summary.json](../../artifacts/software-benchmark-v094/zero-model-environment-handoff-r1/summary.json)。新 scope 必须引用这份新证据，并在桥接实际绑定中使用新授权；不能只更新最外层 guard，不能静默放宽原 guard 的身份检查。预算、唯一请求 ID 和逐槽禁止重采规则保持。

本次工作仅只读核验和形成交接材料，没有启动服务、容器或模型，没有调用 Docker 管理接口、修改账本或改变宿主配置。摘要是观测时点的证明，不是执行授权；新启动仍需确认旧 manager 已退出、新物理目标未消费及来源封存一致。
