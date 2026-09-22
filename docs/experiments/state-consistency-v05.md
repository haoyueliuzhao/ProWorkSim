# v0.5 内核状态一致性与有界恢复：实验报告

日期：2026-09-22。依据：[本轮审计](../reference/state-consistency-audit.md)。实现规格见 [状态一致性设计](../state-consistency-v05.md)、[核心语义](../../CORE_SEMANTICS.md)、[状态归属](../../STATE_OWNERSHIP.md)、[行动合同](../../ACTION_CONTRACTS.md)。

本轮完成 K1 精确阶段回执、K2 两个纯投影、K3 单写者有限恢复，并运行 E1–E5。**247 项代码回归通过；五组正式实验均达到预先限定的验收条件；原十情境回归也通过。**以下分开报告代码检查、缓存变体、跨模板比较、状态探索、恢复切点和变异负对照，不合成一个“总成功率”。

全轮没有模型调用、GPU 使用或参数训练。保留经营模板与文稿微模板，没有新增行业，也未重新采样旧 API 失败案例。本报告支持的是声明范围内的内在一致性，不是专业质量、模型能力提升或任意故障保证。

## 1. 冻结版本与证据范围

正式实验均使用：

```text
commit: fe80b02a69df7cfe8eabf4a62cce2031c4e3035c
source_tree_sha256: 24719e3b38b4bb6d4413db5cbf7f7270ed73b82f0f38752401d5e9d96668347c
schema: 0.5
operating contract/evaluator: operating-world-v0.5
receipt: phase-deltas-v0.5
semantics: work-world-v0.5
```

六组正式任务开始／结束均记录同一提交、`code_dirty=false` 和相同源码摘要。源码摘要覆盖 `src/**/*.py` 的相对路径与字节；各实验还记录脚本摘要。报告归档提交不回填成实验条件。

代码回归命令为 `.venv/bin/python -m pytest -q`，结果 **247 passed in 38.12s**；Ruff 通过。此时间仅是该次本机运行记录，不是性能比较。正式实验作为独立任务并行启动；E1、E2、E4、E5 和原机制套件各用 4 workers，E3 按确定性 BFS 探索。

| 实验 | 正式范围 | 结果 | 精简证据 |
| --- | --- | --- | --- |
| E1 缓存无关性 | 2 模板 × 6 检查点 × 4 缓存条件 | 48/48 变体，288/288 检查；未执行 0 | [v05-projections.json](v05-projections.json) |
| E2 适配器符合性 | 2 条抽象轨迹 × 2 模板 | 4/4 世界，11/11 比较标记；含局部和范围 fixture 共 31/31 检查 | [v05-conformance.json](v05-conformance.json) |
| E3 有界参考状态机 | 2 角色、2 工作、2 产物、最多 3 版、长度 ≤4 | 446 状态、5139 次转移尝试，未发现反例 | [v05-bounded-states.json](v05-bounded-states.json) |
| E4 进程中断恢复 | 4 类动作／事件、10 个进程终止切点，4 个对照 | 10/10 切点，60/60 检查 | [v05-recovery.json](v05-recovery.json) |
| E4 补充异常探针 | 事件保存后普通确认异常 | 单列 1 例、4/4 检查 | 同上 |
| E5 验收负对照 | 7 个预注册语义变异，逐项独立进程 | 7 对照通过，7 个指定断言触发；存活 0、夹具异常 0 | [v05-mutations.json](v05-mutations.json) |
| 原机制回归 | 原 10 类有限情境 | 10/10 机制、56/56 检查；8 业务完成、1 规格拒绝、1 合理阻塞 | [v05-world-regression.json](v05-world-regression.json) |

这些分母有重叠与不同含义；同种子、模板、检查点副本不构成独立统计样本。

## 2. 修订前刻画与实现变化

修订前证据见 [v05-before.json](v05-before.json)，分为两个版本层次。

### 2.1 隔离旧提交的接口刻画

在隔离的 `git archive d1d53e6` 中加载原始代码，没有拿开发树冒充旧实现：

- `Apply` 将 `view: 0→1`、`Derive` 不执行修改时，旧回执仍是 `direct_changes=[]`、`derived_changes=[["view"]]`。它确实表示字段区域的净变化，没有记录真正的阶段差分；未声称因此发生过错误批准。
- 真实 `World.act` 对相同 request_key 先调用 `calculate("1+1")`，再调用 `calculate("9+9")`，第二次静默返回第一次的 2.0。v0.5 为操作身份加入完整有限 JSON 负载摘要，不同负载显式冲突。

### 2.2 新回执与提交边界

