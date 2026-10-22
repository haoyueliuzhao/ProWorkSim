# v055阶段磁盘预约与双卷调度部署说明

本轮目标是使DeepSeek实际生成并发接近CPU资源公式给出的27–30，而不是仅提高配置中的最大值。09:52只读基线显示实际14个生成，目标30，API仅1个请求在途；176核主机尚有CPU／内存余量，新生成主要被磁盘峰值重复预约拦下。基线与阶段观察见[并发性能基线](software-benchmark-v055-concurrency-performance-baseline-r1.md)。

## 实施的调度修改

第一步按可信host发布的环境manifest区分“尚未clone”与“主clone已物化”。主clone已经占用的空间不再全部作为未来增长重复预约；PROJECT未来公开测试clone及工作区余量仍保留。缺少或不可信阶段证据时继续按完整峰值估计，不通过扫描全部活动目录来推算空间。该阶段只改变准入计量，不改变模型、模板、工具、token限制或正在执行回合。10:06:04–10:06:05上线Qwen disk-stage-r3与DeepSeek native-host-r6。

第二步使用真实data1新目录，经项目内新空路径bind为独立工作卷，设备号66307与原data0的66306不同。挂载10:03完成，初始可用约994.9GiB；没有沿用实际指回data0的旧`/data1/zhuxinrui`符号链接。副盘经过唯一MATCH零模型实际clone、SDK程序响应、候选导出与静止清理控制，所有真实API、正式claim、grader调用均为0，见[副盘控制说明](software-benchmark-v055-secondary-volume-control-r1.md)。

10:12:01–10:12:02上线Qwen `proworksim-v054-formal-queue-disk-volumes-r4.service`和DeepSeek `proworksim-v055-deepseek-six-conditions-native-host-r7.service`。两卷分别计入已分配空间和未来增长预约；future DeepSeek generation目录选择secondary，队列状态、共享费用账本及既有回合路径保持原位置。它们不会因为新卷上线而搬动或重放原primary回合。CPU／内存公式与2000元预算仍有效，官方评分继续使用独立异步队列。

两次交接各有intent及launched回执，明确只向旧协调器发信号，未向worker、模型或grader发信号；没有GPU重载、原任务重跑或在途目录迁移。实际启动记录与revision SHA集中归档在`artifacts/software-benchmark-v055/scheduling-deployment-r1/`。完整多MB的state-before仍在本地原处，不复制入此次小型证据归档。

## 截至首五分钟的交付边界

双卷host已部署，副盘路径已通过实际控制，但截至10:15:25–10:20:26首五分钟，**没有secondary正式生成回合，尚未达到27–30实际并发，也没有取得提速结果**。监控看到的只是2–3个既有primary回合继续收口，pending2142未变化。

原因是一个早于本轮双卷交接的共享费用账本hard halt：`provider_usage_exceeded_authorized_request_bound`。审计定位到09:52:16发起的一条PROJECT-thinking请求；发送上限2048，而旧client在usage校验分支中触发越界保护。由于当时没有保存该响应，审计只能依据分支逻辑推断completion计量超过2048，不能恢复确切tokens或确切费用。原未知请求及其预约证据应保留，不能把未测量的数值填成已知，也不能直接抹去hard halt。该问题不是2000元预算耗尽，首五分钟也没有429或新增共因异常。

只读审计原文作为历史时点证据归档于`usage-bound-halt-audit-r1/audit.json`。其中的恢复建议尚未执行字段描述的是该审计时点，不代表后续部署状态。后续独立r8的实际恢复单列如下，未改写这次审计。

首个独立只读监控每60秒采样，CPU上限1核、内存256MiB，原计划一小时上限。首五分钟JSONL／CSV与摘要见[r1监控说明](software-benchmark-v055-multivolume-runtime-monitor-r1.md)。因为费用表的新增补充预约需要新口径，10:44:33停止的仅是这个旧观察器并启动独立r2；r1没有运行满一小时，其先前样本保持。

## 10:44后的实际恢复

旧r7自然收口后，独立费用策略r4保留历史未知请求与原行，再通过补充现金预约覆盖其文档上界；未来请求的现金预约与发送给模型的`max_tokens`分开。有效计量但超过请求输出上限的响应会保留真实费用与协议证据、不给Agent使用，并将该回合归为延期技术异常；绝对模型上界、费用或身份完整性问题仍触发共享hard halt。该修订不是放宽模型输出或总2000元上限，详细迁移和隔离事件说明见[费用策略r4](software-benchmark-v055-budget-policy-r4-and-isolation-incident.md)。

2026-10-22 10:44:15正式启动`proworksim-v055-deepseek-six-conditions-native-host-r8.service`，revision SHA为`c4837307e41735fd8ae9e1b53fe62fb362bedf871e8dd31fa76edca89c011107`，只接续原2142个pending，旧进入槽不重放，GPU重载0。10:44:34只读直接样本显示28个正式生成全部位于secondary设备66307、pending2114，账本halted为null、dispatch_stopped为false。此前无法使用的额外磁盘已开始承载正式工作，并非只完成了部署控制。

10:45:34观测到28个在途、API15个请求在途、无新增异常或429。动态准入目标随共享CPU预留降到25，已在途28个没有被抢停；目标约束后续派发，暂时超过变化后的目标会等待自然收口，不能将目标25误写为当前只有25个任务。既有每任务CPU／内存限制、主机准入门及API64上限保持。

恢复后的独立r2观察器有一小时上限，约11:44自动结束，实际首五分钟10:44:34–10:49:35保持25–28个secondary生成，正常生成闭合增加29、技术未知增加3；真实API请求行增加1269、已结算行增加1262。六组各一份实际controller绑定证据均指向r4费用客户端。独立官方评分端点完成报告增加24，评分未知不变；这些不是独立题数或评分通过数。

首五分钟内出现1次新的API请求输出上限越界局部事件，共享hard halt始终为null，后续派发继续；新增429为0。最低可用内存约911.7GiB、primary空间461.1GiB、secondary空间888.5GiB。完整口径、异常和费用快照见[r2监控记录](software-benchmark-v055-multivolume-runtime-monitor-r2.md)。实际并发相较09:52的14已有提高；短窗口正常生成闭合折算约346.7个／小时，但29个正常闭合全来自REF／MATCH，较慢的PROJECT仍有19个在途，尚未进入本窗口的正常闭合数。加上clone与启动影响，该短窗口不足以宣称三组稳定吞吐都翻倍或直接缩短ETA。一小时观察器继续后台运行。

本说明不报告模型评分，不把代码修复、项目交付和技术未知混成一个指标。调度修改只涉及运行准入与工作目录放置；后续费用完整性修订单独登记。回合内公开测试仍按原单Agent工具语义返回，正式评分继续独立执行。
