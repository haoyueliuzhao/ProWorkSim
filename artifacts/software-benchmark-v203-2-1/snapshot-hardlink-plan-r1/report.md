# 历史快照硬链接去重只读计划

本计划未改变历史文件、目录、链接、权限、时间戳、账本或运行状态，未调用Docker/API/服务。只从 `runs/software-benchmark-v*/<直接batch>/episodes/<episode>/` 的baseline/terminal snapshot provenance读取已有SHA，结合同回合result/quiescence与目标文件lstat；没有遍历rootfs，没有读取或重新哈希大快照内容。

扫描4318份provenance，接纳4262个快照路径。实际共读取9079份小JSON（包括result和quiescence），约7.7秒。55项缺少合格终态元数据，1项清理证据不足，被排除。所用batch没有active resource claim；回合需要已结束状态，quiescent=true、all_owned_objects_removed=true、空cleanup_errors、create_result_unknown=false且无retained_objects。结果中的quiescence引用与实际小文件哈希相符。

按已有SHA、字节数、device、uid、gid及权限mode分组，排除同inode已去重项。发现97组至少两个不同inode的重复候选。仅替换episode snapshot路径，可保守估计回收 **13.5256GiB**；若执行范围另纳入已精确定位的同批 `content/baselines/<sha>.json` 硬链接别名，并替换丢弃inode的全部别名，潜在量为 **30.1949GiB**。这不是实际已释放空间，显著不足以单独满足约230GiB的释放需求。

baseline已通过既有 `software_benchmark_archive_storage_v064.retain_baseline` 使用内容地址硬链接。一个inode可能有多个episode路径和一个store路径；只把episode路径连到新inode，旧store链接依旧保有全部块。计划因此分别列出episode-only与including-known-store两种数值。没有找到全部硬链接别名的目标inode不计入可回收量；source keeper存在未解析别名时，执行前还需证明整个inode没有writer，或选择所有别名已知的keeper，不能把一条closed回合记录泛化为所有别名都安全。

硬链接与跨盘符号链接的区别在此是实际校验边界：原 `reference()` 使用Path.resolve，硬链接的原绝对路径与resolve结果保持不变，因此原路径、字节、SHA引用仍可保持。目标路径的inode会变；其mtime将继承keeper，多个硬链接不能保留各自不同mtime；keeper及所有关联路径的ctime/nlink也会改变。权限、uid/gid必须匹配，不能为了去重擅自放宽权限。原Docker归档元数据里的mtime属于原容器见证，不应重写成新宿主mtime。

`plan.json` 是待验证候选，不是执行凭证。实际执行需由主任务在相应本项目锁内重新核对终态、无活跃owner、lstat稳定性，并对每个受影响不同inode执行实际内容哈希及字节一致性验证，再用临时硬链接与原子替换、目录fsync留下操作回执。禁止通过修改共享inode内容来更新某一个历史快照，也不得把未知外部硬链接当作已回收。

复算工具：`tools/prepare_snapshot_hardlink_plan_v203_2_1.py`。候选和逐inode路径见本目录plan.json，统计见summary.json。准备程序的分组依据为历史SHA见证，执行方仍须核验实际文件内容，不能把本计划的零payload读取表述为已经完成字节相等验证。
