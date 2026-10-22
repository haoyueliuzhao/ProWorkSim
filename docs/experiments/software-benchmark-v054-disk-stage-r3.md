# v054 Qwen 磁盘阶段计量 host r3

原磁盘保护对所有活跃回合再次扣除完整预计峰值，已经落盘的主clone既降低真实空闲空间，
又继续计入未来增长预约。这种保守重复扣除限制了DeepSeek并发，即使CPU和内存仍有余量。
本版本仅调整共享磁盘准入的计量方式，不修改任何求解器、模型、单回合资源或科学配置。

新增 `tools/run_qwen_disk_stage_v054_r3.py`。原Qwen正式dispatcher直接继承复用，已封存
的r2预热需求包装继续生效；仅在新的独立host进程内，把共同磁盘snapshot委托给
`proworksim.software_benchmark_disk_stages_v055_r1`。原恢复adoption不重复执行，原rows、
claims、在途worker、GPU驻留模型和评分记录保持原身份。独立planning revision记录本次接管。

共同helper按每个活跃回合实际的`slot.arm`区分原生REF/MATCH和PROJECT。只有host写出的
`public-environment.json`及根文件系统manifest通过完整SHA、任务、源模板及目标路径匹配后，
才将已经完成的主clone从未来增长预约中移除。原生回合仍保留8 GiB工作空间余量；PROJECT
继续预约下一份公开测试clone和8 GiB余量。缺失或无效证据不会获得阶段减扣。

Qwen旧dispatcher在新任务准入时未传入所选arm，本适配器因此仍使用原双clone估算，避免
从同题其他组状态猜测本次类型。任务进入并具有明确arm和host发布证据后，共同snapshot才
使用准确阶段。DeepSeek新任务的单clone/双clone估算由其独立host处理。

预热同样保留原128 GiB冷启动预约；具有准确基线映射和发布证据的已展开模板只预约剩余
初始化clone及余量。已展开初始化clone后仅保留余量。此处不依据目录存在就给信用，不遍历
正在运行的完整rootfs，也不从磁盘空闲量中人为加回已用空间。

两队列继续使用同一`disk-dispatch-r4.lock`，保持观察、准入、durable intent和启动之间的
互斥。生成100 GiB、准备128 GiB余量不变；存在尚未启动的旧消费者补齐需求时，原256 GiB
预热启动空间保护仍生效。未知任务大小、未知阶段和共享元数据异常继续保守处理。

一次必要CPU控制检查了真实r2包装委托新snapshot的路径、当前两队列状态传递、Qwen新任务
保守双clone估算、原共享锁与dispatcher身份以及预热优先余量。控制中没有模型调用、GPU
加载、正式claim、服务变更或真实队列写入。共同helper的阶段与伪造发布证据控制由同次
DeepSeek磁盘阶段修订单独记录。

部署材料位于`runs/software-benchmark-v054/disk-stage-r3/`，小型封存与CPU收据原字节归档
在`artifacts/software-benchmark-v054/disk-stage-r3/`。实际开始使用本修订以planning adoption
和运行状态为准。多卷磁盘扩展属于另一个独立修订，不混入本单卷阶段版本。
