# 五种固定组织的实现与CPU验证

日期：2026年11月1日。按当前汇总文档选定的五组实现：CHIEF 4人、PIPELINE 3人、REVIEW 2人、SPRINT 4人、MATRIX 4人。PEER未纳入本次实现。新增v104组织规则与运行入口，旧v065和历史实验记录保留。

本次没有启动模型、API生成、GPU、Docker或官方评分。新入口目前只接受显式脚本化离线适配器；配置与准备计划中的正式模型、团队总预算和seed均未冻结，`real_evaluation_enabled=false`。

## 五种实际生效的规则

1. **CHIEF集中决策。** `org_assign_task`只有001可调用，绑定任务修订、被指派成员和优先级。授权不会直接改变owner，领取及offer／accept仍沿用原协议。`org_select_patch`决定谁可集成哪个固定补丁；001最终提交前还需选择自己的精确最终固定版本。其他成员的直接通信保持星形边界。
2. **PIPELINE产物交接。** 001用`org_pipeline_design`发布有任务绑定的设计，002用`org_pipeline_implementation`交付固定补丁，003用`org_pipeline_validation`发布同版本实际测试证据与结论。状态推进依赖明确交接；任务修订变化、证据缺失或代码变化会阻止后续步骤，`org_pipeline_return`负责显式退回。001最终树须包含验证补丁的真实`integrate_patch`来源，手写等值内容不能替代交接；最终测试、固定和提交仍须由001执行。
3. **REVIEW版本复核。** 只有002可通过`org_review_patch`接受或要求修改001的固定候选。提交根据当前代码版本的最新独立意见判定；改版后旧接受意见失效，同一版本重复发布不同patch ID也不能绕过最新拒绝。复核不自动执行测试或提交。
4. **SPRINT周期协作。** PO通过`org_sprint_propose`提出任务排序与目标，两名开发者各用`org_sprint_plan`确认工作与计划，SM在证据齐备后显式`org_sprint_start`。已开始周期中的实施和目标协商都计入机会数；当前实现控制值为24，正式实验配额仍待冻结。到期进入检视，不能借目标协商暂停计时或重启旧周期。`org_sprint_inspect`绑定候选和公开测试凭据，两名开发者可复用一次已公开的同版本测试证据，避免强制重复测试；无产物周期可明确记录失败。SM通过`org_sprint_close`记录回顾后进入下一轮规划，不自动启动新周期或宣布成功。
5. **MATRIX双权责。** 001通过`org_matrix_scope`确认工作范围和优先级；001与002分别通过`org_matrix_review`给出项目、技术意见。两类确认绑定候选、全部任务修订及当前范围身份，缺一不可。范围或任务修订变化使旧确认失效；同一代码版本改用patch别名不能绕过任一责任线的最新拒绝。002与实现者仍可在自己的私有树检查、集成和测试公开候选，避免技术确认前无法检查的死锁；001最终集成与提交受双确认门约束。

## 接入既有harness

全部通过真实World／HarnessPort分派，角色名称不替代权限检查。新增组织工具产生普通、可追溯、计入工作机会的成员操作。`org_status`提供有界的公共事件目录，`read_work_event`读取精确记录；不把其他成员的私有代码、测试正文或模型历史放入组织观察。

私有工作区、公开固定补丁、显式合并、同版本测试、预算池和唯一最终候选继续由原harness管理。所有成员共用一个团队预算，不按人数复制。上下文131072、输入98304、输出上限32768；全队512次决定／模型尝试／公开测试及原6小时软限沿用实现基线，正式实验仍须单独冻结配置。

调度按组织状态筛选成员，再公平轮转，不因轮数用尽自动交接。只有真实SDK机会会更新组织计数；周期到期产生可回读的真实状态事件，供等待成员在原会话内恢复，既不创造模型调用，也不重置预算。组织阻塞与执行完整性错误分别记录。当前仍为逐机会的single-writer运行方式，未验证物理并行性能。

接入v103分页参数修复及预算适配工厂。仅001的最终工作树与最后合法提交可导出为双端点；阶段或复核未完成不会导致事后挑选其他成员候选，也不会自动生成提交。

## 必要验证结果

共验证**29项CPU用例及1项真实SDK脚本控制**：治理10项，流程9项，目录／运行装配8项，公共记录与身份隔离2项；SDK控制另计1项。每次发现窄问题后只补跑受影响检查，未为了汇总计数重新运行全套。

- 五组真实World装配与注册成员数量一致，共享预算和私有会话绑定保持；真实运行适配器及非离线调用被拒。
- 越权派工、陈旧复核、重复patch别名绕过拒绝、单边矩阵确认、陈旧任务／范围均被正确拒绝。
- PIPELINE缺少同版本测试、最终树变化或缺少显式集成时拒交；合法交接链可完成。
- SPRINT目标协商不重置或暂停周期时钟；同候选复用一次公开测试证据，无产物周期如实闭合。
- 组织事件可分页回读，私有后续编辑仍不可见；畸形参数及未获调度的调用不产生组织决策。
- 固定版本OpenHands SDK的REVIEW控制建立2个私有会话，执行13个脚本响应，贯穿分页参数、独立复核、同版本测试／固定／提交和唯一候选导出。13221 token为人工计数，用于预算机制验证，不是真实模型消耗或任务成绩。

准备中有两项夹具问题已修正并留档：普通项目解释器不含SDK专用依赖，因此SDK工厂改为实际装配时延迟导入；首次SDK控制试图使用默认用户配置目录，被只读文件系统拒绝，改用本轮专用`/tmp`目录后通过，未修改HOME或用户配置。整合审阅还补齐了重复patch别名的最新意见约束、协商阶段计时及显式集成来源检查。

证据见[联合验证摘要](../../artifacts/software-fixed-organization-v104/validation-r1/summary.json)和[SDK控制回执](../../artifacts/software-fixed-organization-v104/validation-r1/scripted-sdk-control.json)。这些结果验证机制与接口接入，不证明多智能体成绩提升。

## 文件与后续状态

[五组配置](../../config/software-fixed-organizations-v104.json)和[准备计划](../../artifacts/software-fixed-organization-v104/preparation-r1/plan.json)可供审阅。组织目录在[software_fixed_organization_v104.py](../../src/proworksim/software_fixed_organization_v104.py)，公共World与证据规则在[world模块](../../src/proworksim/software_fixed_organization_world_v104.py)，治理与流程分别在[governance模块](../../src/proworksim/software_organization_governance_v104.py)和[flow模块](../../src/proworksim/software_organization_flow_v104.py)，SDK调度和候选导出在[runtime模块](../../src/proworksim/software_fixed_organization_runtime_v104.py)。

`tools/prepare_fixed_organizations_v104.py`只生成配置和未启用的计划，没有启动实验的子命令。本次不恢复任何已暂停队列；真实运行仍需后续明确启动并冻结任务、模型、预算、seed及调度配额。
