# v141：公开测试的父子会话证据与实际执行接线

本修订解决 pytester 等测试中嵌套运行 pytest 时，公开测试反馈无法正确归属的问题。原 v130 观察器在模块级保存结果，并假定每次命令只有一份报告；同进程嵌套运行可能覆盖外层计数，子进程运行则可能产生多份合法报告。v141 将一次公开命令与其中的各个框架会话分别标识，以最外层会话决定命令结果，完整保留内层证据。原 v130 及其历史实验记录不改写。

具体来源是 [v137 保留的调用证据](../../artifacts/software-benchmark-v137/review-sprint-causes-r1/case-events.json)及[对应源码证据](../../artifacts/software-benchmark-v137/review-sprint-causes-r1/public-observer-source.json)：pytest-9037 曾出现 8／2／9／3 份报告，pytest-9032 出现 84 份报告。保留的某次 stdout 显示外层 5 passed，但反馈为 `unknown_collection`，原因为 `expected exactly one complete framework report`。这是已观察到的反馈缺陷；其造成的分数或 token 损失尚未单独测量，本修订不把旧 stdout 直接补成通过。

本页是实现及 CPU 验证记录，不是正式评测结果、实验运行许可或环境准入通过声明。未启动模型、API、Docker 或评分容器，未修改共享服务器配置。

## 结果归属规则

- 每条命令创建随机 command token。每个 pytest Config、unittest runner 或 SymPy reporter 创建独立 `run_id`，记录 `parent_run_id`、PID、进程组，以及开始／结束事件。
- pytester 同进程调用使用活动会话栈；子进程继承父会话身份。父子必须在同一命令的进程组内，子会话完整落在父会话生命周期内。缺失开始、缺失结束、孤儿、多根、环或身份冲突均不能产生“通过”。SymPy 原有 hash-randomization 子进程可以成为该命令唯一的根，不能按测试数挑选某个子进程。
- 同一会话内按测试 node ID、真实执行序号、setup/call/teardown 阶段保存报告。同阶段的完全相同重传只计一次，冲突报告保留为异常。同 ID 在另一个会话或一次新的实际执行中独立计数。
- 判断只采用根会话计数。测试 pytest 自身时，内层故意失败、外层断言其失败状态，可能是合法的外层成功；不能把内层失败直接加到根上。反过来，内层通过也不能掩盖外层失败。
- 零测试、全部跳过、收集失败、非零退出、超时、不完整执行及缺失／畸形证据均不标记通过。不从 stdout 中搜索“passed”文字推断成功，不用最大测试数替代根会话。

证据字段 `test_evidence.source` 给出根会话；`counts` 始终是根计数。`nested_report_count` 显示嵌套会话数，`sessions` 保留各会话及其逐测试、逐阶段报告。完整报告属于执行该测试成员的反馈证据，展示层应保留原有权限和分页，首屏只需要根状态、计数和嵌套数量。

观察日志上限为 4 MiB、最多 1024 个会话，命令 stdout 仍沿用 32 MiB 上限。超过上限不能误报通过。证据包含字节摘要；这是一项框架观测机制，不宣称能阻止同 UID 恶意代码伪造证据。公开测试成功也不等于官方隐藏评分通过。

## 实际运行接线

新入口为：

`run_managed_worker_docker_v141.py` → `software_benchmark_managed_actor_v141.ManagedOperationSession.execute` → `software_benchmark_public_test_evidence_v141.run_public_entry` → `public_test_execution_v141.execute_public_entry` → `public_test_evidence_v141`。

worker 在发出 ready 之前校验只读部署文件的实际 SHA256：公开测试 launcher、library、dependency helper、executor、observer 五个文件，以及公开测试合同。ready 原样返回实际文件身份；`software_benchmark_runtime_inputs_v141.validate_actor_selection` 必须与本次 actor config 一致。依赖 helper 沿用已验证的 v130 实现，公开选择语法沿用 v110；结果实现版本必须是 `v141-session-bound-public-test-execution-r1`，观察器为 `v141-session-bound-framework-observer-r1`。

actor 与 controller 输入直接使用共同的 v141 alignment / role contract，接受 S1、FREE2、REVIEW2 的真实成员名单。actor 只接受本组织实际成员的测试请求，并回执 actor、组织、候选树及请求摘要。旧 CHIEF 专用诊断及“600 秒自动选择某题”的快捷入口不进入新版。CPU 测试实际调用了 `ManagedOperationSession.execute`，不是仅替换一个未接入的辅助函数。

最终 SDK bundle-r2 已将 packaged aliases 指向上述 v141 文件，并纳入最后一项观察异常隔离修复；原 bundle-r1 保留为未部署准备记录。实际离线导入及变化模块的字节身份控制已通过，详见[运行器接线记录](software-benchmark-v141-runtime-wiring.md)。此修订没有运行真实容器，不能据此单独宣称容器部署或正式任务已完成验证。

## 已完成的必要 CPU 验证

| 验证 | 结果 | 范围 |
| --- | --- | --- |
| 公开测试证据单元及真实框架控制 | 28 项通过 | 真 pytester 同进程＋子进程嵌套、外层失败、收集异常、零测试、跳过、timeout、unittest 嵌套、缺失／多根／畸形与重复证据 |
| 实际 actor、部署字节及 controller 绑定 | 10 项通过 | 三种组织合同、ready 版本和文件哈希拒绝、真实 managed_public_test 路径、错误成员拒绝、CLI 退出状态 |
| 原有缓存 SymPy 框架微型控制 | 3 项通过 | 真 reporter 和 hash 子进程：通过、零测试、全部跳过；只运行新建的微型函数，不运行 benchmark 题 |
| 静态检查 | 通过 | 本修订 11 个 Python 文件的 Ruff |

初次合成控制暴露的是 fixture 配置问题：pytester 子进程禁用 user site，无法找到本地已有 pytest。控制脚本显式把已安装 pytest 目录加入 fixture 的 PYTHONPATH，未对正式任务安装新依赖或修改任务解释器。部署绑定控制另修正了合成镜像 identity 与正式 frontend argv 的构造。上述失败及后续验证口径不混同为正式模型失败。

实际 Django 项目 frontend 未运行；本次验证覆盖其使用的 unittest `TextTestRunner` 真实结果通道。pytest 控制使用当前本地已安装版本，不冒称重新执行了历史 pytest 题或其旧解释器。SymPy 的第一次控制记录保留，最终共享 parser 加入严格收集完整性检查后另存 final 控制，不覆盖旧记录。完整产物、版本及文件 SHA 见 [public-test-repair-r1](../../artifacts/software-benchmark-v141/public-test-repair-r1/summary.json)。

pytest 的 hook 与 pytester 行为以 [pytest 官方 API 文档](https://docs.pytest.org/en/stable/reference/reference.html) 为依据。这里采用每个 Config 的独立观察器，并保留真实嵌套执行，而非修改框架的测试语义。
