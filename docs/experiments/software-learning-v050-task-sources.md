# v050 新开发材料、用途登记与有限 CPU 合同控制

日期：2026-10-13（Asia/Shanghai）。本文件只报告材料准备和 CPU 程序控制，不报告模型能力、学习收益或组成干预收益。

v050 保留 LA/LB 的原 v045 业务字节及 DA/DB 的原 v049 业务字节，另在本轮新采集、方向选择和任何新开发模型结果产生前，冻结 DC/DD 两项人工业务合同。用户提供的审计明确指出这两项材料原先尚不存在；这里是按该建议新编写的材料，并非复用了附件中已经核实的任务。附件外链所称 JSON/ZIP 未取得，不将本地新清单冒称为外链原件。

“中等工作量”是基于多个相互作用的公开约束作出的事前设计判断；没有先跑模型筛题，也没有关于难度或打破成绩天花板的实测证据。两新 root、两旧开发 root 都是人工政策开发材料，不属于独立确认或外部基准。

## 1. 六根来源与新窗口用途

| 标签 | 业务根 | 用途 | 材料关系 |
|---|---|---|---|
| LA | `sc-event-utc-boundary-la-v045` | 本轮训练采集 | 原 v045 合同、starter、测试、来源指纹精确复用 |
| LB | `sc-rule-range-local-lb-v045` | 本轮训练采集 | 原 v045 合同、starter、测试、来源指纹精确复用 |
| DA | `sc-credit-apportionment-da-v049` | 开发 | 原 v049 人工整数分币家族精确复用 |
| DB | `sc-dependency-batches-db-v049` | 开发 | 原 v049 人工依赖分批家族精确复用 |
| DC | `sc-inventory-reservations-dc-v050` | 开发 | 新编写的原子库存预留事务家族 |
| DD | `sc-snapshot-text-patches-dd-v050` | 开发 | 新编写的原始坐标文本补丁家族 |

LA/LB 仅获得 `v050-o1-learning-window-01` 新记录的训练登记。原 v049 3/3 八槽、历史开发轨迹、DA/DB/DC/DD 开发记录均不因此成为新的训练材料。开发四根的 training/contribution/independent-confirmation eligibility 均为 false。

六根路由实现在 [software_organization_tasks_v050.py](../../src/proworksim/software_organization_tasks_v050.py)。其 `files`、`root_goal`、`initial_binding`、`editable_paths`、原来源 manifest/partition/requirements 指纹均精确保留原四根值，新的用途登记另存 `v050_source_*` 字段。无旧模块或原业务资产被修改。

新 DC/DD 来源提供器是 [software_learning_sources_v050.py](../../src/proworksim/software_learning_sources_v050.py)。它只接纳这两个新 ID，复用通用 isolated Python sandbox、原 API driver、严格 JSON 比较和软件世界接口。独立的来源和窗口清单如下：

| 清单 | SHA-256 |
|---|---|
| [新两根源 manifest](../../examples/software-learning-v050/source-manifest.json) | `d62444491f3d8ad825e39b90bd3b480fb5a5a4caa786686998bff9a765543945` |
| [新两根用途 partition](../../examples/software-learning-v050/source-partition.json) | `5b573d87cc24794647e410736ff6af434eb26565698ca6fb7861ee5d440fb87e` |
| [六根窗口 manifest](../../examples/software-learning-v050/window-source-manifest.json) | `b4a6326b46c8329ed9e3d49f1adef0ff99a4ed13dc7699893f59e6aae486043a` |
| [六根窗口 partition](../../examples/software-learning-v050/window-source-partition.json) | `6dd8d7baead1a48806cbce7cbe178268a6383d4e2804c999e32f873da9c2e093` |

材料作者上下文提交为 `542bcea493c6f7fcbf0b8256994ec70b5de06f4e`，这只是编辑前仓库上下文，不等同于新材料已在该旧提交中存在。新文件字节由本轮 manifest 冻结。新材料不从 LA/LB 训练实现或测试派生；共享的只有执行基础设施。

## 2. DC：原子库存预留事务

完整公开合同：[DC contract.md](../../examples/software-learning-v050/sc-inventory-reservations-dc-v050/contract.md)。生产 API 是 `inventory.transact(stock, operations)`；标准库范围内完成有界多 SKU 库存、预留与取消。

合同同时要求：

- 严格对象字段、ASCII 名称、整数而非 bool、容量边界；一次验证整批 schema 后才执行业务状态转换。
- 同一预留中允许重复 SKU，按精确整数聚合；不足、活动 ID 重复或取消非活动 ID 统一为业务冲突。
- 取消完整返还全部数量并删除活动预留；取消后同 ID 可重新使用。
- 成功和失败都不修改输入及嵌套对象；结果列出全部初始 SKU 和仍活动预留，并按明确键排序。
- 后部 schema 错误优先于前部业务冲突，失败无部分结果。

