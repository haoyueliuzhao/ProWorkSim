# v054／v055 资源与环境准备协调器的最终上线观察

2026-10-22（Asia/Shanghai）09:18:32至09:19:18进行了两点有限只读观察。服务`proworksim-v054-formal-queue-preparation-r2.service`、`proworksim-v055-deepseek-six-conditions-native-host-r5.service`与`proworksim-v055-cache-reclamation-r2.service`均为active/running。本观察只读取任务状态、文件计数及资源metadata，没有读取模型思考正文或评分值，也没有重启模型、重放回合或改变冻结代码。

## Qwen三组的实际运行证据

此窗口内旧Qwen pending从1045降至1044，closed从448增至449，表示新增派发1个并闭合1个。最后一个快照中，PROJECT的django-15572在GPU3、sympy-21847在GPU6执行，共2个running；此前在GPU3执行的MATCH刚刚闭合。因此不能说三组在最后瞬间同时都有执行回合。

按09:00以后终态result文件时间和队列closed状态计数，MATCH已有4个、PROJECT已有2个、REF已有1个闭合；这是运行状态盘点，不是题目修复成功数。REF的django-11999位于GPU7，已从实际运行进入closed。其`ref-ledger`包含31个非空request文件与30个非空response文件，足以证明存在真实模型交互，而非仅协调器派发；观察没有读取这些请求／响应的消息正文。`result.model_calls`为null，因此不能用31个请求文件代填31次成功调用，也不能忽略其中一次请求与响应数量不等的情况。

## 库存不足与环境准备

新`shared_preparation_demand`按旧REF／MATCH／PROJECT分别计算可用库存；最后观察时REF有1个pending qualified和1个pending preparing，`running_preparation_count=1`，且总prewarm状态也显示1个preparing。原有v055未消费ready库存112、8个库存上限仍被保留，但它没有阻止为缺少任务环境的REF启动准备。这证明新的按消费组准备通道已有任务在途，不表示所有后续任务都已准备完成。

第一份观察里另有`running_preparation_rows=0`，这是观察脚本按`attempts[].status == running`计算的非权威诊断，与该队列实际准备状态结构不匹配；不得据此称没有准备任务。第二份观察改用协调器公开的`authoritative_running_preparation_count=1`，两份回执均保留，未覆盖原观察。

同时，DeepSeek pending从2243降至2242，closed从687增至688，最后仍有11个running。两个协调器的共享磁盘预约metadata_error均为null。等待字段仍可表示下一槽受磁盘峰值预约门限制，这不影响已经派发回合的运行与收集。磁盘预约是保守估计，不是文件系统配额或精确剩余写入量。

## 清理计量与实际余量

最后一次观察中，按已完成rootfs回收receipt统计，共96个模板、历史普通文件逻辑大小308,689,913,657字节（约287.49GiB），GC failed与dispatch-uncertain均为0；data0实际可用459,047,792,640字节（约427.52GiB）。逻辑文件大小与另行授权的历史中间layer清理所报告的allocated物理占用采用不同口径，应分开报告，不能相加后称为统一实测回收量。系统free还会同时受新回合clone与清理影响。

该46秒观察确认队列继续派发和收集，以及REF已经发生真实模型交互，未据此推断长期吞吐或全部实验已完成。此次部署后观察到此结束。

## 小型回执

- `artifacts/software-benchmark-v055/cache-activation-r1/preparation-hosts-first.json`：SHA-256 `1308571167d0f5f90e0aa2b6ed9911f1d21109bdb4cfffdd3a50efcc7ccd6674`。
- `artifacts/software-benchmark-v055/cache-activation-r1/preparation-hosts-last.json`：SHA-256 `f6c08862d1c1c84275f174d7de578d4df42e5b1f7e4145d49f86ea6585582835`。
