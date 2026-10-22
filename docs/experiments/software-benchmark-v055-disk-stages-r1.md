# 按已完成阶段预约剩余磁盘增长

## 修订结果与边界

原 r4/r5 host 对全部在途任务持续扣除整段峰值预约，故实际已分配的主 actor clone 同时计入文件系统 free 和未来预约。这一保守处理解决了异步克隆超发，但在已有可靠完成证据后仍重复预约，压低了可用并发。

新共同模块 `software_benchmark_disk_stages_v055_r1.py` 与两个薄 host 仅改变未来主机准入计算，保留相同共享 flock、100 GiB generation 余量、128 GiB preparation 余量、冷预热优先门、CPU/RAM 上限、API64 与 ¥2000 预算。不更改 solver、模型请求、单回合限制、任务顺序或在途 worker。

一次只读实际快照中，同一时点 9 个活动任务的旧预约为 139.9443 GiB，新剩余增长预约为 99.7785 GiB，减少 40.1657 GiB 重复预约；当时实际 free 为 424.4786 GiB，元数据错误为空。这是资源准入空间的变化，**不是回收了 40 GiB 物理文件，也不是已经测得吞吐提高的比例**。实际并发仍由所有硬门及队列需求共同决定。

## 运行生命周期依据

v054 与 v055 runner 均先同步完成主 actor clone，再捕获公开仓库、启动 actor/controller。`clone_prepared_rootfs` 等待 bootstrap 的复制子进程成功退出后写 rootfs manifest，随后发布绑定其完整 SHA 的 `public-environment.json`。这些 metadata 保存在 actor rootfs 之外，由 host 写入。

REF/MATCH 的原生 terminal 在这份主 actor 中执行，不调用受管 `PublicTests.run` 的第二份 clone。PROJECT 则持续保留主 actor，并在受管公开测试时额外创建一个同步测试 clone；正常测试完成后清理该 clone。故 PROJECT 不能直接取消主 actor，也仍需为下一份测试 clone 留空间。异常保留的测试 clone 已计入实际 free；本模块不清理它们。

设 `C = regular_file_bytes + entries_count × 8192 bytes`，成长余量固定 8 GiB：

| 类型/阶段 | 剩余增长预约 |
| --- | ---: |
| 新 REF/MATCH，主 clone 尚未证明完成 | C + 8 GiB |
| 新 PROJECT，主 clone 尚未证明完成 | 2C + 8 GiB |
| REF/MATCH，主 clone 完成证据有效 | 8 GiB |
| PROJECT，主 clone 完成证据有效 | C + 8 GiB |
| 冷 preparation 尚无有效提取 publication | 128 GiB |
| cache 提取 publication 有效，初始化 clone 未证明完成 | C + 8 GiB |
| 初始化 clone publication 也有效 | 8 GiB |

Qwen 原 dispatcher 的新启动估计接口不传 selected arm；为避免从同题其他行猜测所选组，其新启动仍保守按两份 clone。进入 active 后，共同 snapshot 根据该行冻结的 `slot.arm` 处理 native/PROJECT 差异。DeepSeek 新 host 明确传递当前实际 launch 的 arm。

## 阶段证明与保守回退

每次阶段折扣要求固定 host 目录、普通非符号链接 metadata、完整 manifest SHA 与 publication 一致、任务身份一致、prepared_root 指向该精确目标，且 numeric ownership admission 为真。对主/初始化 clone 还核对 `cloned_from_manifest_sha256`；对准备缓存核对其冻结请求的 baseline_mapping。

准备请求须来自原 worker 的不可变 job argv，匹配其 request SHA、任务和 cache 根目录。冷模板只有在原导出、提取与 ownership 流程发布完整有效环境后才能从 128 GiB 转为已知的后续初始化增长。初始化复制没有证据时始终保留一份完整 clone；最终模板 metadata 更新而暂时不能与初始化 clone 绑定时也只回退到更保守阶段。

缺少、未写完、错误任务、错误模板 SHA、错误路径或发生变化的 publication 均不能获得折扣。未知模板仍沿用旧 96 GiB fallback；无法读取两队列状态仍拒绝新派发。manifest 的完成验证按 metadata 文件身份缓存；不执行在途树遍历、不读取 actor payload，也不对文件系统实际已分配字节进行猜测或扣减。当前真实 free 已反映落盘内容，本模块只计算之后仍可能增长的部分。

这里的 8 GiB 成长余量、clone 估计和准备预约仍为准入预算，不是对任意命令输出或其他用户写盘的文件系统配额。

## 控制与证据

必要 CPU 控制通过，覆盖 native/PROJECT 新预约、完整 publication SHA/任务/模板/路径绑定、主 clone 完成后的剩余份数、缺证据回退、准备三个阶段、原 100/128 GiB 门与 256 GiB 冷预热优先门、两队列共同记账。没有模型、真实 clone、正式队列写入或既有 payload 删除。

初次 fixture 使用相对路径，被绝对 host 目录保护正确拒绝；只将 fixture 输出转成绝对路径后重跑必要控制。原失败 fixture 保留，不改变生产 guard。

- 共同 stage 模块 SHA：`fa5aa4de90393f6b8c3f2d482d54ec34ef6a685961e5f7ccb576b63739c08ac5`。
- v055 r6 revision SHA：`67400cf32f7eb49550d1b5ca969e4b7d4312257400f4e11c87aabc77682e5ac4`。
- CPU 控制 SHA：`7b73ec366a28b20a4f2dc3ee41f8dc2f46fd86f62fa2f74d3deaf9fb2c541c5d`。
- 实际只读 snapshot SHA：`a2ddaaf63e1ac67094577ec4f45fa1a5cd3a6623a0fd0c84a1a3a5acb3bab9b0`。

小型证据归档于 `artifacts/software-benchmark-v055/disk-stages-r1/`。实际部署与后续并发监测由主协调端另行记录；本阶段未自动停止或接管任何正在运行的服务。
