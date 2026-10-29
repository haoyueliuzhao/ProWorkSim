**Qwen 暂停后的数据留存核验（v090）**

本次已按用户要求暂停四卡 Qwen 队列并保存数据；四个本项目 GPU 驻留均已停止，资源预约已释放。以下为只读留存核验，不修改原实验状态、不重跑模型或评分。具体暂停信号由主代理执行；API 队列不在本核验范围。

最后需收尾的是 slot340、341、345、351。原 slot348 在停止前自然闭合并清理，其后首次派发了 slot351，已计入本次保存范围。四任务均已形成终态，writer 静止、host 模型桥线程结束，actor/controller/专用卷已清理；残留对象和清理错误均为空。

| 槽位 | 条件 | 已知输入＋输出 token | 未决预约 | 终止原因 |
| --- | --- | ---: | ---: | --- |
| 340 | SymPy-19040 REF 10M | 6,098,889 | 59,188 | 用户暂停引发 coordinator cancellation |
| 341 | SymPy-19040 PROJECT 10M | 5,076,338 | 0 | 同上 |
| 345 | SymPy-19040 PROJECT 5M | 2,320,670 | 0 | 暂停前已发生 SDK 参数变换错误 |
| 351 | Xarray-6992 REF 10M | 1,143,175 | 0 | 用户暂停引发 coordinator cancellation |

345 的 `list_files` 未进入受管网关，报错为 `SDK transformed arguments; managed gateway was not invoked`。其 controller 于北京时间 21:38:47 退出，早于 21:42:52 的 manager 停止信号；它使用正常的 `controller_output_transfer` 字段保存原件，而非失败分支字段。因此不能把缺少 `failure_controller_output_transfer` 误判为数据丢失，也不能把该题的接口故障归于本次行政暂停。

四任务的完整 controller 压缩归档均保留，原导出回执已验证完整往返；本次只检查归档存在、大小和结构，未重复解压大文件。四份中间工作树 tar、host 请求派发、已返回用量、manifest 及 final ledger 均保留。合计已知用量 14,639,072 token；slot340 第175次请求没有确定回执，59,188 是未决预约上界，不填为实际消耗或零消耗。

有些终态文件未在停止前生成，必须如实列出：340 没有 `sdk-terminal-state.json`；341 没有 `controller-result.json`、`managed-boundary.json`；351 没有 `controller-result.json`、汇总版 `native-rpc-transcript.json`、`sdk-terminal-state.json`。对应运行期间落盘的会话、逐条原始 RPC、模型记录已归档；PROJECT 的 managed-world/runtime 保存在完整压缩包内。这些记录可用于诊断，但不构成经验证可精确续跑的 checkpoint。

所有中断工作树都标记为诊断材料，`official_final_candidate=false`、`scoring_authorized_by_this_record=false`，没有把未正常闭合的中间代码计入正式正确率。原三项行政停止和345原接口未知继续分别保留，不能改填模型失败。

完整证据：[留存摘要](../../artifacts/software-benchmark-v090/qwen-pause-r1/retention-summary.json)、[逐任务清单](../../artifacts/software-benchmark-v090/qwen-pause-r1/retention-audit.json)、[四驻留原身份](../../artifacts/software-benchmark-v090/qwen-pause-r1/host-readonly-ownership-audit.json)、[精确停止范围](../../artifacts/software-benchmark-v090/qwen-pause-r1/exact-stop-review.json)。[驻留停止回执](../../artifacts/software-benchmark-v090/qwen-pause-r1/resident-stop-result.json)确认 model1/3/4/5 四个用户服务均 inactive、子进程正常退出、四份资源预约已释放，Qwen 不自动重启。随后一次[宿主只读核验](../../artifacts/software-benchmark-v090/qwen-pause-r1/gpu-post-stop-readonly.json)确认四个原 PID 和专属 cgroup 均不存在，显存进程表没有这四个 PID 的记录；未保存或输出他人进程。不据此声称 GPU0/2/4/5 整卡无人使用。
