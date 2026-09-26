# v0.15 模型资产获取快照

快照：2026-09-26T23:23:11.053675+08:00。下载与模型实验仍在运行，本记录不是最终完成报告。

| 检查点 | 此刻资产状态 |
|---|---|
| Qwen3.5-9B | 16文件、19,329,393,661 bytes已完整；4/4权重shard实际SHA与冻结官方HF身份匹配。 |
| Qwen3.8-27B | 22,131,515,576 bytes已有完整range SHA；4/18整shard通过官方完整SHA；还需33,431,491,200 weight bytes。 |

最近5分钟range封口速率6.28MiB/s，按这一窗口估计剩余约1.41小时。该估计不保证：32MiB提交成批，在途数据未计，速率会波动，最终整文件hash与模型加载另需时间。未经完整manifest确认，不能将27B标为已入场模型。

当前使用官方ModelScope.cn，先核对镜像元数据与冻结HF LFS SHA，再验证实际range及整文件。HF初始失败日志保留；后续curl已取得首MiB成功。ModelScope.ai早先500用了.cn revision，不能据此判断国际站不可用；改用自身revision后可用，但有界测速没有显示更快持续吞吐。各试源路径、结果及证据文件汇总在[JSON快照](v015-model-acquisition-status.json)。

9B完成后，仅停止并等待本人27B旧下载退出，再以durable journal恢复；当前PID3149741为8文件×8连接。新增8／16连接的24个首MiB探测中23成功、1失败，全机总RX仅比基线增加约1.8%／3.1%，故维持64连接。主下载器不记录中间重试，不能把这24次探测成功率当成整体失败率或声称零失败。

资产SHA准入、聊天接口、工作能力及在线训练是不同证据。9B停止协议修订见[独立说明](../design/candidate-chat-stop-v0151.md)；完整9B manifest见[v015-qwen35-weights-manifest.json](v015-qwen35-weights-manifest.json)。
