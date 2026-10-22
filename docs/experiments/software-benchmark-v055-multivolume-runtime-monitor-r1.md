# v055双卷上线后的限时只读监测

独立USER服务`proworksim-v055-runtime-monitor-r7-r1.service`于2026-10-22T10:15:25.320823+08:00开始采样，每60秒一次，脚本满3600秒自动结束，systemd另设3700秒兜底。限额CPUQuota100%（最多1核）、MemoryMax256MiB、Nice10、IOWeight10；部署时服务确为active/running。监控只读队列metadata、SQLite的mode=ro/query_only汇总、systemd状态与CPU／内存／两卷空间，不调用API、不派发job、不读评分值或模型正文。

## 首五分钟的实际结果

观察窗口2026-10-22T10:15:25.320823+08:00至2026-10-22T10:20:26.096436+08:00，共6点、300.8秒。尚未达到27–30个生成回合：实际仅2–3个原primary回合，secondary新增执行为0，目标仍为[27, 28, 30]。期间pending变化0，正常生成闭合变化1，技术未知变化0。

直接阻塞是先前已触发的全局账本门`provider_usage_exceeded_authorized_request_bound`，`dispatch_stopped`保持true；不是本次副盘容量不足、429或预算2000元耗尽。监控没有解除或绕过此门。API在途峰值0，新增429为0，新增异常原因计数为{}。两卷设备仍为66306／66307，最低free分别为465025216512与1068149768192字节。

因此不能把这段被完整阻塞的窗口与09:52基线14个并发、160–166终态／小时直接比较，更不能称已经稳定提速或据此缩短正式ETA。需要在用完整证据处理授权请求bound异常、正式恢复派发后，使用后续样本观察真实并发和吞吐。监控仍按原一小时上限继续运行，后续修订不需要为它重载模型或重跑任务。

首五分钟JSONL／CSV、汇总和部署回执归档于`artifacts/software-benchmark-v055/runtime-monitor-r7-r1/`；完整实时输出位于`runs/software-benchmark-v055/runtime-monitor-r7-r1/`，结束后将写`finished.json`。后续样本属于之后的时间，未预先填作已取得结果。


## 后续账本迁移时的监控口径

r1运行源码继续保持不变。若后续r4账本迁移引入`budget_adjustments`补充预约，r1的`committed_conservative_cny`仅来自requests，将缺少这部分新增hold；迁移后的该字段不得作为完整预算结论。r1已有时间窗口在迁移之前，没有事后改写。

独立r2监控脚本在同一个只读SQLite事务中汇总requests与`budget_adjustments.amount_nanoyuan`，直接读取metadata policy、halted及cooldown，不依赖旧state里的预算缓存；旧表尚未迁移时明确标记not_migrated_to_r4。r2还逐次记录新增任务异常和API失败的slot／reason／http_status等安全字段，不读取响应正文。

2026-10-22 10:44:33，r8正式恢复原pending槽后，r1只读监控被停止并切换到r2，因此r1没有按原计划运行满一小时；历史采样保留，没有补造`finished.json`。新观察器的独立一小时上限及恢复窗口见[r2监控记录](software-benchmark-v055-multivolume-runtime-monitor-r2.md)。切换只向旧观察器发停止信号，没有停止实验worker、模型或评分器。