新回执把实际阶段与字段区域分开：

| 字段 | 计算对象 |
| --- | --- |
| apply_delta | before → after_apply |
| derive_delta | after_apply → after_derive |
| net_delta | before → after_derive |
| primary_region_changes | 上述净变化中属于基础区域的路径 |
| projection_region_changes | 上述净变化中属于投影区域的路径 |
| preflight_projection_delta | 执行前内存缓存重建的单独差分 |

差分是路径列表与状态摘要，不是包含所有旧值／新值的完整 patch。逻辑时间、交互日志、排程和 journal 记账随后由运行器处理；`after_derive` 不是整个操作最终 `state.json` 的哈希。未完成阶段记录 null、failed_phase 和 attempted_delta，不把中途异常说成阶段“没有变化”。

命令和环境事件分别登记身份、绑定主体、完整请求摘要、前置 revision、语义版本、结果及已提交 revision。状态和登记同时原子保存。命令成功之后发生的事件失败不改判为命令未提交；失败事件保留，已提交事件的确认异常单列为 event_delivery_errors。

## 3. E1：指定派生视图与旧缓存无关

原始目录：`runs/state-projection-v05/`。seed907。两个模板各取得 6 个已经支持的真实检查点：initial、pending_reply、in_review、withdrawn、revised、late_reply。

对每个检查点复制出正常缓存、删除缓存、错误缓存和重复重建 4 个条件。**只操作预先声明的缓存路径**：work 状态摘要字段、condition 状态摘要字段、兼容 blockers、condition_responses。不删除提交、需求、版本指针、批准、原始回应或历史观察，也未声称清除所有可能存在的缓存。

每个变体检查六件事：纯查询不修改状态；重建后的两个视图相同；基础事实不变；文件字节不变；真实角色观察相同；再次重建幂等。**48 变体、288 检查全部通过，未执行数为 0。**

条件真源为定义、绑定／撤除／接收等事件，以及 `raw_condition_responses`。接收记录固定当时的相关事实，重建时重新匹配；不是把 PASS/FAIL 缓存重新当作答案。兼容 blocker 单向生成，不反过来决定条件状态。

工作视图区分当前实例、前驱、未满足条件、真实 pending 提交、提交版本是否当前及可执行动作。公开使能再按角色过滤。已获正式批准但独立质量错误的历史决定不会因重算被删除。

证据支持指定视图的检查点重建与缓存无关性，不支持从任意残缺历史日志重建所有世界对象。

## 4. E2：共同制度关系在两个真实适配器间一致

原始目录：`runs/adapter-conformance-v05/`。seed907。

两条轨迹分别经经营和文稿的真实工具入口执行：

1. 初始 ConfirmGrant → Submit1 → Withdraw → Submit2 → Approve，共 5 个比较标记。
2. 初始 ConfirmGrant → OldRequest → ReviseLateReply → NewReply → Submit → Approve，共 6 个比较标记。

初始 ConfirmGrant 是编译器实际签发／授权的 bootstrap 事实，不冒充工作人员运行过 Confirm 工具。经营回信自动延迟，文稿由明确编辑者回复；因此第二条在预声明的 `ReviseLateReply` 宏边界比较，不偷偷移动事件时间。

比较的是凭据授权、条件满足、当前义务、撤回／批准及历史保持。身份与对象按预声明别名映射，不比较两个领域的文件字节或质量尺度。运输标签 `outdated_reply` 与 `delivered` 原样留在原始状态；共同投影使用“回复是否已记录”和“请求是否指向当前义务”，不把两个枚举偷偷改成同值。

**4 个真实世界全部完成预期轨迹，11/11 标记一致；另有每世界 4 项局部检查共 16 项。**独立设置的 A/B 范围授权组件 fixture 有 4 项检查：A 可确认、B 被拒、B 不产生确认副作用、A 事实保持。合计 31/31；这个 fixture 不是额外的适配器世界。

实际后果包括：撤回后原提交继续为 withdrawn；新提交另获批准。旧请求在修订后不满足新义务、不开放新凭据；当前请求才获得所需授权。两个模板实际调用次数不同，不要求动作数相同。

## 5. E3：有界系统探索与独立参考

原始目录：`runs/bounded-state-v05/`。范围为内存共享规则层，不含文件系统和工具适配器端到端。

固定 2 个角色 owner/reviewer、2 个工作 A→B、2 个产物，每项工作／产物最多 3 版，最长序列 4。两个起始状态是 clear 和 waiting_for_evidence。探索 submit、withdraw、approve、revise、reply、edit 以及错角色、旧工作、错版本、错证据、缺前驱等邻近变体。请求在起始夹具中明确登记；新请求创建不在本组范围。edit 是显式环境版本元数据输入，不是文件写入实验。

