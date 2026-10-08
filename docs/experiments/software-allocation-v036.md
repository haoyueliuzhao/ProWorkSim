# v0.36 条件B／G-raw／I-P真实学习与局部确认

状态：`interrupted`；源码：`e26ab99df8e555cd144eef2b38641174addb28d7`。

新16槽支持先闭合，合格后冻结实际完整方向与面板。共同B一次测量真实输入／概率／完整反向与更新成本；其他试训及正式三分支均恢复相同完整common。开发和确认各4个root×4个seed，原始16槽、失败／unmapped残余及本人分母保持。

| worker | 状态 | actor/critic新增步 | 完整材料更新秒 | 配对面板已知 |
|---|---|---|---:|---|
| trial-B | complete | 1/1 | 92126.64815449715 | True |
| trial-G-raw-921acfdd63de71e71598 | not_started | None/None | None | None |
| trial-G-raw-1c36ded15bfba605666d | not_started | None/None | None | None |
| trial-G-raw-61a57dcdd833a0f95e8b | not_started | None/None | None | None |
| trial-G-raw-1b2527d8b85a1f3451f1 | not_started | None/None | None | None |
| trial-G-raw-a3cf0f8ee28e58709841 | not_started | None/None | None | None |
| trial-G-raw-5826a7ca1dc6b7f1ce0a | not_started | None/None | None | None |
| trial-G-raw-0e8b1a607cbf45c4eb79 | not_started | None/None | None | None |
| trial-G-raw-2e807d1b09bbaf5833e6 | not_started | None/None | None | None |
| trial-G-raw-2f7add35a392f411646f | not_started | None/None | None | None |
| trial-G-raw-a7b672dc8b4b6a8034e5 | not_started | None/None | None | None |
| trial-G-raw-1a14f9218ecf68b59774 | not_started | None/None | None | None |
| trial-G-raw-addb679d01f599ccfaa8 | not_started | None/None | None | None |
| trial-G-raw-2be0eacb41c0b8f450ff | not_started | None/None | None | None |
| trial-G-raw-869f623bc8b8fd4cad04 | not_started | None/None | None | None |
| trial-G-raw-3d7f27ddf883061d5c78 | not_started | None/None | None | None |
| trial-G-raw-bba6ac427f9bd4699f97 | not_started | None/None | None | None |
| trial-G-raw-155fc024fb85f9b4d170 | not_started | None/None | None | None |
| trial-G-raw-40ce423e9efb6e22ca06 | not_started | None/None | None | None |
| trial-G-raw-92c3ad9b1e5dca6292f0 | not_started | None/None | None | None |
| trial-G-raw-4042c55874b961775f2c | not_started | None/None | None | None |
| trial-G-raw-8e71b4162e6e9ff95380 | not_started | None/None | None | None |
| trial-G-raw-05bf87f5e770686c6b66 | not_started | None/None | None | None |
| trial-G-raw-4cd3e2a02adf213024a8 | not_started | None/None | None | None |
| trial-G-raw-9c8e760c27d7bc8b8767 | not_started | None/None | None | None |
| trial-I-P-921acfdd63de71e71598 | not_started | None/None | None | None |
| trial-I-P-1c36ded15bfba605666d | not_started | None/None | None | None |

独立确认逐root（各方法分母4）：

| root | B | G-raw | I-P |
|---|---:|---:|---:|

独立局部平均差：I−B=`None`，I−G-raw=`None`。null表示未测／未闭合，不能填0。

D=16仍是有限机制面板，不保证Contribution精度。未检出方向差不能证明真实C=0；若q仅因先验／覆盖锚而变，不能称为发现高价值经历。正式更新预算相同不等于端到端探测资源相同，G-raw完整方向不删除。

闭合开发／确认目录通过逐文件SHA复核后无损冷归档，原相对路径与字节均可恢复；原始支持材料保持可读。单任务、64GiB RSS、128GiB产物及20GiB磁盘余量保护保持，未恢复累计GPU／worker／统一墙钟上限。
