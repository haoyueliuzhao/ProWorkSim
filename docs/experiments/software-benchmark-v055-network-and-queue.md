# v055 DeepSeek 六组实验的网络、CPU 队列及评分接入

本修订只增加独立 v055 执行路径。原 v054 GPU resident、队列、冻结源码、已进入回合及评分缓存均不修改，不新增 GPU 负载。网络和资源准入不等于模型接口准入，也不等于正式成绩；实际启动仍依赖单独冻结的模型／预算／接口条件与运行许可。

## 网络边界与实际验证

可信 SDK controller 通过 `DirectHTTPS` 直接连接 `api.deepseek.com:443`。客户端不采用环境代理、不跟随重定向、不自动重试，端点只允许 Chat Completions 与只读官方模型／余额接口；模型工具清单不含搜索工具。本地不建立 API 反向代理，也不把官方密钥传入 Actor。每个子进程另设直连环境，不修改宿主或其他项目的网络配置。

Actor 继续使用已验证的官方镜像环境、独立 user/mount/network/PID namespace、chroot、零 capabilities、私有 `/proc` 与清空后的环境。仅保留隔离 namespace 内的 loopback，允许代码的本地服务测试。原生 terminal/file_editor/task_tracker 都在该 Actor 中执行，不能访问宿主 `.env` 或官方 API；PROJECT 仍走受管接口，其公开测试也启动同样的隔离 Actor，没有新增不受管 bash。这个控制防止运行过程中联网检索答案，不能证明预训练知识没有包含评测内容。

2026-10-21 23:50 CST 的一次真实集成控制使用已准入 matplotlib 环境的独立临时克隆，没有调用模型、官方评分器或隐藏测试，也没有申领正式槽。结果如下：

| 检查 | 观察 |
| --- | --- |
| 实际 Actor 接口 | 只有 `lo`，PID 1，capabilities 全零，`no_new_privileges=true` |
| 外部 IP 连接 | 对文档测试地址 `198.51.100.1:443` 的连接在本地被拒，errno 101 `ENETUNREACH` |
| 密钥隔离 | Actor 环境没有 `API_KEY` 名称，宿主 `.env` 路径不可见 |
| 实际资源 slice | `cpu.max` 为 4 CPU、`memory.max` 为 16 GiB、`pids.max` 为 16384 |
| 首次可信 SDK `/models` | TLS 证书链校验失败；原失败完整保留 |

首次集成失败发生在可信 SDK 私有运行时的 CA 信任链，不在 Actor 隔离。宿主项目 Python 使用 Miniconda 的 240216 字节 CA bundle，而私有 SDK 使用较旧的 182140 字节系统 bundle。宿主实际验证的官方证书颁发者是 `TrustAsia DV TLS RSA CA 2025`，主体和 SAN 均对应 `api.deepseek.com`。没有关闭 TLS 校验。

修订只为新的 `run_native_sdk_controller_v055.sh` 指定本机已验证 CA 的固定副本：`runs/software-benchmark-v055/network/ca-bundle.pem`，SHA256 `9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f`。该副本来自本机，不产生下载流量。wrapper 校验 CA SHA，随后在私有运行时内设置 `SSL_CERT_FILE`。只重测失败的 controller `/models` 环节即成功，返回包含 `deepseek-flash`；没有重复已经通过的 Actor 控制。

综合准入记录为 `runs/software-benchmark-v055/network-resource-admission-r2.json`。它引用原失败、Actor 连接证据、CA 来源、修复后的元数据响应及评分路径控制，不覆盖旧记录。所有临时 Actor 进程已退出，资源 slice 已释放，克隆已按静默证明删除。

## 新执行目录与旧资产复用