参考模型使用独立 ledger／tuple 表示，不调用被测 current_id、approve_submission、match_response 或 derive 计算预期。回归还检查了禁止参考路径调用 UUT，以及向被测实现注入错角色行为时能返回最短反例。

| 深度 | 访问状态 | 展开状态 | 尝试转移 |
| --- | ---: | ---: | ---: |
| 0 | 2 | 2 | 58 |
| 1 | 11 | 11 | 340 |
| 2 | 39 | 39 | 1229 |
| 3 | 110 | 110 | 3512 |
| 4 | 284 | 0 | 0 |
| 合计 | 446 | 162 | 5139 |

**冻结范围内无反例，shortest_counterexample=null。**5139 次尝试中，914 次许可／幂等无新增效果，738 次回复没有满足条件，3487 次规则拒绝。回复未满足与工具规则拒绝分别记录。

规则拒绝分布为：权限 1270、未知版本 95、非待审 914、前驱缺失 564、动作不使能 279、旧工作 357、过时产物 8。110 个状态达到工作版本边界，93 个达到产物版本边界；两者可重叠，不能相加当截断状态总数。

BFS 去重后覆盖的是可达状态代表及深度边界以内的全部生成出边；不是全部历史路径，也没有扩到长度 6，更不是无限状态证明。

## 6. E4：真实进程终止后的有限恢复

原始目录：`runs/bounded-recovery-v05/`。seed823。每个动作族先生成一个真实检查点，逐字节复制到一个不中断对照和相应故障目录。新动作使用固定 command key。每个目录只有一个写者。

| 类别 | 预先定义的切点 | 结果 |
| --- | --- | --- |
| JSON 文件创建 | version_staged；after_apply；after_command_commit | 3/3 |
| Submit | after_apply；after_command_commit | 2/2 |
| Reply 环境事件 | before_event_commit；after_event_commit | 2/2 |
| 批准依据修订 | version_staged；after_apply；after_command_commit | 3/3 |

故障子进程在切点执行 **os._exit(73)**，不运行 finally 或内存回滚。每例确认实际退出码和切点标记，再用新 World 从磁盘恢复、重试相同命令、完成必要的待审事件。

每例 6 项检查：切点真正到达、提交前缀连续、状态与不中断对照一致、所有正式版本及当前镜像字节一致、命令公开结果一致、再次重试不产生正式效果。**10/10 切点、60/60 检查通过。**

状态比较保留身份、基础事实、投影、journal／结果和实际观察，仅递归排除 `wall_seconds` 与诊断性 `state_digests`。所有不可变版本、当前镜像的字节哈希仍比较。没有按“最终 complete 一样”代替状态比较。

文件写入组的共同检查点包含真实 `=1/0` 错误公式；恢复不重算或修正历史文件。未提交暂存版本被隔离，不计正式版本；状态引用的正式文件仍存在并符合哈希。

对 19 个目录（4 检查点、4 对照、10 恢复世界、1 补充探针）作了额外只读文件／状态核对，未实例化 World 或再次执行动作，正式版本和镜像均相符。切点前的完整内存快照并未单独保存；原运行记录了重新打开前的 committed revision，不能把后续核对说成独立重审了不存在的内存快照。

### 6.1 十个进程切点没有掩盖普通异常反例

开发期十个 os._exit 切点已经通过时，审查另发现新协议的一处实现缺陷：事件保存完成后，确认 hook 抛 ValueError，旧 except 分支仍用提交前 state 恢复文件，误将已正式提交的 basis/v3、scope/v2 隔离。磁盘 state 仍引用它们，重新打开世界得到 FileNotFoundError。

该反例来自**未冻结的 v0.5 开发实现**，不是 `d1d53e6` 的旧回执问题；原世界和报告保存在 `runs/event-commit-exception-v05-before/` 并归档于 [v05-before.json](v05-before.json)。

修复区分提交前失败与提交后确认失败。后者重新读取已提交前缀，记录 `event_committed=true` 与 event_delivery_errors，不回滚旧文件。正式 E4 另预注册一例普通 ValueError 探针，**4/4 检查通过**：命令已提交、事件被正确标成已提交、文件可重新打开、相同命令重试保持正式效果。它单列于原 10 个切点之外，没有把原分母改成 11 个进程中断。

以上只支持单世界、单写者、当前文件系统、声明工具与切点。不证明断电持久性、机器丢失、跨机器共识、任意插件副作用或任意并发的恰好一次。

