# 2026-10-22 主副盘清理与实验派发恢复

用户要求清理无用数据，解决当前九组实验被磁盘预约门限流的问题。本轮保留在途工作区、原任务身份、补丁、候选、评分、账本、模型和镜像；没有下调磁盘保留门槛，也没有重跑模型任务。

## 主盘：回收九组均已结束的共享缓存

原后台回收器仍正常运行。额外找到16个模板：原Qwen三组和DeepSeek六组均已终态，但旧静止回执中的退出竞态、额外preclaim attempt或resource_release缺证使原回收器保守跳过。这不等同于当前仍有进程使用缓存。

独立r2工具固定这16个目录，在原cache排他锁内重新验证144个终态消费者、所有历史attempt、362个scope、进程身份与完整claim slice静止；仍使用原清理器的精确rootfs路径、manifest、设备和无挂载校验。旧false回执与技术未知保持，另写新现场证明和转发完成凭据。

15:33:52—15:34:56已完成16/16回收、失败0，释放原allocated占用61,978,038,272字节，即57.7215GiB。该数字来自所删对象的allocated测量，不把共享磁盘free的全部变化归因于本操作。后台回收器未停，原正式队列与GPU未重启。8项必要CPU控制通过。

## 副盘：保全异常现场后回收展开副本

正常终态Actor的rootfs已由原生命周期清理，重复调用不会带来收益。额外找到47个技术未知Actor遗留根目录；这些回合没有最终candidate，末工作树仍有审计价值。另有17个异常公开测试根目录，外部stdout/stderr/execution导出缺失，测试结果可能只留在内部 `/tmp`。因此不能直接删除这些目录。

首批固定63个对象（46 Actor、17公开测试），可读allocated占用下界212.345GiB。一项历史静止证明不完整的xarray Actor暂保留，不填造旧证明。每项需原回合与全部评分终态、原claim锁、当前worker和所有scope/slice静止、精确根目录身份与无挂载条件。

无损归档使用GNU pax tar和zstd，压缩包留在源副盘。逐成员完整回读核对成员集合、文件内容SHA256、uid/gid/mode、纳秒mtime、软硬链接、xattrs/ACL与稀疏extent；明确不把inode或ctime视为可原样恢复的内容。只有完整验证成功并再次确认静止及全树metadata不变，才删除展开副本。原manifest、日志、claim、result和账单不改；旁挂恢复索引，恢复工具默认写入新目录且拒绝覆写。

首两项真实归档、验证、回收已完成；随后15:45:21启动有限63项批次。同claim串行，最多两个claim并行，每个root操作由systemd限制2CPU、2GiB、IOWeight10、Nice10及1800秒，父进程仅管理。普通单项失败保留原件并跳过；无法证明失败清理worker已退出时停止新增清理工作，防止超出两路上限，不停止实验队列。

归档器的完整fixture往返与拒绝控制、owner/空间门控制、批处理纯内存路由控制均已通过。实际空间收益以成功release后的源allocated减保留压缩包allocated计算；主盘少量清单和回执的占用另计。不会将212.345GiB展开体积直接称为净释放。

## 观测与最终结果

15:47:58已释放8/63，净回收13.759GiB（未扣少量主盘清单），无失败；Qwen已恢复7个在途生成且其最新磁盘准入通过。DeepSeek当时18个在途、目标27，下一题投放后预计余量95.38GiB，仍低于100GiB门，尚不能称已恢复满并发。归档与实验均在持续运行，最终结果另补。

本轮清理采用上述固定有限批次及只读观察；随后按用户“寻找其他可用磁盘”的要求增加第三卷调度接入，见下节。不启动训练、不改变模型参数、不降低API或资源预算护栏。

## 证据与恢复

- [主盘回收说明](software-benchmark-v055-terminal-cache-recovery-r2.md)及[16项回收证据](../../artifacts/software-benchmark-v055/terminal-cache-recovery-r2/)。
- [副盘归档工具及恢复说明](software-benchmark-v055-terminal-rootfs-archive-r1.md)。
- 固定计划：`runs/software-benchmark-v055/terminal-rootfs-archive-r1/plan.json`，SHA256 `2842e8a4ce9476706fce081e9c1b710f29be89dd2caf86c014b850200bd6d8fb`。
- 归档工具SHA256 `a1929b16a0deb0884e08ea66b542451d7bd8780ef6a6e936fd47a1661b233e13`；有限批处理SHA256 `71020bcdcbad655763b938665dc8183f219c9bda24a7db626739f45d7d664bf2`。
- 批次状态、单项操作日志：`runs/software-benchmark-v055/terminal-rootfs-archive-batch-r1/`。压缩包和成员清单仅保存在本机，不纳入Git。

## 新增磁盘：区分普通可用空间与root预留

