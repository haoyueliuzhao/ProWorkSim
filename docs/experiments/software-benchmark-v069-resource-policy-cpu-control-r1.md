# v069 API 500 万 token 条件的资源扩展

本修订只为原 DeepSeek REF／PROJECT 的 500 万 token 条件增加可调度容量。原任务、seed、模型可见配置和每题预算不变。750 万／1000 万条件不再新增派发；此前在途任务自然收口。既有 Qwen 驻留和任务不停止、不重载、不迁移。

## 共用原预算池

新资源模块继续在原 R3 的 `resource-claims/allocation.lock` 下登记和释放预约，读取所有实际 active claim，并调用原 `_budget`。全局仍限 152 CPU、832 GiB；没有建立第二个预算池。

每个 actor／controller pair 继续预约 6 CPU、32 GiB：actor 4 CPU／16 GiB，controller 2 CPU／16 GiB。Docker 的 NanoCpus、memory、memory-swap、PID、隔离及工具设置均不降低。controller／volume 依附同一 pair，只由 actor 预约一次完整容量。

actor 准入额外保留至少两个 grader 的容量。已有一个 grader 时补 4 CPU／16 GiB，已有两个或更多时不再重复预留。该余量用于准入计算，不伪造 grader claim，也不重复记入实际已预约资源。模型驻留、所有辅助 coordinator 和实际 grader 都从共同 active 集合动态统计，不能假设永远只有两张卡或两个模型服务。

例如，恰好保留两个 grader、两个 coordinator 时，两份 96 GiB 模型驻留最多容纳 18 个 pair；增加第三份模型驻留后最多为 15 个。旧 API coordinator 尚在收口、存在第三个 coordinator 时，第三份模型下最多为 14 个。实际 grader 更多、宿主物理余量不足或其他原预算门关闭时，并发还会更低。这些是条件上限，不是保证同时运行的数量。

## CPU 共享的准确含义

逻辑 actor lane 上限从 12 增至 18；新增 lane 12–17 通过 `lane % 12` 复用原 lane 0–5 的 6 核片段，每片段仍划分 actor 的 4 核和 controller 的 2 核。使用的仍是原 actor CPU 池，不占用 model CPU 分区，不创建假的 model lease，不消耗 model 创建身份，也不修改宿主 cpuset。

**逻辑槽不代表新增独占 CPU。** 重叠任务由操作系统在相同 CPU 上调度，可能增加 CPU 密集步骤的等待时间。每题硬限额未降低，但 CPU 独占性和实际可得时间不同于原互不重叠的 lane。该部署变化必须单列，不能仅凭并发数宣称相同计算机会或吞吐必然按比例提升。新增 claim 的 `CPU_sharing` 明确保存逻辑 lane、原 CPU lane、actor／controller cpuset 和 `exclusive_CPU_guarantee=false`。

## 身份和清理边界

只允许原计划中尚未消费的 API 500 万 token actor／controller／volume 身份。新 claim 保持原通用资源格式，但另有 `expansion_authorization`、`expansion_revision` 和源文件凭据，明确额外并发许可来自新作用域，而不是声称原授权已经覆盖 18 个 lane。

provider 与 episode 使用私有函数／类 namespace 绑定新资源 policy，不修改 v066／v068 的冻结源码或全局变量。创建、启动、传输等操作经过新 scope 的 run 门；停止、清理及释放经过 drain 门，并核验普通用户身份及每份 claim 的确切归属。即使 pair 已过生命周期截止，仍可在合法 drain 范围收口；不能因此清理其他任务。

## CPU 验证

初轮 5 项必要 CPU 测试通过，覆盖：原 12 lane 全满后分配新 lane；原总账及相同分配锁；4／2 CPU 和各 16 GiB 不降；两 grader 余量及第三模型的动态影响；满额拒绝不消耗身份；原／外来 claim 保护；旧 policy 和函数源码不变。

随后只增加并执行 1 项收口边界控制：过期 pair 仍须通过自己的 drain guard，只释放其已预约、尚未创建的对象身份对应容量。该项通过，未重跑前 5 项。合计 6 个不同 CPU case，Ruff 通过。

验证只使用临时目录、私有 namespace 和假客户端，没有真实容器、服务、模型、API 或 GPU 操作。正式部署和吞吐变化应以新作用域的运行记录为准。凭据见 `artifacts/software-benchmark-v069/expansion-resource-cpu-r1/validation.json`。