## 7. E5：验收对指定错误实现敏感

原始目录：`runs/semantic-mutants-v05/`。7 个变异与必须失败的具名断言在运行前登记；每个正常对照和变异各在独立新子进程中运行，共 14 次执行，不修改仓库源文件。

| 指定变异 | 检查对象 |
| --- | --- |
| 授权 v2 时一并授权 v3 | 精确版本访问 |
| 回复额外解除另一工作条件 | 局部性 |
| 用全局最新替代上下文适用性 | 指定工作与凭据关系 |
| 批准时忽略当前前驱 | 行动使能 |
| 重复事件额外追加正式批准提交 | 重放不能产生第二次正式效果 |
| Derive 修改基础事实 | 投影所有权 |
| 修订改写旧 submission.answer | 历史保持 |

**7/7 正常对照通过；7/7 变异实际激活且触发预注册断言；存活 0、夹具异常 0。**没有把导入错误、语法错误或一般测试异常计为检出。

重复事件变异故意绕过正常提交边界，在真实 review 重放时复制一条同版本的正式批准提交；批准数由 1 变为 2。它证明指定断言能发现这一错误，不替代 E4 对正常恢复协议的证据。Derive 负对照针对基础状态字段，不由此宣称覆盖任意文件系统副作用。

这些是 7 个有目的的语义负对照，不是自动变异框架的任意 bug 覆盖率。

## 8. 开发期失败、协议修正与范围限制

下列记录保留，没有被正式通过报告覆盖：

- **E1/E2 初轮：**经营初始工作只保存 required_basis，缺少共享 required_credentials，检查点构造失败。E1 尚未进入 48 个缓存变体，不能报告成“0/288”；E2 文稿及范围 fixture 通过，经营构造导致跨模板比较未执行。修正发生在生产 workflow 的初始事实映射，脚本没有偷偷补 state。首轮脚本和日志在 `runs/e1-e2-v05-draft-failure-evidence/`。
- **E1 报告改进：**构造失败显式标为未执行，区别于真正的投影不一致；未放宽预声明缓存字段。
- **E3 开发：**发现没有兼容 blocker 的条件未随需求修订撤换，已修复；另一轮把失败回应收据误放入“正式满足”比较投影，修正了比较口径，保留各轮报告。
- **E5 开发：**首轮只有 5 个正常对照通过。M2 是未初始化与已重建空缓存的夹具比较问题；M5 是迁移中的文稿事件误走经营审阅。修正后在新目录复验；没有修改 7 个变异分母或看到结果后更换断言。
- **K3 开发：**保留上述提交后确认异常反例；另发现非有限输入若用截断 repr 构造摘要会碰撞。v0.5 直接在身份形成前拒绝非有限 JSON，不把它纳入重放域。
- **事实与缓存的测试迁移：**旧夹具中仅写 status=accepted 的对象改为真实 submission/review 事实；没有为了通过旧缓存断言让投影重新信任 status。

当前仍使用可信检查点、基础记录和事实快照，不声称能从任意残缺旧日志重建世界。当前运行器只接受 schema 0.5；旧世界使用对应冻结运行器，本轮没有隐式历史迁移或重写旧观察。

组织规则是静态配置，金融和文稿质量检查仍有限。没有证明外部专业合理性，也没有通过内核恢复实现专业人士永不犯错。

## 9. 复现与留存

输出目录必须新建；旧世界与失败记录不覆盖：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python scripts/state_projection_experiment.py --output runs/e1-new --workers 4
.venv/bin/python scripts/adapter_conformance_experiment.py --output runs/e2-new --workers 4
.venv/bin/python scripts/bounded_state_experiment.py --output runs/e3-new --depth 4
.venv/bin/python scripts/bounded_recovery_experiment.py --output runs/e4-new --workers 4
.venv/bin/python scripts/semantic_mutation_experiment.py --output runs/e5-new --workers 4
.venv/bin/python scripts/world_mechanism_suite.py --output runs/regression-new --workers 4
```

完整检查点、状态、真实文件、原始／标准化比较、子进程输出、切点标记和反例保存在本地 `runs/`。Git 保存脚本、规约、精简结果及原报告哈希。精简归档清楚标注省略字段；不能将其等同于全部原服务器世界的独立重审。

本阶段完成依据是：在冻结范围内，同一事实能够经缓存重建、两个适配器、有限动作组合和指定中断切点获得一致解释。未把范围之外的问题加入一个无限增长的验收清单；进一步扩展应另行冻结新的边界。
