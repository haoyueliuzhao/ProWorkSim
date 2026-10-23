# 九组实验中协作环境的实际组成与 S1 边界 r1

记录日期：2026-10-23。本文补充 `software-benchmark-v055-condition-interface-facts-r1.md`，只核对源代码和已有实际请求，没有运行模型、测试、重放动作或修改实验状态。

本次 PROJECT 是**协作型受管环境的单成员 S1 条件**：保留版本、责任、消息、权限、交付及团队资源等组织结构，但真正运行的模型成员只有 `member_001`。原生 REF / MATCH 也只有一个实际 Agent。本轮没有测试多人团队效果，不能据此证明协作收益，也不能把 PROJECT 分数差称为“多智能体协作造成的损失”。

## 1. 实际模型可见的是 33 个工具

来源不是仅统计 `software_benchmark_world_v054.TOOLS`。世界层有 27 个，HarnessPort 追加 4 个私有工作台工具，SDK 再加入 `staff_wait` / `staff_done`，合计 33 个。

| 类别 | 数量 | 具体工具名 | S1 的真实可用性 |
|---|---:|---|---|
| 代码树与问题读取、编辑 | 10 | `list_files`、`read_file`、`search_file`、`replace_file`、`write_file`、`diff_workspace`、`create_file`、`delete_file`、`rename_file`、`read_task` | 在文件策略及当前工具契约内可用；包括已修复的增删改名 |
| 公开测试及精确回读 | 2 | `run_tests`、`read_test_result` | 可用；测试对应当前版本，保存结果归本成员，不提供隐藏评分 |
| 自主任务形成与责任 | 6 | `create_task`、`revise_task`、`claim_task`、`return_task`、`declare_dependency`、`remove_dependency` | 可用；N=1 时仍可建立自己的工作计划和版本依赖，但不是开始编辑的前置要求 |
| 固定补丁、合并、交付 | 3 | `fix_patch`、`integrate_patch`、`submit_integration` | 可用；S1 可读取或合并自己已经发布的固定补丁，合并代码没有“必须他人作者”的要求；不能因此称为发生了跨成员协作 |
| 通信、补丁交接、责任转交 | 5 | `send_message`、`handoff_patch`、`offer_transfer`、`accept_transfer`、`decline_transfer` | **仍在模型 schema 中，但 S1 无合法协作对象 / 待接收转交，见下节** |
| 组织事件回读 | 1 | `read_work_event` | 可读取公开固定补丁 / 任务事件及自己有权访问的定向事件；不能读取任意私有编辑或其他成员私有历史 |
| 私有工作台 | 4 | `work_note`、`work_todo`、`work_history_search`、`work_history_read` | 可用；只保存本角色主张及检索本角色实际见过的观察 / 工具回执，不改变任务完成、责任或验收事实 |
| 生命周期 | 2 | `staff_wait`、`staff_done` | 可用；等待 / 结束当前工作，不创建伙伴、不补预算、不自动提交 |

明确**不在当前 schema**中的工具包括 `spawn_member`、`retire_member`、旧式 `delegate_task`，以及通用 `write_object`。HarnessPort 的通用 JSON 编辑工具 `work_replace_text` 仅在下层暴露 `write_object` 时才追加，因此本次也没有它。不能把通用框架曾有的全部工具算进这 33 个。

实际请求依据：

1. 首个正式 Qwen PROJECT 槽 `matplotlib__matplotlib-25479`：
   - `runs/software-benchmark-v054/formal-queue-r1/slots/2/preclaim-1/episode/managed-transport/request-00001/original-request.json`，SHA-256 `bc8516632f514386e9bd491e04231812d5ab4806fd6d1256c697c62b9c6b0082`；
   - 同目录 `selected-request.json`，SHA-256 `5ade0002aa6f2bae45d1451016be2a9c619d465328cb3055ebb7127254f19c53`。
   - 原始及投影后请求均含上述 33 个工具；因此不是只从当前源码猜测过去模型可见内容。
2. DeepSeek 已有中性接入资格请求：`runs/software-benchmark-v055/neutral-qualification-r1/PROJECT_THINKING/ledger/request-0001.json`，SHA-256 `5392cd62453a58bc5c36ae463da575795cda90bd06c5d7facfcd8e78b8ce6522`，实际 wire 同为这 33 个工具。该请求用于 schema 接入证据，不计入正式 500 题成绩；正式接入仍由同一 `managed_port` 构造，见 `tools/run_deepseek_controller_v055.py`。
3. 源码：`src/proworksim/software_benchmark_world_v054.py::TOOLS`、`src/proworksim/harness_port.py::HarnessPort.tools`、`src/proworksim/model_policy.py::CONTROL_TOOLS`、`src/proworksim/software_calibration_collector_v051.py::specialize_control_tools`。

## 2. 可见协作入口与真实成员权限不同

