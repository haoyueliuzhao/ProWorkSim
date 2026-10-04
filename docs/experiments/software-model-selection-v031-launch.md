# v0.31 实际GPU修复验证与接续启动

2026-10-04晚，按“修复问题，继续实验”以及后续“先抢占空闲GPU4,6”的要求，已完成CPU修订核验、两张卡预约、真实旧trace GPU对照，并启动两个新组合的全套资格。执行冻结提交为`3baa4783b7a76d3513a4e2a0d07a0eccb3a81475`，工作树`runs/v031-frozen-source`保持干净；CPU绑定结果为`runs/v031-controls/frozen-qualification.json`。

本页是启动与修复验证的固定观察，后续完整资格、筛选及终态以[运行报告](software-model-selection-v031.md)为准。[结构化快照](software-model-selection-v031-launch.json)保留原件引用及当时值，不能把可变supervisor文件的快照hash当作永久hash。

## GPU4、6实际预约与交接

GPU6于北京时间22:00:02.042、GPU4于22:00:12.275各预约76GiB，分配进程分别为3079853、3080393。两张卡的UUID、PID启动ticks、只有自身compute进程的观测和心跳均保留；GPU5的CPU等待预约已取消，没有多占第三张卡。

总驱动PID3104163于22:14:04启动。GPU4在22:14:09释放预约后交给SWE数值对照PID3104374，GPU6在22:14:12交给Devstral数值对照PID3104516；两份handoff记录均为`immediate_capacity_available=true`，probe state的`reservation_handoff=true`。该过程先验证已持有的连续60秒独占证据，再在释放后最多5秒内复核原空闲条件，没有重启60秒空窗计时。

预约记录为`runs/v031-gpu4-reservation/`、`runs/v031-gpu6-reservation/`；实际交接为`runs/v031-dense-probes/reservation-handoffs/{0,1}/reservation-handoff.json`。预约显存占用时间与模型worker时间分别记录。

## 真实旧trace对照结果

两模型都严格重载原v0.30-r1共同状态，actor身份与原采样记录完全相同。只使用各自原先失败的完整trace，未生成新token、未调用优化器、未修改原概率或原文件。

| 对照 | SWE-Next-14B：原第1条 | Devstral：原第3条 |
|---|---:|---:|
| 原完整输入／输出token数 | 433／32 | 10,225／6 |
| 原整序列重算max delta | 0.0543878078 | 0.0181124210 |
| 原整序列重算mean delta | 0.0030140834 | 0.0056520325 |
| 原生缓存no-grad max／mean | 0／0 | 0／0 |
| 新路径no-grad max／mean | 0／0 | 0／0 |
| 新路径train/grad max／mean | 0／0 | 0／0 |
| 全部原目标与完整backward | 通过 | 通过 |
| 原共同状态完整恢复 | 通过 | 通过 |
| 新采样／optimizer步数 | 0／0 | 0／0 |
| 实际分配worker时长 | 28.811610秒 | 40.724319秒 |

原误差门仍为max≤0.02且mean≤0.002。两次旧失败被精确复现，而原生缓存及新完整可微路径都与原行为一致；这把本次偏差定位到生成缓存路径与旧整序列重算的执行差异。该对照没有逐个替换GEMM、attention、norm等算子，因此不能宣称已证明某一个BF16算子是唯一成因。

两条GPU证明都通过，包括所有原目标保留、真实有限非零LoRA梯度、原actor匹配、零新采样/更新、原文件与执行源码未变，以及清梯度后的全bundle恢复。合计69.535929分配GPU秒；每份admission proof另存worker函数内部时长，完整父进程分配时长用于成本账，不省略启动退出开销。

这不是16K输出压力容量证明：SWE原输入较短，Dev原输出只有6个token。真实近16K完整反传仍由接下来的新资格独立验证，见[数值设计](../design/dense-replay-v031.md)。

## 新鲜资格已实际运行

数值证明通过后，控制器自动冻结正式v0.31计划，并在GPU4启动SWE worker PID3107025、GPU6启动Devstral worker PID3107100。两者都从各自原始权重及新LoRA/critic/optimizer 0/0起点进行新资格，旧9B全部12槽只读继承。

截至22:24的观察，Devstral前三项原生接口全部通过；SWE第2/3项通过，第1项生成的XML已正确解析，但path为`/public-note.json`，与要求的`public-note.json`不符。这是实际参数选择错误，不能去掉斜杠后改判，也不归为解析器仍失效。两者前3条新trace的无梯度及有梯度重算误差均为0、完整反传已完成；第4条近16K压力反传仍在进行。记录时没有程序异常，但不能提前宣称完整training_ready或正式筛选成功。

新运行目录为`runs/software-model-selection-v031/`；总接续账为`runs/v031-dense-probes/continuation.json`，日志`runs/v031-continuation.log`。每臂只有完整新资格通过才会进入原六案例×两seed的12槽。所有原失败、原数值复现、新数值证明与新worker成本分别保留；全部终结后自动生成v0.31两份报告并提交推送，不启动未冻结的分配试训。
