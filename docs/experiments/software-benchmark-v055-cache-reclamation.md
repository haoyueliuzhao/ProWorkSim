# v055 共享原生模板的受限滚动回收

本修订处理运行中的磁盘容量问题。原v054与新v055共用`runs/software-benchmark-v054/native-lazy-cache`，每个任务的原生环境可能占数GiB；同时提前准备全部500个模板会耗尽可用空间。本轮不移动在途任务，不删除Docker镜像、候选、补丁、轨迹、评分或资格材料。回收对象仅为已经没有本轮消费者的共享模板`rootfs`目录。

## 观测与容量边界

2026-10-22 01:05:18 CST的只读审计发现16个任务的原3组与新6组生成和评分均终态，其中12个还满足历史资源释放、完整writer静止、当前systemd scope／PID／cgroup静止以及原cache锁可独占。12个模板的manifest所记普通文件逻辑大小合计43,245,083,032字节，约40.28GiB；这不是已经回收的物理空间。4个任务因某些历史释放或静止证明不完整而排除，不因为它们已显示技术异常就假定进程已结束。

完整审计保留在`runs/software-benchmark-v055/storage-readonly-r1/assessment.json`。公开归档仅保存摘要与其精确引用，避免复制12118行scope观测。审计时data0约345GiB空闲，根协调器稍后观察约307GiB；这些都是特定时点，不能视为固定余量。`/data1/zhuxinrui`实际链接到data0，在该路径建缓存不会增加空间。真正的data1、data2、data3另有容量，但迁移需要新路径资格与生命周期验证，本次先采用原地滚动回收。

只测过一个模板的实际占用：`matplotlib__matplotlib-25479`原生目录的`du`结果为7,627,214,848字节，manifest普通文件逻辑大小为7,126,560,821字节；单个任务不能代表全部仓库。本方案不依据这个样本保证500题可同时驻留。

## 为什么只回收这些目录

原`prepare_rootfs`成功完成后通常已经删除`rootfs.tar`；原生clone、PROJECT公开测试clone实际读取的是manifest的`prepared_root`目录。因此必须等待同题旧3组与新6组全部生成结束，且所有实际writer静止，才可回收该目录。独立正式评分以及旧v054末尾异常评分从锁定候选、补丁、baseline mapping和官方Docker镜像运行，不读取共享原生rootfs。保留这些材料，仍可对同一候选进行官方评分。

原`qualified_paths`和`ensure_native_instance`检查资格metadata，不检查payload是否已被清理。回收器因此保留原`lazy-preparation.json`和其绑定的4份环境／资格manifest，另写明确tombstone；绝不删除整个cache key，以免当前预热器误判缺失并反复重建。当前两批实验同题9个消费者均已终态，不会重新派发，故不会再依赖该rootfs。未来若新增实验，必须先识别tombstone，在新的cache generation中显式重新准备和资格验证，不能只看到旧qualified receipt就复用；本回收器不声称从Docker镜像再导出一定逐字恢复旧rootfs。

## 回收前的必要证明

新工具`tools/reclaim_benchmark_cache_v055_r1.py`不修改冻结r1/r2/r3运行源码。普通用户watcher只选择候选，每次通过一个有限时的独立特权helper执行；helper不接受任意删除路径，而是从固定workspace、固定registry SHA、instance和baseline mapping推导唯一`rootfs`。

每次操作必须同时满足：

- 原v054恰有REF／MATCH／PROJECT各1条，新v055恰有六种condition各1条。全部generation为closed或technical_unknown，全部既有score端点为official_report或technical_unknown；closed生成必须有评分记录。
- 每条生成的引用结果记录资源已释放；其完整quiescence材料显示all_quiet且无errors。随后按记录的invocation、主PID和start ticks、outer launcher、cgroup再次读取系统状态；不存在仍存活的相同进程或非空cgroup。
- 生成与评分worker用户unit均inactive或failed、MainPID为0；新队列没有同题preparer在途。
- 持有与原准备器相同的`native-lazy-cache/locks/<instance>.lock`独占非阻塞锁，且锁保持至删除和回执完成。锁内重新读取9条任务记录，删除前再比较同题投影，其他题正常推进不造成误拒。
- lazy receipt和4份引用metadata仍匹配；payload恰为该cache key下的真实`rootfs`目录，无路径符号链接、设备跨越或内部挂载。使用Python fd式防符号链接攻击的`rmtree`实现，拒绝不支持这种实现的环境。

生成终态包含技术异常不等于模型失败。本工具不修改任何实验结果分类；对历史静止证明不完整的异常保守保留rootfs，等待单独处理。

## 写入顺序、异常与后台限额

helper先写不可覆盖并fsync的intent，绑定source SHA、同题9条终态证明、manifest引用、payload inode／device以及删除前空闲空间；随后只删除`rootfs`。确认payload消失后，在cache key写`cache-eviction-v055-r1.json`，并在独立回收目录写completion。删除中或写入中异常另存第一次failed记录；未闭合intent绝不自动重试。原资格metadata、所有episode目录和`rootfs.tar`即使意外仍存在也不删。

watcher持有独立collector锁，每个周期至多尝试4个helper，周期之间等待60秒，游标轮转避免前面的暂不可回收任务阻塞后项；root helper自身600秒截止，用户端等待620秒。已有failed、未闭合intent、派发状态不明的任务进入持久异常集合，不再自动重试；单题helper异常不阻塞后续候选。它不发服务信号，不创建模型请求，不改调度claim；运行时应给独立CPU／内存／IO限制。磁盘前后空闲空间会受到并发生成／评分影响，completion明确不把空闲增量全部归因于GC。

本措施与新host的准备库存门配合使用：r3仅在未使用ready任务加在途preparer少于8时新增准备，已有preparer收口，生成／评分继续。旧v054预热器本身已有1worker和最多2个未消费模板的限制。回收量受旧三组与新六组共同进度限制，不能保证始终足以满足后续全部500题；100GiB生成、128GiB预热磁盘底线仍保留。

## 实施状态

源码已经完成完整及增量独立静态审查，最终SHA为`add7b61e57b7518f130eda86294b225a30dadacec70ad549dd6ed94649e300de`。两次必要纯CPU边界检查分别覆盖4次helper尝试上限与游标轮转，以及持久异常跳过、单题超时后继续派发后项；实际helper、模型请求与删除均为0。后台启动和每个周期都要求源码仍匹配同一seal。

首次实际单例计划为`matplotlib__matplotlib-25479`，但命令在创建进程前被自动审批拒绝。审批理由是现有实验运行和优化授权尚未明确覆盖删除共享cache rootfs的具体目标，并要求不得通过其他执行方式绕过。故实际回收0、后台GC未启动，不能宣称已释放上述40.28GiB或样本7.1GiB；具体事件存于`cache-reclamation-r1/approval-block-r1.json`。需要明确许可或获得认可的新证据后再走审批。已上线r3的预热库存门不受这一阻断影响。

自动审批原文中的具体理由为：

> 该命令会实际删除共享缓存中的 rootfs，属于不可轻易逆转的数据破坏；用户授权了实验运行和优化，但未明确授权删除该具体缓存及其目标路径。

被拒绝的确切目标是`runs/software-benchmark-v054/native-lazy-cache/matplotlib__matplotlib-25479/e57fdfb0e9bf2591/rootfs`；确切命令、工作目录和完整拒绝原文均保留在blocked receipt。没有创建任何GC后台服务，也没有改用其他路径执行同一删除。
