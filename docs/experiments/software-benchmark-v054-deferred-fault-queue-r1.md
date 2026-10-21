# v054 宿主调度异常延后处理 r1

本修订只新增宿主调度 overlay。原 r11 科学执行源码、`formal-bindings-r7.json`、1500 个槽的任务与 seed、每题预算、模型常驻进程、并发上限、S1 接口、候选锁定及 r5 官方评分器均不改变。原 bindings SHA256 为 `43fb7dde14a7c7abf3a0dc97de8b0de119f41d4f4199f8482793b9b6c24bc3de`。

用户授权在中途遇到异常时继续处理独立任务，并在主清单完成后集中处理异常。此前 slot 93 评分没有形成可信的正式结论。原候选、账单、评分请求及异常记录保留；该状态不转换为错误答案或零 token，也不会重新生成该题。此前三次已处理故障的历史不删除。

## 作用边界

新增 `ResilientCoordinator` 继承原 `Coordinator`，构造时仍实际执行原完整冻结文件校验、1500 槽授权校验和独占 controller lock。新 overlay 的三个运行文件由另一份不可变 policy 固定；它们不替换原 source manifest 中任何文件。所有 generation 与 grading worker 继续使用原入口、原 job bindings 和原资源限制。

以下明确归属到题目或评分端点的事件保留为 `technical_unknown`，并写入不可变异常 sidecar：回合未闭合、单题终态证据无法读取或验证、评分进程失败或结果不确定、已登记 worker 消失、启动交接无法确认。歧义启动如果对应原 unit 实际仍在运行，继续观察这个既有 unit；不会再次启动同一 intent。所有失败 attempts、claim、候选、费用证据和错误消息仍保留。

模型费用或执行完整性未知时，该题记为技术未知，并持久隔离其 resident，防止继续向这一资源派新题。其他可证明独立的健康 resident 可继续运行；隔离不发送停止信号，不重载权重，不自动修复。没有可确定 resident 的账单问题仍停止新派发。

新的只读健康过滤器首先验证整个原注册链及不可变准入证明，再分别查询现存 resident。当前 PID、ready、socket 或 poison 故障仅使该 resident 不可领取。全部资源暂不可用时等待。注册链、源码、共享 schema、global claim 身份或无法确定范围的控制器错误继续保留全局停止门。CPU prewarm 的共享生命周期失败也仍停止新派发，不能绕过环境准入继续执行。

原候选的评分可以在生成端记为技术未知时继续完成测量，但这不会清除其账单异常。未知评分没有 `resolved=false` 替代值。新增异常清单的引用可回溯到完整原 row、请求、候选及费用文件；不读取隐藏评分材料给 actor。

## 接管与恢复

接管只要求原协调器停止并释放原 `controller.lock`；独立 generation / scoring worker 可以继续运行。一次性的 `adopt` 在同一锁内验证所有活跃 intent 的 job、原 bindings、unit 名称和目录身份，保存完整接管前状态和 `adoption.json`，追加 operator policy adoption，再将控制器状态设为 running。旧 `state.bindings` 不改，原历史故障和所有已有技术未知均保留。再次执行 adopt 被拒绝；重启新协调器使用 run，不能重新接管或重放。

部署顺序（由主管代理执行，本次 CPU 控制没有执行）：

1. 应用三个新运行文件和本文，保留所有旧冻结源码。
2. 用项目 `.venv/bin/python` 和 `PYTHONPATH=src:ROOT` 运行新工具 `freeze --bindings runs/software-benchmark-v054/formal-bindings-r7.json --previous-controller-unit proworksim-v054-formal-queue-r7.service --output <policy.json>`。
3. 只停止旧协调器；不得停止其独立 workers 或模型 resident。
4. 执行 `adopt --policy <policy.json> --policy-sha256 <sha>`。如果原锁仍被持有，或者共享身份校验失败，接管拒绝。
5. 在新非自动重启 unit 中执行 `run --policy <policy.json> --policy-sha256 <sha>`。原 workers 由相同 job 和 completion 证据接续观察。

## 主清单终态与末尾异常处理

只有全部 1500 个 generation 都进入 `closed` 或 `technical_unknown`，并且所有已建立的评分端点均进入 `official_report` 或 `technical_unknown`，才写入 `primary_inventory_finished_with_deferred_exceptions`。其中正常 closed generation 必须有 code 端点评分记录。任何 pending、intent 或 running 均不能满足终态。

该终态是主清单的执行结束，不是全部结果已知，也不是完整完成率。原按任务、仓库、组别和运行修订分层的统计继续保留。`primary-state.json` 是不可变完整状态快照，`primary-completion.json` 固定其 SHA、原 bindings、overlay policy、1500 分母、零活跃计数和异常集合。

policy 单独记录末尾允许的评分处理：主清单结束后，对具备可信原候选与评分请求的未知端点最多追加一次评分 attempt，资源限制与原请求相同，不重新选择补丁，不重跑模型。该操作由独立 deferred-scoring 工具完成，保留原主清单记录。本核心 overlay 仅生成终态交接标记，不在日常派发中自动重评，不伪称末尾工具已经执行。

## 本次必要核验

一次组合 CPU 控制通过，耗时 0.263 秒。它使用临时合成 1500 行状态和程序化 worker 完成信息，实际调用原 `complete_score`、`complete_generation`、selector 和原构造冻结校验，覆盖：单题评分未知后仍 running；单题生成未知后仍 running；旧 unknown 不再次 reconcile / 派发；全部终态才完成 inventory；共享账单异常隔离自身 resident；不明确范围的错误暂停；原冻结源码被篡改时真实构造校验拒绝。

控制没有启动服务、模型、GPU、正式 claim 或官方评分，没有修改 live queue。新增 live-resource helper 的独立必要 CPU fixture 由另一并行代理完成；此处未重复运行。CPU 结果不构成实际模型或官方成绩验证。

主管代理进一步要求核对不中断接管分支，因此仅追加一次有针对性的合成 adoption 控制（0.064 秒）：构造 5 个采用真实 job/unit/kind/bindings/directory schema 的活跃 generation intent，验证 adopt 后五行与原 bindings 完全不变，活跃计数仍为 5，重复 adopt 拒绝。它没有重新执行上一组合控制，也没有实际运行或停止任何服务。
