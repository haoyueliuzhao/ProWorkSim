# v068：TLS 生命周期与物理清理证明修复

## 停止原因

R3 的 `psf__requests-1921` gold／empty 控制已完成测试，并在官方日志中分别记录容器删除成功。但评分器使用了 v063 诊断修复创建的私有 `run_instance` 函数：该函数复制了官方模块的 globals。原 TLS 包装器随后只修改官方模块的 `cleanup_container`，没有修改私有函数实际使用的清理绑定。

因此，官方清理先删除容器，TLS 收尾再读取 CA 末态和 exec 状态时得到 404。两个 relay 线程已经结束，容器也已删除，然而 CA 证据缺失被放入 `cleanup_errors`，使评分器不释放 grader 2／3 预约，并触发共同队列停止。这不是新的模型能力失败。

官方原始报告的 gold／empty 结果存在，但缺失的 CA 末态不能补造；原 receipt 的技术未知状态和原 `quiescence=false` 保留。root 已针对两个原容器 ID 作只读实时检查并取得 404，另存物理清理证明、释放原预约。v068 包装器复用这些独立证明，不重新修改原件。

## 新执行路径

`software_benchmark_requests_tls_v068.run_official` 直接包装传入函数的 `__globals__['cleanup_container']`，在调用原清理之前执行原 TLS wrapper 的 `finish_transport()`。清理绑定在 `finally` 恢复；同一容器的重复清理只发起一次 finish。它核对容器属于该 wrapper，遇到非本任务容器立即拒绝。CA／relay 测量异常仍记录，资源清理继续执行，测量不会因此被提升为成功。

`software_benchmark_grading_recovery_v068` 提供与现有 coordinator 对应的评分函数接口。它私有克隆原 `run_request` 和 scorer 函数的 globals，仅重定向评分子进程入口及 TLS 生命周期钩子；不修改 v066／v067 模块的 globals 或冻结源码。官方测试、补丁、基线、评分规则和资源限制继续使用原路径。每次新的评分另外保存 `lifecycle-runtime-v068.json`，明确原 manifest 证明原官方安装与规则，新的宿主生命周期修订由独立源码凭据描述。

## 两类判断分开

资源预约是否能够释放，与代码／环境是否得到有效评分，分别判断。旧 `trustworthy_cleanup` 已通过时直接保留原判断；未通过时，仅满足下列证据才进行独立物理清理和预约收口：

- 原 request、plan、claim、初始容器 ID、结束记录和输出目录全部对应同一任务；没有创建结果未知。
- 评分进程有明确退出码，relay 明确 `thread_finished=true`。
- 新的只读 Docker inspect 对全部原 owned ID 返回准确的 404。存在对象、超时、其他错误、过期观察和错误 ID 均不能当作不存在。
- 只释放原 claim；不停止或删除容器，不删除其他任务的预约。若预约已释放且该 lane 已被新任务占用，也不会删除新预约。

物理证明保存到新的独立文件，原 receipt、quiescence 和 completion 不覆盖。CA 末态不恢复，原评分仍为未知；若原评分 receipt 根本没有生成，则记录缺失，不能虚构一份未知 receipt。正常测量失败因此可以作为局部异常继续排队；真正的物理清理不明仍返回失败，不能绕过资源保护。

## 验证范围

共 12 个必要 CPU case 覆盖私有 namespace 与官方 module namespace 不同的真实机制、收尾顺序、重复 finish、异常恢复、foreign owner 拒绝、私有 scorer 不修改旧 globals，以及精确 404、过期观察、存活容器、未知创建、未退出进程、活跃线程、缺失评分和其他预约保护。初轮 11 项通过；补充缺 receipt 边界后只重跑两项受影响控制，均通过。Ruff 通过。

对 root 已封存的旧 1921 两个物理证明还做了一次只读接口验证：包装器接受既有证明及释放标记，未调用 inspector、releaser 或运行 guard。该阶段没有真实 API、Docker、GPU 或评分操作。新路径的真实运行状态应以随后正式执行凭据为准。
