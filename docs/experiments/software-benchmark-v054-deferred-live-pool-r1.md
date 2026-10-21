# v054 异常资源隔离辅助模块 r1

新模块 `software_benchmark_deferred_pool_v054.py` 只供独立封源的宿主 Coordinator overlay 使用，不替换 r11 的模型、resident、runner、评分器或原 pool/session/provisioner 文件。调用方仍先执行原全局 source/binding 检查。

`healthy_residents(policy_ref)` 先通过原不可变 pool 策略、事件链和各注册准入证明；然后逐个调用原 `admitted_resident(query=False, exact policy/registration refs)` 核当前部署/PID/租约，再以独立的 2 秒只读管理请求获取 status，沿用原单会话和双会话健康语义。单个当前 ready 文件/PID/socket异常或 poisoned 状态进入 `deferred`，其他健康资源继续出现在 `available`。满槽但健康的资源保留在 `healthy`。所有资源均暂不可派发时返回 `waiting`，没有取消、重新生成或停止其他任务的动作。

不可变 policy、注册事件链或历史 admission/readiness/control 证明缺失或损坏仍是 `SharedPoolIntegrityError`。这不是可以按资源忽略的运行态故障：原服务工厂和 worker 也会再次检查这些全局证据。遇到 live 检查错误时重新核不可变证明，避免把检查期间的证据变化伪装成单卡失联。模块没有修改或绕过既有验证器。

本次一项有限 CPU fixture 通过（0.11 秒）：一坏一健康时仅返回健康资源、全坏时保持等待、不可变证明错误停止进一步 live 探测。全部管理回复均为显式程序化数据，实际模型请求、实际 admin 请求、正式 claim 和服务修改都为零。这不替代真实 resident 的已有准入证据。

原 provisioner 的 REF→MP 转换仍要求全部 500 个 REF 官方评分已知。把某个评分异常延后处理不会自动改变这个转换门。若最后只剩这类评分未知，需在异常集合处理阶段完成评分闭合，或通过另行显式封源的资源转接操作处理；本辅助模块不会把未知评分填成失败或假称 500 项已知。
