# v088：高编号描述符修复与实验恢复

本次修复针对 v086 的 `filedescriptor out of range in select()` 以及由单题初始化故障触发的全队列停止。原始故障、取消结果、候选及费用未知全部保留，不将已经消费的任务重新生成。

此前提高 NOFILE 只解决了进程可打开文件的数量限制；`select()` 另有描述符编号限制。Linux 手册明确说明其编号须小于 1024，并推荐使用 `poll()`／`epoll()`。此次私有宿主适配改用 `poll()`，同时覆盖 episode 直接创建通道与 provider attach 两个实际调用点，以及评分子进程的同类 TLS/TCP 等待路径。原帧格式、截止、EOF、取消、CA/TLS、评分候选与官方测试保持。[Linux select 手册](https://man7.org/linux/man-pages/man2/select.2.html)

只有同任务身份、零模型派发、受信本地传输初始化错误、完整线程和容器清理证据同时成立时，新结果才按单题技术未知处理。真实共享完整性、身份、账单异常及清理不明仍保留原停止规则。原 5552 故障仅用于只读核验，没有回写为新分类，也没有重跑。

恢复时还发现旧 v085 的管理进程因自身文件缓存而持续暂停评分。仅对该普通用户服务设置运行时 MemoryHigh=32 GiB，保留 MemoryMax=64 GiB、swap0 和原 PID；没有操作全机缓存。实际内存由约 57 GiB 降至约 32 GiB，准入恢复，评分记录由 611 推进至 640，全部原在途与评分自然结束后，按既有精确 pidfd 交接退役空管理进程。新 v088 延续相同软回收线。MemoryHigh 会触发本服务的回收和节流，可能改变墙钟延迟，不应声称没有时序影响；硬上限没有降低。[Linux cgroup 文档](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory-interface-files)

新评分权限与 API 容器父组的存活解耦：评分容器本来就在父组之外，API 空父组合法退出不能使固定候选无法评分。评分仍核验原权限、任务、候选、资源上限、实际宿主与管理进程余量，且其私有策略只能创建原评分角色，不能创建 actor、模型或额外数据卷。

验证包括真实复制到 FD2048 的 socket／pipe、Docker 帧拆分、EOF、截止、模型桥 ready／合成请求／结束协议，以及实际私有绑定；异常集合 HUP 的截止边界另做窄复测。队列控制验证一个有完整证据的本地初始化故障不会取消另外七题，真实共享错误反例仍停止。恢复集成验证库存互斥、候选身份、已消费评分禁止重放与评分父组独立性。详细执行次数及源码 SHA 见对应验证文件，不把 CPU 控制算作正式模型回合。

真实准备固定接续 **61 个未消费任务、13 个原固定候选评分**。初始历史为 705 个生成闭合、205 个技术未知、29 个登记未启动，保持原两组各 500 题分母。API 上限48、启动槽16、管理8CPU、64 GiB硬限、NOFILE16384、父组224 GiB、模型／seed／每题预算均保持；人民币上限仍为原1500元账本。Qwen v084 四题并发和四个原模型驻留未被重载或停止。

18:20:28–18:30:28 的十分钟窗口中，新服务持续运行，API 任务预约从15升至43，在途API请求峰值6，无新的全局 failure 或隔离异常事件。出现11个主进度超过5秒的采样，其中10个伴随新心跳但主循环尚未刷新，最大循环间隔约40.04秒；没有60秒严重停滞报警。这说明仍存在调度报告延迟，不能把本次修复表述为长期稳定性认证。

窗口后的宿主只读核验记录实际 **1085 个打开描述符、最高编号1093**，服务仍为running、failure=null、API48／Qwen4，内存 hard/high 分别64／32 GiB，未见本服务OOM或memory.max事件。这是在线越过旧编号边界的运行证据；独立高FD控制进一步覆盖了2048编号。

13项原固定候选评分均完成执行和清理：**12项取得有效官方结论（7 resolved、5 unresolved），1项仍为技术未知**。该未知是 `astropy__astropy-7336` 的 score-5530：原补丁未成功应用，保留其原候选和诊断，不填成模型失败，也不归因于此次通信修复。此小集合不代表完整基准正确率。PROJECT 已知 `cursor:null` 参数兼容问题同样不在本次在线接口修订范围内。

现金门仍在工作。十分钟窗口末已结算1319.42元、不确定预约152.04元，另有5项在途预约，可继续预约2.32元；部分后续快照为 `waiting_inflight_cash`。这是等待已有预约释放，不能直接说总预算已经耗尽。实际资金不足时不得扩额或释放没有用量证据的不确定费用，因此不能保证剩余61题全部闭合。

证据与实现说明：

- [高FD修复及验证](software-benchmark-v088-high-fd-transport-r1.md)
- [局部初始化异常隔离](software-benchmark-v088-local-initialization-isolation-r1.md)
- [恢复与权限边界](software-benchmark-v088-api-recovery-r1.md)
- [在线监测](../../artifacts/software-benchmark-v088/live-monitor-r1/summary.json)
- [超过1024编号的在线状态](../../artifacts/software-benchmark-v088/live-monitor-r1/post-window-unit.json)
- [13项固定候选评分核验](../../artifacts/software-benchmark-v088/recovered-score-verification-r1/summary.json)
