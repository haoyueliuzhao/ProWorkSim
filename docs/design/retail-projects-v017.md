# v0.17 四项目正式效用与模型采集边界

本扩展把 v0.16 报告内核验转为固定提交与闭合 episode 上的正式合同。它复用同一 UCI 开发片段、真实 SQL 执行器和独立 Decimal 算术，不增加自动求解器，不修改 H1 六情境及已冻结的旧学习线。

## 分开的四项判断

| 维度 | 正式检查 |
|---|---|
| `P1_quality` | 已固定的实际 SQL code/result，独立按真实发票、实际合法合同计算客户金额及 DISTINCT 发票数 |
| `P2_quality` | 已固定的实际分析 code/result；独立 Decimal 金额、发票数、完整客户，以及 positive/zero/negative 分类 |
| `P3_fixed_input_fidelity` | P3 的真实 SQL 输入必须在其构建前已是 P1/P2 的固定提交版本；按双方实际输入逐客户检查 FULL OUTER JOIN、金额及发票差异，缺失一侧保留 NULL |
| `overall_business_goal` | 前三项成立、P0 原始资料未被改写、四项目固定交付、声明的发布义务完成、P3 消费的恰为终局所选两分支成果，而且双方及 P3 合同引用一致并达到该 case 的目标版本 |

P3 忠实性与上游质量不是同一项。两分支共同把金额加 1，P3 如实计算零差额，可以得到 `P3_fixed_input_fidelity=true`；P1/P2 独立质量为 false，整体为 false。标量 `reward` 仅为整体目标的 0/1 合取；分项不再伪装成完整成功率或偷偷改变奖励份额。

新 `retail_project_product` 在共用 `work_product` 中注册。提交必须带内核生成的 `execution_provenance`，匹配同一工作版次、代码版本与真实 SQL 输入；JSON 里的 `status=success`、复制的执行标签、可编辑测试通过均不足以认证实际构建。P3 还要求上游固定提交的 `at` 不晚于其实际构建时间；后补上游提交不能追认过去构建已消费固定成果。

`assess_project_episode(closed_episode)` 首先通过现有历史边界校核，再只读取 end/start 独立快照和已捕获版本。没有提交是有限责任未完成，可评为 0；证据损坏、无法读取或评估/执行服务故障保持 unknown。后续活世界的修改、发布、采用或补交不会改变旧 episode 的分数。

业务依据仍是公开模拟客户合同。合法两版合同的哈希公开绑定在检查声明中；真实字段及政策内容可通过受管读取取得。评估器不把期望数值、参考 SQL 或评分接口暴露给模型。

## 静态与一次变更

新模板 `retail_projects_v017` 保留旧 `retail_projects.py` 及旧证据。新 case 为：

- `retail-projects-v17-static`：终局要求最初的全期 sales_only 合同。
- `retail-projects-v17-change`：先完成四项目第一版固定交付，预声明事件发布截至 2011-07-01 的 net_signed 合同，终局要求该第二版成果。

初始化只声明共享订阅并实际发布可用初始合同，不生成下游 SQL、采用、成果或提交。客户合同现在由 operator 持有；P2 分析员可以读取它，不能通过改合同让自己结果变为“正确”。变化是显式客户端事件，产生版本和维护义务，不替任何下游读、采用、编辑、执行或交付。

已接受的首版义务保留，变化创建有限维护后继；还在进行中的义务按既有修订关系替代。评价通过每个项目节点的终局维护 head 固定责任。这里的整体奖励以终局目标版次为准，不声明每个历史中间版本都正确，也不声称验证任意长期维护。首版与后继的文件、固定提交和依赖仍完整留存。

## 准备的模型采集接口

`proworksim.retail_project_collection.collect_project_episode(owner, case_id, output_dir, harness=...)` 由调用方传入**已经选定**的共享模型与 `native_v15` 或 `openhands_v16`。本函数不加载权重、不选择模型、不更新 actor/critic。

调用方沿用已有固定参数评价生命周期：`capture_evaluation_state()`，`begin_window(slot_id)`，按固定 slot seed `reseed()`，调用本采集器，再 `finish_evaluation([], ...)` 和 `finish_evaluation_guard(snapshot)`。必须保存并检查实际学习状态不变和 RNG 恢复；不能用本采集器返回业务 R 代替数值/训练准入。

