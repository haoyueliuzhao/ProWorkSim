# v092：补齐 API 初始化授权链后继续原 44 项

v091 已修复压力监控器拒绝恢复身份的问题，但真实启动仍失败：预算 runtime 在 `initialize_for_run()` 中固定调用 `v089.api.request`，新 scope 的允许操作遗漏此名称。拒绝发生在客户端、模型和任务环境初始化之前。此前只检查函数绑定，预算单元控制又使用了替代 guard，没有测试完整生产授权链；这属于实现及测试覆盖不足。

**实际运行结果更新：v092 初始化通过，但44项均在模型调用前因计划缺少 `host_cpu_pool` 失败。** 全部44个 actor 容量 claim 和 episode 元数据目录已经创建，容量已释放；没有创建 DockerClient、容器或任务卷，也没有 API 请求。原始结果均保留为技术未知，不能将零调用写成模型失败或完成评测。此前完整 API 初始化控制覆盖了授权和计费链，没有执行真实 episode 的 CPU 库存读取，因此仍漏掉这项计划合同缺失。旧物理索引6000–6043已经消费，不允许覆盖后重用；v093另用6044–6087，同44个仍未消费的逻辑模型尝试保持。完整证据见 [44项零模型／零Docker审计](../../artifacts/software-benchmark-v093/zero-generation-physical-handoff-r1/summary.json)。

v091 管理进程已自然退出，自己的 reservation lease 已释放。只读核验确认：没有 `execution-started.json`，44 项 API 请求0、任务资源 claim0、episode目录0，原父组仍为 v089 已批准的同一实例。v092 不追加恢复次数、不修改任务、seed、模型输入、工具、预算或控制器；新建独立普通用户 manager，继续原44项未消费身份，现金仍共享1700元账本。

## 修复与实际初始化控制

新 scope 明确接受预算 runtime 的 `v089.api.request`／`v089.api.run`。这些请求在新 scope 本地执行新 manager 的 host-limit 和 lease 校验；不会把 API 操作名转交仍缺该名称的 v091 guard。旧授权链只以固定 `v089.run` 核查原计划和资源范围。资源、provider、评分所需的原操作名同时保留，未知操作继续拒绝。

这次执行完整真实 `RuntimeView.initialize_for_run()`，不是替代 preflight：核对原增补预算回执、账本、原 neutral 资格、真实 SDK schema，加载真实官方 tokenizer，创建真实 amended client；分别创建 REF 和 PROJECT broker 并调用其原 `authorize`。初始化与两个 broker 都实际经过 `v089.api.request`。

控制使用生产 scope 和 host-limit 函数代码，临时 cgroup 文件明确模拟新服务的64GiB硬限、32GiB MemoryHigh、swap0、512进程、原8核及FD16384；真实执行七次资源核验和 lease 字节比较。缺 lease、外来 lease、错误 MemoryMax 和未知操作均被拒绝。临时 cgroup 是 CPU 夹具，不冒充对真实服务的内核观测。

原 preflight 继续只读真实账本；写入能力的客户端改指 SQLite 一致备份，使用无效测试 key，不读取实际密钥。控制期间 socket connect、HTTP connect 和 DNS 均设置为立即失败，实际尝试0；没有 `.complete()`、模型、Docker、GPU或服务操作。真实账本请求数前后均为46504。该控制验证的是初始化和派发前授权，不是服务端模型响应质量。

结果及操作名调用链见 [完整初始化控制](../../artifacts/software-benchmark-v092/real-initialization-control-r1/summary.json)。独立自然退出和零消费证据见 [交接回执](../../artifacts/software-benchmark-v092/unentered-handoff-r1/completed.json)。Ruff 通过。没有为此重复运行旧大套测试。

## 部署和结果边界

新服务为 `proworksim-v092-api.service`，运行目录为 `runs/software-benchmark-v092/unentered-pressure-recovery-r1/api-coordinator/`。保留 v091 及更早源码和失败记录，复用 v091 已验证的精确44项压力白名单；原父组生命周期、异步评分和资源门保持。

准备封存之后由新 launcher 启动；真实运行恢复应以模型请求数实际增长、任务 entered、actor 创建及压力门正常为依据，不能再以 manager 启动成功替代。最终结果以新目录运行回执为准。

```bash
.venv/bin/python tools/run_offline_scorer_v058.py tools/prepare_api_pressure_recovery_v092.py --prepare
.venv/bin/python tools/run_offline_scorer_v058.py tools/launch_api_pressure_recovery_v092.py --launch
```
