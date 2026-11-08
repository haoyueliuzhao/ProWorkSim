# v161：14 个技术故障回合的独立恢复队列

用户已明确批准14题各一次独立恢复，仍共用500元累计上限。v159首波暴露新的观测器错误后，尚未启动的部署更新为r2；原r1准备记录保留。修复及实际启动状态见[观测器修复说明](software-benchmark-v167-observer-repair-and-recovery.md)。

## 范围与身份

恢复对象为最终提案中列明的 14 个原回合，涉及原面板前五个任务。每个原回合最多增加一次独立尝试，新物理编号为 16100–16113，新 `slot_id` 为原身份加 `:independent-technical-recovery-r1`。题目、初始仓库、seed、C0/C1/C2 条件、REVIEW2 双人成员、非思考模型及推理设置保持不变。配置只修改 `slot_id` 和 `slot_index`；原上下文、补丁、反馈、费用和失败记录不重用或覆盖。

原 15703 已有唯一可信候选并完成独立评分，不在新模型队列中。此次不根据代码得分挑选重试，不增加正常模型失败的重复尝试。

每个团队仍共享 5M 输入＋输出 token 和 512 次物理请求上限，包含 agent、历史摘要及通信压缩费用。全批新增 token 上限 70M，属于上限而非预计消耗。现金继续使用原 v157 唯一 500 元 SQLite 账本，无新增额度，不是三组各 500 元。新身份只在实际运行初始化且旧队列已清理后注册。若原账本剩余额度不足，未进入回合明确保留为现金等待／截断（运行状态 `cash_exhausted` 或 `remaining_cash_reservation_insufficient`），不得自动扩额或把它记成正常模型失败。

## 实现与隔离

新 scope、episode、controller、runtime inputs、closure、bundle、runner、launcher 和 waiter 均位于 v161 新文件，不修改冻结 v157/v159 源码。模型运行保留 v159 已验证的来源追踪、HTTP 重试未知预约闭合和先保存后关闭的 finalization 修复，另绑定 v167 的执行器复核凭据与有界测试报告观测；派生统计故障不会打断模型。

交付校验和候选导出保留原函数代码对象，只在私有命名空间重绑精确的 14 项新身份映射；不修改旧模块全局变量。host 的完成用量校验另绑定新计划，仍使用原严格物理请求与保守未知预约对账逻辑。

这 14 回合属于一个固定波次，不套用原 36 回合波间门；生成和官方评分异步执行，个体异常独立保留。最多 16 对生成、4 路环境启动及 2 路评分，总资源上界沿用 112 CPU / 840 GiB。最多 56 个容器和 14 个卷；评分仅涉及五个已有资格的任务，不需要任何真实评分出网。容器维持 `network=none`、`drop ALL`、无宿主绑定或 GPU，不修改共享主机配置。

普通用户等待器最多等待 48 小时，每 60 秒检查一次，内存上限 512 MiB、CPU quota 5%、禁用 swap。它只读 v159 的确切资源释放记录、工作区清理证明和服务状态；只要有活跃预约、未知创建、未完成清理或仍运行的协调器，就不会启动新实验。等待器不创建模型请求或实验容器，超时后留档退出，不自动重启。

## 核验与证据

7 项部署 CPU 控制通过，覆盖完整 14 个实际 host 配置、身份变更拒绝、原交付代码对象保留、实际 episode/controller/FIFO 绑定、14 项单波排空以及未清理旧队列阻止启动。新增 host/API 的 4 项 CPU 控制独立覆盖三类请求共享预算、503 后成功的真实传输形状与捕获、未知预约及禁止第二次消费身份。新版离线 SDK bundle 已实际导入控制器和工作成员入口，未调用模型、下载模型或创建 Docker 对象。

五题评分资格复用原实际 gold/empty 控制，逐项验证环境、测试和官方评分机制一致；新候选使用新评分身份，不借用旧候选分数。

- 题单：[final-independent-recovery-plan-r1/proposal.json](../../artifacts/software-benchmark-v161/final-independent-recovery-plan-r1/proposal.json)
- 部署核验：[deployment-controls-r2/summary.json](../../artifacts/software-benchmark-v161/deployment-controls-r2/summary.json)
- API/预算核验：[host-budget-controls-r1/summary.json](../../artifacts/software-benchmark-v161/host-budget-controls-r1/summary.json)
- 环境核验：[environment-readiness-r1/summary.json](../../artifacts/software-benchmark-v161/environment-readiness-r1/summary.json)
- 具体执行范围：[runtime-authorization-r2/proposal.json](../../artifacts/software-benchmark-v161/runtime-authorization-r2/proposal.json)

`prepare_communication_recovery_v161.py` 准备计划或离线 bundle；`seal_communication_recovery_v161.py` 默认仅生成可审阅资料，显式 `--seal` 才创建最终授权；`wait_communication_recovery_v161.py --start` 是授权后的有界排队入口。上述步骤都不会提前登记模型使用。真实启动、消费和结果应读取新目录中的时间戳、账本和收据，不由本文推断。
