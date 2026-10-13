# v050 宿主、运行器与结果测量的有限 CPU 控制

本文件只描述新实现的 CPU 合同检查，不是模型资格、真实模型结果或学习收益证据。原 v049、r1、r2、r2g 源码和历史运行记录均不改写。

## 新执行依赖

宿主先按原构造路径恢复原 v049 完整 B4/4，并引用该 checkpoint 构造新的 S* 声明；不复制旧材料、不再次创建 S0 checkpoint，不作新模型资格。随后固定 `collect-0/1/2` 各八槽，按原24槽位置对3取余分配，每个shard保持登记顺序。全部24条完成后，宿主在没有新GPU驻留的支持阶段只读汇总原导出文件，运行记录准入和可靠类别计数。

若 `run_B50=false`，全部更新和32条件开发均为未尝试的不适用库存。若支持存在，B先实际完成，再封存梯度方向。梯度方向退化时执行S*/B两状态各八单位；有方向时Q±各自再次从原S*独立恢复并真实更新，随后四状态各八单位。每状态两个开发shard，固定前四/后四单位，不按模型结果选择。累计最多56生成槽，最多3 GPU worker并行。

新 `software_organization_v050` 绑定六个任务根和新窗口；运行器绑定新 `software-organization-runtime-v0.50` 版本。原两成员控制描述、O1行为、Γ1投影、3072分页、18432/2048容量、预算及90+10分钟保持；实际SDK worker class精确引用原v049 `worker_type`，其真实类来源和工作事件名称保留。测量器严格要求新v050 episode版本与新case来源，不能用旧episode填新槽。旧算法事实字段中保留 `requests_verified_under_v049` 这一内部标签，其接受版本由新v050运行器绑定，不混淆为旧样本。

## 计算与资源门

GPU0—7采用原r2g已执行的私有资源绑定；装载前57344MiB、60秒稳定、运行6144MiB余量、最多3驻留与其它原门不放宽。宿主主动停止前继续写原因/PID/进程身份回执；无法归属的外部信号不被写成已知发送方。

训练的48小时单分支上限从实际输入验证/概率复核开始计，到保存完整checkpoint结束，不误用episode的6000秒。原单native前向/后续反向 bookkeeping段900秒、loading900秒、普通boundary600秒仍保留。每branch至多3072准入行，前向上界 `2*N+6`；六来自原recipe `post_update_max_decisions=6`，不把v049实际观察的两行强制成新规则。新的只读前向观察器仅记录真实开始/返回及grad模式，在超上界的下次调用dispatch前拒绝，不改参数、传入参数、autograd图或RNG；反向/optimizer计数仍读取原H=1报告。各branch最多actor/critic各一步，新状态允许原算法合法零步边界，最高5/5。

## 已执行控制及失败披露

24个不同CPU案例覆盖：24+32库存与shard冻结、先完成24再CPU门、三条条件路径、拒绝含糊门和擦除已尝试工作、原各段资源门、独立48小时训练门、全部GPU范围、八单位S*差和未知保留、旧SDK真实class来源、新旧runtime拒绝、新训练/开发SDK路线、零信号加载边界、native前向越界前阻断、真实admission列表形状、全部新材料hash冻结及材料变更拒绝。

初次普通`.venv`执行18通过，两个SDK案例因缺依赖跳过；这两个案例随后在原native解释器、`CUDA_VISIBLE_DEVICES=''` 下单独运行。首次两个SDK案例均失败：测试误用了 `evidence_kind=cpu_programmed_fixture` 的transport辅助器，而严格生产测量重建要求原transport的来源标记。模型、运行器、Γ1与测量门均未修改，只将fixture transport设回已有SDK测量控制使用的 `SoftwareContextTransport`；随后两条路线均通过并各产生四条程序响应。首失败的原结果与完整测量存 `software-learning-v050-host-evidence/first-sdk-attempt.json`，通过回执存同目录 `sdk-passing-receipt.json`。这些是显式CPUOwner程序响应，真实9B请求与GPU worker均为0。

追加的前向上界案例单独1通过；admission列表和材料冻结两例单独2通过。另用真实24槽/48成员材料fixture完整经过宿主、准入、支持构建和CPU门的一项集成控制通过，保留R0和unmapped基础材料。合24个不同案例，累计26次实际执行（24通过、2失败），另2次依赖跳过。初次Ruff的未用导入/局部lambda/import位置，以及新增fixture局部lambda均在冻结前修正；最终新增文件Ruff通过。重复只读解析保存的SDK原件不是新SDK执行或模型请求。

集成审阅还在真实模型启动前发现两项实现遗漏并窄修：支持准入的 `decisions` 是行列表，计量必须取其长度，不能直接作整数运算；新材料实际目录为 `examples/software-learning-v050`，需全部入源码冻结。新增列表合同和22个资产的变更拒绝案例覆盖了这两项遗漏。新 `frozen` 还逐次核对六root `source_manifest/source_partition`。这不是对实验结果或候选协议的热改。
