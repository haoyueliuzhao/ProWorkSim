# v0.31r2 SWE路径契约修订与有界补验

2026-10-04，用户针对SWE“数值与近16K容量检查通过，但首次路径参数错误导致整体资格未过”要求修复并继续实验，随后要求先抢占GPU4。本修订只解决该技术准入阻断；GPU6上的Devstral筛选继续原批次，公共工作世界、六案例、SDK、模型权重、native codec、学习路径与正式验收均保持。

## 原问题与修订对象

v0.31首条SWE响应已被正确解析为`read_public_note({"path":"/public-note.json"})`。执行器要求精确的`public-note.json`，但公开工具schema只把path声明为普通string，未公开这一完整限制。任务文本虽然指定了文件名，schema与执行器的路径契约仍不完整。这里同时存在实际参数选择错误与可修的接口说明缺口，不能把旧失败直接改判通过。

新请求明确给出workspace-relative路径规则，并在公开schema中声明`const: "public-note.json"`。新执行器验证**原样的模型参数**，再用它在实际fixture root内定位并读取真实文件。绝对路径、`..`、`./public-note.json`或其他别名均拒绝；不会删除斜杠、strip、猜测路径或改写模型输出。该唯一公开诊断文件与软件业务案例无关，不提供隐藏验收答案。

## 事前固定的补验边界

本轮只恢复SWE原共同状态，最多新增4次原生调用：

1. 读取实际公开note。
2. 仅当第一次产生真实拒绝且有完整trace时，允许最多一次基于该错误反馈的纠正读取。第二次仍失败即结束。
3. 读取成功后，在原约8K输入下记录实际note中的code与整数revision。
4. 在原约10K输入下，接收控制器实际missing-file异常后再次记录真实note事实。

首次读取成功时共3次调用；发生一次纠正时最多4次。概率检查失败不触发再采样，不补到通过，不追加业务seed。首条失败的原始tokens及反馈同样保留并进入新轨迹的完整数值检查。

新`const`可能在native parser/schema层先拒绝路径，此时反馈必须注明`read_executed=false`，保留原assistant文本，通过user-channel提供实际校验错误；不能补造structured tool_call或tool返回。真正进入文件读取后发生的FileNotFoundError另标文件操作错误。schema拒绝和OS读取异常不能混称。

## 继承已完成的数值资格

SWE原v0.31已经完成四条新trace的行为/有梯度概率核验，max/mean误差全部0；四段完整反传、一次actor及critic诊断更新、保存重载、新身份回流和原共同状态恢复均通过。压力trace合计16,362 token，近16K容量证据真实完成。原整体`inference_ready=false`与`training_ready=false`仍保留，它们不会被覆盖为通过。

这些已有数值证据可继承的条件是：同一原common状态、actor身份、actual profile、recipe、权重manifest、native与学习实现及实际依赖版本。新运行器绑定原SWE的22份不可变回执，包括原请求/响应、common checkpoint、最终qualification、诊断update、updated checkpoint和新身份SDK返回；再次加载后严格migrate并restore原common，不能用新的随机初始化冒充旧起点。

新增3或4条真实补验trace仍逐条执行原max≤0.02、mean≤0.002的no-grad及grad-mode概率门，并对所有原输出完成真实backward。**新增optimizer step为0**；最终清除梯度，完整恢复actor、critic、两个optimizer、recipe、身份、Torch RNG及窗口状态。本轮不重做已经完成的约46分钟压力资格，不把继承证据称作再次进行的16K测试或再次参数更新。

## 正式筛选及并行边界

只有新路径/反馈准入、新轨迹数值门与完整恢复全部通过，才执行SWE原6案例×原2seed的完整12槽。SWE之前正式筛选为0，不挑旧失败槽、不改变案例、seed、角色预算或完整独立验收；正式筛选依旧零更新。原9B和正在运行的Devstral不重跑，不修改其冻结源码或运行文件。

补验失败则本次SWE尝试结束，不自动重复。单新owner、GPU4优先并保留八卡权限；加载900秒、单原生调用900秒、boundary600秒、单episode2400秒、RSS64GiB、128GiB原件和20GiB卷预留门沿用。资格backward无统一时长帽，累计GPU/worker/墙钟及队列截止仍无上限。仅核验并释放本次拥有的预约进程，GPU6既有worker不受控制。

## 记录与报告

新模块为[native_path_admission_v031r2.py](../../src/proworksim/native_path_admission_v031r2.py)，独立运行器为[software_path_recovery_v031r2.py](../../scripts/software_path_recovery_v031r2.py)。新增CPU控制验证路径真读取、别名拒绝、真实缺失错误、parser拒绝的历史承载、3/4调用上界、失败轨迹数值门、零step和完整恢复；原native SDK矩阵、旧16K资格及已完成的正式槽不重复。

新报告只写`software-path-recovery-v031r2.md/.json`，不覆盖仍由原driver维护的v0.31报告。两份报告及源码修订按既有授权提交推送。r2只报告自身SWE结果和明确时间点的其他组合参考，不在Devstral尚未结束时伪造最终三模型选择；也不自动开始未冻结的分配试训。所有旧失败、预约、继承证据、补验及新筛选成本分别记账。

## 启动前CPU证据

路径模块11项控制通过。运行器先完成14项控制，最后窄改后仅补跑受影响和新增的4项，覆盖最终16项定义中的12项未受影响控制与4项最终控制；这些数字有重叠，不能相加称为18项独立测试。两组Ruff及CPU证据绑定脚本的最终Ruff均通过。记录位于`runs/v031-path-repair/controls/`，包含执行命令、退出码、原输出和最终文件哈希。

冻结后的CPU绑定还比较原v0.31代码与公开资料的实际字节、原CPU资格引用及新文件哈希；运行器再检查原SWE的22份真实记录与全部原Python实现。以上是控制器与证据连接检查，不代表真实模型已经通过新路径或正式业务验收。只有实际GPU补验和后续正式记录能支持后两项结论。
