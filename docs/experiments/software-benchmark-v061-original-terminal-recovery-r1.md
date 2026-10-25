# v061：恢复原终态候选的导出

日期：2026-10-25。用户要求修复剩余未知后重新评分。本记录只涉及 `scikit-learn__scikit-learn-14894`／500万预算的原 slot 163，测量类型为 `original_terminal_snapshot_recovery`。

**该项已完成离线候选恢复，尚未执行本轮官方评分。** 没有重新调用模型，没有访问残留 actor 工作树，也没有使用 Docker、GPU、网络或 root 操作。旧 episode、claim、账本、队列状态和缺失的旧结果文件均保持原样。

## 恢复依据

原控制器已记录 `closed`／`native_finished`／`normal_completion`，SDK 记录 `finished`。原派发关闭、两个写入者的静止证明、候选占用凭据构成同一 claim 链；候选在任何评分之前已经选定。原终态快照及来源 manifest 完整，先前审计的 SHA256 为 `376cc7b31af638feac09a6605f362e205e9d48b2b5e5ec4e2e548d607ce554b3`，本次检查一致。

恢复只读取这份已经保存的快照和原基线，不重新捕获工作区，不重新选择代码版本。固定原任务、预算、seed、dataset revision、base commit 和原配置引用。任一来源身份、候选占用或静止证明不一致时，工具在导出前拒绝。

## 实际导出与验证

从原快照的内容及文件模式构造 Git blob／tree。对不能严格解码为 UTF-8 的变更路径，使用既有 v056 的 binary diff 表示方法；临时 Git 的属性规则不会成为候选文件。没有忽略生成文件或只保留参考修复附近的路径。

| 项目 | 结果 |
| --- | --- |
| 原终态文件数 | 1,586 |
| 新增／修改／删除路径 | 98／4／0 |
| 强制二进制表示路径 | 94 |
| 导出补丁 | 930,928 字节，严格 UTF-8 |
| 原终态内容身份 | `3629cb171357a7b417c121e8310513b2952b936d732717c45183420e2dfbe388` |
| Git 应用后目标 tree | `9e6709828a5c7cfdb4c1e0eedc409cf33c3cca15` |
| 精确往返 | 通过；文件字节、路径和模式均绑定 |

新候选锁采用既有 `software-benchmark-native-closure-v054` 数据格式，并额外记录 v061 恢复版本、原候选占用凭据和本次恢复来源。它是本次新补齐的导出锁，**不是伪称原来已经存在的 lock.json**。原 slot 和 seed 不变，也没有产生新模型回合。

9 项必要 CPU 检查覆盖：正常终态准入、拒绝仍在运行或例外退出的状态、拒绝评分后重新选择、静止证明错绑、来源快照替换，以及二进制、符号链接、删除、可执行模式和 CRLF 的精确导出。静态检查通过。实际原快照又完成了一次完整 Git 应用往返；未重复运行模型或官方测试。

## 评分接入

恢复结果位于 `runs/software-benchmark-v061/original-terminal-recovery-r1-20261025/recovery-result.json`，包含新候选锁、补丁和原配置的不可变引用。评分器应从原配置取得原镜像、官方基线映射、dataset 和评分规则，在新输出目录和 run ID 下评分，并保留原未知记录与本次恢复关系。

本恢复记录不授权 Docker 或自动解除共享服务器暂停。正式评分仍须通过新的限定评分入口和相应授权。它也不说明修复一定正确；只有官方评分完成后才能决定 resolved。

摘要与来源引用见 [summary.json](../../artifacts/software-benchmark-v061/original-terminal-recovery-r1/summary.json)。实现为 `software_benchmark_snapshot_recovery_v061.py`，命令入口为 `tools/recover_terminal_snapshot_v061.py`；固定输出目录存在后拒绝重复导出，保留唯一恢复记录。
