# 第三块真实磁盘的独立准入与分卷预约

本修订为后续新 DeepSeek 回合增加 data2 放置能力，同时显式记录普通用户可用空间与含文件系统保留块的 free。它不移动已经开始的回合，不改题目、seed、模型设置、预算或评分协议，也不自行启动实验任务。

## 卷身份与放置边界

只读盘点发现 `/data2` 是独立的 `/dev/nvme2n1`、ext4、`st_dev=66308`，与已有主盘 66306、副盘 66307 不同。观测时对普通用户可用约 334.32 GiB。`/data3` 也是独立磁盘，但仅约 140.58 GiB 可用，在保留原 100 GiB 余量后可使用容量较少，暂不纳入本修订。

data2 专属源目录是 `/data2/proworksim-zhuxinrui/v055-spare-volume-r1`，项目内第三卷挂载点固定为 `runs/software-benchmark-v055/tertiary-volume-r1`。目录创建、64 KiB 实际读写探针与清理由独立容量准入操作记录；helper 本身不创建、挂载、格式化或搬移文件系统。

独立新模块 `src/proworksim/software_benchmark_disk_volumes_v055_r2.py` 接受一份三卷 manifest，分别引用原副盘 registration 与新第三卷 registration。三卷须为不同的真实 device。每次派发前重新核对清单 SHA、新 helper SHA、source 与 bind 目标 device/inode/owner、marker SHA/UUID 和确切 mountinfo 来源；挂载丢失、符号链接替代或未知 device 均阻止派发，不会落回底层主盘目录。

既有 primary、secondary 活跃回合根据原绝对 worker 路径及实际 `st_dev` 分别记账，新的 tertiary 回合记入第三卷。无法确定位置的预约保守计入三卷，并同时阻止准入。Qwen、共享 cache、准备 worker、Docker 评分、队列状态、claim 与账本仍在原主盘。

## 容量统计与保留块诊断

旧 r1 使用 `shutil.disk_usage(...).free`。本机 Python 实现经检查，该字段已经采用 `f_bavail * f_frsize`；它没有把 ext4 保留块当作普通用户可用空间。data2 的实际准入回执同时记录了约 358.96 GB 普通用户可用空间和约 743.05 GB 含保留块的 free，两者不是同一个调度容量。

新 r2 对三卷显式采用 **`f_bavail * f_frsize`** 作为准入字段 `free_bytes`，与本机旧 r1 的容量语义相同；仅新增 `f_bfree * f_frsize` 的 `free_including_reserved_bytes` 诊断字段。差值另列为 `filesystem_reserved_unavailable_bytes`。实现过程中曾误认为旧 `shutil.free` 等于 `f_bfree`，该判断已被本机源实现与实际计数否定，在部署前纠正；不能把这一诊断增强描述为修复既有容量 bug。任何卷实际可用空间不足仍须拒绝启动。

原生成 100 GiB、准备 128 GiB 底线及相关优先余量不降低。原 phase reservation、公开 clone 完成后的剩余增长计算、generation estimate、admission 和跨队列共享磁盘锁直接复用原函数对象。没有把 data2 的空闲空间合并成主盘空闲，也没有把同一个副盘 bind 或符号链接重复计作新增容量。

## Host 接线接口

新 helper 保留原函数形状：

```python
configure(manifest_reference)
partition_snapshot(snapshot, v054_state, v055_state, volumes, *, placement=_placement)
shared_disk_snapshot(
    *, v055_state=None, v054_state=None, cache=None,
    target_volume="primary",  # 也允许 secondary、tertiary
)
```

`shared_disk_snapshot` 的 `volumes` 包含三卷各自的 `free_bytes`、`active_peak_reserved_bytes` 和 `active_reservations`。调用者必须在同一原共享锁内完成选卷、再次准入、持久 intent 和启动；不能把不同时间的快照相加派发。仅本 helper 准入通过不等于真实新回合已经进入第三卷，实际接管与生命周期控制另由新 host 修订记录。

封存工具 `tools/freeze_three_volumes_v055_r2.py` 仅接受已经挂载并具有独立 receipt 的两个副卷，在真实身份检查通过后写入新的三卷 manifest，不修改旧 registration。

## 必要控制与证据

11 项纯 CPU 控制已经通过，涵盖第三卷与前两卷设备重复拒绝、旧/新 worker 的三卷分账、未知实际设备拒绝、Qwen 移出主盘拒绝、准备只能留主盘、未知路径不释放预约、保留块排除、挂载丢失拒绝和原 floor/phase/lock 函数身份保持。控制没有创建真实挂载、写队列、发模型请求、加载 GPU 或更改服务。

原 11 项回执位于 `artifacts/software-benchmark-v055/disk-volume-control-r2/cpu-control.json`，SHA `4c0987066509395c955732fbd1644d141048e6641c75bd1f3e913a94b62a035a`，绑定初始候选 helper SHA。data2 原探针 marker 使用 `identity` 字段而非 `uuid`；最终 helper 不改写原 marker，而是固定其 `v055-spare-volume-identity-r1` 版本、source/device/owner，并将 `identity` 与新 registration 的 UUID 绑定。针对这项窄改另保留 marker 控制及最终 source 回执，不重复原分卷/锁/计量控制。真实绑定、manifest 封存、跨卷生命周期和 host 部署须使用各自独立回执；CPU 控制不代替这些实际准入材料。

## 实际封存与只读观测

root 已完成 data2 的真实 bind mount。最终 helper 的 8 项补充控制确认原 marker 可用、版本/identity/device/source/owner 任一变更均拒绝，并通过本机 `inspect.getsource(shutil.disk_usage)` 与同一 mock statvfs 证明旧/新可用容量语义一致。

- 最终 helper SHA：`df117c1ec357ef4cab207aca61aa91b16164096adfc82d9c0f80bf6169a205fe`。
- 新第三卷 registration SHA：`9ca2e8e9bbd5f0085579f150f83b041292520f0b54324f0354c89a6b226f31f9`。
- 三卷 manifest：`runs/software-benchmark-v055/three-volume-admission-r2/volumes.json`，SHA `e63806b732f40ecc4c8c85cf7c6710e28a1eac118a292a64135ba31de3092e2a`。
- 最终 marker/容量控制 SHA：`c271298ee911aa3236dfe5e807a9aeb0afc224804f0b98c00e9b0926fde395d0`。

2026-10-22 **16:07:33 CST** 在原共享锁内进行一次实际只读快照，`metadata_error=null`：

| 卷 | 普通用户可用 GiB | 活跃未来增长预约 GiB | 活跃预约数 |
| --- | ---: | ---: | ---: |
| primary / data0 | 329.62 | 69.01 | 7 |
| secondary / data1 | 332.05 | 234.56 | 21 |
| tertiary / data2 | 334.29 | 0 | 0 |

表中可用量尚未扣除预约和原余量底线；每个卷另有约 357.71 GiB 文件系统保留块，仅列入诊断，不能重复加入可派发空间。所有数值只对应观测时点，不保证共享服务器后续容量不变。第三卷此时没有正式回合进入；helper 已封存，host 接线/部署尚未由本专项执行，不能把这一快照描述成已经提高实验并发。

实际快照 SHA 为 `1cdbfefd5c2d45343546f746325eba633e6ee21b7b5ee5d16a44b8b6967cf697`。manifest、第三卷注册、原 marker、初始实际读写 receipt、只读盘点和快照的小型副本集中在 `artifacts/software-benchmark-v055/three-volume-admission-r2/`，共约 11.5 KB；CPU 回执仍放在前述独立目录。没有复制大队列 state、读取他人目录内容或接入第四卷。