`software_calibration_world_v051.py` 固定 `MEMBERS=("member_001",)`，初始成员、最大活动成员、累计出生数均为 1。出生关闭、主动退休关闭、外部干预关闭；初态没有任务、补丁、提交、转交或初始诊断执行。`member_001` 是唯一执行者；`operator` 是环境安装 / 控制身份，不是第二个模型伙伴或自动项目经理。

`spawn_member` / `retire_member` 从公开工具表移除，S1 实现也明确拒绝创建或退休身份。`SingleMemberBudget.register_member` 拒绝注册额外成员。`staff_done` 不调用退休以制造可替换的空位；同一会话的完成与成员身份存续分开。

保留的通信工具 schema 的 `recipient` / `to_member` **仍枚举 `member_001` 到 `member_006`**。这是继承的候选身份范围，不能当作实际 6 个 Agent。执行时 `_available_recipient` 要求收件人“不是自己、已注册且 live、预算下仍可接收工作”。S1 的实际 registry 只有 001，因此：

- `send_message`、`handoff_patch`、`offer_transfer` 找不到合法接收者；给自己或从未出生的 002–006 都不能通过该执行检查。
- `accept_transfer` / `decline_transfer` 要求一个真正存在、发给当前成员且仍 pending 的 offer；S1 初态没有 offer，也没有第二个合法成员产生 offer，不能凭空完成转交。
- `integrate_patch` 本身仍可用，它读取已发布固定版本并作三方合并。它不等同于接收责任，也没有新增伙伴；S1 的自有补丁使用不能计为团队贡献。

这属于**组织 schema 仍可见、部分操作在 N=1 下不满足业务前提**，而不是“协作工具全部隐藏”或“所有协作工具均可用”。保留这类可见但无对象的入口会增加 schema 内容，并使误用产生拒绝反馈；本次静态核对不能单独量化它对成绩的影响。

证据：`software_calibration_world_v051.py::{case_spec,SoftwareCollaborationWorld,SoftwareCollaborationPort}`；`software_organization_v038.py::{_available_recipient,_action_offer_transfer,_offered,_action_accept_transfer,_action_decline_transfer}`；`software_collaboration_v030.py::_action_send_message`；`software_collaboration_v028.py::_action_handoff_patch`；`software_benchmark_world_v054.py::_action_integrate_patch`。

## 3. 协作环境引入了什么

### 共享基线、私有工作区与固定发布

环境安装一份由 operator 管理的共享源基线，以及成员自己拥有、自己可写的私有工作副本。成员读取、编辑的是有 object / version 身份的真实版本，不是可任意修改的账本。发布 `fix_patch` 后，公开的是**该确切版本**，不是授予其他成员随后私有编辑的实时访问权。

多成员设计因此支持成员隔离探索后交换固定产物，而不是多人同时写一个无区分工作树。本轮实际仅有一个私有工作副本。S1 的 `_share_fixed` 也只向实际 `MEMBERS` 中的 001 记录固定版本授权，没有为不存在的伙伴建立工作区。

固定补丁记录作者、源与基线引用、内容及元数据 hash、变化路径、已合入补丁和绑定任务快照。合并使用基线 / 当前 / 来稿的三方规则；文本冲突产生需自行处理的冲突内容，结构或非文本冲突有明确拒绝分支。没有自动修复冲突、自动测试或自动提交。

### 任务板、责任与显式转交

根问题保持原始 issue；没有预先人工拆成执行任务。`create_task` 最多创建 24 个任务，初始 owner 为空；`claim_task` 才取得责任。任务含父项、说明、revision、owner、依赖。改任务需要当前 revision 和理由；依赖无环，并绑定上游任务的确切 revision。旧责任与旧文本保留在事件中。

任务归属不限制文件编辑，直接修复合法，`fix_patch(task_ids=[])` 明确允许不绑定任务。只有选择了非空任务绑定时，才检查拥有者和前置任务版本；不应把可选任务板手续描述成每次修复都必须完成的固定流程。

多成员语义下责任转交是 offer → 受方 accept，而不是发送消息就自动变更所有者；owner 或 revision 变化会使旧 offer 失效。`return_task` 归还到未分配任务板，不自动指派别人。上述责任机制在 S1 仍有自组织用途，但没有本轮实测的跨成员分工。

### 定向消息、私有记忆与受限观察

消息和 handoff 是定向事件，不隐式复制文件、转移责任或复制模型历史。消息可引用已公开固定补丁 / 提交；任意私有版本不能仅通过伪造引用变为公开。

默认观察包含成员 registry / availability、当前工作区版本、任务摘要、团队预算、当前版本测试覆盖、已发布补丁及提交信息；最近 4 条定向消息 / handoff、最近 6 个补丁、最近 2 个提交被摘要展示，文本预览有界，旧定向消息的事件序号仍供精确回读。`read_work_event` 按公开事件或定向权限检查，私有测试报告也要求原成员身份。

