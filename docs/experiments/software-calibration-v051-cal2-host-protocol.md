# v051 CAL2 十八槽独立宿主

本宿主只承接静态库存中的十八个 CAL2 槽；不重跑 CAL1，不读取 HOLD 业务材料，也不启动训练。六个固定任务的 R/P/U 顺序、seed202610170551—556、每槽500000 token与128决定/attempt均从原库存校验后保留。P/U的32次成员公开测试与R的128次原生query/action分别记账，不把两种工具机会说成相同。

## 独立准入与来源冻结

启动前必须同时绑定三个独立凭据：CAL1阶段解释与进入CAL2的root release、六题来源与真实初始输入资格、root最后汇总的compound admission。必要检查键集合固定；任一缺项、false、未决或引用变化均拒绝准备。原CAL1两个用户中断请求、七个已完成但缺终态guard请求及全48正式均值null继续保留；不从CAL1成绩选择CAL2题目、执行器或门槛。

来源凭据中的相对路径只在新宿主内按原仓库根解析为绝对引用，原凭据和SHA不回写。四个已测试PWS模块逐一匹配原SHA/字节后才快照；沿用原来源30次状态执行、PWS十二项不同控制和六个真实SDK初态分词记录，不重复执行。mini/shell/统一runner的旧控制亦直接绑定。新增宿主控制只覆盖本轮冻结、接线、调度、费用汇总及停止逻辑；R权威评分树的新增纯函数控制单列。

prepare要求工作树已提交，复制本次完整src/scripts源码，记录commit、逐文件SHA、原模型manifest、S-star4/4完整checkpoint文件引用、固定mini清单、来源和控制引用。worker重新验证冻结绑定后，才进入资源预约。没有新模型资格请求，没有候选长度或seed替换。

## 新资源范围与每槽新驻留

按用户2026-10-18最新指令，允许物理GPU0—7，最多四个本项目resident；取消GPU2/5排除及无compute/util0/连续60秒门。继续精确复用r3/r5容量预约：装载前实际空闲至少46080MiB，目标为min(73728MiB, floor(free−1024MiB))且至少45056MiB。允许与其他进程共享容量足够的卡，不控制其他进程。每张卡同一时点至多一个本宿主worker；容量不足等待。

每个槽启动一个新进程并仅加载一个actor；R/P均原始权重，U仅原S-star4/4的actor张量，不安装critic、Adam或旧RNG。全部条件使用同一project数值路径、18432/2048、nonthinking、temperature0.7及HF max_time600秒。原始模型和actor指纹、无梯度/更新、episode RNG恢复继续在正式闭合时检查。

只有独立进程留下完整的零模型startup-resource-unavailable回执、且该槽尚未进入装载时，才能再排队创建一个新资源尝试。创建slot started回执发生在模型装载前；此后即使装载失败也不自动重试。生成后的异常、未知费用或缺guard不重采。

## 时间、资源和子进程闭合

90分钟停止新query、100分钟包含在途动作、关闭和权威评分的硬界保持。宿主保存一个不随生成/测试阶段重置的episode起点；HF600秒是迭代停止，不宣称硬抢占forward。外层另保留生成900秒、装载/预约900秒、准备/评分/测量600秒的阶段故障界、64GiB RSS、128GiB实验文件和20GiB卷余量，以及原120秒遥测失联守卫。收集结束后的只读测量独立计时，不为模型提供新动作。

原始native generation方法的参数与返回不改；每次进入前使用既有r3 native-cache context核查/补足自身可复用allocator缓存，临时预约张量不跨数值边界保留，不改变采样、请求计数或RNG。

所有shell/pytest执行证据与process.json登记均位于该槽attempt根；P/U准备世界也放在attempt/prepared下，避免公开测试登记漏出扫描范围。主动停止worker前和worker退出后都调用已通过控制的登记组helper；只对spec、父PID/start ticks及实际PID/start ticks/PGID/SID充分绑定的独立组清理。没有任意逃逸或未登记后代的全进程树保证。helper未决会暂停未启动库存。

模型前另补一处原生shell环境接缝：`COVERAGE_FILE`指向已经排除交付的`.calibration-tmp/.coverage`，与统一评分器的scratch策略一致。这样原仓库pytest-cov产生的二进制数据库不会被当作UTF-8交付文件。只做新增环境构造的静态AST断言，未重跑旧shell控制或真实仓库测试。

## 两种结果和机械停止

P/U保留原collector的最后合法固定提交R_joint，并独立报告终态工作树R_code/Q_task_terminal；未提交R_joint=0不能替代未知R_code。固定提交与终态树完全同SHA时由已冻结collector复用一次权威验收。R保留原mini完成标记、raw candidate和patch；宿主还原原测试/config/support，只保留预声明生产修改、真删除和合法新helper，再执行一次同源统一评分。原生完成标记本身不构成通过。

唯一费用来源为每个新resident的actual native prepared/started/complete/fault原件。完整回包按真实输入/输出IDs计一次；已开始而未完整回包的请求保留原预约，不填零。上层mini或团队账单仍分别保存；P/U真实使用总额、R实际调用/账本与原生回执必须相符。

正常完成、代码R0/R1、充分绑定的context/token局部执行前拒绝同等允许继续独立槽。只有原生实际费用闭合、终态actor/RNG guard通过、原机械测量continue且R_code已知才记槽安全闭合。任一评分未知、输入/来源/身份/账单不一致或真实执行故障暂停未启动库存；P/U即使R_joint=0也不绕过R_code未知。已在途独立槽依原界闭合，除共同宿主/资源停止外不随意中断或重采。

十八槽收口后没有自动HOLD、追加任务或训练。实际模型结果由本轮独立只读报告给出；本协议及程序化CPU控制不能作为模型能力或学习收益。

## 新增必要CPU控制

首组十二项宿主控制一次通过；第二组五次执行通过，其中三项为R/P/U新worker接线、一项为宿主原生拒绝来源/余额反例、一项是因加强原生prepared/started/complete归属绑定而必须复查的先前账单控制。合计十六项不同pytest控制、十七次累计执行，零失败。没有重复无关已通过节点。另有上述一项环境构造静态断言；R权威树模块的纯函数控制由独立记录另计。

这些控制使用程序给定worker/provider/runner/进程返回，不启动实际shell、GPU、tokenizer、SDK对话或仓库pytest，不消耗模型预算。覆盖原十八槽顺序、独立compound缺项拒绝、相对来源引用、GPU2/5可入选与最多四驻留、每槽新进程、零模型资源尝试可重排、实际费用与不确定预约、episode起点不重置、R0与R1同等继续、R_code未知必停、guard失败必停及登记子组停止前/退出后清理接线。真实helper生命周期控制和旧组件控制继续复用原件。

全部原件和唯一汇总位于`artifacts/software-calibration-v051/cal2-host-controls/`。最终compound admission由root独立汇总、提交和冻结，本子任务没有运行prepare、supervise或worker命令。
