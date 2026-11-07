# v145：21项API中断回合的停止代码恢复

本次从v143原批次的21项技术未知中，恢复并冻结了21份唯一停止代码候选：FREE2 11份、REVIEW2 10份。没有调用模型、执行工具动作或进行评分，原回合、账本及技术未知标记均保留。后续评分应作为`recovered_stopped_code`补充端点；它不能证明中断回合正常结束，也不能自动消除原用量未知。

## 恢复规则与已完成工作

全部21项的原controller、actor均有停止证明，容器及卷清理证明完整，controller压缩归档在原导出时已完成流校验。本次再次按恢复所需读取唯一原归档，核对解压流、提交前缀、正式baseline、源文件manifest、源版本摘要及文件策略；选取已停止`managed-world`中`member_001`的唯一`current_version`。导出的UTF-8补丁通过源树往返验证，再写入不可覆盖的候选锁。

选择规则在评分前固定，不查询评分、隐藏测试或参考修复，不在多个成员或历史版本之间择优。actor的`/testbed`是公开测试使用的工作树，可能属于另一个成员或旧测试版本，因此不能替代最终交付成员的源版本。

21份中10份补丁非空，11份`member_001`停止版本仍等于基线。空补丁保留原样，不从`member_002`补拿修改。10066存在一份历史交付记录，但交付来源是v6，停止代码来源为v7，因此不能把v7的代码评分直接视为v6交付评分。

恢复清单见[export-results.json](../../artifacts/software-benchmark-v145/recovery-inventory-r2/export-results.json)，逐项源版本、补丁大小和用量下界见[export-summary.json](../../artifacts/software-benchmark-v145/recovery-inventory-r2/export-summary.json)。候选及锁位于`runs/software-benchmark-v145/stopped-code-recovery-r1/<slot_index>/`，原结果仍位于`runs/software-benchmark-v142/role-pilot40-r1/episodes/`。

## 用量与会话边界

每项仍有且仅有一次未定API请求。新清单保留已结算token下界、未定请求ID及原现金预约，不把未定用量填成0。10090、10096、10104在第一次API请求就中断，已结算下界为0，但实际消费仍未知；21项都没有因离线导出增加API费用。

原归档保存了私有SDK会话记录和两名成员的会话ID，但当前`build_runtime`会重新构造成员预算、调度器和`Conversation`，SDK工具注册也使用新的随机nonce；没有已验证的联合恢复入口来原样还原SDK会话、组织调度、工具关联、所有权及未定请求。因而本次没有声称“原会话续接”，也没有重采模型。将来实现续接需要独立验证这些状态及未定调用边界，不能只把旧消息复制到一个新会话就称恢复原回合。

## 资源与验证

离线导出串行执行，普通用户、2核亲和、nice 10、16GiB地址空间上限，无Docker、网络、GPU及共享服务器配置操作。首个候选导出前发现旧v122的512MiB单文件限制不适用于双成员状态：10066的`state.json`为759,508,937字节的普通文件。失败时未创建候选或锁，r1清单留档；新r2仅将STATE读入上限设为2GiB，源版本及manifest仍受512MiB限制，路径、文件类型、摘要和进程资源限额继续生效。21份随后全部成功导出。

评分时使用独立的`software_benchmark_recovered_validation_v145.validate_recovery_result_bounded`。它核对原停止证据、候选锁、源版本摘要与冻结文件字节，不再次解析巨型状态或重建源树。10066在4GiB地址空间限制下实测验证成功，峰值RSS43,089,920字节，耗时约2.80秒；记录见[验证凭据](../../artifacts/software-benchmark-v145/recovery-inventory-r2/bounded-validation-smoke.json)。7项CPU检查通过，覆盖actor替代、错误成员名单、仍活动写入者、丢弃未定用量、巨型metadata误读和冻结文件被修改等反例。

恢复实现来源为新的v145模块；原v122及v143冻结执行源码未修改。v145导出模块在首份候选锁定后保持不变，后加的有界验证器是独立模块，不使已冻结候选来源失效。
