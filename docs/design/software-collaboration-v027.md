# v0.27 有限软件协作工作接口

本模块落实 2026-10-02 审计要求的三个工作组件：代码工作空间、轻量任务板、集成与独立验收。它复用 WorldCore 的身份、文件版本、权限、原子命令账和 OS 隔离执行；不增加 Agent 平台、训练器或 GPU 队列。现有 v0.15 与 v0.26 结果没有重评或覆盖。

源码：[software_collaboration_v027.py](../../src/proworksim/software_collaboration_v027.py)。CPU 正负控制：[test_software_collaboration_v027.py](../../tests/test_software_collaboration_v027.py)。它们是接口实现与程序见证，不能充当当前模型有效经历、训练支持、分配增量或独立确认结果。

## 用途与材料

固定使用 v0.15 已引入的真实 Marshmallow 源码；`source_bundle()` 继续逐文件核对旧 source manifest 的 SHA-256。任务需求和 inventory consumer 是模拟工作材料。此处不重新声称真实上游 issue、来源迁移或未见测试。两个情境均标记 `usage=interface_dev`、`training_eligible=false`、`independent_confirmation_eligible=false`：

| case_id | 实际工作依赖 | 允许选择的路线 |
|---|---|---|
| `marshmallow-interface-dev` | String 新增可选空白规范化 API，inventory SKU 消费该 API；组合后必须保持原行为 | 一人完成、上游先行、各自实现后交换、重新委派 |
| `marshmallow-integration-dev` | 同一 String 类中的空白规范化与 Unicode casefold 两功能要兼容，consumer 仍只启用空白规范化 | 共享模块由一人整合、独立补丁后合并、冲突后修复 |

第二项新增的开发验收在既有 API 输入适配器上增加 8 个 casefold / 组合 / 回归案例，与旧 29 个案例共同在同一最终树上执行。公开需求说明默认行为、错误处理、序列化和组合行为。私有期望与组名不装入成员世界。以上测试属于重复使用的开发家族，不能划到独立确认用途。

## 两名成员、独立文件和可变责任

稳定成员为 `member_a`、`member_b`，两者有相同的编码和测试能力。WorldCore 中每人一个私有文件对象，写权限只属于本人；只读共同基线属于 operator。可编辑 `src/marshmallow/fields.py`、`consumer.py`、`test_member.py`。文件名来自有限索引，不接受宿主绝对路径、目录穿越或任意 shell 命令。

模型通常使用 `list_files`、`read_file`、`search_file`、`replace_file`、`write_file` 和 `diff_workspace`。工具参数直接是路径、文本或 diff 对应内容；模型不需构造含全部源码、权限或采用关系的 JSON 对象。WorldCore 在下面保存不可变版本。`read_file` 记录实际行区间，不能据此宣称读过整个文件。

任务初始无人领取。`claim_task` 在核心文件锁和事务中完成，两个独立会话并发领取只会有一个成功。`delegate_task` 只允许当前负责人转交；新负责人不替代历史编辑者。责任快照和领取/委派事件保留实际稳定 actor，并与原始命令账关联。成员可以承担一个或两个任务，也可以把责任转交给伙伴，最终提交者不限。

`declare_dependency` 记录无环任务依赖。若成员声明了依赖，发布下游补丁时必须已集成上游固定补丁，或在同一补丁中承担上下游任务；依赖声明不会自动读取文件、合并代码或使测试通过。模型不必填写声明来证明每次读取，程序也不把声明文本当成语义使用证据。真实 API 依赖仍由执行后果验证。

## 固定补丁、交换和真实集成

`fix_patch` 固定成员当前源码版本，保存作者、责任列表、共同基线引用、改动文件、文件树 SHA-256、bundle SHA-256、unified diff SHA-256，以及已集成补丁列表。固定版本被共享给两名成员，伙伴可按 `patch_id` 读取。`handoff_patch` 另记录消息和接收人，不自动合并。工具没有 SQL 式 basis/adopt 或批准手续。

补丁是相对共同初态的**累计补丁**，不是仅对上一次个人提交的增量。已有伙伴改动可能包含其中：发布者是该固定版本的发布者，不能因此把伙伴历史编辑归为他的独立贡献。`included_patch_ids` 和原始 `edit` / `integrate` 事件用于追溯。不能仅凭 `task_ids` 或最终发布者判断实际贡献。

`integrate_patch` 用实际 `git merge-file --diff3` 对每个变更文件进行三方合并，输入为共同基线、本人的当前文件、伙伴的固定文件。git 只收到控制器写入临时目录的选定源码字节；模型不能指定命令、选项、环境或宿主路径。无冲突时写入新工作版本；冲突时把真实冲突标记写进成员副本并返回冲突路径，成员必须自行读改修复。不会静默偏向任一方。

