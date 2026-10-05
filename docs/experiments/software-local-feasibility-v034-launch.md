# v0.34 修订、P0资格与P1启动记录

**固定8条T开发经历的监督队列已启动。** 北京时间 **2026-10-06 01:00:43** 启动；本快照时两个模型都为`not_started`，GPU均未满足原空闲门槛，新增模型调用和已分配worker均为0。结束后自动生成报告、提交并推送。动态结果以[运行报告](software-local-feasibility-v034.md)和[机器汇总](software-local-feasibility-v034.json)为准，本启动快照不回改。

冻结执行提交为`522f3331c87cae4f7070f6cc798624bad44dc564`，已推送至`haoyueliuzhao/ProWorkSim`。详细设计见[协议](software-local-feasibility-v034-protocol.md)，P0逐项证据、失败历史及范围见[P0报告](software-local-feasibility-v034-p0.md)／[机器摘要](software-local-feasibility-v034-p0.json)。本记录的完整启动身份见[同名JSON](software-local-feasibility-v034-launch.json)。

## 1. 已完成的修订与检查

- 新增directory与name-index两个低领域负担根目标，保留真实Marshmallow Schema—消费者依赖、完整交付、独立验收、私有工作副本和空任务表。没有预置分工或强制通信。
- 对16个预先固定的旧实际请求复现完整native input IDs，合同去重后的离线新请求总量少20581 token，约12.4%。这不是575次旧调用或未来模型工作的节约率。
- 另行冻结公开测试反馈投影：保留失败诊断、成员自测完整输出和版本guard，公开通过项的全部明细保存在审计原件。这项新Γ不是无损去重或行为不变。
- 8种实际程序变体符合依赖控制预期，4条真实SDK脚本路线有完整固定交付。最终94个条件native请求均在16K／2048内，最大整条路线预约上界149797／500000；没有模型生成或当前策略支持结论。
- 输出比较和输入保持都保留JSON标量类型，过程满足与观测完整性分开。控制器绑定实际回执与源码hash，缺失／失败／过期预算证据均不能启动。

合同呈现6项、新目标8项、控制器7项不同测试覆盖均通过；这些来自必要增量检查，不能合称一次同源全套pytest执行。最终全项目Ruff通过，资格Path修复后只重检资格脚本。P0没有新增GPU资格、近16K训练压力、优化步骤或旧模型重采。旧失败、首次CPU脚本问题、容量失败、差异归档错误和初次资格路径错误均保留，不伪装成首次全通过。

CPU资格已在干净执行工作树通过，SHA256：`9e1e49a30a6fda10374c2e418741f4a4dd5fc6a568378ed3f176689cc5897b34`。正式计划SHA256：`25310a6591bdab2d80bc7f44d725bacdc9a10635dfb6b39c84121cd039aa2f22`。所有新资产、控制器与呈现文件、最终预算旁证及原common／数值引用均绑定；资格修复只改读取引用的Path处理，业务接口与P0计量未改变。

## 2. 实际执行与监督

| 项目 | 本次绑定 |
|---|---|
| 执行工作树 | `runs/v034-frozen-source` |
| 计划 | `runs/v034-plan.json` |
| 原件 | `runs/software-local-feasibility-v034` |
| finish PID／start ticks | `2531909`／`364403898` |
| supervisor PID／start ticks | `2531984`／`364403949` |
| 启动日志 | `runs/software-local-feasibility-v034-finish.log` |
| 启动模式 | `software_local_feasibility_v034 finish ... --publish` |

启动健康检查确认两进程身份匹配、存活且监督状态新鲜。最多两个owner并行，各占一张满足原条件且稳定60秒的A100 80GB；优先4、6，其余原授权卡按固定次序候选。不提前预约显存，不影响其他作业。原单加载900秒、单episode2400秒、边界600秒、worker RSS64GiB、产物128GiB和卷预留20GiB保护保留；累计GPU／worker／统一墙钟上限仍为空。

每模型固定四槽：seed `202610060701`下directory→name-index，member_a先手；seed `202610060702`下name-index→directory，member_b先手。9B恢复原3／3 common，Devstral恢复原0／0 common；不作新的参数更新。每episode两成员共用128次决定、128次attempt、500000实际token、32次实际测试；16K上下文和2048单次输出不变。没有新S组、新模型下载、额外失败重试或旧16槽重跑。

## 3. 成本、结果与后继边界

本快照新增GPU worker成本为0；等待是排队墙钟，不算GPU占用。后续只按本阶段逐卡worker区间并集核算，不混入旧v0.33的2.591725 GPU小时或历史预约。逐槽保存请求／响应、token、世界事件、固定交付、独立验收、过程观测和预算／恢复保护原件。

候选必须同模型四槽全部可信、完整common恢复且至少一条完整成功；依次按成功数、成功根目标覆盖、四槽全量token及固定模型顺序选择。未开始、技术未知和业务失败分开。若全部失败，固定批次结案；不会修改提示后重做同一库存。

P1开发轨迹不能改标训练。即使有成功，也只支持有限局部可行性；P2仍须冻结新训练用途来源、当前策略窗口及根据全体有效产出率／精度规划的重复数，P3仍须根据真实n+和K冻结公平B／G-raw／I-P试训及独立确认。没有自动启动未冻结的训练或分配试验，也没有分配算法收益结论。
