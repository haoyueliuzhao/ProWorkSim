# v121：PROJECT两阶段恢复说明

本轮仍覆盖原50题，使用同一个DeepSeek Flash非思考模型、一个PROJECT Agent、每题5M输入＋输出token。先完成23题的首次生成，再为已经受系统故障中断的27题各运行一次独立恢复。**后27题已获用户授权，但必须等待前一阶段生成、评分和资源清理全部结束后启动。**

## 两阶段分别处理什么

| 阶段 | 任务数 | 处理方式 | 结果口径 |
|---|---:|---|---|
| v120首次生成 | 23 | 19题此前从未派发；4题只消耗了环境、没有调用模型，换用新环境进行首次生成 | 原任务的第一次模型尝试 |
| v121独立恢复 | 27 | 全部来自已调用模型、随后因系统性参数校验问题中断的固定名单；各从原始仓库和空会话重新开始一次 | `independent_recovery_v121`，独立于旧尝试 |

已复现的故障来自参数比较：实际回包与SDK解析结果具有相同JSON键和值，仅键的排列不同，旧校验却判为不一致。v120改为按JSON值比较，同时保留数组顺序、布尔值与数值的区别，以及原始回包字节。真实SDK控制已证明正常调用可执行，普通参数不合规则返回受管拒绝，不再因此使SDK崩溃。[修复与SDK证据](../../artifacts/software-benchmark-v120/cursor-sdk-control-r2/summary.json)

27题按**是否已调用模型并受本次系统故障中断**确定，不按通过、失败或“接近成功”筛选；旧盘点中没有正式评分请求。恢复不继承旧补丁、旧测试反馈或旧对话，也不从新旧候选中选择较好的一个。[原任务盘点](../../artifacts/software-benchmark-v120/recovery-inventory-r1/summary.json)

## 沿用已验证的执行条件

v121直接复用v120已封存的bundle与实际执行层，不重新构建模型环境，不改变提示、工具schema、上下文、输出上限、history、actor或评分规则。上下文仍为131,072，输入上限98,304，单次输出上限32,768；摘要和Agent继续共用原任务预算。[接线等价证明](../../artifacts/software-benchmark-v120/runtime-wiring-controls-r1/summary.json)、[实际bundle](../../artifacts/software-benchmark-v120/runtime-wiring-controls-r1/bundle-summary.json)

Requests2931的公开夹具资格也复用已完成的真实控制：原Python3.9.20／pytest7.4.4下，私有localhost的HTTP和严格HTTPS均返回200，原仓库CA、requirements和公开测试字节保持一致。该证据证明公开夹具可运行，不代表模型修复通过官方验收；本阶段不再次运行这项诊断，也不增加中性API调用。[真实诊断回执](../../runs/software-benchmark-v118/project-repaired-r1/diagnostic-2/controller-output/controller-result.json)

27份新配置已逐项通过现有v117身份规则和原条件校验，物理编号8500–8526，新的记录seed为20261104012100–20261104012126；每题运行身份均与旧尝试不同。API实际不发送seed，因此这些新seed用于标识与审计，不能据此声称服务端生成可复现。[身份核验](../../artifacts/software-benchmark-v121/identity-review-r1/summary.json)

## 预算、启动和统计

27个恢复回合的新增生成上限为**1.35亿token**，不是预计实际消耗量。继续使用原累计350元API账本，不追加现金；启动前需在v120清理后重新读取真实余款。最多新增108个容器和27个专用卷，并发仍为16对生成、2个评分，合计112 CPU／576 GiB；两个API协调器不得同时运行。新记录保存在`runs/software-benchmark-v121/project-independent-recovery-r1`。[已审阅方案原件](../../artifacts/software-benchmark-v121/independent-recovery-proposal-r1/proposal.json)

旧27题的技术中断、用量和费用完整保留。固定盘点记录了214个正式请求，其中213个已结算、1个用量未定，已知实际用量下界为6,365,091 token。已结算费用与5.24288元未定预约分别保留；预约不是实际支出，也不能为恢复任务而清零。

最终分别报告23题首次结果和27题独立恢复结果，并按任务给出代码通过、合法交付、实际输入／输出／缓存token及未定项。若将两阶段合并覆盖完整50题，应标为**修复后协议下的完整题单结果**，不能改称原50题第一次尝试的通过率。原尝试与恢复尝试的成本各计一次，不冲销旧费用，不将重复尝试当成新增独立任务，不挑选较优分数。

v121运行实现和必要CPU控制现已完成，27项环境资格复用校验也已通过。模型、提示、schema、history和actor继续复用v120，不构建新bundle，不增加中性API调用或重复公共夹具诊断。[运行控制](../../artifacts/software-benchmark-v121/runtime-controls-r1/summary.json)、[评分准备与资格复用](../../artifacts/software-benchmark-v121/grading-transport-control-r1/preparation.json)

已启动普通用户[限时等待启动器](../../tools/start_authorized_recovery_v121.py)：每30秒只读检查v120的生成、评分、资源清理全部完成，且原服务已inactive；条件满足后封存真实余额，按用户已批准的grant启动同名原服务的新生命周期，自动串行接续27题，无需再次确认。最多等待6小时；超时或异常单独留证并停止，不自动重试，不另建并行API协调器，也不影响当前在途任务。

已授权方案原件、冻结源码和旧27题结果均保留。以上准备与文档更新不代表v121已经开始模型生成；实际启动及结果以新批次运行回执为准。


## 本次接续部署状态

用户已明确批准27题独立恢复。普通用户等待进程已启动，PID `346987`，每30秒只读检查前批完整收口；当前为 `waiting_for_prior_cleanup`，尚未启动第二个API协调器。它在全部清理和同名原服务inactive后封存真实现金余额与运行源码、绑定这次授权并启动；任何检查失败均单独记录，且不自动重复启动。当前状态以[等待记录](../../runs/software-benchmark-v121/project-independent-recovery-r1/authorized-start-wait.json)和[实际启动结果](../../runs/software-benchmark-v121/project-independent-recovery-r1/authorized-start-result.json)为准；后一个文件仅在启动成功或出现异常后产生。


## 2026年11月4日13:12收口核对

v120于11:53:12（北京时间）完成23题全部生成和评分流程，取得16通过、6未通过、1评分未定；未定题为pylint-4604，官方侧补丁未成功应用。v121在前批全部清理后于11:53:21自动启动，12:08:56结束：27题均调用过模型，18题正常闭合并完成有效评分（12通过、6未通过），另9题因累计现金准入不足被协调器取消，保留technical_unknown和停止工作树，不填成模型修复失败。两阶段共41题正常生成、40题有效代码评分，28通过、12未通过、10未定；完整50题点估计未取得，不能将这个混合恢复口径写成原50题首次尝试成绩。

原350元累计账本已结算334.30876480元，保留旧未定预约10.48576元，可用余额5.20547520元，低于现行单请求保守预约5.24288元，因此触发现金保护；并非实际已花满350元。本次27题889请求全部结算，没有新增未定预约。23题实际总token55,391,588、平均2,408,329.91；27题44,055,901、平均1,631,700.04，后者包含9个现金中断回合，不能解读为完整求解平均成本下降。两个owner均已释放，待评分与保留对象均为0。

[本次状态及来源](../../artifacts/software-benchmark-v121/completion-status-r1/summary.json)。本次只读统计，没有增额、退款、重跑模型或新增评分。
