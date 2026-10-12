# v049 最终报告：严格 O1 的真实 B 更新与原开发面板收口

本轮授权库存已执行到终态：原八条训练全部正式成功；B完成一次原H=1真实更新，actor/critic从3/3变为4/4；四条原B开发结果为 **R=[1, null, 1, 1]**。DA-s2在生成中收到来源未定的SIGTERM，正式结果与完整实际费用仍未知。原剩余两个DB在用户扩大GPU范围后，于物理GPU0/1首次并行执行且成功闭合。

四个root/member支持块均只有一个达到事前两例门的类别，没有可行I组成方向，Q±更新和八个条件开发槽均未执行。ρ、ε、四单位F_B/Q_B、分支对比和有限差分均保持null。没有S0同面板开发，不能把B参数变化或开发成功解释为已证学习提升。

机器结果：[最终JSON](software-learning-v049-final.json)。完整损失、16条成员分母、优势、梯度、Adam及RNG证据见[训练方法与完整状态](software-learning-v049-final-method.md)。详细版本链、工作行为、费用和资源回执见[最终开发事实](software-learning-v049-final-evidence/development-four-work-facts-r2g.md)与[资源执行审阅](software-learning-v049-final-evidence/r2g-execution-resource-audit.md)。原阶段快照、unknown和停止记录均保留。

## 原库存与来源

原设计为LA/LB各四条训练、B/Q±各四单位开发，最多20槽/10M实际生成token，Q为条件分支。本次开始12槽，11正式R/Q已知且成功、1技术未知；条件不适用8槽，适用未开始库存0。两个人工训练根各四重复不是八个独立新任务；16条成员轨迹也不是16个独立episode。新DA/DB是事前编写冻结的两个人工业务家族，外部仓库数0，不称外部基准或独立确认。

| 阶段 | 冻结提交 | 实际工作 |
|---|---|---|
| 原v049 | e2221fc5 | S0及原五训练，GPU3/4；原记录归因unknown与停止保留 |
| r1 | fa392e24 | 原余三训练、一次B更新、DA-s1和中断DA-s2 |
| r2 | 255fdae6 | 两DB仅等待资源，0worker/0生成；因新GPU授权有意停止等待宿主 |
| r2g | 9d8a8f75 | 原DB-s1/s2在GPU0/1首次执行，无新seed、无重采、无重训 |

旧reader要求预算包装包含世界身份字段；原包装缺字段，但同源manifest、世界start/end、ledger和准备请求可充分绑定三次执行前共享预算拒绝。r1只窄修这一记录接缝，旧47条准入回包同值，恢复原有72条，共119条；原输入输出、R、费用、unknown与停止不改写。原五槽不重跑，原余三完成后唯一registry合成八槽。见[r1协议](software-learning-v049-record-binding-r1-protocol.md)。

## 原八条训练与支持

| 原槽 | 完整seed | 完整回包 | 实际token | 成员测试 | R/Q | 类别 |
|---|---:|---:|---:|---:|---:|---|
| org49-train-LA-r1 | 202610120491 | 14 | 182504 | 2 | 1/1.0 | local_lineage_delivery |
| org49-train-LA-r2 | 202610120492 | 38 | 493282 | 2 | 1/1.0 | local_lineage_delivery |
| org49-train-LA-r3 | 202610120493 | 15 | 196209 | 3 | 1/1.0 | local_lineage_delivery |
| org49-train-LA-r4 | 202610120494 | 32 | 448905 | 5 | 1/1.0 | evidenced_peer_product_delivery |
| org49-train-LB-r1 | 202610120495 | 34 | 495438 | 5 | 1/1.0 | local_lineage_delivery |
| org49-train-LB-r2 | 202610120496 | 18 | 250554 | 2 | 1/1.0 | local_lineage_delivery |
| org49-train-LB-r3 | 202610120497 | 20 | 270431 | 2 | 1/1.0 | evidenced_peer_product_delivery |
| org49-train-LB-r4 | 202610120498 | 35 | 495265 | 5 | 1/1.0 | local_lineage_delivery |

训练合209宿主决定、206完整回包、2781260输入/51328输出/2832588总token、26次成员测试。三次执行前共享拒绝没有伪造生成目标。全部16条成员轨迹、206回包、51328本人输出进入B；每成员轨迹actor分母为16T、critic为16K，51328不是统一损失分母。真实Γ1 native input条件及本人output mask保持，没有按代码作者或成功子集另筛材料。本次实际八条恰好全R1，不能称观察了失败训练样本。

四块LA/001、LA/002、LB/001、LB/002均M=4，门前local3/peer1，门后只有local3，v=.75、b(local)=1、I自由度0。两条peer联合轨迹有真实非同值伙伴采用→接收者同树测试→最终固定交付；每块peer只一例，不能跨root或成员投射拼成两次重复。四条peer成员轨迹共52决定/12136输出仍单位权重入B，v=.75不删除25%目标。G-raw每块仍有两个类内自由度，本轮未执行。