starter 保留可运行 API 与部分正确输入验证，但有四项彼此可分的缺陷：重复 SKU 只留末值、取消不返还库存、没有拒绝活动 ID 重用、逐操作验证导致验证优先级错误。这不是单一一行缺陷的复制任务。

来源冻结 seed 为 `202610130605/606`；本轮宿主计划先手为 `member_001`。seed 和先手不影响业务合同或验收预期。源清单固定两个完整参考反例：`last_quantity_wins` 和 `cancel_without_return`；它们分别只破坏聚合与取消返还，在参考实现其余行为保持时仍须失败。

## 3. DD：原始坐标文本补丁

完整公开合同：[DD contract.md](../../examples/software-learning-v050/sc-snapshot-text-patches-dd-v050/contract.md)。生产 API 是 `textpatch.apply_batch(document, patches)`，处理有界 Unicode 字符串的一次同时修改。

合同同时要求：

- start/end 为原文 Unicode 码点坐标，严格类型、边界、唯一 ID 和固定字段。
- 先验证整批结构，再验证原文 expected，最后判几何冲突；分别使用 `patch:invalid/stale/conflict`。
- 非空半开区间内部重叠是冲突；插入点在非空区间内部是冲突，而邻接区间和边界插入合法。
- 同点多插入按 ID 升序；位于边界的插入在前一区间替换之后、后一区间替换之前。
- 全批同时针对原文应用，结果不依赖输入补丁顺序；删除、空文档和空操作合法，Unicode 与换行不规范化，输入不变。

starter 提供了可运行的验证辅助函数，却在已修改文本上逐项验证并应用，因而没有实现整批原坐标语义、跨补丁冲突及 ID 检查、确定性同点顺序与整批验证优先级。修订必须把验证、冲突、排序和输出构造衔接为同一合同。

来源冻结 seed 为 `202610130607/608`；本轮宿主计划先手为 `member_002`。两个语义反例为 `reverse_insert_id` 和 `allow_interior_insert`，分别违反共点排序和内部插入冲突。

## 4. 可见材料与私有验收边界

每个新 root 有 8 条公开检查、16 条私有同合同输入。请求和期望表在参考解执行前手写；没有执行参考解来生成期望。每个 root 同时保存 starter、参考解、两份语义反例、初始作者来源说明、公共检查、私有验收、诊断分组与完整逐文件 SHA。

模型成员只获得合同、生产 starter、公共 test_visible.py 和空的可选 test_member.py。参考解、私有验收、反例、manifest 与初始作者缺陷说明不进入成员工作区。没有预定义执行任务、初始所有者、强制责任或协作验收条件。正式交付仍走原固定成果与同树公共测试机制。

8 条公共检查机械分成两个互斥且完整的诊断组。每组的初始真测均为 2 通过、2 失败；初态准备不算模型调用、当前成员自主发现或团队 run_tests 消耗。初始诊断只披露同一公开合同中的真实请求、值与观察，不给修复分工。

私有验收只是公开合同的不同输入，未新增私有需求。“upstream_regressions”沿用旧线协议字段名，实际只指保留的人工 API 公共检查，不声称存在外部 upstream 缺陷或测试套件。

## 5. 有限 CPU 结果及计量

必要控制见 [test_software_learning_sources_v050.py](../../tests/test_software_learning_sources_v050.py)，机器汇总见 [source-controls.json](software-learning-v050-source-controls.json)。来源合同在这些执行中没有调整。

| root | starter 公共 | reference 公共 | reference 私有 | 反例私有拒绝 |
|---|---:|---:|---:|---|
| DC | 4/8，通过 API 基本保持 | 8/8 | 16/16 | 聚合反例 2 条；取消反例 2 条 |
| DD | 4/8，通过 API 基本保持 | 8/8 | 16/16 | 同点排序反例 1 条；内部插入反例 1 条 |

两 root CPU 业务程序共 **18 次**：普通公共 driver 8、私有 driver 6、初始分组 driver 4。sandbox 区间累计约 **2.139 秒**；这是两根并行程序区间之和，不是整个准备任务墙钟时间。模型、tokenizer、GPU 调用均为 0。

15 项不同来源控制最终全部通过，定向 Ruff 通过。第一轮 pytest 产生全部业务回执，但交互工具只保存了早期进度，末端测试回执未取回。随后按同 source-manifest 严格绑定复用了这批回执，完成 15/15 断言及 JUnit 记录，**没有重执行业务程序**；这不是另一次独立复制，也不应把程序数加倍。原终端信息不足与最终明确通过分开记录在 JSON 中。

上述有限控制证实参考实现与固定输入一致、starter 确实未满足全部合同、四个特定语义缺陷被验收拒绝、来源和可见范围受控。它不构成穷尽正确性证明，不测模型难度，不保证 DC/DD 不会饱和，更不产生学习收益证据。没有因为模型表现而修改 root、合同、期望、反例或 seed。
