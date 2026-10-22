# 2026-10-22 主盘冷环境预热恢复

## 问题与定位

用户要求处理“新增预热被主盘空间预约门限制”。17:19主盘普通可用约307.26GiB，在途未来增长预约71.40GiB；每个冷模板的新预约为128GiB，此外保留128GiB预热底线，预计余额107.87GiB，故拒绝派发。DeepSeek队列、评分与API并未全局停止，瓶颈在没有现成备用模板。

只读审计确认原阶段抵扣正常：可信缓存manifest/public-environment发布后，冷预约降为初始化clone+8GiB；初始化clone发布后再降到8GiB。当前没有遗漏抵扣。Docker image Size只反映镜像尺寸，原32GiB解包限制仅约束regular payload，不能据此推导导出tar和条目数量的严格总上界。因此本次不直接下调128GiB冷预约或128GiB底线，也不更改原100GiB生成底线。

## 已执行的恢复措施

1. 两份九组及评分均终态的共享缓存采用原r2当前静默证明机制重新准入，保留历史false。18个消费者、47个scope现场静止，原cache独占锁与原严格删除器复用。17:28:50及17:29:03两项成功，释放8,093,892,608B（7.538025GiB），无失败、无模型调用或worker信号。
2. 固定53个主盘DeepSeek异常终态Actor根目录进行无损归档后回收展开副本。单次allocated测量合计187,935,690,752B（175.03 GiB；最终精确值见回执），这不是净回收量。所有项目均通过原scope锁内现场静默预检；其余19个不满足历史条件的候选排除。原异常状态、补丁/候选/账本/评分不改。
3. 复用已验证的GNU pax tar+zstd、完整内容和元数据回读、再次静默/源稳定检查及release顺序。新wrapper仅绑定独立namespace与固定53名单；原63项副盘批次和源码保持不变。最多2个slot并行，每项2CPU/2GiB、IOWeight10、Nice10；普通单项失败保留源并继续，不能证明清理worker已退出时停止新增清理而不停止实验。

真实批次服务为`proworksim-v055-primary-terminal-rootfs-archive-batch-r1.service`，状态位于`runs/software-benchmark-v055/primary-terminal-rootfs-archive-batch-r1/state.json`。压缩包保存在主盘`queue-r1/terminal-rootfs-archive-r1/<item_id>/rootfs.tar.zst`，恢复入口及证明位于独立`primary-terminal-rootfs-archive-r1`。不能将完整原始175GiB都当作释放量，净值须扣除保留压缩包allocated。

## 必要核验与观察口径

新增缓存wrapper的5项边界控制和Ruff通过；归档wrapper只做新namespace、固定53及与旧63不重叠、错量/错namespace/跨盘payload拒绝控制，复用原codec、解压恢复和调度器控制，不重复运行已验证控制或模型测试。独立审阅通过。

只读观察每60秒记录原队列状态、实际预热unit、qualified数量、备用模板、生成实际/目标并发和主盘余量。首轮observer查询systemd bus受执行沙箱限制，仅重启了observer自身；原source、原始样本及execution-environment-correction.json保留，实验服务不变。续测从17:33:54开始，qualified总计可连续比较，续测会话内的new-qualification计数重新从0计算。

17:38:54的五分钟窗口：qualified367→371，DeepSeek20/27，连续多个样本有1个真实active预热，unused-ready仍0，元数据错误为空；第二预热仍缺约9.53GiB。归档10/53完成、失败0，净释放20.23GiB。该阶段只证明恢复在推进，尚不声称稳定满并发。

## 结果边界

本次只处理物理空间供给，没有更改模型配置、单题预算、题单、seed、工具接口、候选规则或官方评分；没有重载GPU，也没有重跑已经进入的任务。异常单列，不改成模型失败。剩余模板持续增长，其他用户也可能写盘，因此一次门通过或瞬时满并发不能保证全部剩余实验的长期容量。最终状态与观察窗口另行补充，既有阈值、共享预约锁和后台终态cache watcher继续生效。

- [两份共享缓存回收证据](software-benchmark-v055-primary-prewarm-relief-cache-r1.md)
- [53项主盘无损归档及恢复说明](software-benchmark-v055-primary-terminal-rootfs-archive-r1.md)

## 恢复验证与交付时状态

17:33:54—17:44:55的11分钟观察中，qualified367→377，正常生成closed增加47、技术未知另增加2；最新生成并发26/27。来自原预热worker的实际start/finish证明，自17:34:50起相邻任务间最长间隔约5.54秒，已恢复连续环境供给，没有此前长时间无预热空转。一处双预热真实重叠仅4.36秒，不能表述成持续2路。unused-ready仍很少（窗口最高1、最新0），冷预热128GiB预约与第二路准入限制保留。

交付快照2026-10-22T17:48:52.188792+08:00：归档26/53、批次状态running、失败或partial 0，归档净回收55.146755GiB；加两共享缓存7.538025GiB，当前合计62.684780GiB，未扣少量证明元数据。DeepSeek实际生成27/资源目标27，metadata_error为空，dispatch_stopped=false。原有限归档服务继续自动完成其余对象，每项成功/失败由原生state与released/verified回执记录；本提交不把未完成部分记作已回收，不需要暂停任务等待清理收尾。

[恢复窗口证据](../../artifacts/software-benchmark-v055/primary-prewarm-relief-observation-r1/)与[交付时运行快照](../../artifacts/software-benchmark-v055/primary-prewarm-unblock-r1/recovery-runtime.json)。此次已恢复连续预热与生成供给，不声称所有剩余模板的长期空间已获保证，也不以短窗速率作完整实验ETA。

只读observer于17:48:56通过自身stop marker正常结束，末次样本381个qualified、2个实际预热、DeepSeek27/27。这个末次双预热快照不替代前述11分钟窗口，也不等于持续双路认证；实验队列与真实归档服务均继续运行。
