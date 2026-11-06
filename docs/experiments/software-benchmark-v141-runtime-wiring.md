# v141：三条件运行器、闭合及离线部署接线

本页记录 S1／FREE2／REVIEW2 的正式执行路径实现。它承接 v141 角色合同、世界和观察模块，供 v142 主控准备使用。当前完成的是本地 CPU 验证及离线 SDK 包，不代表正式 40×3 回合已启动或已通过容器准入。

## Controller 与实际运行路径

`tools/run_role_baseline_controller_v141.py` 接受 `v142-role-baseline-controller-r1` 配置，槽位使用 `v142:<task>:<condition>:<seed>`。三条件直接使用同一份 `software_benchmark_alignment_contract_v141`，不存在旧五组织 ID 或 CHIEF 专属默认诊断。

实际 controller 的 `prepare_case`、`build_team_owner`、`build_runtime`、`run_fragment` 和 `close_runtime` 均来自 `software_role_baseline_runtime_v141`。旧 v132 文件仅提供未改变的 FIFO RPC、初始树同步和生命周期工具；不会调用旧 `main`、旧五组运行循环或旧世界组织守卫。模型路由仍由外部授权主控提供。

controller 检查真实 actor ready 的成员名单、角色合同版本及 SHA、公开测试合同和五个运行文件 SHA。与 actor 的相同入口校验一起，防止只改 helper，却仍运行旧入口。诊断组保留真实成员 registry、独立 SDK 会话 ID、实际工具声明及零模型字段；新增自身进程的 `resource.getrusage(RUSAGE_SELF).ru_maxrss × 1024` 峰值，明确其 scope 为当前 controller，不冒称整个宿主或所有子进程的峰值。

## 精确本地内容计数

正式 `build_team_owner` 调用固定传入 `require_content_counter=True`；不提供字符数兜底，也不在计数器缺失时偷偷略过测量。使用项目已冻结的官方 recipe 0.2.0 与 `deepseek-ai/DeepSeek-V4.1-Flash-1017` tokenizer 文件，不下载新资源。

新 bundle 仅复制冻结 manifest 列出的 recipe、共享库、词表和许可证。文件字节及 SHA 不变，路径重定位到 `/opt/pws-runtime/content-tokenizer`，重定位 manifest 另保留原 manifest SHA。controller config 中的 `content_tokenizer` 绑定重定位 manifest、原 manifest 和 vocabulary 三个身份，部署后只从本地加载。CPU 探测确实使用离线包中的同字节 recipe／词表编码了非空和空内容。

这里的“精确”指对冻结 tokenizer 的实际内容编码计数，**不是把这些内容数冒充服务商账单或整条 chat request token**。完整输入、输出费用继续以 API usage 为准，通信及阅读的内容计数由观察模块另报。

## 两个最终端点

`software_benchmark_project_closure_v141` 调用新 runtime 的 `lock_fixed_candidates`，在全部 SDK 会话停止后，仅锁定事前指定 `member_001` 的最终工作树及最后合法交付。不会在两个成员中挑最佳代码，不会把最终工作树补成正式提交，不测试、不生成或评分新候选。

两端点继续独立保留：最终代码可供官方离线评分；合法交付需要原有同版本测试、固定、提交链。两树不同会明确记录，未提交仍为未提交。

REVIEW2 的离线验真另绑定真实 v141 组织交付证据：作者 001、复核者 002、精确固定版本、提交前最后一次明确接受、复核者已取得的版本、该版本实际测试及任务修订身份。提交后出现新的拒绝或后续修改，不追溯删除当时合法的交付；也不能借旧接受授权后来修改的版本。S1／FREE2 没有这项独立复核门，证据中不得凭空加入。

候选锁定调用观察模块一次 `finalize`。闭合结果保存 `collaboration_observation` 摘要引用，同时保留观察错误及不完整通道，缺失不填成零成本或没有协作。技术异常未到达候选锁定时，原始 sidecar 仍保留，不捏造成功闭合。

## CPU 与离线包验证

- 新 controller／closure 有 6 类必要控制：三种真实微型世界的合法交付与后来修改；无交付不能替代为工作树；新运行路径和 counter 绑定；新 controller config／ready 校验。REVIEW2 控制还覆盖提交后的新拒绝，以及篡改复核测试成员被拒绝。全部通过。
- runtime_inputs 加入 tokenizer 描述后，三个组织的实际输入控制重新通过；已有 28 项公开测试证据和 10 项 actor/input 控制的适用部分保留。
- 离线 bundle 确实启动其自带 Python、SDK 1.49.6、三个条件的工具定义、controller／actor／public-test 入口；额外显式导入 lazy closure、runtime_inputs、content helper 和 observer bridge。审计禁止网络及创建新子进程，禁止操作计数均为 0，无模型或 Docker 调用。
- 对实际 staging 文件调用新 actor 的字节／只读校验，并核对实际 tar 中五个公开测试 alias 为 0444、root uid/gid 元数据。这里只写普通用户自己的归档文件，未调用 root 或改宿主权限。缓存重用入口亦重新校验当前源码与 archive。

准备期间发现并修正了两个部署问题：旧 tokenizer manifest 有历史路径别名及额外来源字段，不能使用只接受严格 candidate reference 的检查器；改用已有 tokenizer 校验器核对实际字节、大小及 SHA。通用 bundle 原先生成 0644 alias，与新 actor 的严格只读门不一致；仅修正本次生成 stage 和 archive 中五个 alias 的权限，并把规则写入新 builder。前一失败及权限修订均单列保留，不计作模型或 benchmark 失败。

最终离线包为 `runs/software-benchmark-v141/sdk-bundle-r2/manifest.json`。r2 仅增补观察模块写错误日志再次失败时的异常隔离，实际包内导入及最终模块 SHA 已检查；原三条件 SDK 和未变化计数器控制直接复用，不重复运行。原 bundle-r1 完整保留、未部署。完整证据在 [公开测试与接线产物目录](../../artifacts/software-benchmark-v141/public-test-repair-r1/summary.json)。本文未创建批准标记，不扩大正式实验、网络、容器或费用权限。
