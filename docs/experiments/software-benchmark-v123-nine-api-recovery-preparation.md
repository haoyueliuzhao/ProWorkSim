# v123：九题重新调用API后评分

用户已明确要求“九题重新调用api进行测试后补评”。本轮为v121中因现金门停止的**全部九题**各新增一次独立模型尝试，再评分该新回合锁定的候选。九题身份已经一次固定，不按旧成绩、旧停止树是否接近正确或后续分数选择。本轮不评分旧停止树，也不把新尝试称为原会话的精确续接。

## 固定题单与初态

按原v121物理编号升序，固定新物理编号8600–8608、新seed为`20261104012300＋0…8`。seed只用于本地身份和账务，不发送给DeepSeek API，不承诺API生成可重复。

| 原v121编号 | 新v123编号 | 任务 |
| ---: | ---: | --- |
| 8510 | 8600 | scikit-learn__scikit-learn-10908 |
| 8511 | 8601 | matplotlib__matplotlib-23476 |
| 8514 | 8602 | matplotlib__matplotlib-20826 |
| 8516 | 8603 | sphinx-doc__sphinx-10614 |
| 8518 | 8604 | django__django-13807 |
| 8520 | 8605 | astropy__astropy-8872 |
| 8523 | 8606 | sphinx-doc__sphinx-8265 |
| 8524 | 8607 | pydata__xarray-4687 |
| 8525 | 8608 | sympy__sympy-23824 |

每题从原始公开仓库基线及空会话开始，不输入旧补丁、测试反馈、思考、消息或停止工作树。问题文字、`base_commit`及公开测试入口与原配置一致。旧回合来源只保存在宿主审计材料中；actor公开题目仍仅含`instance_id`、`repo`、`base_commit`、`problem_statement`四项，不加入参考修复或隐藏测试。

## 模型、token与现金

继续使用DeepSeek Flash非思考模式、PROJECT单Agent，复用v120已修复的实际执行层及原bundle；不调整模型说明、工具schema、历史处理和结束协议。每题仍最多**500万输入＋输出token**，九题总上限**4500万token**。这只是上限，不是预计实际消耗。

v122已按用户指令将同一旧账本的可用余额精确调整为**45元**，累计cap为**389.7945248元**。本轮使用这45元，不重新设立现金账本，也不再申请一笔新的API额度。所有旧费用和未定预约继续保留；余额不足时停止新派发并保留未完成状态，不自动增额或再次重采。因此45元并不保证九题都能用满500万token。

原九题共270次API请求，全部已结算；已消耗输入12,349,290、输出44,746，合计**12,394,036 token**，其中缓存命中1,572,608、未命中10,776,682。原已结算保守费用为**18.76648776元**。这些费用不退款、记录不删除；旧九题仍保留现金中断的技术未知身份，不凭新结果回写旧回合。

## 资源与评分边界

准备范围为8个生成pair加2个评分槽，普通用户协调器8 CPU／32 GiB，各actor为4 CPU／16 GiB，各controller为2 CPU／16 GiB，各grader为4 CPU／16 GiB，合计上界**64 CPU／320 GiB**。生命周期总量最多**36个新容器、9个专用卷**，包含九题的actor、controller、代码评分和可能不同版本的合法交付评分；同树时沿既有协议复用对应评分证据，不为凑数量重复评分。

账本API请求并发policy仍为16，没有随资源并发改写。单请求保守预约仍为5.24288元；8次同时预约最多41.94304元，额度会随已知用量结算回收差额，旧未定预约不回收。实际生成、请求与评分并发分别受原调度和现金门限制。

九题没有Requests任务，因而本轮**无需HTTP/TLS评分通道或网络能力例外**。全部容器仍为`network=none`、`drop ALL`，无宿主目录绑定、端口发布或GPU；模型API由原受信任宿主通道直连，不通过代理，不给模型联网搜索答案的入口。只管理本轮自建对象，不改共享服务器配置。复用已通过的环境资格，不新增gold/empty控制、零模型诊断或neutral API调用。

新结果单列为`independent_recovery_v123`。代码通过和合法交付分别报告，只评分新生成结束后锁定的候选，不在旧、新候选间择优。统计九个新回合各自及全组的实际输入、输出、缓存和总token；新组均值以九题为计划分母，未定时明确已知用量边界。旧尝试成本另列，避免把重试成本隐藏或与新组平均token混算。

## 已完成的准备与启动边界

本材料生成时，九份新配置、公开题单、旧／新映射、资源身份及环境资格引用已封存。实际v117身份校验通过；九题旧270条请求均已逐项核对保留，全部原环境资格为通过，新身份在账本中均无已有请求；静态检查通过。准备工具没有发送API请求、创建容器、修改旧源、修改旧结果或改动账本。

用户已授权九次新模型尝试，本材料不再等待新的API或额度确认。实际启动仍须由新v123运行入口绑定同一题单、新现金API视图、最终源码与具体资源授权；本准备材料本身不执行资源操作，也不声称任务已启动。运行目录固定为`runs/software-benchmark-v123/nine-api-recovery-r1`。

证据： [完整准备提案](../../artifacts/software-benchmark-v123/api-recovery-preparation-r1/proposal.json)、[九题面板](../../artifacts/software-benchmark-v123/api-recovery-preparation-r1/panel.json)、[仅公开题目信息](../../artifacts/software-benchmark-v123/api-recovery-preparation-r1/public-panel.json)、[原中断库存](../../artifacts/software-benchmark-v123/api-recovery-preparation-r1/prior-interrupted-inventory.json)、[旧／新映射](../../artifacts/software-benchmark-v123/api-recovery-preparation-r1/original-to-recovery.json)、[旧用量](../../artifacts/software-benchmark-v123/api-recovery-preparation-r1/original-usage.json)、[准备核验](../../artifacts/software-benchmark-v123/api-recovery-preparation-r1/preparation-check.json)。

准备提案SHA256：`2d2b24fd124c902c0814d21f49553cfdc82d9f30dd289f541bc8e808d64fcd7b`。现金调整及备份见[v122预算说明](software-benchmark-v122-cash-amendment.md)。


## 实际部署

本批已按上述具体范围通过工具审批并启动原同名普通用户协调服务的新生命周期。新预算API绑定、原27回合/18评分的全部清理证明、九题新身份与代码/交付评分接线均已通过；起始余额45元。队列先等待本批首个实际模型响应结算，再扩展到最多8个生成任务；生成和两路评分异步。不得用服务启动回执代替模型生成或评分完成数。

[实际启动证据](../../artifacts/software-benchmark-v123/deployment-r1/launch.json)、[实时进度](../../runs/software-benchmark-v123/nine-api-recovery-r1/api-coordinator/progress.json)、[具体运行授权](../../config/v123-nine-api-recovery-authorization.json)。本批所有生产源码已封存，不在运行中修改。

此前pylint-4604评分未定的解释已纠正：原官方日志证明补丁已干净应用，候选删除`import re`导致测试收集阶段`NameError`，属于候选代码失败；原receipt保留，新只读测量将其记为false，不修改模型补丁、不重跑模型或官方测试。[裁定及来源](../../artifacts/software-benchmark-v122/pylint-patch-repair-r1/derived-resolution.json)。

首次实际API路径已结算通过，调度器已从首题扩至8个活动生成任务，第9题等待空位；首路回执见[initial-routes-api-health.json](../../runs/software-benchmark-v123/nine-api-recovery-r1/api-coordinator/initial-routes-api-health.json)。这仅证明新现金接线和实际模型路径已运行，尚不是九题完成或正确率结论。