对四个真实NVMe数据设备的只读盘点显示，系统合计约2.7TB空闲块；其中约1.54TB是四卷各5%的ext4 root预留。普通用户可用量在盘点时合计约1.2TB，分散在/data0、/data1、/data2、/data3，并非另有一个完全空闲的2TB卷。容量随其他用户及当前实验运行持续变化。没有修改全局文件系统预留比例，也没有检查或清理其他用户的数据。

必要实现核验确认，本机Python的`shutil.disk_usage(...).free`原本就是`f_bavail * f_frsize`，旧调度没有把root预留计入普通可用量。新三卷helper使用显式statvfs，保留原可用口径并增加“含预留空闲”和“预留差额”诊断，不应描述为旧容量计算bug修复。

新建用户专用源目录`/data2/proworksim-zhuxinrui/v055-spare-volume-r1`，独立设备66308，绑定到`runs/software-benchmark-v055/tertiary-volume-r1`。普通用户64KiB写入/fsync/读回探针通过，初始普通可用约334.29GiB；保留原100GiB生成底线后，约234GiB可用于新增任务和相应预约。原primary/secondary设备66306/66307保持；/data3没有接入。

真实零模型生命周期使用现成公开scikit-learn-15100模板，持cache共享锁，完成一次clone、两条程序化SDK响应、候选导出及根目录清理；API、GPU加载、正式槽claim和官方评分均0。第一次控制在任何clone/model前因新目录继承setgid导致模式02700而拒绝；仅将新专用目录改为0700后，第二次于16:11:10通过。原失败日志和修正回执保留。

## 三卷调度实际部署

16:14:31 Qwen管理器切换到独立r6，16:14:48 DeepSeek管理器切换到独立r9。只在旧manager睡眠边界停止管理进程，原worker与GPU服务不发信号；Qwen沿用r5 REF→MATCH/PROJECT接管方案，DeepSeek沿用r4财务适配、native r3科学配置与2000元预算。

Qwen、评分、预热、账本与队列状态继续使用主盘；DeepSeek只给原pending生成槽在secondary/tertiary中按实际可用空间扣除预约后选卷。三卷身份和所有在途预约共同核算，原跨宿主flock覆盖选卷、容量门、durable intent及worker启动；三个可能目录都检查preintent，禁止切盘绕过已进入任务。已冻结接口、模型、采样和任务身份不变。

三卷分账11项控制、marker/容量8项控制、新host13项核心与3项窄异常控制、限定Ruff通过。审阅发现的新host模板估算异常穿透风险在freeze前修复：单题元数据故障进入defer集合，后续题继续；公共卷身份故障保留共享准入门。没有重跑已有模型结果。

16:15:01观察DeepSeek27个生成、其中第三卷7个，等于当刻资源目标27；Qwen7个生成保持。随后独立交接核对确认全部1500/3000个原slot身份不变，交接前Qwen7、DeepSeek21个在途worker的原目录/配置/服务身份保持。并发提升同时受到清理和第三卷接入影响，不能全部归因于某一个措施；单个瞬时并发数也不是稳定吞吐率测量。

- [三卷设备与容量准入](software-benchmark-v055-three-volume-accounting-r2.md)
- [Qwen r6与DeepSeek r9宿主接线说明](software-benchmark-v055-three-volume-hosts-r1.md)
- [第三卷真实生命周期及首次拒绝证据](../../artifacts/software-benchmark-v055/tertiary-volume-lifecycle-r1/)
- [管理器交接与原身份保持证据](../../artifacts/software-benchmark-v055/three-volume-host-deployment-r1/)

## 本批最终收尾

截至2026-10-22T08:23:04.447203+00:00，固定63项无损归档及展开副本回收全部完成，失败0；副盘净回收129.890499GiB（源allocated减保留压缩包allocated），加主盘57.721546GiB，本批合计净回收187.612045GiB，未扣少量主盘审计清单与回执。原始异常工作区已保存在验证通过的压缩包中，原实验记录、补丁、候选、评分和账本均保留。被排除的1个静止证据不足Actor仍保留。共享磁盘free变化还同时受实验及其他用户写入影响，不能用上述回收量直接推算最终free。

收尾快照Qwen在途生成7，DeepSeek在途生成26、当刻资源目标26；DeepSeek新第三卷状态{"closed": 21, "running": 9}，在途分卷{"secondary": 17, "tertiary": 9}。生成closed表示生成端闭合，不等于官方评分通过；并发目标可随旧组评分和共享CPU/RAM变化，在途数量短时超过新目标时不会终止已有任务。实际状态与磁盘容量见[最终运行快照](../../artifacts/software-benchmark-v055/three-volume-host-deployment-r1/final-runtime-and-cleanup.json)，归档完整终态见[有限批次回执](../../artifacts/software-benchmark-v055/terminal-rootfs-archive-batch-r1/)。