O1保留原两成员身份，staff_done只休眠、不重置会话或预算。接续三训练槽实际有12次staff_done及6次后续真实唤醒，来源为3次较晚伙伴patch_fixed和3次submit，均有后续本人生成。LA-r4、LB-r3存在非同值采用；LB-r4采用前后已同值且最终交付为001本地谱系。LA-r4来源成员在采用前已有固定提交，不能称采用是成功必要原因。原五槽三个任务/认领事件晚于生产编辑，不能回写成实现前分工。原业务拒绝和未呈现反馈保留。见[八槽工作证据](software-learning-v049-r1-evidence/training-eight-work-support.md)及[接续三槽行为](software-learning-v049-r1-evidence/r1-new-collection-behavior.md)。

## 真实 H=1 更新

原配方epochs1、无minibatch、原顺序一次窗口积累；actor/critic LR=1e-5/1e-3，PPO clip=.2，梯度L2 clip1，terminal MC、γ1、无优势标准化、critic系数.5，LoRA r8/alpha16/dropout0。保留原Adam状态与数值code object；只读梯度hook返回None，不增加反向。Q=B及observer同值由事前小CPU控制验证，不冒称又重放了一遍完整9B B。

实际完成414次actor wrapper前向：206有梯度、208无梯度（206首轮核对+事前固定2行后更新测量）；actor/critic backward各206、各一次optimizer step，3/3→4/4。H=1不是一次backward，wrapper前向也不是GPU kernel数。两轮概率核对均206/206通过；已有critic值非零，当前优势全部正。裁剪前actor/critic范数为.050031084567308426/.6273561120033264。

独立一次CPU完整状态比较确认actor 1114091/1114112元素变化、L2=.004814564051435489；critic 833/1025元素变化、L2=.017421175089141885；两个Adam逐参数step与全局step均3→4，动量实际变化。recipe、base/profile、存档CPU/CUDA RNG保持。B完整摘要为ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39。

原JSON-only reporter的full_comparison=false保留原scope，独立CPU比较另列，未在最终汇总重读张量。比较wall约1.4421秒、process约1.5934秒、峰值RSS747016KiB，读取两checkpoint共26881848字节，CUDA API/模型/更新均0。详见[完整状态比较](software-learning-v049-r1-evidence/S0-B-saved-state-comparison.md)。

方向在任何开发前封存：四块均single_qualified_category，16组基础B梯度非零也不能替代I方向支持。没有追加材料、跨root拼支持、换门槛或按开发收益选择。Q±未执行不是Q失败、Q=B或Contribution=0。

## 原四单位开发

| 单位 | seed | R/Q | 完整回包已知数 | 实际token已知小计 | 扣账 | 测试 |
|---|---:|---:|---:|---:|---:|---:|
| DA-s1-B | 202610120591 | 1/1 | 33 | 491926 | 491926 | 7 |
| DA-s2-B | 202610120592 | null/null | 4，另1在途未知 | 39347 | 52396 | 0已观察 |
| DB-s1-B | 202610120593 | 1/1 | 14 | 178399 | 178399 | 2 |
| DB-s2-B | 202610120594 | 1/1 | 14 | 179838 | 179838 | 2 |

DA先手001、DB先手002，均原初态和B4/4。DA-s1验收绑定早先001固定树，后续工作区编辑不改写交付。两个DB各两成员自行修改planning.py并各测试一次，任务/消息/采用/唤醒均0，最后均001本地固定树、included_patch_ids为空。DB1有两个合法固定提交；DB2仅001合法提交，002两次submit_integration业务拒绝保留。不能称所有工具动作成功，也不能由无candidate_adopted否定所有语义信息使用。

两DB恢复B4/4和policy revision4；逐槽四守卫及外层collection guard通过，新增学习/反向0，机械判断continue，无新context/fixed/shared拒绝或全局暂停。闭合开发三槽共61反馈全部保存，55条有后继均首次真实后继呈现；6无后继为DA-s1两次共享预算终止及DB四次staff_done无可达事件。DA-s2完整反馈分母null，不能拼成完整四槽分母。11份测试报告均保存并出现目录/至少一页，实际read_test_result请求0；不强制全读、不把首返回页冒称主动读页。

