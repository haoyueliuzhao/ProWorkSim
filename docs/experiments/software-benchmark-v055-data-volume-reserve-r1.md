# v055 数据卷预留空间调整：待明确授权

## 当前状态

自动审批拒绝了首次 /data0 调整，进程未创建，三个数据盘均未执行本计划。用户的明确授权问题已发出，在得到授权之前不执行调整，也不通过间接路径规避拒绝。

## 已准备的精确范围

仅修改保留块计数，5%降至2%；不删除文件，不更改挂载、UUID、文件系统特性或项目100/128GiB门槛。该改变作用于整个共享数据卷，不是项目独占容量。系统根目录与/data3排除。

| 数据卷 | 设备 | 原保留块 | 新保留块 | 新增普通可用GiB | 剩余root预留GiB |
|---|---|---:|---:|---:|---:|
| /data0 | /dev/nvme0n1p1 | 93768311 | 37507324 | 214.618633 | 143.079086 |
| /data1 | /dev/nvme1n1p1 | 93768307 | 37507322 | 214.618626 | 143.079079 |
| /data2 | /dev/nvme2n1 | 93768324 | 37507329 | 214.618664 | 143.079105 |

合计预计新增普通可用容量643.855923GiB。原值、精确apply和rollback argv、设备UUID和几何参数已封存；每卷独立执行，任何核验失败都停止后续卷。

## 核验与风险

已完成限定Ruff、实际只读设备/UUID/geometry/挂载身份核对和独立源码/计划审阅。实际执行后同时比较目标reserved_count及 Δf_bavail−Δf_bfree，以分离同期任务真实写入造成的空间变化。不会将新的普通可用容量称为删除数据后的回收量。

保留块配置可以按原count精确恢复；如果新增空间已被使用，回退会降低普通用户可用量，可能再次触发队列门或ENOSPC。因此回退前必须核对当时空间，不能将配置回退描述成无运行影响。

本机e2fsprogs1.46.5的-r分支和superblock仅修改字段写入逻辑支持mounted文件系统此单字段操作：

- [tune2fs.c](https://raw.githubusercontent.com/tytso/e2fsprogs/v1.46.5/misc/tune2fs.c)
- [closefs.c](https://raw.githubusercontent.com/tytso/e2fsprogs/v1.46.5/lib/ext2fs/closefs.c)
- [Linux5.15 ext4 statfs](https://raw.githubusercontent.com/torvalds/linux/v5.15/fs/ext4/super.c)

[冻结计划及审批拒绝回执](../../artifacts/software-benchmark-v055/data-volume-reserve-r1/)。
