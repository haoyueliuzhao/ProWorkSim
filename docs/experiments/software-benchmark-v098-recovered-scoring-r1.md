# v098：25份历史原候选的独立补评准备

本批承接用户“处理这些问题”，只对已审计封存的25份历史原候选准备官方评分，不调用模型、不选择新补丁、不覆盖原结果。名单来自v095固定恢复索引的26份候选，明确排除已经由v095首批补评的6068。两批独立计划、资源身份和评分目录，避免重复计费、评分缓存混用或修改在途源。

## 候选来源与证据

| 来源 | 数量 | 准入依据 |
| --- | ---: | --- |
| PROJECT终态同步失败 | 22 | 真实受管闭合先锁定唯一终稿，随后同步失败；原候选、完整归档校验、用量对账和静止证据已由v095逐项封存。原result仍为技术未知，不补造正常退出；没有合法交付 |
| PROJECT管理进程丢失外层结果 | 2 | 3171、3459的原controller已经closed并正常退出，原合法交付与终稿均有锁；原owner清理证明、完整原归档、逐请求现金账单一致，外层result原本不存在，继续保留其缺失事实 |
| REF管理进程丢失外层结果 | 1 | 3514原controller正常结束，native_finished和normal_completion均为true；按原candidate-claim、停止后的原完整工作树归档恢复唯一候选，补丁已验证无损往返 |

三项owner结果缺失与22项同步失败使用不同的精确审计分支。准入必须绑定固定索引中的recovered-result、原配置、原slot、候选锁及审计引用；不能将任意unknown或任意工作树目录加入。原controller成员的SHA和长度必须匹配已完整验证的归档成员。原CPU池、官方镜像、控制资格、测试和评分规则保持不变。

3171与3459的交付另外执行原有同版本测试／固定／提交证据校验，并逐一核对终稿与交付的完整代码树及基线。两者同树时复用代码官方结果；不会因为另有一份补丁就宣称合法交付，也不会把缺失controller transfer伪造成普通正常传输。原账单和原异常记录只读。

## 准备的运行边界

- 25个代码端点（REF 1、PROJECT 24），每个只新评分一次；为2个合法交付预留独立端点，只有版本确实不同时才评分。容器上限27，同树复用时实际需要25。
- 先REF与PROJECT各1项获得可信official_report及布尔resolved后扩为4个worker；true/false均通过健康门，不依据模型成绩选择后续任务。共同的评分配置错误暂停未开始队列，单题错误单列。
- 共享原四条grader lane锁。每个容器4CPU／16GiB、network=none、drop ALL、无宿主挂载、端口、GPU或数据卷；host评分子进程使用相同4核、4GiB地址空间。
- 管理器为普通用户服务，指定18核配额、24GiB内存、swap0，不新建系统级slice或修改共享主机。每个任务最终清理自身评分容器。
- 新准入读取实际CPU、MemAvailable和磁盘容量，不将空闲API容器的内存上限之和当成实际占用。CPU需低于85%，内存保留128GiB及每条在途评分lane的20GiB余量，磁盘保留128GiB及既有spool预约；全局lane锁和每个容器硬上限不变。

官方scorer manifest由与实际评分相同的固定独立Python子进程生成，保留完整严格相等校验，避免API tokenizer overlay污染。新源码独立于正在运行或已经完成的v095。

## 必要CPU验证与当前边界

4个实际独立`python -m`子进程执行原`validate_request`完整路径：同步失败PROJECT、3171、3459、3514，均通过；子进程真实限定4核与4GiB。3171、3459另外通过完整交付版本链及同树校验；污染API依赖manifest被原validator拒绝。控制仅创建临时本地claim，无Docker或模型调用，未修改原目录。见[控制结果](../../artifacts/software-benchmark-v098/real-scorer-validation-r1/summary.json)。

本说明发布时仅完成准备与CPU控制，尚未启动真实评分；不能把CPU控制通过称为官方评测通过。计划：[recovered-candidates-r1/plan.json](../../runs/software-benchmark-v098/recovered-candidates-r1/plan.json)，固定候选索引：[combined-ready-results](../../artifacts/software-benchmark-v095/candidate-recovery-batch-r1/combined-ready-results.json)。本批不包含79项首次生成接续、1675／5530环境修订或四项仍缺少可信controller闭合证据的候选。
