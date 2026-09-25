# v0.13：短工作情境与范围化回报

本模块为共享模型直接在线交互提供有限环境反馈。它没有提供标准动作轨迹，也不通过 Teacher 或 SFT 制作训练目标。模型从自己的局部资料、公开工具与实际后果中选择动作；奖励由封闭 episode 的真实世界记录独立计算。完整工作有效性、多类别支持和重配资格不再是基础 RL 的统一前置条件。

## 固定两窗口组合与数据用途

`templates.online_work.registry()` 预声明两个在线窗口，每窗口固定四段、各占 1/4：

| 情境 | 当前目标角色 | 每角色决策上限 | 合法起点 |
|---|---|---|---|
| handoff | provider | 4 | 资料持有者可见业务依据，接收者尚不可见 |
| implement | implementer | 8 | 真实准备过程已交接资料并为当前工作采用 data/basis，尚未实现或提交正确结果 |
| review | reviewer | 6 | 真实 SQL build 和 submit 形成原始 pending 提交，尚无复核 |
| chain | provider、implementer、reviewer | 4、8、6 | 完整初始工作，需要三方自己完成交接、实现与复核 |

第一窗口的 review 起点为实际正确提交，第二窗口为实际错误提交；这项准备控制只在宿主 registry 和准备记录中出现。两者角色任务和公开 reward 合同完全相同，不包含窗口、数据用途或“正确/错误”标签。当前 actor 自行判断已有工作，并不获得未来答案。

各段使用预先固定 seed 的新合成金额/口径事实。窗口更新后重新创建世界、重新实际交互；不会重播上一窗口的行为。registry 还先声明 8 个 `dev_check` 和 8 个 `locked_within_family_check` 情境，分别用于开发判断与固定初始/最终模型的配对检查。它们与 `online_train` 都属于 **development 的同一个来源/世界家族**；`independent_test_source_families=[]`。不存在把事实变体注册成独立来源来绕过划分校验的做法。

本轮布局全部是 `split_a`，锁定检查只引入新事实，不宣称信息布局迁移或独立来源泛化。完整三成员链与单岗位短段分别报告结果。配置见 `examples/online-work-v13/registry.json`、`windows.json`；不得按中途奖励改变任务份额、换槽或补采到出现正例。

角色预算应分别耗尽：provider 的 4 次机会用完不终止 implementer 尚余的机会。角色轮转与段边界由在线 collector 预先声明；本模块不读取评分来隐藏地帮模型继续做题。

## 真实准备与当前 actor 分开

`build_online_case(case_id, new_case_root)` 返回 `PreparedOnlineCase`，包括真实 `ScenarioDeployment`、world、scenario、reward_spec、active_roles 和 prefix。

准备阶段调用公开工具：provider 实际读取并 handoff；implementer 实际读取、采用；review 情境还真实写 SQL、build、submit。错误 review 也由真实可执行的错误 SQL 产生，不直接注入伪造结果。准备保存每次 command 返回、独立端口捕获、环境事件及起止业务摘要，标记 `origin=preparation`。

调用方必须在准备返回之后，用空的新 target recorder 创建 `begin_episode`。准备 actor 即使与后来角色同名，也不是当前模型的动作。源状态中已有的读、交接、build、提交和批准不产生本段新增信用；重放准备阶段已有 command receipt 也不计新动作。前缀不会作为示范对话追加到 actor 输入，但准备后的合法世界状态与当事人可见的资料仍可读取。

实现短段的初始代码仍是不满足完整业务要求的起始 SQL，不在后台为实现者写入正确解。review 中的代码/结果是该角色需要判断的现有工作对象，不是待模仿的目标动作。

## 公开奖励合同

每个工作要求中有 `requirements.online_scope`，与 episode 开始前的 `scenario.variation.online_reward` 完全一致。`assess_online_reward(episode, spec)` 拒绝事后换奖；null 回报也保留 episode ID、manifest 摘要和原 spec。

| 范围 | 唯一成果分项 | 总分为 1 的含义 |
|---|---|---|
| handoff | 本段读到适用的精确依据 0.25；选择该依据并实际送达正确接收者/工作 0.75 | 仅本段交接责任完成 |
| implement | 本段读取确切输入 0.2；真实且独立正确的 SQL build 0.3；正确 code/result 精确提交 0.5 | 仅本段实现及提交责任完成，不要求本段之外的复核 |
| review | 判断前 inspect 并读取固定交付、data、适用 audit_basis 0.25；有依据正确批准，或定位原提交真实错误 0.75 | 原始固定提交得到正确、有据的处理；错误提交可通过真实 blocking issue 完成本段 |
| chain | 真实适用交接 0.2；读/采用依据并真实正确提交 0.3；有据、正确复核 0.5 | 依据、业务交付和真实审阅义务全部成立 |