合并事件区分 `merged` 与 `conflict_markers_written`，保留输入补丁、合并前/后固定引用和输出哈希。后者是已落盘的冲突版本，不是成功集成。非法参数、重复集成等命令失败仍在核心 journal 中记录为拒绝，不产生成功事件。修复通过新的普通文件编辑产生新版本，历史冲突记录保留。

`included_patch_ids` 表示曾实际送入合并的固定补丁及其祖先。后续编辑可以改变或删除此前内容，因此它不能单独证明最终保留该功能、语义使用或合作因果贡献。下游 Mapper 应结合真实文件变化、操作账、测试与最终独立验收；不能把集成尝试一律标成成功使用。

## 测试与完整交付

`run_tests` 在现有 `software_sandbox.run_isolated` 的新只读树中运行固定公开 suite，然后运行成员可写的 `test_member.py`。沿用 Linux Landlock/seccomp、20 秒 wall / 10 秒 CPU / 512 MiB、输出上限和禁网/禁进程边界。该受限 Python 环境不等同于完整仓库 Docker/SWE-smith 环境；新来源接入仍须单独验证实际依赖和环境。

每次测试记录源码固定引用、内容哈希、实际执行状态、退出码、完整驱动标记和输出。工具不接受模型提供的退出码或测试 JSON。成员自己写的测试和待测库可能篡改 `unittest`，因此公开测试通过只作工作反馈。

`submit_integration` 要求当前精确版本已发布固定补丁，并在真实隔离环境中运行过测试。允许带失败测试提交，以保留可判定失败；不把“绿色测试”设为隐藏过滤器。未测试的新编辑不能沿用旧版本测试。提交固定同一版本及其测试事件，此后工作区变化不改写交付。

`assess_software_collaboration` 在会话之后重建最新固定交付，在隔离子进程执行 API 输入，并由父进程使用未发给子进程的期望值比较。复用 `software_acceptance.assess_api`；模型报告、成员测试通过和任务声明均不具有验收权威。完整奖励只看一个**合并后的固定树**是否通过全部合同案例，不把两个独立 feature 分数求平均后叫完整集成。

无交付为可评分的 0；隔离未能安装等无法执行情形为 unknown。独立验收在本开发用例中指评价进程与实现代码分离，不代表数据用途已成为独立确认集。测试数、领取速度、消息数不进入功能正确性奖励。

## 运行器与事实接口

```python
from proworksim.software_collaboration_v027 import (
    PROJECT, SoftwareCollaborationPort, build_software_collaboration_case,
    assess_software_collaboration, software_collaboration_facts,
)

prepared = build_software_collaboration_case("marshmallow-interface-dev", new_case_dir)
port = SoftwareCollaborationPort(prepared.world.session("member_a", PROJECT), "member_a")
# 同一个 port 可接现有 capture_port、StaffRuntime / SDKStaffRuntime 与原始模型 token 捕获。
# 控制器不能替模型调用实现、合并、测试或提交。
facts = software_collaboration_facts(prepared)
# 也可传入归档 episode 的完整 state 字典；不会执行代码或改变评分。
assessment = assess_software_collaboration(prepared, run_root=private_assessment_dir)
```

`PreparedOnlineCase` 继续提供 deployment、case、prefix、world 和 port_factory；当前 reward spec 明确 `training_supported=false`。`observe()` 包含原 world/instance/branch/actor 身份及绑定项目，适配现有运行器的权限检查；不泄露另一成员尚未发布的工作树。公开资料包含合同、任务板、固定补丁与转交记录，不暴露私有验收。

状态中的 `projects[SOFTWARE27].software` 保存用途、任务当前状态、固定补丁表和交付列表；`software_events` 为核心 transition 保护的追加历史。每条事件包含 `operation_id`、`action_id`、稳定 `actor_id`、逻辑时刻和当时责任快照。下游必须把它们绑定到 `operation_commits`、原始 capture 和成员动作；此汇总不是可以替代原始证据的模型自报日志。

## 本次 CPU 核验

`python -m pytest -q tests/test_software_collaboration_v027.py`：7 项通过；其中前 6 项与旧 v0.15 的 5 项合跑为 11 项通过，新增运行器绑定检查单独通过。静态检查通过。覆盖：

