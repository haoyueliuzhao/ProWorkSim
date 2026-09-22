# 状态归属与重算（v0.4）

| 状态 | 产生／修改者 | 基础或派生 | 保持要求 |
| --- | --- | --- | --- |
| artifacts.versions 的文件身份、哈希、来源 | 文件适配器 CreateVersion | 基础 | 旧版本不可变；缓存由同一字节恢复 |
| artifacts.current_version | CreateVersion | 基础指针 | 不代表任何具体工作的适用性 |
| credential / basis 正文及 attestation | 有权 Confirm 行动 | 基础 | 主张文本或工作簿自填批准字段不能替代签发 |
| role / organization grants | 编译配置（本轮无动态授权委任） | 基础 | 行动输入不能切换绑定身份或扩权 |
| version_readers 与授权记录 | 明确版本授权 | 基础 | 不扩展到其他版本；重放幂等 |
| messages / replies / request bindings | Request / Reply | 基础 | 旧消息不改写；请求状态可由回复推进 |
| 条件历史 | DeclareCondition / Reply / Revise | 基础 | resolved 不等于 superseded，unavailable 不等于 fulfilled |
| 条件当前状态、工作就绪、freshness、按工作适用性 | 由基础记录及当前条件计算 | 派生或带历史的投影 | 可重算；不得独立成为第二份业务真相 |
| work_items requirement 内容及替代关系 | 初始编译 / ReviseRequirement | 基础 | 修订生成新义务，保留旧提交；只影响显式范围 |
| submission 固定版本与原回答 | Submit | 基础 | 后续修改文件不改写已提交内容 |
| review / withdrawal / invalidation | 有权审阅／撤回／修订 | 基础业务事实 | 完成的旧批准保持；当前效力另表述 |
| knowledge/read receipts | Read / 实际输出日志 | 观察记录或其索引 | 不等于相信、采用或正确支持 |
| clock / queued events / event history | 运行器及事件策略 | 基础演化记录 | 相同时刻有明确顺序，事件效果独立于触发它的动作 |
| interactions / transition receipts | 行动运行器 | 基础日志 | 尝试也记录；直接效果与派生效果分开 |
| evaluations / verified_dependencies | 世界外评价器 | 派生证据 | 不回写工作人员产物，不抹去原评价版本 |

派生视图可能缓存到 state，缓存不是可由模型直接写入的对象。重算不能产生新文件版本、阅读收据、批准或工具调用。适用关系以提交固定版本或当前义务为上下文，禁止把历史通过等同当前交付通过。

本轮不建设通用事件溯源数据库：部分带历史的状态投影仍以 JSON 快照保存；重算与保持测试覆盖当前声明的有限关系，不宣称仅凭日志能重建所有外部文件。
