# Qwen REF 生成结束后由 GPU7 接力 MATCH／PROJECT

用户要求在 Qwen REF 组结束后，将释放出的显卡用于另外两组的部分生成。本次仅修订资源交接条件与相应宿主读取接口；原三组各500个槽、seed、模型权重、推理参数、工具、候选导出和官方评分均不变，不恢复训练或重跑已进入的回合。

## 原条件为何不能满足当前运行需求

当前动态资源池原本有 REF→MATCH／PROJECT 转换流程，但要求500个REF回合全部为正常生成闭合、全部取得明确官方代码评分、所有历史token账均完整。14:09的只读观察中，REF已有4个生成技术未知。因此即使后续所有预定生成完成，旧门仍不能自动释放显卡。

GPU空闲与历史结果完整性是不同条件。评分在CPU异步执行；历史技术未知需要保留并单独处理，但不能仅凭历史未知永久占用已无模型工作的GPU。新协议不会把技术未知改成正常完成，也不会伪造 `all_500_ref_scored=true`。

## 新交接边界

1. 原1500个槽及其中500个REF的身份必须与固定清单一致；全部REF生成必须为正常闭合或明确技术未知，不能留有待运行、启动意图或运行中的生成。
2. 在真正达到上述边界时，核对REF生成worker、claim与相关进程作用域已静止。CPU评分可继续；缺失关键静止证据会阻止交接，不能通过填写空白状态跳过。
3. 原GPU7 REF驻留服务须空闲、没有活动claim及在途推理，且声明、进程、systemd invocation与GPU UUID均匹配。只停止这一精确服务，核对退出后再进入MP部署。
4. 退休事件使用独立版本的真实生成终态证据，保留原事件链、技术未知、评分和账本。旧动态资源池源文件及原policy不改写，新增封存修订明确变更的退休语义。
5. GPU7按原MATCH／PROJECT双会话模板部署，复用相同模型与容量证明；实际转换时仍需执行原设备准入和六次短合成请求控制。仅准入通过后接原队列中尚未开始的MATCH／PROJECT回合。

## 执行接线及影响范围

新的pool reader仅针对原canonical dynamic-pool-r4；GPU6的独立kernel源／独立pool保持其既有路径。因为新回合启动时也会验证注册链，除队列协调器和资源池管理器外，未来canonical episode入口也通过独立wrapper安装相同reader。旧owner、controller、官方评分器和在途回合的release流程不改。

部署顺序是先接入队列和未来worker的reader，再接续资源池管理器。所有管理器交接保留原state、devices、已失败设备加载记录、正式claim和在途worker；不会重启当前GPU模型。未来只有REF生成彻底结束时才发生一次GPU7运行模式切换，不能称为跨进程显存原子交接，也不保证其他用户永远无法竞争释放后的容量；实际加载继续受原GPU UUID、容量与lease约束。

当前MP已使用GPU3、5、6。GPU7加入后，MP可由三卡六会话增至四卡八会话，仍受全局会话及CPU、内存、磁盘准入限制。这个会话数变化不是实测吞吐提升比例，不能直接宣称完成速度增加三分之一。

## 验证与部署记录

本轮完成6项生成终态／进程边界控制、8项注册链／资源池转换控制及7项队列／worker路由控制，共21项必要CPU控制。实际模型调用、正式槽重跑均为0。另仅对当前4个REF技术未知做一次只读现场核对：其worker和登记scope均已退出，不会仅因这些历史未知而永久卡住新门。未对尚未完成的500题执行完整终态检查。

2026-10-22 14:17:02（北京时间）已将原队列协调器接续到 `proworksim-v054-formal-queue-ref-handoff-r5.service`；14:17:17再将资源池管理器接续到 `proworksim-v054-dynamic-pool-ref-handoff-r1.service`。交接在旧管理进程睡眠且状态字节不变的边界进行，只向两个管理器发信号，没有停止GPU驻留服务或在途worker。原失败加载记录及正式任务状态保留。

独立overlay SHA256：`a0b5a1e69d1343a2df2247acc208b5e71265dba45f5b80100d8379567dcae3ae`；host revision SHA256：`b579c732e93c642d8213d09d60a052180774f45e85ba9b2c154d7ca6a5ed81dd`。实际GPU7模式转换仍等待剩余REF生成完成；不能将当前CPU控制或等待程序已启动冒称GPU7已成功运行MP。

14:19上线只读观察确认两个管理器均active、状态持续更新且 `conversion=null`；4个旧失败设备记录与部署前逐行同值。该瞬间REF为305闭合、4技术未知、191待运行，正在等待原共享磁盘预约门；因此尚没有采用后新启动的canonical正式worker可供现场观察。未来worker接线已通过CPU控制，不能将此观测描述为新的实际模型交接已通过。GPU6当时两条在途snapshot路径保持，未为检查额外制造模型请求。

小型证据见 [终态边界](../../artifacts/software-benchmark-v054/ref-terminal-boundary-r1/)、[资源池](../../artifacts/software-benchmark-v054/ref-handoff-pool-r1/)、[队列接线](../../artifacts/software-benchmark-v054/ref-handoff-host-r5/)与[部署收据](../../artifacts/software-benchmark-v054/ref-handoff-deployment-r1/)。完整state-before仅保留在本地runs目录。