私有工作台另提供本成员笔记、todo、历史搜索和原记录回读。它只检索实际观察过的历史，不读取其他会话、隐藏评分材料或未读源文件；“todo done”不等于任务被完成或代码通过。Γ1 在模型上下文内做受约束去重 / 引用 / 轮次选择，与这些可回读的原始记录分开。

### 交付语义与同版本测试

协作环境区分“改好工作树”“发布固定补丁”“显式交付”。`submit_integration` 检查当前准确 source reference 已有真实测试事件和同版本固定补丁，保存 delivery 与 test sequence；测试不必全部绿色，提交也不代表官方验收通过。

多成员时这防止拿甲版本测试证明乙版本合并后的提交；在 S1 中同样执行，最后编辑后仍需为新版本测试 / 固定 / 提交。工作区与最后合法提交可以分叉，因此本轮同时测最终代码端点与交付端点。它们不是同一个成功标准，也不能仅将均值差都归为流程影响。

### 团队预算、工作机会与可追溯执行

项目引入统一团队模型预算和测试预算；本轮一个成员独占原 128 decision、128 attempt、500,000 token、32 次公开测试额度。创建任务、私有记忆操作、分页回读及格式修正都使用真实交互机会，不能因为是“管理操作”而免费补次数。`staff_wait` / `staff_done` 不重置预算，也不制造唤醒事件；无可运行成员或真实后续事件时按单成员边界闭合。

执行由绑定成员的 trusted session 进入真实世界操作。世界层事件记录 actor、逻辑时刻、operation / action ID、责任快照；HarnessPort 分开记录公共观察、世界调用和私有工作台事件，私有调用还带请求键及前后状态 hash。数据所有者、版本、公开权限和实际预算都有独立记录，模型不能通过修改文本自我宣布这些事实已经成立。

## 4. 已知机制效果与尚不能断言的影响

| 引入的机制 | 从实现可直接确认的效果 | 本次不能直接证明的结论 |
|---|---|---|
| 私有版本、显式固定与合并 | 将代码作者、版本、修改和集成行为区分开；不自动共享未来私有编辑 | 团队一定比共享工作区更快或更准 |
| 任务 revision 与接受式责任转交 | 责任变更有前提、有记录；任务板可选，直接工作合法 | 本轮已发生有效分工或减少重复劳动 |
| 定向消息、历史与精确回读 | 信息访问按身份和来源控制；回读旧记录与读取当前世界不同 | 全部模型都充分利用了消息或历史工具 |
| 33 工具及组织观察 | 本轮模型实际接收比原生五工具更复杂的操作与状态说明；部分协作入口在 S1 无合法对象 | 单靠数量就能确定下降多少分，或证明删除它们必然改善 |
| 同版本测试 → 固定 → 提交 | 最终代码与合法交付成为两个可区分端点；修复代码后仍有明确闭合动作 | 所有未交付都源于环境 bug，或全部差分都是流程损失 |
| 统一预算与机会计量 | 管理、读取、修正也使用原预算；结束 / 等待不额外补资源 | 相同 128 次调用在不同接口下具有完全相同工作量 |
| 审计及权限隔离 | 可追溯实际调用、版本和授权，不把笔记或自报测试当作验收 | 仅由九组单 Agent 成绩证明多 Agent 学习数据质量或长期训练收益 |

上述“可能增加交互负担、降低误共享风险、帮助定位交付问题”可作为设计层面的作用解释；若要比较净收益或定位分数差异，仍需实际轨迹、配对结果及针对性消融。**本轮能校准单模型通过这套协作型接口独立工作的表现，不能验证团队协作增益。**

## 5. 主要源码定位

- `src/proworksim/software_benchmark_world_v054.py`：当前工具表、完整文件版本、补丁与合并、S1 观察、私有副本安装。
- `src/proworksim/software_calibration_world_v051.py`：唯一成员 / 无出生与退休、S1 固定版本授权。
- `src/proworksim/software_collaboration_v027.py`：版本化 `_bundle`、事件来源、同版本测试与提交检查。
- `src/proworksim/software_collaboration_v030.py`：任务自主创建、修订、依赖版本、定向消息与事件回读。
- `src/proworksim/software_organization_v038.py`：真实 live registry、接收方可用性、显式 offer / accept / decline、责任归还。
- `src/proworksim/software_organization_v042.py`：成员私有测试报告与精确页。
- `src/proworksim/harness_port.py`：四个私有工作台工具、已观察历史、请求键与独立事件记录。
- `src/proworksim/software_benchmark_managed_v054.py`：实际 HarnessPort / SDK / 单成员 runtime 绑定。
- `src/proworksim/software_calibration_collector_v051.py`：SingleMemberBudget、单成员 wait / done、实际工作机会及闭合。
- `src/proworksim/software_context_v048.py`：实际 Γ1 观察与历史投影。

本文没有把历史多成员版本的预算、出生规则或人工任务合同套回本轮 Verified S1，也没有根据本轮分数追加任何环境修改。
