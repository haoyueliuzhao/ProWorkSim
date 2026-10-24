# v056 独立运行器与受管异常修复

2026-10-24。Qwen REF 预算实验使用新的宿主入口、任务claim和输出目录；受管接口修复位于独立 v056 模块，不改变 REF 的工具、提示或生成路径。旧实验源码冻结副本、轨迹、未知结果及claim均保留。

**独立 REF 运行器**

入口为 `tools/run_ref_budget_episode_v056.py --config <配置> --output <新目录>`。配置、题槽和授权分别用路径、大小、SHA绑定；只允许四个预定 REF 条件和原始 Qwen3.5-9B。共同512次尝试／决定、21,600秒软期限和23,400秒硬期限由新条件校验，累计token按档位变化。

每槽在 `runs/software-benchmark-v056/episode-claims` 只创建一次claim；进入后的失败不重采。运行器只拥有 actor／controller 子进程，模型服务由外部池驻留，本槽不加载或停止GPU模型。只有写入者scope及其外层launcher实际退出，才锁定唯一最终代码树，再生成独立评分请求；评分run_id绑定条件、槽、配置SHA和候选树SHA。单题异常落盘为technical_unknown，不阻断其他独立槽；评分由另一个队列处理。

新 `native_uid_bootstrap_v056.py`、mapped worker、clone及cleanup模块保留原numeric ownership、manifest、路径和cgroup检查。actor目标只能位于v056目录；只读模板来源额外允许明确的新缓存 `runs/software-benchmark-v054/v056-budget-cache-r1`。不修改旧helper或以preparation-only绕过正式环境身份。模板payload缺失时拒绝使用旧qualified元数据。

验证：5项宿主窄控制通过；真实pylint已准入镜像经新helper完成clone、Actor隔离、一个固定CPU终端命令、静止证明、克隆删除及资源slice释放，结果为passed。模型调用、GPU加载、正式题槽claim和官方评分均为0。记录位于 `runs/software-benchmark-v056/runtime-cpu-control-r1/result.json`，父控制另补真实SDK构造，不重复本控制。

**“同一工作机会第二次决定”的真实原因**

依原审计已保存的fatal行偏移，仅读取54条记录各自之前最多64 KiB。54／54均在第二决定错误之前出现 `run_tests` 的SDK `AgentErrorEvent`：52条为公共测试IPC等待超时，2条为无法证明测试进程后代已退出。它们不是普通模型格式纠错。

旧受管worker只在 `ObservationEvent` 暂停。SDK把工具异常转为 `AgentErrorEvent` 后继续自身循环，于是被“一机会只能一个模型决定”的保护拦下；原保护阻止了第二调用，但第二错误掩盖了第一工具异常。

新 `software_benchmark_managed_worker_v056.py` 仅用于v056受管装配：记录原SDK错误，核对其tool名称／call ID与本机会准入动作，暂停SDK，并保留execution_integrity_error。发生未知工具执行后禁止复用worker；不重试副作用、不改成模型失败、不退款或重置计费。原第二决定保护保留。实际OpenHands SDK的3项程序响应CPU控制通过：一次请求和一次工具调用、首个异常可追溯、未知后不重放，以及普通已知业务拒绝仍允许下一工作机会继续。

**公共测试IPC期限错配**

旧client固定等待1,860秒，但host先等测试资源，再clone／初始化，之后才给公开命令最多1,800秒。因此排队和准备可能挤占合法命令时间。首个按原顺序选取的sympy24539例中，工具动作发生在16:51:58，测试worker到16:57:28才初始化完成，17:23:00 client超时；worker就绪后仅约1,532秒，未达到命令的1,800秒上限。此例证明等待阶段的期限错配，但不证明该题延长等待就会通过。

新 `software_benchmark_public_tests_v056.py` 的client按本回合剩余hard期限等待整个RPC；host仍保持命令最多1,800秒及剩余hard限制，保留kill／reap与静止证明。新host记录排队、取得容量、clone、worker就绪、命令开始／返回、停止、静止及回收时间。新managed装配入口明确绑定此client，拒绝无意沿用旧1,860秒等待策略。

3项真实本机Unix IPC控制和2项host阶段控制通过，覆盖长等待额度、过期／跨回合拒绝、静止失败不降格且不得重放、命令上限及静止后清理。另2项真实装配入口控制确认：旧callback在加载SDK前被拒绝；显式public_test_config安装新runner、禁止延长managed hard期限，且不改变世界状态。新host与client均绑定v056策略身份，避免只增加一个未被实际调用的helper。测试先被沙盒禁止socket绑定，移到授权宿主执行；测试服务端曾错误使用多行JSON，改为原wire格式后仅重跑失败项。实际SDK测试先被无关pytest插件阻断，在隔离Python中关闭自动插件后通过；未修改SDK或运行模型。

这些修复不抹除原54个未知，不保证测试自身不再超时，也不把无法证明退出的2例改为普通测试失败。公开测试仍是预先规定的合法入口，没有新增不受管bash或隐藏验收反馈。

证据：[54条有限读取与期限错配例](../../artifacts/software-benchmark-v056/managed-execution-error-r1/audit.json)。实现和测试为本次新增v056模块；旧v054/v055运行器、claims及通用 `harness_sdk.py` 未为此修复改动。
