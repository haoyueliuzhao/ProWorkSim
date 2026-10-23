# 六个零模型前置失败槽的独立恢复（r1）

## 范围、授权与旧记录

本批属于用户“集中处理异常”及既有自主修复授权，主协调者完成技术审查后启动。仅处理 `astropy__astropy-12907` 原六个条件槽：原clone失败已证明entered=false、controller routing0、共享API请求0；原错误在actor/controller启动前发生。其余155个已进入或证据不足的生成未知没有重跑。完整事实见[161项只读审计](software-benchmark-v055-deepseek-generation-exception-audit-r1.md)。

新恢复使用原slot_id、seed、六份冻结配置原字节、原r4 controller路由、原始DeepSeek Flash与原预算。DeepSeek不支持provider seed，原seed仅是题单身份，不暗示服务端可复现实验。旧queue继续保留六个technical_unknown，旧claim／state字节未变；恢复状态通过独立记录关联原题，不混写原首轮，也不把新调用归到旧clone失败时刻。

## 独立实现及封存

`tools/deepseek_preentry_recovery_v055_r1.py`在单独worker进程里把原runner的RUN_ROOT绑定到 `runs/software-benchmark-v055/pre-entry-recovery-r1`，创建全新claim namespace。每个新claim在enter之前写 `pre-entry-recovery-link.json`，绑定旧slot、旧claim、旧result及恢复plan。原r4配置与controller activation复用，原validate_activation和validate_config继续检查冻结来源。

`tools/native_uid_clone_preentry_v055_r1.py`只允许该题精确合格manifest、prepared_root、设备和初始化资格，调用原clone及数字所有权映射。没有扩大原bootstrap的整段目录白名单、没有修改原helper，没有重建或重复下载模板；正式每回合的隔离actor clone仍沿原机制建立，六组不共享可写工作区。

| 封存项 | SHA-256 |
| --- | --- |
| 恢复plan | `b5be9b6a9fa502b3c3606520495a15f491bcefc8982074026e2d8543704b8013` |
| 恢复wrapper | `16a2347c3cd73a6d7b9a1b2cd46de7308d7c7c4a0801c9e77b4832ad0a29fbe7` |
| 精确clone helper | `af55ec3a02c498043f1738216e878432688664527c236863f654b9d00be7fd08` |
| 六槽整体资源准入 | `b9fe499df251762887d83eed9372c505ddb6fa28e688dbccea4471e0977691f3` |

准备阶段曾错误读取manifest entry的size字段，低估磁盘峰值；该阶段没有启动worker或模型。原plan、原preflight和当时源码保留在 `preparation-peak-field-fix-r1/`，改用清单实际 `regular_file_bytes` 后重新封存。12项有限准入CPU控制、3项新增峰值控制通过；未重复不变控制。新源码Ruff通过。

## 整体资源准入与实际启动

北京时间 **2026年10月23日09:50:13**，在原 `disk-dispatch-r4.lock` 内一次核算全部六槽，确认原两队列生成库存均终态、六个原unit inactive／MainPID0、原claim仍pre-entry、六slot API仍0，原r4 activation通过。

六槽完整两clone最坏峰值合计 **93,269,551,320B**；主盘普通可用822,612,815,872B，仍保守扣除旧Qwen记录的76,494,339,750B预约后，剩余 **652,848,924,802B**，高于256GiB保留门。不是六个worker分别查看同一free然后重复承诺。原生成库存已终态是本次并发准入前提；固定最多六槽，原API64共享门与2000元总预算继续执行。

六个system unit于 **09:54:25.898810—09:54:26.011823** 成功启动，名称为 `proworksim-v055-preentry-recovery-r1-2827.service` 至 `...-2832.service`，每个Restart=no。每个外层launcher单独硬限1CPU／512MiB，原episode slice另限4CPU／16GiB，后者覆盖actor、controller和公开测试。六个episode合计24CPU／96GiB之外，launcher还最多6CPU／3GiB，不遗漏这层资源。首次观察实读六个launcher均 `cpu.max=100000 100000`、`memory.max=536870912`；原resource-slice回执均记录4CPU／16GiB／16384 tasks。

**09:55:39**六个新claim、原题链接、actor clone和entered记录均已存在，全部真实进入首次API调用。该时点共享账本已有70个settled及2个reserved请求。新调用沿原slot_id记账，但来源由新claim和恢复时刻区分；不能改写此前0模型前置失败的事实。

