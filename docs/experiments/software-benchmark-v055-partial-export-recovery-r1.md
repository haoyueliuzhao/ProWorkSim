# v055 单题中断导出的显式环境修复 r1

## 状态与范围

本文件记录 `matplotlib__matplotlib-25122` 的单题零模型环境恢复 r1。r1 已于 2026-10-23 00:34:45（北京时间）实际部署一次，在导出开始前因 user cgroup 缺少 `cpu.max` 被拒绝；本版本结果为环境失败，新增导出 0、模型调用 0、正式 claim 0。原件及这次失败完整保留。后续独立 r2 已完成修复，见 [r2 实际结果](software-benchmark-v055-partial-export-recovery-r2.md)。

用户已要求六小时运行监控和自主修复异常。本工具限定于原 Verified 500 题中一个从未进入正式回合的环境故障，不增加任务、seed、条件或模型尝试，不改变科学配置、2000 元预算或既有安全门。

## 原故障证据

原 `native-prewarm-r4/events/00000299.json` 记录 `RuntimeError: Native rootfs disk reserve gate during export`，model_calls、formal_claims、hidden_grader_calls 均为 0。原 worker PID 已退出。原缓存为：

`runs/software-benchmark-v054/native-lazy-cache/matplotlib__matplotlib-25122/b770350da573155d/`

此目录只有 457 字节的 `preparation-failure.json` 和 6,928,990,208 字节的 `rootfs.tar`。没有 rootfs、rootfs-manifest、public-environment、初始化或 lazy-preparation 凭据。不能将部分 tar 冒充完整导出，也不符合已有 `--continue-exported` 或 `--continue-initialization` 的准入前提。本次没有扫描或重新哈希该 6.45 GiB 部分 tar，仅以设备、inode、长度和 mtime 绑定，保留原字节。

固定 mapping SHA256 为 `b770350da573155d40a3455740b95205fb868897cd63156e80d21deb8d3a9dc4`；本地 actor image ID 为 `sha256:620e603424132a9f94e0e262abfc980e3c981395feeab85d07ebfe3eb0e791e6`。只读 Docker inspect 确认镜像仍在本地，Size 为 7,515,621,783 字节。该数字是 Docker image Size，不作为 tar 完整性的证明。

原失败 SHA256 为 `f39babc6bb10f3c9fc720c7eab920e59fc4aa90a56e149e2cc421fe20cc65cd9`。Qwen 现有恢复层每轮校验此原路径引用，因此原失败文件不能被移走、覆写或替换成新状态。

审查时 Qwen 三槽及 DeepSeek 六槽均 pending，无生成 attempts，无正式 claim；DeepSeek 三个工作卷也没有这些槽的 generation 目录。freeze 与 register 会再次以实际身份和原先固定的九个 slot 对象核验，不以模型成绩决定恢复。

## 实现与状态交接

新增工具为 `tools/repair_partial_export_v055_r1.py`，不修改任何冻结 runner、model provider、host 或原环境模块。

1. `freeze` 只写独立计划 `runs/software-benchmark-v055/partial-export-recovery-r1/plan.json`，绑定原 mapping、任务、九个 slot、失败引用、保留 tar stat、r9 host、工具源码以及原公共初始化依赖。
2. `register` 要求当前 r9 DeepSeek 协调器已经以 `KillMode=process` 停止，并获取原 `coordinator.lock`。它不停止协调器或任何工作进程，由操作侧先完成一次有证据的静止交接。
3. 原共享 `disk-dispatch-r4.lock` 内刷新双队列和三卷容量，遵守原 CPU/RAM 准入、最多 2 路预热、128 GiB 冷模板预约及 128 GiB 余量门。原主盘已有在途预约全部保留。资源不足时登记前拒绝，不创建正式回合或自动循环重试。
4. 生成正常 schema 的 `request.json` / `job.json`，在 DeepSeek preparation 记录内登记一个独立 worker，readiness 从该特定旧 failed 转为 preparing。所有原 rows、exceptions、预算、dispatch_stopped 和 active_host_revision 保持。
5. 如果协调器已经自然进入 `primary_finished_with_deferred_environment`，仅在恰好本题 6 个 pending、环境均 failed、没有运行或待评分工作/其他预热时，独立 registration 回执记录旧 status 与 ended_utc，然后允许 status 回 running。其他停止、预算 halted、dispatch_stopped 或不明状态一律拒绝。
6. state 的 durable worker intent 先于 `systemd-run`。启动不明确时不自动重试，保留 intent/launch 证据，由原队列按 completion 或 missing-worker 规则处理；同一 register 不允许执行第二遍。
7. 恢复使用原 queue worker 框架，4 CPU、16 GiB 内存、16,384 PID、3660 秒 systemd 上限，内部任务超时 3600 秒。实际 worker 读取 cgroup，要求三个内核限制精确匹配，不能直接从无约束 shell 执行。

DeepSeek 原 `refresh_preparation` 不重新查询 failed readiness；因此只修文件不足以恢复六槽。这里通过显式 preparing worker 交接，之后**相同 r9 host** 即可用原 completion 路径收取结果，无需替换 host revision。旧 environment exception 留存，新恢复计划、登记回执、worker attempt 和结果独立存在。失败仍不阻塞其他任务，也不转换成模型错误。