所有分项是绑定责任、精确版本与 episode 的布尔成果，每项最多一次。重复读、重发、重复 build/submit/approve 不叠加奖励；先制造错误再修正也不能多领一份成果奖。错误批准不产生正确复核分，错误位置或无关证据不产生问题定位分。错误提交的位置检查从实际 data 与独立 audit 口径重算，目前明确限定到 `tables.metrics.rows` 的真实错误行/单元格，不把任意 issue 当作正确审阅。

复核要求真实发生在判断之前。事后补读不能给此前无依据的批准补分；后续重复批准也不能洗掉已经发生的无依据批准。完整链不能仅凭制度 accepted 或批准数量得到满分。

合法工具拒绝与未达成成果通常保留为可评失败；不可读/变化的历史证据、评价异常或不可计量的服务故障保持 reward=null，不伪造为模型零能力。读和采用、工具实际执行输入、文件依赖、固定提交分别核验。真实 DuckDB `execution_status=success` 不自动等于独立业务正确。

## 范围有效性与真实模型输入

奖励同时给出独立的 `work_components.basis/delivery` 事实，用于 `online_support` 的范围化 V。它们直接检查成果与依据，不通过 `R==1` 生成有效性：

- handoff 检查本段真实适用读和当前工作真实送达。
- implement 检查提交前的真实输入读取/采用，以及独立正确的实际 build 和新固定提交；不强加不在本段责任中的 review。
- review 检查原始 pending 提交的实际读取、独立依据和正确处理。
- chain 检查完整交接、正确提交及有依据复核。

record/permission 由独立捕获、实际模型记录与 WorldCore receipt 检查。`read_alias`、`read_version` 必须对应同名真实 receipt contract，不能把旧日志字符串重命名后冒充新操作。旧准备可使用 `read_object`，但不计当前 actor 信用。

对真实模型的消费动作，先前 read/inspect 的确切 `model_tool_result.message` 必须真实出现在该动作对应的成功 HTTP request 中。保存过但未呈现的材料不算模型已使用的依据；明确缺席为未满足，必要请求/返回链缺失保持未知。规则见证只有实际直接返回，不伪装 HTTP 模型调用。

部分奖励不代表 V=true；短段的 scoped V=true 也不代表完整团队成功。更不代表可重配类别或训练收益。无类支持时仍按基础处理，当前 actor 的失败动作和未知记录按在线协议分别保留。

## 调用与规则验证

```python
from proworksim.templates.online_work import build_online_case
from proworksim.online_rewards import assess_online_reward

prepared = build_online_case("train-w0-implement", new_case_root)
# prepared.deployment 是可绑定 runtime 的真实 ScenarioDeployment。
# 准备已执行并单列；从此处开始建立空 target recorder 和新的 episode。
# 模型只对 prepared.active_roles 实际决定，所有目标角色共享当前 actor 参数。
# finish_episode 后：
reward = assess_online_reward(episode_path, prepared.reward_spec)
```

独立规则见证命令不调用 API、GPU 或模型：

```bash
.venv/bin/python scripts/online_work_experiment_v013.py --output runs/online-work-v013-new
```

开发 `runs/online-work-v013-dev3/` 保留 8 个正常短段及 8 个反控制，16/16 通过：正常结果均 1；仅读依据 0.25、重复交接仍 1、准备后不动作 0、真实错误 SQL 0.2、继承正确提交却不复核 0、错误批准/错误定位各 0.25、完整链缺复核 0.5。正常实际动作数为 handoff 2、implement 6、review 6、chain 各 2/8/6，证明所给预算下规则工作可行；**不是模型成功率或在线更新证据**。

开发早期的一次新读取 capability 尚未并行集成、一次规则脚本误取未公开的 `submissions` 字段均保留在独立 dev1/dev2 世界。后者改用公开 pending/latest submission ID；没有因此修改目标产物或奖励合同来凑通过。后续定向测试另覆盖准备 receipt 重放、事后换奖、错误复核、实际输入呈现、伪重命名新读以及先批准后补读。

正式规则运行、真实 O0/O1/O2 和模型参数更新由各自冻结报告给出，不将这里的开发矩阵或已实现的模块直接写成学习收益。