## 实际生成结果

六槽全部结束，三项正常闭合并各自锁定唯一code候选，另三项新技术未知原样保留，不再重跑。

| 条件 | 恢复生成状态 | 实际模型调用 | 已知实际token |
| --- | --- | ---: | ---: |
| REF非思考 | closed | 24 | 444,939 |
| REF思考 | closed | 15 | 264,485 |
| MATCH非思考 | closed | 17 | 210,066 |
| MATCH思考 | technical_unknown：tool arguments JSON解析失败 | 18 | 210,930 |
| PROJECT非思考 | technical_unknown：managed执行完整性失败 | 11 | 156,601 |
| PROJECT思考 | technical_unknown：managed执行完整性失败 | 24 | 379,091 |
| 合计 | 3 closed／3 technical_unknown | **109** | **1,666,112** |

这109个请求已结算共 **1.04466792元**，继续包含在原共享2000元预算内，未另设隐藏预算。生成闭合不等于官方测试通过。两项PROJECT的外层错误记录SDK integration失败；这里不仅凭通用错误把它解释成模型不会修复，也不对其未锁定工作树追加评分。六份原claim及原state经收尾小文件SHA核对均未改变。

## 独立首次评分队列

有限watcher `tools/watch_deepseek_preentry_first_scores_v055_r1.py`实际于 **10:02:34.470559** 启动，system unit为 `proworksim-v055-preentry-first-scoring-r1.service`。固定计划SHA为 `6588e463146aa19681b97f3265c373faa7f94b9370210d6788bd4abb68ab7201`。其部署时六个生成已结束，所以不能宣称这批实际评分时间与生成时间已经重叠；实现上生成收集和官方评分由独立队列解耦，闭合请求可逐项派发，不等待其它槽，也不因单异常停止队列。

三份正常闭合结果产生三个原生attempt1 code请求。使用原 `software_benchmark_scorer_v055`，原request字节、唯一锁定候选、原评分资源与attempt1不改，不套用于旧attempt2补评的r6入口。共享DeepSeek四个grader锁为 `exception-reconciliation-r1/deepseek-scoring-r1/grader-slots/{0,1,2,3}.lock`；评分子进程继承driver／endpoint／grader锁FD，直到评分子进程退出，和其它补评批次合计不超过四路DeepSeek grader。获得资源门之前不写started、不消费评分attempt。

watcher宿主及scorer Python进程单元另设4CPU／4GiB；Docker官方评分容器仍执行原请求的独立限额。宿主包装与容器资源不能合称只有4CPU／4GiB。watcher只接受六槽最多8个首次端点，单个生成／评分异常独立入结果，禁止自动重放，官方测试结果不反馈给模型。

首个接线观察为6个生成已终态、3个code端点排队、0评分终态。当时共享四门均占用，三端点等待资源，没有占满外新增grader。REF非思考于10:05:29获得lane2、REF思考于10:05:39获得lane1，其余端点沿同一共享门等待后进入；未新建另一组容量锁绕开上限。

## 最终收尾：10:06:49

三个首次code评分均正常退出，原官方评分器取得严格 `official_report`，没有新增评分技术未知或第二次评分尝试：

| 条件 | 首次官方code结果 | 评分结束北京时间 |
| --- | --- | --- |
| REF非思考 | resolved=false | 10:06:00.116832 |
| REF思考 | resolved=true | 10:06:10.579913 |
| MATCH非思考 | resolved=true | 10:06:35.538687 |

有限watcher于 **10:06:49** 保存最终summary；六生成全部终态、三个可创建评分端点全部终态。MATCH思考及PROJECT两组新生成仍为technical_unknown，既无可信锁定候选也未另行评分，不将其填作resolved=false。三个official_report只说明该题三种已闭合条件的实际code结果，不把六种条件混成总体正确率，也不从一个不同任务外推完整基准。

最终结果为**六个原零模型前置失败槽实际首次执行后，3个正常生成闭合并完成首次评分（true／true／false），3个新技术未知保留**。旧六个unknown及旧claim仍原样存在，新增109模型调用、1,666,112已知实际token、1.04466792元已结算成本独立归属本恢复revision。没有对新未知再生成、挑选工作树或增加评分attempt。

