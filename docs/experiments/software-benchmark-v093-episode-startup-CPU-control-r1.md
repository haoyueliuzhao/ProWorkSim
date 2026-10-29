# v093：任务启动链的必要 CPU 控制

本次扩大了检查范围：不再仅检查管理器初始化。**REF、PROJECT 的真实任务启动代码均已执行到第一次构造 Docker 客户端之前；独立的真实 API 运行时初始化及物理编号映射授权也通过。** 这仍不是完整系统运行通过，没有创建容器、发送 HTTP 或运行模型。

入口为 [check_api_episode_v093.py](../../tools/check_api_episode_v093.py)，最终证据为 [summary.json](../../artifacts/software-benchmark-v093/episode-startup-control-r1/summary.json)。最终四项门为 `passed=true`、`full_required_CPU_control_complete=true`、`interfaces_checked=[REF, PROJECT]`、`broker_controls_complete=true`；同时明确记录 `full_system_runtime_verified=false`。

## 实际执行的范围

| 路径 | 真实执行内容 | 模拟／停止边界 |
| --- | --- | --- |
| 新 scope 与完整计划 | 实际 `require_allowed`、`validate_complete_plan`、44项物理映射与原配置身份检查 | 新管理器的授权／source／lease 文件和管理器 cgroup 使用临时夹具；parent 存活仅显式模拟，不声称验证内核状态 |
| 实际 episode | REF、PROJECT 各1项真实 `bindings.episode(policy).run_episode`，包括 `_row_and_config`、实际 claim／release、冻结包校验、公开环境与公开测试上下文 | 只在新建的私有函数字典中把 claim 和输出路径改到 `/tmp`；无正式任务记录或预约被写入 |
| 固定 CPU 清单 | 原 `host_cpu_pool` 真正读取新计划绑定的原固定 CPU 清单，数量至少176，并与原清单一致 | 没有 stub 此函数，也没有更改服务器 CPU 设置 |
| Docker 入口 | 原流程实际完成项目 socket 的文件类型检查并到达 `DockerClient(...)` 调用点 | 构造函数被 CPU 哨兵截住；真实客户端、连接、容器和挂载均未创建 |
| 模型可见配置 | 实际原 `controller_inputs` 和 REF／PROJECT 各自原 `validate_config`；原 condition 字节保持 | actor-ready 明确是模拟标记，没有把它当作隔离证明；未启动 PID1 控制器 |
| API 初始化与新旧编号 | 原完整 preflight、真实 tokenizer 和 client，继而调用实际 `PhysicalRuntimeView.transport_factory` 和 broker `authorize` | 写能力 client 仅使用临时 SQLite 副本；授权载荷是程序构造的 schema 载荷，并非 SDK 实际生成的首次请求；停在授权，未发 HTTP |

检查中的新物理编号6044、6045分别严格映射回 canonical 6000、6001，逻辑 `slot_id` 不变；将旧物理编号误当新启动输入会被拒绝。真实唯一账本通过只读连接检查，运行前后请求数均为46,504。临时账本也没有新增请求。全部 scope 调用及边界记录保存在最终证据中，Ruff通过。

## 不能由这次检查得出的结论

没有验证真实 Docker 创建／启动与内核隔离、实际 rootfs 和解释器、基线工作树快照、PID1 SDK 进程、FIFO／stdio 链路、首次 SDK 生成的请求及真实 API 响应，也没有执行公开测试、候选导出或官方评分。因此，这次只能说明已覆盖的准备和映射路径可执行，不能宣称评测恢复或环境端到端通过。

下一次受控恢复仍应先让 REF、PROJECT 各1项完成可信生成与实际用量结算，再扩大派发；实际部署中出现的其他未知必须单独记录。不能仅凭本文件的 CPU 门通过，再次直接扩大到44项而绕过尚未覆盖的运行边界。

原仅到构造边界的阶段记录保留为 `startup-only-summary.json`，其 `broker_mapping_stage` 为 pending，**不作为最终准入证据**。最终 `summary.json` 同时包含 episode 边界与独立 broker 控制，明确区分已覆盖与未覆盖范围。
