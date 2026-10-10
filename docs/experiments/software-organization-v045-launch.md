# v0.45主24槽启动记录

启动时刻：2026-10-10T21:36:17.017144+08:00（北京时间）；持久finisher PID 2507420。

冻结源码 `757b603d3a48d003ddd8af69f154fd3e31622858`，src树 `944e4ae925423b62af54db5c5bd1bef8c5c7f7684ed23a89a533ae4c73035163`。执行目录 `/data1/zhuxinrui/projects/ProWorkSim/runs/v045-frozen-source`；真实运行根 `/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045`。

本快照记录于2026-10-10T21:38:11.960908+08:00，supervisor状态 `running`。快照只反映当时排队/执行情况，最终实际分配以资源与worker日志为准。

已通过65项不同的必要CPU控制、最终Ruff，以及12新材料条件单元准入。原36请求失败检查经只读补核、8独立伙伴初态补形；原false完整保留，无模型资格题。

仅冻结四root×两seed×S1/F2/O3的24槽，八个独立worker块；最多3驻留，物理GPU3/4/5/7依原56GiB空闲稳定60秒门启动。容量不足自动等待，不借用其他GPU。

每槽原9B完整common3/3、16K/2048、3072精确页、128决定/attempt、500000token、32tests。原common每worker恢复一次，逐槽独立初态和seed，无参数/反向更新。安全局部context终止保持成员停止与未呈现事实，继续其他独立槽；完整性故障或缺证暂停未开库存。

总预算上限12000000token、3072决定/attempt、768tests，旧余额不转移。额外C/A探针关闭，旧训练/Contribution/正式更新/独立确认/缓存生产暂停，无自动后继。

| worker | 条件顺序 | 快照状态 | 物理GPU |
|---|---|---|---|
| block-r0-s0 | S1→F2→O3 | running | 5 |
| block-r0-s1 | F2→O3→S1 | not_started | None |
| block-r1-s0 | O3→S1→F2 | not_started | None |
| block-r1-s1 | S1→O3→F2 | not_started | None |
| block-r2-s0 | O3→F2→S1 | not_started | None |
| block-r2-s1 | F2→S1→O3 | not_started | None |
| block-r3-s0 | S1→F2→O3 | not_started | None |
| block-r3-s1 | F2→O3→S1 | not_started | None |

[协议](software-organization-v045-protocol.md) · [准备证据](software-organization-v045-preparation.md) · [启动机器快照](software-organization-v045-launch.json)