`first-scoring/summary.json`保存逐slot生成／逐endpoint评分及精确引用；顶层 `summary.json`只作其绑定索引。集中reconciliation应把原首轮与此恢复修订明确区分，不直接重写原queue的closed／unknown计数。

## 证据入口

原生完整记录：`runs/software-benchmark-v055/pre-entry-recovery-r1/`。其中 `plan.json`、`batch-admission.json`、`deployment-intent.json`、六份deployment回执、`first-launch-observation.json`、`generation-final-observation.json`均独立保存。三份未知现场、所有正式候选与补丁继续保留。

首轮与恢复必须在集中reconciliation视图中分开列出：旧六个unknown不可静默覆盖；可把这次经证明0模型前置故障后的首次实际执行作为单独运维修订结果报告。整个恢复不新增不同任务、不另抽seed、不重跑其余155项。

最终发布证据：[恢复summary索引](../../artifacts/software-benchmark-v055/exception-reconciliation-r1/preentry-recovery-r1/summary.json)、[逐项生成和评分最终summary](../../artifacts/software-benchmark-v055/exception-reconciliation-r1/preentry-recovery-r1/first-scoring/summary.json)、[生成闭合及成本观察](../../artifacts/software-benchmark-v055/exception-reconciliation-r1/preentry-recovery-r1/generation-final-observation.json)。归档只复制小型元数据与引用，没有重复复制rootfs、解压历史归档或发布模型消息／补丁正文。

## 按结束后清理授权完成的精确磁盘回收

用户随后明确要求实验完成后释放GPU并清理磁盘。本子任务仅处理这次六槽的临时rootfs及同一astropy题的legacy模板，不触及其它历史工作区或一般native-lazy-cache回收。GPU释放由独立操作记录负责。

窄检查确认：3个正常closed回合的actor/rootfs，以及两份PROJECT公开测试clone，早已由原生命周期自动清理；本轮未再次删除或重复计入收益。剩余3个unknown的actor/rootfs有原all_quiet=true、errors为空与resource_release=true证据，使用独立适配器 `tools/cleanup_deepseek_preentry_v055_r1.py` 精确绑定三路径、新claim锁及system-manager unit，复用原GNU pax tar＋zstd1、完整内容／metadata回读、源稳定检查及descriptor-safe释放实现，没有重跑不变codec控制。

三项均已完整验证并释放展开副本，**3/3成功、0失败**，原展开allocated 9,095,716,864B减保留压缩包allocated 3,461,226,496B，净释放 **5,634,490,368B（5.247528GiB）**；同盘压缩包、members清单、verified／released回执和恢复marker继续保留。每次归档及释放均在对应原scope-registry锁与恢复worker锁内重新核对原／新unit、登记PID／cgroup／slice静默及无内部mount。新独立有限namespace不包含其它任务路径。恢复仍只能写新目录，不能覆盖原位置或改判实验结果。

另以 `tools/reclaim_preentry_astropy_template_v055_r1.py` 对精确路径 `runs/software-benchmark-v054/native-lazy-r3/astropy__astropy-12907/843dcc65484d2d05/rootfs` 复用原严格模板deleter。持原legacy模板锁与同题cache别名锁，核对3个旧Qwen消费者、6个旧零模型claim、6个新恢复及3个评分均终态／静默后，回收 **3,024,695,296B（2.816967GiB）**。旧qualified回执和manifest保留为历史证据，实际源路径及native-lazy-cache同题别名均有eviction marker；后续新实验必须在新的准备generation重建，不把历史qualified当作payload仍存在。

本子任务合计净释放 **8,659,185,664B（8.064495GiB）**，少量新sidecar与审计metadata未扣。主盘普通可用空间在本批前后观察为772.952438→781.006306GiB；其它实验或并行回收可能改变同一盘free，所以净收益按source allocated减保留archive allocated计量，不以整盘差值替代。原API账本、claim、正式候选／补丁、评分、项目源码、配置、模型与Docker镜像保持；三份未知现场以无损归档形式保存。

清理summary：`runs/software-benchmark-v055/pre-entry-recovery-r1/cleanup-r1/summary.json`，SHA-256 `0880d5313f1f37c52e71e1ab6db3a3d85527bfe7a35491d7207ed353cc2f71e8`。发布小证据见[cleanup-r1/summary.json](../../artifacts/software-benchmark-v055/exception-reconciliation-r1/preentry-recovery-r1/cleanup-r1/summary.json)及其索引；本轮没有模型调用或任务重放。
