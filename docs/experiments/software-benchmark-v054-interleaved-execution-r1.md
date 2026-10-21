# v054 MATCH／PROJECT 同卡两回合交错执行 r1

本次修订来自用户对“同卡多题交错尚未上线”的明确继续优化要求。目标是在一题等待CPU工具或公开测试时，让同一张卡处理另一独立题目的生成。REF沿用原服务，不在本次同时增加引擎并发。下面区分已经实现和实际准入／运行状态；不能用CPU程序控制代替原始9B实测。

## 不变的任务、模型和边界

保持原Verified500×REF／MATCH／PROJECT共1500个固定槽、原seed、每题一个实际Agent、原始Qwen3.5-9B检查点、无项目训练适配器；不追加正式任务或重跑已进入任务。单题500000输入＋输出token、128尝试／决定、5400软截止／6000硬截止保持。MATCH／PROJECT原18432上下文、2048输出、非思考、采样与原始CalibrationActor.generate_native完全保留，REF数值路径不变。公开测试仍返回真实完成结果，不向同一Agent提前返回后台任务状态；没有增加工具、bash入口或隐藏反馈。

全局最多8个正式回合。新MP resident同时容纳两个独立会话，REF仍一个；每张GPU只驻留一份本项目模型、同一时刻只执行一个完整原始生成请求，不合并batch、不在token中途抢占。每个正式回合保持自己的4CPU／16GiB资源scope。三组共享既有CPU环境预准备与官方评分服务，官方评分仍最多两路。

## 实现

两个真实CalibrationActor facade共享同一model、tokenizer、Torch对象和原head execution对象；不重新加载权重或重复安装head hooks。每个facade拥有独立窗口、输出目录、身份副本、原服务、账本和连续Torch CPU／CUDA RNG状态。唯一FIFO计算线程在完整请求前安装该题RNG，调用原数值服务，完成同步和原缓存清理后保存该题RNG，再恢复常驻空闲RNG。下一次属于该题的调用从其连续随机流继续，不按每次调用重复reseed。

生成前采用两阶段票据：提交绑定完整原请求、claim及绝对期限的预申请；FIFO授予不执行的轮值；客户端随后确认提交，服务才执行原调用。每会话最多一个等待／执行请求。PROJECT在获得轮值后才写原可信dispatch标记和SDK attempt；MATCH继续使用原server端账本。正常未派发取消有服务端独立回执，释放原预约、保留已消费决定，不伪造usage。已提交调用的输出或费用不明继续保留技术未知，不自动重试。

排队计入原请求与回合时钟，未在获得轮值后重置660秒宿主门。生成票据排队截止为原绝对门减615秒与入队后45秒中的较早者，给原600秒生成及收尾留出时间；非生成begin/count/finish不错误套用615秒门槛。授予后至确认最多5秒，晚到确认不得产生迟到生成。这会改变有限墙钟下的实际工作机会，不能声称原seed就保证全部正式轨迹相同。未派发调度期限单列为资源边界；PROJECT原行政运行框架标签保留，同时输出明确scheduler原因。

单题正常release只证明本题请求、账本及RNG guard闭合，不要求整resident空闲，不暂停另一题的计算。CPU宿主退出时，未派发票据只取消本会话，必要的原finish／RNG收尾进入同一FIFO；重复abort幂等。只有已派发费用或共享模型状态不明才标共享故障。已闭合会话的大请求／response／token trace内存及时释放，磁盘证据及小身份墓碑保留，避免常驻服务随任务数无限积累完整请求。

## 最小必要控制

控制分为三个层面，均保存原回执与源码身份，不重跑旧完整上下文、镜像或正式题：

- CPU owner组合控制：程序化facade／RNG验证独立连续流、FIFO单执行、agent与condenser共账本、B存活时A关闭、取消和迟到提交、共享错误范围。真实Torch facade与GPU未由该控制验证；后续两处实际生命周期修订只补验相关分支。
- CPU客户端与调度控制：两把真实会话flock及第三拒绝、release不停止B、严格双会话准入；真实SingleMemberBudget／原NativeDispatchGate／DispatchDeadline检查获得轮值前不计派发，未派发取消无费用，原660秒不重置；提交后错误保留原不确定费用。后续只补验宿主停止标记两个受影响分支。
- 实际GPU准入：单独授权至多6个短合成请求，四个独立准备会话。基线A1、A2、B1与交错A1、B1、A2逐一比较完整原始输出、input/output IDs、chosen-token logprob和RNG。A为MATCH，A2为condenser，B为PROJECT。不同窗口／响应ID不作为文本差异，但不删除工具参数。没有正式claim或评分，不重复旧16384输入容量资格；准备费用独立记录。

