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

本轮唯一新增后台处理是上述固定有限清理批次及只读观察，不启动训练、不改变模型参数、不降低API或资源预算护栏。

## 证据与恢复

- [主盘回收说明](software-benchmark-v055-terminal-cache-recovery-r2.md)及[16项回收证据](../../artifacts/software-benchmark-v055/terminal-cache-recovery-r2/)。
- [副盘归档工具及恢复说明](software-benchmark-v055-terminal-rootfs-archive-r1.md)。
- 固定计划：`runs/software-benchmark-v055/terminal-rootfs-archive-r1/plan.json`，SHA256 `2842e8a4ce9476706fce081e9c1b710f29be89dd2caf86c014b850200bd6d8fb`。
- 归档工具SHA256 `a1929b16a0deb0884e08ea66b542451d7bd8780ef6a6e936fd47a1661b233e13`；有限批处理SHA256 `71020bcdcbad655763b938665dc8183f219c9bda24a7db626739f45d7d664bf2`。
- 批次状态、单项操作日志：`runs/software-benchmark-v055/terminal-rootfs-archive-batch-r1/`。压缩包和成员清单仅保存在本机，不纳入Git。
