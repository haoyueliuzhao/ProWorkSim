# v0.31r2 SWE路径修复：实际GPU补验与筛选启动

快照时间：2026-10-04T23:47:17.466948+08:00。本页为固定启动记录，后续状态见[独立运行报告](software-path-recovery-v031r2.md)；事前边界见[修订协议](software-path-recovery-v031r2-protocol.md)。

## 修订与执行身份

执行源码`2456572481b01a8b6bde9cfd5fd168c35024a830`，冻结工作树`/data1/zhuxinrui/projects/ProWorkSim/runs/v031-path-repair/frozen-source`。CPU绑定已通过；旧Python实现、模型profile、正式六案例及两seed保持原字节。仅新公开note请求明确相对路径并给出schema const，以及一次真实错误反馈纠正上限。

用户要求的GPU4预约从就绪到交接连续持有1467.627889秒，预约未调用模型。2026-10-04T23:42:45.653010+08:00仅释放本任务预约child；立即容量检查通过，没有额外60秒空卡等待。正式worker PID `3229249` 于2026-10-04T23:42:49.605282+08:00在GPU4启动；监督PID `3228904`，最终归档进程PID `3228838`。GPU6原Devstral继续运行。

## 本次真实补验结果

实际补验用时86.456665秒，3次新原生调用均成功，纠正次数为0。首次输出原样为`{"path":"public-note.json"}`，执行器按该参数读取真实文件。旧`/public-note.json`响应和旧整体资格失败保留，不回改。

| 调用 | 实际输入token | 实际输出token | 接口／完整trace |
|---|---:|---:|---|
| read_initial | 569 | 20 | True / True |
| record_fact_8k | 8190 | 38 | True / True |
| missing_file_feedback_10k | 10235 | 38 | True / True |

三条trace在no-grad与grad-mode下的概率重算max/mean误差全部为0，未改变原0.02／0.002门。每条原输出均完整反传，完成3/3；数值检查耗时75.295687秒，actor梯度有限且有2359296个非零元素。新增actor/critic optimizer step均为0；受保护状态一致、optimizer对象复用、最终原common完整恢复和梯度清空均为true。

本次零step阶段峰值allocated为39431449600字节，reserved为41636855808字节。此为本次三条短输出trace的测量，不能替代近16K容量测试。

原v0.31 SWE已真实完成16,362-token压力轨迹、四条概率／反向、一次actor/critic诊断更新、重载和新身份回流；本次按原common、profile、源码及22份记录绑定继承。未重做该约46分钟完整资格。新`inference_ready`、`training_ready`及`common_restored_exactly`均为true；这是路径补验加原数值正证据的组合准入。

## 接续边界与观察

SWE当前已进入`screening`，闭合0 / 12槽，正在原定库存上继续。旧SWE正式筛选为0，因此此处没有补采旧失败业务槽。全部正式筛选零参数更新，不声称诊断通过带来业务成功。

独立Devstral读取时闭合5 / 12槽、成功1槽，正在`screen-0-5`；它的推理、训练集成、近16K容量与common恢复均已通过。这是读取时快照，完整成绩尚待原进程结束。9B原12槽不重跑。

两批各自保留自动结束、资源监控和报告提交推送。r2只写自己的运行报告，不覆盖原v0.31报告，也不在候选未闭合时得出三模型最终选择。此次仍无参数训练收益或分配算法增量结论。完整调用、状态、资源与成本原件在服务器runs，紧凑引用及SHA256见同名JSON。
