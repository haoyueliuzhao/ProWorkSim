# v0.37 精确加权梯度缓存：持久接管已启动

状态：`waiting_for_original_B`。启动时间：北京时间 **2026-10-07 16:05:03 +0800**。源码为独立干净检出 `ced3eaa293b4dfff59e6ffef83d8f90403ec8bc1`；接管进程 PID `1600254`。

当前是等待原B完成的接管监督进程，未加载第二个9B、未启动新候选、未向原实验发送信号。原B仍在GPU5继续训练。本次快照为 `2026-10-07T16:07:04.609130+08:00`：原B反传 **191/682**，行为概率核验通过，actor／critic本窗口实际optimizer步仍为0／0；这个计数不是任务完成率。

## 交接将如何发生

原B必须完整训练、完成16条开发评估、成功退出并完成无损归档。随后接管程序重新核对原supervisor命令、cwd、源码和PID开始标识及新资格，才通过pidfd请求其正常结束。原supervisor负责清理可能刚启动的后续worker；外部任务不受干预。原finisher保存旧状态和报告后，新执行器导入原B的只读结果，并执行全部剩余26试训、416条开发评估、3次正式更新和48条独立确认。

原B结果、optimizer步和GPU成本归入原v0.36，不重复计算或计作新执行。任何来源、数值、评估或归档条件失败都保留实际状态并停止交接，不自动补采或重试。

## 优化及当前证据

只缓存同一原行和同一精确loss权重已经实际反传得到的裁剪前梯度；相同完整common、RNG、原token、分母和数值源码才允许复用。各候选按原行序累积，独立执行原裁剪和AdamW更新，所有开发与确认轨迹保持。

27试训从空缓存的理论计算量为18,414次反传降至4,338个唯一键，减少76.44%。**本次导入的原B没有逐行缓存**：余下26试训自己需要4,300键；正式B另补38键，正式G/I最多再补454键。新执行总量预计4,338–4,792次真实反传，旧B成本另算。

CPU完整updater及原正式mixed-BF16 CUDA小模型控制通过；额外全FP32 CUDA严格逐位门失败，原失败记录保留，未放宽阈值。当前尚未实测9B缓存执行的端到端加速，不报告训练收益或独立I−B／I−G结果。缓存命中、真实新反传和完整行应用在运行中分别记账。

实现提交 `ced3eaa` 已推送远端。后续完成或中断时自动更新本报告并按既有授权提交、推送。

## 记录

- [完整优化协议](software-gradient-cache-v037-protocol.md)
- [准备与检查记录](software-gradient-cache-v037-preparation.md)／[机器证据](software-gradient-cache-v037-preparation.json)
- [当前启动机器快照](software-allocation-v037.json)
- 原件：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-allocation-v037-handoff`，接管日志：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-allocation-v037-handoff.log`
- 新执行根目录（条件满足后创建）：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-allocation-v037`

这份文件是启动时快照。实时等待心跳与原B进度在接管原件`status.json`中；新候选开始后，正式执行报告会覆盖此启动快照，原launch/request记录保留。
