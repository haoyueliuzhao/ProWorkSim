# v203.2.1 r4：原始归档中的 SDK 主轨迹补分析

本目录记录对已经结束的 2032201（django__django-11095）的只读补分析。没有重跑模型、工具或任务，没有修改 r2 analyzer、原 measurement、原归档或准入条件。仍在运行的另一题不属于本次取证范围。

## 根因

原 `extract_controller_output` 对 PROJECT 模式明确将 managed-runtime 和 managed-world 保存为 archive_only，不在 controller-output 目录展开。r2 analyzer 只查找磁盘上的 experience.jsonl，没有读取原始 controller-output.tar.zst 中对应成员，所以未取得 SDK 主轨迹。

这产生两个分析结果：85 个 agent 请求缺少 SDK decision-link；没有完整 decision/response 的 staff_done/staff_wait 等控制 outcome 无法独立覆盖全部回执，导致 tool_receipts 的 closed 判定为 false。旧测量仍有 90/90 请求原始字节及响应匹配，差异不来自原请求或旁路日志丢失。

## 修订

新文件 `tools/analyze_passive_capture_v203_2_1_r4.py` 保持原函数签名、分维度完整性要求与严格成员视图。若没有展开的 SDK 主轨迹，按以下链读取原件：host result 的 controller_output_transfer 引用 → 原 transfer 文件 → 归档存储与原传输信息 → 精确压缩 blob → 完整解压原流 → `output/managed-runtime/experience.jsonl`。

必须同时满足 controller_result 引用、host_prefix 归属、压缩大小与 SHA-256、传输与存储对解压原流摘要的一致性、完整解压大小与 SHA-256。仅读取目标成员；不把其他成员解压到 controller 目录，也不修改 archive-only 原件。临时缓冲超过 1 MiB 后落在自动关闭的临时文件中。zstd 只使用仓库既有且按 manifest 核验的普通用户 codec，不修改系统或安装依赖。

SDK decision/response 和工具回执的匹配逻辑及必须具备的来源数量保持原条件；新增的是读取原本已保留但未展开的主证据入口，不是将未知字段补成假定值。重复、缺失或错误身份的归档成员仍不能获得 COMPLETE。

## 2032201 的实际结果

独立输出为 `2032201-measurement.json`，schema 为 `passive-capture-analysis-v203.2.1-r4`。

- 完整性 COMPLETE，9 个维度均 COMPLETE。
- 90 次主请求与物理请求/响应、sidecar 和主 ledger 关联；85 个 agent 决策身份有原 SDK 主来源，其余 5 次为 condenser 请求，不伪造 agent decision。
- 86 次主执行机会与 sidecar 完全一致，主动作回执对账成立，主 runtime trace 闭合。
- 压缩归档 46,078,292 字节；完整解压流 1,441,382,912 字节，SHA-256 为 `0518ad1fec7e349ccfcba37dd4fbae7f31148a6ffea302ddcf3f927ba174c04f`。
- SDK 原成员 134,188,042 字节，SHA-256 为 `67a0754979569f96707a973a5ff1b274210291c2bdc6543cb8ae83a09fa44077`。
- 这次离线命令约 5.65 秒，无新模型请求或世界动作。

完整来源及原件哈希在输出的 source_files 内；原 r2 measurement 仍保留 PARTIAL。是否继续队列应由父流程依照原冻结条件，结合首两题全部已完成材料独立生成准入结论，本文件不改动队列或 gate。

## 必要 CPU 控制

`tests/test_passive_capture_archive_v203_2_1_r4.py` 共 7 项通过，0.29 秒。测试使用临时目录及 gzip 小归档：合法归档补齐关联、目标成员缺失、重复成员、SDK 响应归属错误、压缩 blob 改变、完整原流摘要不一致、错误 controller 归属。所有拒绝案例都不能得到 COMPLETE，也不会凭空填入 decision_id；合法案例分析前后原件哈希一致，controller 目录没有新增展开的 trace 文件。

该验证证明这道既有任务的捕获关联可从保留证据恢复，不证明自然依赖识别、组织失配判定或组织干预收益。