公共问题文本、500 题身份、原官方镜像、基线映射、完整公开测试入口以及 SDK 版本保持不变。新的回合 UID bootstrap 允许读取已准入的 `v054/native-lazy-cache` 作为克隆来源，但回合克隆的创建、修改、启动和删除目标均限定在 `runs/software-benchmark-v055`。新增 helper 的目的，是适配原 helper 仅允许 v054 目录的路径合同；没有放宽 Actor 网络或宿主可见范围。另有最多两个 CPU 预热 worker 复用原 `ensure_native_instance`，在原精确 task／mapping key 的锁下为共享缓存添加尚未准备的条目；已经 qualified 的模板不修改。

v055 分开保留 queue、episode claims、controller 配置、API 账本、IPC、候选锁、评分请求和输出。IPC 使用短目录 `runs/v055-ipc`，避免 UNIX socket 的 108 字节地址上限。每回合继续复用原 4 CPU／16 GiB／16384 PID 的系统 slice 与监督器实现，因此底层 Actor/controller service 名仍含 `v054-episode-<新随机claim>`；这只是既有监督器命名，新的 claim、授权和结果身份属于 v055，不复用旧回合。

独立 host runner 不启动 GPU owner 或本地模型服务。它先验证原公共任务和环境，建立离线 Actor，再运行可信 API controller。生成结束后等待所有写入者静默，随后唯一锁定原生最终工作树，或 PROJECT 的最终代码与最后合法提交。评分不反馈给模型，候选不依据评分重新选择。PROJECT 的公开测试并发信号量为 8，排队计入原回合时间；原生 terminal 可自行运行测试，所以不能把这个信号量当成全部 CPU 测试的全局上限。

## 并发与预算截断

资源检查观察到 176 逻辑 CPU、约 914 GiB 可用内存，1 分钟 load 约 17.5；该值只表示检查时刻，不是长期保证。项目私有 Docker 为 29.3.1、cgroup v2/systemd，CPU、内存、PID 限制均可用，当时 1531 个镜像、0 个运行容器；其 HTTP/HTTPS proxy 为空，NoProxy 为 `*`。

24 并发的准备草案保留。用户进一步要求尽可能提高并发后，最终冻结上限为 32 个独立生成回合、4 个官方评分和2个CPU预热 worker。实际生成并发取以下约束的最小值：配置上限32；`floor((CPU总数−24−4×v054活动生成与评分数量−16)/4)`；`floor((可用内存−128GiB)/16GiB)−4`；全局API并发64。负值按0处理。24核预留用于系统、GPU owner 和其他 CPU 工作；另16核为4个评分预留。原生根准备最多两个，原精确key锁避免与旧预热重复准备。

内存门额外保守地把现有 worker 已使用内存计算在可用值中。load 达140或旧队列活动数无法读取时暂停新增派发；已经运行的 worker 不因后续容量下降而终止。每个回合保持4 CPU／16GiB，评分继续执行原限制。这里描述的是派发时的容量约束，没有修改其他用户服务或 v054 资源限制。

磁盘空间也是显式门：新增生成要求至少100GiB可用，新增原生根预热要求至少128GiB可用。低水位只暂停新增磁盘工作，已经进入的任务、清理和评分继续收口，绝不删除旧 v054 缓存或任务数据。只测量了一份 matplotlib 模板：实际分配 `7,627,214,848` 字节，约7.10GiB；若剩余模板都达到这一大小，数百题需超过2TiB，所以当时约788.5GiB空闲空间不能证明全部500份原生根都能同时常驻。这只是单题示例外推，不是跨仓库大小估计。

全部 API client 共用一个人民币 2000 元总账本，准入与预检费用也计入。queue 通过零消费 snapshot 读取剩余资金、在途预约和全局 halt；价格、用量及保守预约规则见独立 API／预算说明。没有把并发提高理解为追加资金。

固定题单按同一任务六条件组成一块排序，保持预先确定的公平轮转，不按模型成绩换题。预算只能控制最大支出，不能保证 3000 回合全部完成。全局资金／系统预算边界关闭时，未开始项仍留在计划分母；正在运行的候选可在受控闭合后离线评分。结果中的 `controller_status=budget_exhausted` 另外记录为 `administratively_censored=true`，不与正常单题 token／时间边界或模型修复失败混为一类。完整 500 题点估计不能把这些未知项视作已知失败。