四个角色各有独立模型策略或 SDK Conversation、私有记忆与受管 project session，使用同一个 owner 的 transport。工具白名单只含世界的读、消息、编辑、share/publish、采用、SQL、预检、提交等操作；没有隐藏评价器或通用文件/终端入口。worker 声称 done 不代替项目交付；如显式新义务到达，可以在保留原记忆且**不重置预算**的情况下重新给该角色机会。该机制只派发新义务，不选择其工作动作。

静态角色决策预算为 P0/P1/P2/P3＝14/24/24/24；变更为14/44/44/44。所有工作辅助与等待仍消耗机会。当前四项目没有接入跨项目成员投影、critic 或在线更新，因此不能把这个正式业务评分接口等同于四项目已经具备训练准入。已有短责任训练不被此限制阻断。

固定模型评价计划见 `examples/retail-projects-v17/model-evaluation-plan.json`：静态2次、变更2次，种子为2026100401、2026100402、2026100412、2026100411；无成功重采。须先取得完整 H1 的模型—harness 选择结果，再绑定最终 source/runtime/权重并执行。本次没有启动未选模型，也没有把 CPU 见证作为四项目模型表现。

## 实际 resident 执行 CLI

新增 `scripts/retail_project_model_v017.py` 在模型加载前读取 H1 最终 `report.json` 或 `selection.json`。后者按实际格式保存选择字段与 `report_ref`；去掉 `report_ref` 后必须逐项等于其 hash 绑定报告的 `selection`。CLI 依据原冻结排序函数重新核对选中组合，两条 H1 实际进程均须已结束，原 launch/protocol/runner/owner 引用不得变化。

`--candidate`、`--protocol` 只作显式交叉核对，不能替代完整选择报告或绕过尚未结束的候选。所请求 harness、公共基础模型路径、权重清单、H1实际owner/初态、零更新计数及 recipe/profile 必须与最终选中条件一致；进入真实运行还要求干净源码提交。相对选中仍不代表业务能力充分。

```bash
CUDA_VISIBLE_DEVICES=<明确分配设备> PYTHONPATH=src \
  runs/v016-sdk/resident-venv/bin/python -m scripts.retail_project_model_v017 \
  --selection <H1最终报告目录/selection.json> \
  --candidate <选中候选ID> --protocol <该候选H1原launch-protocol.json> \
  --model <该候选原公共模型目录> --weight-manifest <原权重清单> \
  --harness <选中native_v15或openhands_v16> --output <全新输出目录>
```

CLI 固定执行本计划4槽，使用一个 fresh resident owner，保留 H1 recipe 和初始化seed；不支持恢复训练检查点。每槽另设预声明采样种子，捕获/关闭评价窗口并保存真实学习状态与 RNG guard。相同设备配置下还核对新加载 adapter SHA 与 H1初态相同。保存源码前后、原选择引用、有效profile、真实LoRA模块/参数数、初末actor身份、每槽raw结果与guard；模型服务、终止格式/worker/环境错误保持unknown，停止后续槽，不重试或填0。

如设备数量必须改变，只允许同时给出 `--runtime-profile <显式完整profile.json>` 和 `--placement-reason <具体原因>`。该profile只能改变 `devices`，不能改精度、LoRA、采样、上下文或解析合同。另存原/新设备数、理由和实际adapter身份差异；不同初始化参数身份不会被冒称为逐位相同的 H1初态。实际权重字节仍由 CandidateActor 正常加载器核对，无额外权重遍历。

选中harness在这里使用四项目专有的真实工具白名单与project观察，因为新任务需要发布/订阅/跨项目采用。保留其原生或SDK会话方式、上下文策略和私有工作辅助，但不把新四项目world接口表述为与H1六情境工具集合逐项相同。

## 明确的新义务再激活

`HarnessWorker` 的旧任务 done 锁不能只靠外层 scheduler 删除停止标签来恢复。四项目采集器因此增加局部 `reactivate_new_obligation` 派发：只在角色已done、当前public观察确有同角色新的有效work时执行；保留原Conversation、私有笔记、历史、meter和格式错误计数，仅释放旧任务done锁，并给同一SDK会话加入明确的环境新义务消息。SDK公开send_message/run处理PAUSED/FINISHED会话恢复，采集器不生成新的业务动作。

此扩展只在四项目collector中，未改正在运行的H1或公共HarnessWorker。CPU控制真实创建WorldCore新义务，随后真实SDK处理 note→done→新义务→done：第3次实际fixture transport请求出现新work与原私有note，decision meter由2增至3，未重置预算/记忆。该证据是实际SDK机械流程加人工响应，不能称为模型自主处理变更。