## 导出、发布与初始化

worker 持有原 `native-lazy-cache/locks/matplotlib__matplotlib-25122.lock` 排他锁，检查原九槽仍未进入、其正常 preparation 预约仍存在和磁盘余量，随后：

- 在原缓存同一文件系统的独立 `b770350da573155d-export-recovery-r1` 目录，从上述固定本地 image ID 重新完整导出一次；`--pull never`，没有资产下载、模型或评分调用。
- 精确复用原 `prepare_rootfs` 提取、逐文件内容 SHA、所有权映射和既有 UID/tool/resource 机制。这里只做新的完整导出所必要的提取校验，不重新校验旧模型或全题环境。
- 同盘 rename 将新 rootfs 发布到原规范 `.../b770350da573155d/rootfs`；payload 字节/inode 不变。原 staging manifest 留存。规范 manifest 的 `prepared_root`、public-environment 的 manifest 路径及 SHA 同步派生；保存真实来源与这次路径发布的说明，不把 staging 路径伪装成原路径。
- 原部分 tar 和原 `preparation-failure.json` 始终不变。新 qualified 记录优先于旧 failure 被读取，但旧故障仍是历史事实。
- 只执行原该题公共 Python、模块版本、Git head/tree 初始化。该检查不是隐藏验收，不调用模型或 benchmark tests。
- 初始化及静止清理成功后，沿用原 manifest 控制字段和四个引用生成 `lazy-preparation.json`，在原实例锁内最后发布。它是唯一准入边界。任一步失败则不发布 qualified，保留所有现场和独立 preparation-result。

现有阶段预约器能解析新 worker 的正常 `--request` / `--sha256` schema：导出期间仍预留 128 GiB，规范模板物化后才按已有阶段证据折扣。未发布齐全或 SHA 暂不对应时保守保留原预约，不使用未证实的空间折扣。

## 必要验证

`tools/check_partial_export_v055_r1.py` 执行合成临时目录和内存状态控制，不使用正式队列、Docker 或模型：

- 九个原 pending 身份；拒绝已进入、claim、跨卷 preintent 和 seed 变化。
- 交接不变更所有正式 rows、原异常、预算或输入状态。
- 精确六个环境 pending 的合法终态可显式恢复；其他 halt/额外 pending/评分运行拒绝。
- 同 inode 迁移和规范元数据，旧失败/部分 tar 保留；没有提前 qualified，禁止覆盖。
- 公共初始化失败不发布资格。
- 原磁盘阶段解析器接受正常 request/job 格式。
- 直接调用原 `Coordinator.refresh_preparation`，验证 completion 后转 qualified、保留原异常。

七项控制通过，定向 Ruff 通过。控制实际 model_calls=0、GPU_loads=0、Docker_calls=0、services_modified=false、actual_queue_state_written=false。

## 原部署步骤与实际 r1 结果

1. 检查封存 plan SHA 与工具 SHA；不修改封存来源。
2. 对精确 r9 manager 做现有静止交接：记录 PID/InvocationID/命令与 state，确认睡眠及状态稳定，只停止 `proworksim-v055-deepseek-six-conditions-native-host-r9.service`。worker/model 服务不变。
3. 在项目环境运行：

   `PYTHONPATH=src:tools .venv/bin/python -B tools/repair_partial_export_v055_r1.py register --plan runs/software-benchmark-v055/partial-export-recovery-r1/plan.json --sha256 <封存SHA>`

4. 无论 register 是否启动成功，都根据其 durable intent 和回执判断；不盲目重跑。使用原命令与原 revision SHA 恢复同一 r9 manager，让旧生成/评分继续、收集新 CPU worker。
5. 检查 registration/launch、preparation-result、原初始化 receipt 和九槽后续首次进入。只在真实结果为 qualified 时报告环境修复完成；只有后续原回合自然结束时才更新生成完成数。

原 500 题分母、旧技术未知和原 CPU 磁盘失败不改写。本修复不授权旧 entered 模型回合重跑，也没有自动恢复其他异常集合。


实际部署回执：同一 r9 host 在 00:34:44.844686 恢复，manager PID 2390766；worker/GPU 服务信号计数均为 0。r1 准备从 00:34:45.066901 到 00:34:45.067051，返回 `deferred_environment_failure`，具体为读取 user service 的 `cpu.max` 时 `FileNotFoundError`。没有进入 Docker 导出或建立 staging。register 前队列状态为 running，未伪造终态恢复。

此前文中 4CPU 描述为申请和检查要求；在本服务器 user.slice 未下放 CPU controller，r1 **没有通过实际 CPU 硬限检查**，不得将声明当作已生效。正式 actor 的独立 system slice 不受这个 user-unit 问题影响。r2 专门修正准备过程的执行边界，没有热改 r1。

可发布原件位于 `artifacts/software-benchmark-v055/partial-export-recovery-r1/`，包括原 plan、registration、launch、worker request/job/completion/result、部署脚本/交接与重启回执和精确 service 定义。完整 state-before 只保留于 runs；没有再次扫描或哈希 rootfs。上述原 r1 方案和控制仍保留，其合成控制通过不等于实际服务器资源资格通过。
