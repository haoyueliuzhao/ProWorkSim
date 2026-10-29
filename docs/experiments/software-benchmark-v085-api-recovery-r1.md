# v085：文件描述符异常后的原 API 库存恢复

v083 主协调器因 `OSError: [Errno 24] Too many open files` 退出。原 summary 有 683 条生成状态；退出后的独立只读审计确认，本版调度过的 53 个任务均有原始终态且已完成清理，其中 45 个终态未归入 summary：5 个正常闭合、40 个技术未知。恢复不重跑这 45 题，也不把技术未知改成模型失败。

v085 的新库存由原完整两组 1000 个身份逐一生成：保留原 summary，再导入未归并的同任务、同配置 result；排除旧调度事件、历史资源 claim、已有环境或任何 API 请求证据对应的身份。预期剩余 272 个未消费任务，由实际准备结果再次给出数量。原已有评分终态保留；已完成的固定请求只导入 completion，尚未消费的请求才可执行，已开始但没有可信完成证据的评分保持未知并禁止重放。已恢复的 5 个闭合结果按同规则进入异步评分。

总账继续使用 v064 的唯一 1500 元账本。审计时 `reserved=0`；21 个 uncertain 的最大费用预约合计 110.10048 元继续保留，不能记作零或当成实际已结算支出。已结算费用为 954.71752808 元。以上是审计时点值，运行中由原权威账本继续计算准入。

新普通用户服务为 `proworksim-v085-api.service`，4 CPU、64 GiB、swap 0，仍使用管理 CPU 164–167；仅该新服务设置 `LimitNOFILE=16384`，准备时确认现有 host hard limit 足够，不改共享主机限制。FDGuard 按真实 FD 数和余量暂停新增任务，避免临时描述符不足变成全局队列取消。RuntimeView 必须在首次初始化之前包裹原 API runtime，使主客户端及其每题 fork 使用显式关闭只读 SQLite 预检连接的新 ManagedClient／ManagedLedger。原模型、工具、预算、采样、HTTP 与账本规则不变。具体 FD 缺陷控制见 [FD 治理说明](software-benchmark-v085-fd-governance-r1.md)。

原 v076 父组已完成第一生命周期。在用户已有的精确授权范围内，已建立同名、同限制的第二生命周期，并将 `created/released` 记录写入 v085 独立目录；旧 marker 不改。新 runner 的资格检查、内存探针、actor 容器选项及启动后父组检查均绑定 `software_benchmark_api_parent_v085`。CPU 控制检查的是实际闭包绑定，避免只替换外层引用而内部仍读取旧 released marker。

此恢复仍使用 v082 三线程完整异步评分，不调用或重启 Qwen。Qwen 补位提示读取 v084 状态，失败或结束的旧协调器不使 API 永久暂停；实际全局 API48／Qwen4 边界保持。48 是目标上限，真实并发与 FD 使用情况必须在部署后单独观察。

有限验证：恢复身份、行政预算边界、可信清理、固定评分请求复用、已消费评分禁止重放、新父组及安全 JSON reader 实际绑定、仅新服务 NOFILE、ManagedClient 初始化、嵌套 owner pressure 新服务绑定，与 FD 模块控制联合共 18 项 CPU 检查通过。无 Docker、模型、API 请求或服务操作。主协调者负责执行以下真实准备及启动，并在超过 v083 原触发时长的窗口观察 FD 与进度：

```bash
.venv/bin/python tools/run_offline_scorer_v058.py tools/prepare_api_recovery_v085.py --prepare
.venv/bin/python tools/run_offline_scorer_v058.py tools/launch_api_recovery_v085.py --launch
```

原 v083 源码、状态、收费及已消费身份保留。独立发现的 PROJECT `cursor:null` 与 SDK 参数规范化兼容问题属于遗留问题，本版本不改在线 harness，也不因此重跑旧题。

## 已完成部署

2026-10-29 约 15:19，真实准备形成 272 个未消费槽，并导入全部 45 个原终态。初始历史为 537 closed、162 technical_unknown、29 not_started；另有 5 项未消费官方评分进入异步队列。原 API 总账没有修改或重置。

新父组生命周期通过原授权的精确同名命令建立，内核核验通过；原对象不存在及 API 活跃预约为零是创建前置条件。父组四项必要 CPU 检查验证新旧生命周期绑定隔离及拒绝扩展范围，旧授权、停止记录和源码保持。

新普通用户服务已经启动，真实软／硬文件数限制均为 16384。只读观察初期，API 从 8 个任务逐步启动，Qwen 保持四题。独立 30 分钟监测记录文件数、进程存活、实际任务和请求并发及 CPU／内存／现金边界；监测程序自身的只读 SQLite 连接也显式关闭。最终观察数据以 `artifacts/software-benchmark-v085/live-monitor-r1/summary.json` 为准，本文不以服务成功启动代替持续运行验证。

## 30 分钟观察结果

15:19:56–15:49:56，共 61 个采样点：API 活动任务预约峰值 **45**；末尾 20 个采样点（约 9.5 分钟）均在 **40–45**。目标上限仍为 48。采样中的在途 API 请求峰值为 12，任务并发与请求并发不能混称。

FD 峰值 **945／16384**，期末约 849；没有观察到 EMFILE、OOM、服务退出、现金硬停止或队列级 failure。出现 3 个主循环超过 5 秒的采样告警，最大约 8.75 秒，随后恢复；没有达到 60 秒的严重停滞告警。这是有限观察窗，不是长期稳定性认证。

期末 CPU 空闲约 85%，MemAvailable 约 895 GiB，Qwen 为四题运行。API 正常闭合生成由 537 增至 558，增加 21；技术未知仍为原 162。`closed` 只表示生成闭合，不能将这 21 项称为正确解或评分成功。半小时折算约 42 回合／小时仅描述这一包含启动阶段的窗口，不能作为剩余任务的确定完成时间。

期末账本已结算 1032.07 元，不确定费用预约 110.10 元，另有 4 项在途预约；扣除全部承诺后余额 336.86 元，总上限仍为 1500 元。后续现金门继续生效，没有额外费用授权。

环境启动仍限制补位：近阶段最新 6 次已就绪环境耗时约 351–402 秒，8 个启动槽经常占满。实际 ready 标记均合法，未发现因严格字段核对而误拒已经就绪的环境；不能把该等待归为模型推理慢。本次未进一步变更运行中的启动上限。环境初始化中的具体 Docker 上传、SDK 导入和 I/O 分量尚未独立量化。

证据：[完整监测](../../artifacts/software-benchmark-v085/live-monitor-r1/summary.json)、[统计边界](../../artifacts/software-benchmark-v085/live-monitor-r1/interpretation.json)、[启动观察](../../artifacts/software-benchmark-v085/startup-throughput-observation-r1/observation.json)。实验队列在观察结束后继续运行，本文不是完整 500 题评测结果。
