# v085 API 文件描述符治理

## 已核实事实与归因边界

v083 的 `api-coordinator/run-summary.json` 记录 `coordinator_error`，原因为读取 `resource-claims/active-actor-15.json` 时抛出 `OSError: [Errno 24] Too many open files`。这一异常位于主线程准入观察路径，外层异常处理触发队列全局停止。最后记录的 API 账本状态仍为 `ready`，金额上限仍为 1500 元；因此不能把此次停止解释为现金耗尽。

这说明原 owner 的文件描述符容量不足，且准入读取失败的隔离粒度过大。进程退出前没有完整 FD 分类快照，不能确定当时每类 FD 的数量，也不能声称某一泄漏点独自造成了故障。

源码核查确认，原 episode 的 `finally` 已关闭 Docker client、RPC/model channel、桥接线程及日志；HTTPS 请求路径也有 `connection.close()`。本次没有证据支持盲目重写这些接口或关闭他人连接。

另定位并通过 CPU 复现的具体保留点是 `software_benchmark_deepseek_api_v064.BudgetLedger.__init__`：账本预检使用 `with sqlite3.connect(...mode=ro) as db`。SQLite 连接的上下文管理器处理提交／回滚，**不会在离开 with 时自动关闭连接**。每题 fork 客户端会再次执行这一路径，其释放依赖垃圾回收。在禁用测试进程 GC 的受控条件下，原构造连续 12 次增加至少 12 个 FD；私有修订连续 12 次增加不超过 1 个 FD。这个实验说明存在不确定释放时机，不能将它直接换算为原故障进程的泄漏总量。

## 修订范围

新增 `software_benchmark_fd_v085.py`，不修改冻结的 v064/v082/v083 文件，也不修改共享服务器全局限制。

1. 后继运行器为**自己的新服务**声明独立 `LimitNOFILE=16384`。模块本身不调用 `setrlimit`，更不会调整他人进程或宿主配置。
2. `FDGuard` 读取本进程实际 FD 数和软硬限制。可用量低于 512 时暂停新增；恢复至 1024 后再允许准入。观测不可用同样暂停。每个新回合预留 32 FD 是调度估计，不是内核硬保证；实际服务限制及每轮观测仍持续生效。
3. 包装原 `generation_limit`，仅对明确的 `EMFILE/ENFILE` 返回零新增容量，不设置全局停止，不取消在途请求。不吞掉权限拒绝、身份冲突等其他异常，也不绕过原资格、CPU、内存及实际容器容量门。
4. `RuntimeView` 在 FD 不足或明确 FD 耗尽导致账本观察失败时返回 `waiting_fd_pressure`，其中 `can_start_generation=False`。不以旧金额快照授予新消费。原真实现金超限、账本身份改变、无法解释的 SQLite 错误仍保留原 hard halt 语义。实际请求预留、结算和未知用量保留均沿用原逻辑。
5. `ManagedLedger` 仅私有替换原预检连接工厂：保留原 SQLite 提交／回滚行为，然后在 `finally` 关闭连接。`ManagedClient` 沿用原客户端、模型、TLS、token、现金及工具合同，后续每题 fork 继续使用这一受管连接类。原正常 `_connect()` 本来就显式关闭，无须改动。

本次保护针对准入观察和已证实的连接生命周期问题。评分身份、候选、清理证明等关键证据缺失仍不能被当成成功或跳过验证；不使用广泛的“捕获所有 I/O 异常然后继续”掩盖完整性问题。

## 运行器接入

```python
guard = FDGuard()
api = RuntimeView(raw_api, guard)
api.initialize_for_run()  # 必须走包装后的初始化，私有客户端才会生效。
limit = guard.admission(original_ceiling, active=lambda: len(admission.active))
# queue(..., api_runtime=api, generation_limit=limit)
# progress 中额外记录 guard.snapshot()。
```

原运行器、实际请求客户端及 frozen 模块的全局命名空间不被改写。停止后的候选恢复、评分接管和新服务启动由独立后继运行器处理，本文模块不执行这些操作。

## 必要验证

新增 10 项 CPU 检查覆盖 FD 滞回和原并发上限、单次 FD 错误隔离、未知 FD 状态禁止预算准入、真实现金／身份 hard halt 保留、SQLite 提交与回滚后关闭、禁 GC 时原／新 FD 增长对照、私有初始化和 episode fork，以及注入一次准入 EMFILE 后八个模拟槽全部完成且不重跑。

```text
.venv/bin/python -m pytest -q tests/test_fd_v085.py
.venv/bin/python -m ruff check src/proworksim/software_benchmark_fd_v085.py tests/test_fd_v085.py
```

所有测试只操作测试进程和临时 SQLite 文件，不请求 DeepSeek，不操作 Docker、GPU 或共享服务。真实运行仍应记录 FD 数、软限制、余量、实际 actor 数、在途 API 请求及完成速率；当前没有用 CPU 模拟宣称生产吞吐已恢复。