## 队列异常与评分缓存

每个 generation／score／preparation job 先持久化不可重放的 intent，再启动独立、不自动重启的 systemd unit。协调器重启后继续观察尚在运行的 worker；worker 消失且无完成证据时进入异常集合。单题导出／容器／评分异常不会阻塞其他题，已经进入的模型回合不自动重采。普通 API 系统错误使用短暂冷却，冷却只暂缓新的模型派发，收集和评分继续；401／402／403及账单完整性异常仍阻止新API调用。异常集合保留原 job、request 和原因供后续同候选处理，当前实现不自动追加模型回合。

环境未准备的题保持 pending，不进入模型、不申领正式 claim，也不记作修复失败。队列可以继续安排后续已准备的同题六组，CPU预热并行补齐缺项。明确失败的原生模板仅进入环境异常集合；其余可运行主流水完成后，队列可进入 `primary_finished_with_deferred_environment`，不会为失败模板永久占住流水线。所有组的计划分母仍是500。

官方 SWE-bench 5.0.2 评分逻辑保持原样，v055 adapter 的 identity 额外绑定六条件 ID、思考开关、slot、模型、配置和候选；不同条件及评分 attempt 使用独立 `run_id`，避免官方按 `run_id`／`instance_id` 复用结果。每个请求有固定 receipt 指针，queue 无需扫描整个成绩目录。

在实际评分私有运行时中导入官方 harness，并检查六组真实输出路径解析，均位于 v055 独立根且互不相同。该控制没有启动 Docker 容器、没有调用 grader、没有生成模拟正式分数。新评分安装清单和控制记录在 `runs/software-benchmark-v055/scorer-preflight-r1/`。

## 必要控制与限制

初版 6 项 CPU 控制覆盖 Actor 网络证明拒绝、独立 proxy 环境、六条件 cache 身份、完整同题公平题单、失联 worker 延后及活动 worker 接管，全部通过。随后目录适配及 CA 修复由上述真实 Actor／私有 controller／评分运行时控制验证。

另外执行了 native MATCH 与 PROJECT 两项程序化全 host 生命周期控制。第一版在 controller 入口前被加长的隔离根 IPC 路径阻断，原失败保留；改用短 IPC 路径后，两条实际 clone→SDK→监督静默→候选→评分请求校验→清理路径均通过。程序化响应及其 fixture-only SQLite 记录不是模型请求或实际费用，不使用正式3000个claim或共享人民币账本，也不执行评分。相关记录为 `host-lifecycle-r1` 与通过的 `host-lifecycle-r2`。

32并发的CPU／RAM／API算术新增7个边界控制通过。后续磁盘门只增加4个磁盘算术边界和1个实际queue tick低水位控制，继承已经通过的检查，不重复模型或生命周期测试。原生缓存门、冷却中评分继续及主流水末尾环境异常收口也完成一次CPU控制。静态检查通过。

最终冻结于2026-10-22 00:26 CST：3000个预定槽、六条件各500题，保留原500题顺序并对六组位置轮转平衡。按每题当前精确baseline mapping读取的环境覆盖为170 qualified／330 pending／0当前失败；目录里保留的历史失败文件不能直接当作当前失败计数。源清单绑定1590个文件、86,283,667字节，包括原v054依赖、新v055代码、官方本地counter和CA。单独的六组真实中性API资格12请求均通过，已计入同一总预算的保守费用为0.05128168元；builder只读核验该账本，没有新增模型请求。队列计划SHA256为 `da427337c67204f1afd7f8a674c6657a4a0e39acb14aa30e0426ff78d21ada8e`。构建器本身没有启动正式队列；正式运行状态应以根协调器后续启动证据为准。