## 上线和解释范围

旧GPU6服务没有原位替换manager或移交模型对象的受管入口，不能安全承诺零重载升级。只停止新派发，已有回合和评分自然结束，保留原模型直到新代码和必要CPU控制就绪。若没有另一张容量合格GPU，GPU6需一次受控停止与重载；REF7不重载。物理UUID lease只能约束本项目，不能保证释放显存期间其他用户不会分配，因此不把一次切换描述成绝对保留显存。新增GPU仍要求A80080GB、剩余至少46080MiB，不要求完全空闲。

旧source／condition／plan与真实结果保留在r9快照和原bindings。新运行使用独立冻结修订，只领取未进入槽；旧操作总账可累计，但不同执行修订不能混报为同一冻结配置的完整500题点估计。CPU控制或有限6请求一致性都不构成全任务确定性、稳定性或吞吐倍增认证。公开测试、其他卡共租及排队长度仍影响实际速度，实际收益必须从新的逐题成本观察另报。

## 当前部署与实际控制结果

北京时间2026-10-21 16:12观察，修订r11已恢复正式派发：`proworksim-v054-formal-queue-r6.service`，bindings-r7 SHA256 `43fb7dde14a7c7abf3a0dc97de8b0de119f41d4f4199f8482793b9b6c24bc3de`，source-manifest SHA256 `a87ae9f03f445cb521d072ba255ed4948f17c141159746d6355c470c484f5ca2`。pool-r4／prewarm-r4分别运行，GPU6 host PID 534313，GPU7原host PID 3199584保持。

实际六请求控制在同一个GPU6模型PID／模型对象内完成，三对原始输出、input/output IDs及chosen-token logprob、RNG前后摘要全部一致；A1为432＋3=435 token、A2与B1的逐条用量见原回执。六次合计1620 token、未结0，四会话均独立关闭，未在会话之间重载模型。[上线回执](../../artifacts/software-benchmark-v054/interleaved-rollout-r1/receipt.json)与[完整实际控制回执](../../artifacts/software-benchmark-v054/interleaved-rollout-r1/01-receipt.json)保留源身份和逐条记录。该有限控制不认证全部任务逐token等价，也不是吞吐测量。

必须披露一次失败的准备尝试：r10首条A1真实生成已完成432输入＋3输出=435 token，但检查脚本把MATCH旧`{path,sha256}`引用交给要求`{path,sha256,bytes}`的通用验证器，误报文件改变。实际响应SHA完全一致、账本已结清，helper的0 known／1 unsettled只是后处理未完成的派生状态；独立只读附录恢复为已知435、未知0，原失败回执未覆盖。窄修只在checker中适配旧引用，通用验证器和生成器未改。因为失败保护已poison旧manager且没有受管解锁入口，需要额外一次显式重载，并以四个新r2准备会话执行完整六请求控制；不是继续伪造旧会话RNG，也不是重跑正式题。

所以本次优化实际准备总计**7次调用、2055 token、正式槽0**，GPU6共启动两次新manager（一次原计划升级，一次上述checker修复后的替换），GPU7重载0。原GPU6运行任务全部自然结束才切换，没有信号中断在途正式回合。不能把本次上线描述成零重载；通过后的新manager在正式回合之间继续保留权重。

排空期间还发现原r9槽83 REF Matplotlib24970的导出限制：公开测试生成3个绝对路径expected-image链接，旧候选捕获器因此拒绝；原29次／464460 token已完整结清，resident已释放，原终态及候选锁均保留。新原生终态导出把链接目标当作不跟随的Git blob，不删除ignored测试产物、不修改原工作树，不放宽PROJECT provider权限。按原同一候选行政闭合后，原官方r5评分为**resolved=true**；新增模型调用0。详见[原生符号链接修复](software-benchmark-v054-native-opaque-symlink-export-r1.md)及[行政闭合脚本](../../artifacts/software-benchmark-v054/administrative-closure-slot83-r1/close_retained_slot83.py)。原故障记录与此评分同时保留。

恢复时39个正式回合已完整闭合；16:12的只读快照为39closed／3running／1458pending。GPU6同时有PROJECT槽17（Sphinx11445）与MATCH槽19（Django16595）的独立collecting会话；GPU7运行REF槽85（Sympy21930）。服务显示两份独立claim、仅一个生成ticket在执行，已进入实际三回合并发，不只是把配置上限改为3。实际任务排序受原冻结的准备就绪条件影响，未以成绩选择。

目前仍没有足够的同任务、同条件前后时序证明端到端提速比例，不能宣布倍增或UTL持续满载。两个会话都等待CPU时GPU仍可能空闲；全局上限8与实际两卡三回合并发分开记录。
