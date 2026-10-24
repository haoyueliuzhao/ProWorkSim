# v056 六项官方评分编码异常修复

## 范围与原因

本次只处理预算梯度实验中六项已完成生成、已锁定候选但未取得官方评分的回合。原候选属于同一 50 题校准面板，模型、任务、预算和 seed 均不更改，不新增模型运行。

旧评分入口把原始 Git patch 强制解码为 UTF-8。Git 默认用是否含 NUL 等启发式判断二进制文件，不能保证文本 hunk 一定是 UTF-8；因此，五项 matplotlib 候选中的测试 PDF、一个 sphinx 候选中的压缩 `objects.inv` 被表示为含非 UTF-8 字节的文本 hunk，评分入口抛出 `UnicodeDecodeError`。错误发生在创建评分容器、运行官方测试之前，不能判为模型修复失败。

六项范围预先由原评分异常记录固定：

| 任务 | 每回合 token 预算 |
| --- | ---: |
| matplotlib__matplotlib-22719 | 200 万、1,000 万 |
| matplotlib__matplotlib-26466 | 200 万、500 万、1,000 万 |
| sphinx-doc__sphinx-8593 | 1,000 万 |

## 修复方法与不变条件

新增独立传输模块，根据原锁定的基线快照和最终快照，针对含非 UTF-8 字节的变更路径生成 Git 二进制 patch。属性设置仅存在于临时 Git 仓库的 `info/attributes`，不进入候选文件。普通文本变更仍保留文本表示。

每项实际候选均须满足以下条件，才允许进入补评：

1. 快照、原补丁及候选锁的哈希与原记录一致。
2. 原补丁应用于基线后，得到原锁定目标 Git tree。
3. 新补丁严格符合 UTF-8，应用于同一基线后，也得到完全相同的目标 Git tree。
4. 文件内容、增加、删除、权限和符号链接均保留；不删测试产物，不用替换字符掩盖非法字节。

新评分器继续使用原 `request.patch` 验证唯一候选，传输表示作为独立字段绑定。新版本、评分身份、run ID、输出和回执与旧评分分开，避免官方缓存复用。官方 harness、镜像、仓库初态、隐藏测试、评分规则和资源限额不变；生成已经结束，评分不向模型反馈。

每个评分容器继续使用 4 核 CPU、16 GiB 内存、1,800 秒测试上限并禁外网；两项并发。单项异常不会取消其余项。特殊非 UTF-8 符号链接目标目前明确拒绝，本次六项不涉及这一情形，不宣称覆盖所有可能的文件编码。

## 验证与结果记录

已完成 12 项必要测试：补丁传输 4 项、新评分请求边界 2 项、结果合并与错误拒绝 6 项，三个对应检查均通过 Ruff。覆盖精确往返、字节与模式保留、错误原补丁拒绝、候选身份不变、旧输出不得复用，以及不得把错误条件或不完整评分回执并入结果。官方补评结果以本次独立回执为准，不提前填写成功率。

原始原因审计见 [audit.json](../../artifacts/software-benchmark-v056/score-encoding-repair-r1/audit.json)。完整实际补丁、快照引用、原/新往返证明及补评输出保存在 `runs/software-benchmark-v056/score-encoding-repair-r1/`。原生成结果及旧评分失败证据保持可追溯。


## 实际补评结果

北京时间 2026-10-24 17:31 启动，17:34 完成六项补评及结果合并。六项均取得明确官方报告：**3 项 resolved、3 项 unresolved**。unresolved 是官方测试未通过，不再属于评分编码技术未知。

| 任务 | 预算 | 官方结果 |
| --- | ---: | --- |
| matplotlib__matplotlib-22719 | 200 万 | resolved |
| matplotlib__matplotlib-22719 | 1,000 万 | resolved |
| sphinx-doc__sphinx-8593 | 1,000 万 | resolved |
| matplotlib__matplotlib-26466 | 200 万 | unresolved |
| matplotlib__matplotlib-26466 | 500 万 | unresolved |
| matplotlib__matplotlib-26466 | 1,000 万 | unresolved |

六个原补丁与六个新表示均通过实际基线应用后的目标树同值验证；六个评分回执都附有容器已清理的静止证明。新增模型调用、模型 token、GPU 驻留均为 0。

汇总由 180 个正式评分更新为 **186/200**，已知 resolved 由 69 增为 **72**，已知 unresolved 为 **114**；另外 **14 项生成技术未知**仍保持原记录。本轮仅消除了六项评分编码异常，没有恢复或重新生成那 14 项，也不能把它们当作模型失败。

| 预算 | 正式评分 / 计划 | 已知 resolved | 生成技术未知 |
| --- | ---: | ---: | ---: |
| 50 万 | 50/50 | 12 | 0 |
| 200 万 | 48/50 | 21 | 2 |
| 500 万 | 44/50 | 19 | 6 |
| 1,000 万 | 44/50 | 20 | 6 |

这些是仓库分层 50 题校准面板的当前计数，不是完整 SWE-bench Verified 500 题分数；预算效果仍需按题配对并保留未知范围。

合并时只更新白名单六项的评分状态；对全体 200 项的任务身份及生成记录逐项比较，均未改变，另外 194 项整行未改。旧评分字段、异常事件、旧分析和原始快照保留；已解决评分异常从当前待处理集合移至历史已解决集合。`analysis_finalization`仍是原队列结束时的历史记录；补评后最新分析位于本次 `analysis-r2`，并由`score_recoveries`索引。

逐项结果与不可变回执见 [results.json](../../artifacts/software-benchmark-v056/score-encoding-repair-r1/results.json)，更新后的预算摘要见 [budget-summary-after-repair.json](../../artifacts/software-benchmark-v056/score-encoding-repair-r1/budget-summary-after-repair.json)。
