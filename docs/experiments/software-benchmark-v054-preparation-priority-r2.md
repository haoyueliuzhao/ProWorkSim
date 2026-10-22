# v054 共享环境补齐需求调度 r2

## 问题与范围

恢复磁盘准入后，旧 Qwen MATCH/PROJECT 已能继续派发，但 REF 接近耗尽已准备任务。
新 DeepSeek 队列有较多自身尚未使用的合格环境，其“最多八个未用准备环境”规则因此可能
阻止继续准备，而旧 REF 仍缺少下一题。仅以新队列库存判断共享预热需求，不能满足旧三组
和新六组全部消费者。此处修订的是共享环境准备与磁盘准入调度，不修改模型或实验求解条件。

新增 `tools/run_qwen_preparation_priority_v054_r2.py`，在独立 host 进程内给原恢复模块
绑定磁盘接口包装。原 `RecoveryCoordinator.dispatch_generation` 函数直接继承复用，
冻结源码不修改；锁、估算、候选选择、durable intent、worker 启动与正式求解入口保持原流程。
该包装不是模型服务反向代理，不改变实验 API 网络路径。

## 多消费者需求与容量

与新 DeepSeek host 使用同一共享 helper：
`proworksim.software_benchmark_preparation_priority_v055_r1`。它只读固定题序和运行状态：
对旧 REF、MATCH、PROJECT 各自统计“未开始且已合格”以及“未开始且正在准备”的任务，目标
库存为每组两题。不足时从原定顺序的冷任务中提出补齐需求，合并后最多两个；失败环境不在
此处重试，任务成绩、补丁内容和模型回答不参与选择。

该共享 helper 不选择失败模板，并不扩大旧 Qwen 的错误豁免：旧 dispatcher 仍只对 r1 中
精确审查的 matplotlib 磁盘导出失败延期；若后续出现其他未经分类的准备失败，仍会触发原
共享故障门槛。当前观察到的失败模板只有已审查这一项。本版本没有把新出现的未知失败自动
解释成同一种磁盘问题。

包装从原 dispatcher 在同一个 `disk-dispatch-r4.lock` 内传入的两队列当前状态计算需求。
若存在需要启动的补齐任务，且此时没有正在预热的任务，新生成准入的最低剩余空间提高为
`max(100 GiB, 128 GiB 预热预约 + 128 GiB 预热余量) = 256 GiB`。这样下一次准备启动可以
获得磁盘空间。预热开始后，它本身的128 GiB预约计入共享总额，不再额外强制256 GiB。
其他时刻生成仍使用100 GiB余量；预热自身准入仍使用128 GiB余量。

元数据不完整时拒绝新派发。旧队列只消费合格模板，不启动另一套预热器；补齐实际由新队列
唯一的准备调度执行，保留原评分和在途回合。此修订不提高预算、放宽磁盘底线或重放回合。

## 接管和验证

新 planning revision 与原 resource-recovery revision 分开记录。接管前仅停止旧 host
协调器，独立在途 worker 和所有驻留模型继续运行。构造器继承原 controller lock，核对
旧 host 已停止、原恢复 adoption 仍一致且队列没有新的全局暂停，再写入独立 planning
adoption 和历史。它不会再次调用原 `adopt_recovery`，不会清除新的共享故障。

一次必要 CPU 控制验证了实际包装的委托路径、两份当前状态的传递、同一磁盘锁、生成与准备
余量的作用范围、缺失需求时拒绝派发，以及原 dispatcher 函数身份和输入状态不变。
控制中模型调用、GPU加载、正式claim、服务修改和真实队列写入均为零。

实际部署以 `runs/software-benchmark-v054/preparation-priority-r2/` 内的封存、CPU收据、
planning adoption 及运行队列状态为准；CPU控制不等同于模型回合已完成。