DA-s2约49.285秒收到SIGTERM：前四次回包只有两次列文件、两次读文件；第五次生成dispatch后未获得完整回包或可确定的实际费用，未记录新工具动作。准备11001+2048=13049 fits18432，账本按不确定预约扣账，累计52396、余额447604。没有slot-result或正式关闭验收，不恢复、重采或补验；该预约不是已知生成量，也不是context/fixed/shared拒绝。201条资源采样正常、未见原宿主主动停止凭据，发送者与来源未知，不能归因仅外部信号、GPU、内部故障或用户消息。原scenario证明B4/4；单槽cleanup guard不证明在途生成可精确恢复，外层guard缺失与逐请求状态不足保留。见[中断核查](software-learning-v049-r1-evidence/development-stop-provenance.md)。

F分母仍为4，既不能以三个已知成功改报F_B=1，也不能将未知填0报.75。完整实际费用/calls仍null，只报告已保存完整回包小计。

## GPU 范围修订与实际资源

用户明确允许任何满足显存要求的GPU后，本轮范围扩为0—7。原r2只有等待、0worker，单独保留其有意停止与8文件；新r2g不覆盖原件。资源适配覆盖查询、旧v037筛选、worker环境、run_worker和装载前检查。原57344MiB空闲门、60秒稳定、自身57344MiB上限、实时6144MiB余量、主机/磁盘/telemetry以及90+10分钟制度均保持。

实际GPU0/1装载前空闲72623/73077MiB，10次合格等待样本保守跨度60.841489秒；内部stable精确写入时刻未独立存档。38/40运行采样的最高自身30606/27922MiB、最低空闲42012/44200MiB，无guard停止或身份绑定问题；采样不是连续风险保证。Popen前requested/actual命令分别记录，supervisor实际命令为r2g，UUID和start_ticks绑定通过。两worker退出0、source前后9d8a8f75、mechanism/host-stop文件均0。旧等待主动SIGTERM来源明确，不与旧DA-s2来源未定信号混淆。

## 唯一成本与必要控制

| 阶段 | 完整回包已知数 | 实际生成token已知小计 | 已执行测试 |
|---|---:|---:|---:|
| 原五训练 | 119 | 1617987 | 14 |
| r1余三训练 | 87 | 1214601 | 12 |
| 原DA开发（含部分） | 37 | 531273 | 7 |
| r2仅等待 | 0 | 0 | 0 |
| r2g两DB | 28 | 358237 | 4 |
| 合计 | 271 | 3722098 | 37 |

合277决定、272attempt、271完整回包，输入3639631/输出82467；另1次不确定预约13049，账本3735147，完整实际费用/calls仍null。五次执行前共享拒绝为训练3次、DA-s1两次，不生成目标。原DA2 reporter测试字段null保留，已有实际测试台账另证其已观察0，已执行总37，不覆盖旧解析。

GPUworker原阶段2162.429730653763秒、r1 32796.446522951126秒、r2等待0、r2g 516.901211977005秒；合35475.777465581894秒=9.854382629328304小时，含唯一S0。B worker 30103.32239460945秒，内部updater 29529.820029708557秒是嵌套区间，不重复相加。两个新DB分别251.8527228832245/265.0484890937805秒。worker驻留不是利用率，训练计算不算新增生成token，旧预算不转移。

| 控制阶段 | 不同案例 | 累计执行 | 保留的失败与最终状态 |
|---|---:|---:|---|
| 原实现/业务来源/学习/Mapper/报告 | 77 | 91 | 7次早期失败披露；最终必要控制通过 |
| r1来源/消费者/宿主/报告 | 27 | 28 | 1次fixture缺scope失败后窄修；四消费者案例已含在27中 |
| r2接续宿主 | 32 | 85 | 无测试失败；流程补充及独立审阅修复分阶段验证 |
| r2g资源与实际命令 | 20 | 21 | 无pytest失败；首次Ruff unused import移除后通过 |

组件回执不再重复累加。原小CPU toy更新单列，不能计为9B更新；原早期runtime临时fixture持久化时已不存在，失败与修订有文字记录，不冒称完整原字节保留。r2停止回执写失败可能漏清理子进程、r2g实际命令记录偏差均在任何新模型启动前修复，并有必要控制；不能称其为旧SIGTERM的已知根因。最终资源55项是既有JSON回执断言，不是55条新pytest或资格题。Ruff与分阶段控制均已保存，未重复旧分词、业务验收或完整状态比较。

## 结论边界与终止

已证实际本人Γ1目标进入原H=1、B发生非零参数/Adam变化、冻结支持下无I方向、B真实加载到开发，以及新GPU范围下两个DB成功闭合。未证B相对S0提升、正Contribution、一般协作因果收益或独立确认。记录修复和资源调整不是策略收益；工作采用、交付成功、参数变化与学习收益分开表述。

本窗口结束，无自动后继。Q±、新方向/seed/窗口、旧26次Contribution试训、3次正式更新、48条独立确认、v037缓存生产以及v046中断库存均未恢复。原unknown、停止、业务拒绝、未呈现反馈和不确定收费全部保留。