1. 双会话原子领取、委派后历史作者不变、同命令重放不重新领取。
2. 私有工作副本互不污染、未发布版本不可读、通用对象写入口及路径逃逸拒绝。
3. consumer 单独修改真实执行失败；集成库 API 后完整 29 例通过；旧测试不能覆盖新改动，固定提交不受后续编辑影响。
4. 两个独立 feature 控制分别执行通过，但真实合并产生冲突、整体验收失败；成员显式修复后同树 37 例通过，保留冲突与修复事件。
5. 待测代码伪造 `unittest` 成功时公开报告可绿，父进程独立验收仍判失败。
6. 成员测试实际尝试访问伙伴对象和宿主 canary、写文件、建网络连接、创建进程，均被 OS 边界拒绝。
7. 原 StaffRuntime 和 capture_port 正常绑定两个稳定成员，模型动作入口与原始捕获保持一致。

这些核验只证明所测接口与有限合同的可执行性。没有新模型调用、GPU 工作、策略训练、有效方法频数、B/G/I 比较或参数更新收益；也没有冻结正式软件来源、样本规模或资源预算。

## 实际 SDK 接线与有限采集入口

[`software_runtime_v027.py`](../../src/proworksim/software_runtime_v027.py) 的 `build_runtime(owner, prepared, folder, harness='openhands_v16')` 通过既有 `harness_collection._runtime` 新增的可选 `interface_factory` 连接上面的文件端口。旧入口默认仍创建 WorkInterface。复用同一个 HarnessPort、HarnessWorker、SDKStaffRuntime、原始 token 捕获和成员 policy identity，没有另一套 Agent 循环。构造时不采样、不执行 world action，并核对 world state 完全不变。

`collect_software_window` 只接受显式 `frozen_development` / `interface_dev` 窗口：每条 slot 预先固定 case_id、sampling_seed，必须声明新 `max_slots`、`max_model_calls` 和诊断频数阈值。当前 case 每名成员最多 24 次模型决策，控制器不改写该限额或为失败补采；全部 world、policy 和 seed 绑定先冻结再采样。GPU/进程寿命属于调用者为新实验配置的资源监督器，本入口不加载模型、不分配 GPU、不继承旧 GPU 预算、不执行优化器。

对话结束并关闭 SDK 会话后，才独立验收固定最终树；接着调用 `software_training_v027.export_software_episode` 输出完整性/权限/软件事实绑定、成员投影和方法描述。中断保留 capture、runtime 和异常，已有 slot 不自动重试。没有成果时仍留下可判定的失败，不追加基础训练。

`tests/test_software_runtime_v027.py` 使用真实已安装 OpenHands SDK 和明确标记的 CPU 假响应/假 token fixture，核对初始化零动作、双方真实 world 命令、receipt/capture/token 身份关联、SDK关闭后的导出、新窗口预算拒绝，以及同一情境两次重复的声明绑定。最终 4 项通过；此前完整关闭导出和旧 `test_harness_collection_v016.py` 的 2 项合跑为 3 项通过。使用 `runs/v016-sdk/resident-venv/bin/python`，出现一条 SDK 依赖 Pydantic 关于 `ReadOnly` 的既有 warning。默认 `.venv` 缺少可选 SDK 时对应测试会 skip，不能把 skip 写成 SDK 已验证。这些 fixture 不是 9B 模型采集，也不代表软件在线训练已完成。

重复绑定控制建立两个独立 world，在不同实例/分支和不同 sampling seed 下声明相同情境：完整业务初态摘要、SDK policy identity 和 xi 指纹一致，两个 slot 均能声明和关闭导出。沿用 `initial_business_state` 的严格规范化，不额外删掉代码、权限、任务、安装命令 ID 或逻辑初态；当前准备路径的安装命令 ID 本身确定。每个运行实例和分支身份仍单独保存在 episode 原始 state。此核验不改变指纹实现或放宽不同情境的支持分池规则。

## 工作路线与训练用途边界

[`software_training_v027.py`](../../src/proworksim/software_training_v027.py) 从结束快照、原始capture和WorldCore回执导出只读证据，连接既有TeamRollout/MemberView。路线区分集中交付、分工后顺序消费、独立分支集成和实际冲突解决；仅有任务声明或补丁ID不能产生消费边。跨成员转换要求当前作者实际编辑的路径与合并改变字节的路径相交，转带别人的累积补丁不能全部归功于发布者。这里是文件级执行关系，不是语义必要性、全部内容保留或因果贡献证明。

Mapper 截断固定提交以后的编辑；完整工作为false/unknown或路线无法可靠判断时保持unmapped，不制造支持。当前开发case在原始manifest、reward合同和导出scope中均有用途约束；支持统计和更新器读取冻结用途，删除附加scope也不能使Marshmallow开发材料进入训练。相关9项CPU正负控制覆盖固定版本归属、未知保留、无变化合并、转带修改误归属及开发用途绕过。完整核验见[实施报告](../experiments/software-alignment-v027.md)。
