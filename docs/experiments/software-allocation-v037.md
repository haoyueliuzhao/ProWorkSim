> **2026-10-08用户指令：暂时取消后续试训，等待审计。** 原队列已结束，未重启；26个后续试训均未开始，正式更新及独立确认未启动。已完成的共同B完整保留（开发5/16）。今后如明确恢复，只能使用物理GPU3、4、5、7。
> 下面原执行报告中的`interrupted`对应正常结束旧队列，不能解读为B训练失败。详见[停止与GPU约束记录](software-allocation-v037-audit-hold-20261008.md)。

# v0.37 原冻结清单的精确加权梯度复用执行

状态：`interrupted`；源码：`ced3eaa293b4dfff59e6ffef83d8f90403ec8bc1`。

复用v036已经闭合的16槽支持和完整冻结清单，不重采P2。若共同B来自原运行，保留原记录并单列旧GPU成本，且不将其计作新反向或新优化器步；其原始逐行梯度未保存，不能据此声称新缓存已填充。每个试训及正式三分支均恢复相同完整common；只复用同一原行、同一精确权重和同一完整状态下的原始反向结果。实际反向次数与缓存应用次数分别记录。开发和确认各4个root×4个seed，原始16槽、失败／unmapped残余及本人分母保持。

| worker | 状态 | actor/critic新增步 | 更新秒 | 实际反向/命中/应用 | 配对面板已知 |
|---|---|---|---:|---|---|
| trial-B | 原v036导入/complete | 1/1 | 92126.64815449715 | None | True |
| trial-G-raw-921acfdd63de71e71598 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-1c36ded15bfba605666d | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-61a57dcdd833a0f95e8b | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-1b2527d8b85a1f3451f1 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-a3cf0f8ee28e58709841 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-5826a7ca1dc6b7f1ce0a | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-0e8b1a607cbf45c4eb79 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-2e807d1b09bbaf5833e6 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-2f7add35a392f411646f | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-a7b672dc8b4b6a8034e5 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-1a14f9218ecf68b59774 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-addb679d01f599ccfaa8 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-2be0eacb41c0b8f450ff | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-869f623bc8b8fd4cad04 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-3d7f27ddf883061d5c78 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-bba6ac427f9bd4699f97 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-155fc024fb85f9b4d170 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-40ce423e9efb6e22ca06 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-92c3ad9b1e5dca6292f0 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-4042c55874b961775f2c | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-8e71b4162e6e9ff95380 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-05bf87f5e770686c6b66 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-4cd3e2a02adf213024a8 | 新v037/not_started | None/None | None | None | None |
| trial-G-raw-9c8e760c27d7bc8b8767 | 新v037/not_started | None/None | None | None | None |
| trial-I-P-921acfdd63de71e71598 | 新v037/not_started | None/None | None | None | None |
| trial-I-P-1c36ded15bfba605666d | 新v037/not_started | None/None | None | None | None |

独立确认逐root（各方法分母4）：

| root | B | G-raw | I-P |
|---|---:|---:|---:|

独立局部平均差：I−B=`None`，I−G-raw=`None`。null表示未测／未闭合，不能填0。

D=16仍是有限机制面板，不保证Contribution精度。未检出方向差不能证明真实C=0；若q仅因先验／覆盖锚而变，不能称为发现高价值经历。正式更新预算相同不等于端到端探测资源相同，G-raw完整方向不删除。

闭合开发／确认目录通过逐文件SHA复核后无损冷归档，原相对路径与字节均可恢复；原始支持材料保持可读。新执行单独声明共享卡准入：空闲至少56GiB、自身占用不超过56GiB、运行期间设备空闲至少6GiB；优先空卡，最多4卡。仅停止本执行自己的worker。64GiB RSS、128GiB产物及20GiB磁盘余量保护保持；缓存等待不受单次反向900秒限制，无累计GPU／worker／统一墙钟上限。
