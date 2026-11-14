# v203.2.3 新执行入口的 CPU 准入修订

r1 首次实际进入正式 `_run` 后，在任何 controller/provider 请求前遇到继承自 v066 的 `len(policy.host_cpu_pool()) < 176` 硬编码门槛。构建 namespace、验证 selector 或单独测试 public-test 容器都不会执行这一分支，因此之前这些控制通过不能证明完整 actor/controller 入口可运行。

本批冻结 inventory 捕获 32 个 CPU，但正式同时使用的角色 lane 仅为 24 个；`maximum_combined_reserved_cpu=32` 是资源上界，不能解释为最低可用 CPU 数，也不能为了通过检查把 policy 改成返回全服务器 CPU。

| 角色 | 并行数 | 每 lane CPU 数 | 本批冻结分配 |
|---|---:|---:|---|
| coordinator | 1 | 8 | 0–7 |
| actor | 2 | 4 | 8–11、14–17 |
| controller | 2 | 2 | 12–13、18–19 |
| grader | 1 | 4 | 20–23 |

新 `software_benchmark_episode_v203_2_3_r2.py` 不修改旧源或 bundle。它在最终编译使用的 `_run` AST 中精确替换整个旧分支：原来的 diagnostic 检查当前 affinity 至少 4 个 CPU，而 formal 分支要求 176 个；现在两条路径都执行同一个 `validate_runtime_cpu_lanes(policy)`，并在 episode result 中记录 `cpu_lane_admission`。

新准入核对冻结 inventory 属于当前普通用户，scope 与实际 policy 返回同一 pool；各角色实际 cpu_set 与 scope 冻结分配相同；lane 宽度匹配两组 4+2、一个 8、一个 4；所有 lane 位于冻结 pool 内、互不重叠、并集恰为 24 个，且仍受 32 个 CPU 上界约束。coordinator 本身只有 8 核 affinity，因此不会错误要求 coordinator 的当前 affinity 包含 actor/grader 的其他 CPU。没有扩充 CPU、改变亲和性或调整共享服务器配置。

构建新入口时另检查：实际编译 `_run` 的代码名及 transformed AST 包含唯一的新准入调用，旧 176 条件不存在，`run_episode` 引用的正是该 `_run`。不能只修改未被调用的辅助函数。

## CPU 控制与实际诊断的界限

`tools/check_role_context_cpu_lanes_v203_2_3_r2.py` 已通过 9 个必要控制：24 个已分配 CPU 的 pool 可通过，32 个捕获但仅分配 24 个的 pool 也通过；不足、越界、角色重叠、错误 lane 宽度、policy/scope 分配不一致、policy 返回全 240 个 CPU、捕获 pool 超上界均拒绝。控制还从真实继承 `_run` 源码替换并执行同一 guard 语句，分别传入 formal/diagnostic 标志，确认新检查不再被 diagnostic 分支绕过。

证据：[cpu-lane-controls-r2/summary.json](../../artifacts/software-benchmark-v203-2-3/cpu-lane-controls-r2/summary.json)。这些是 CPU 控制，`Docker_operations=0`、`model_calls=0`，明确 `real_environment_qualification=false`。

新 `run_diagnostic(1)` 从本批已授权 plan 查找唯一、`model_calls=0` 的 diagnostic 身份，直接调用同一个实际 `_run(row, None, diagnostic=True, ...)`。实际执行仍需核验该新计划中的 actor/controller/volume 三份资源身份，随后完整走 bundle 展开、actor ready、controller ready、SDK 初始化、真实工具/RPC、输出留存及 owned cleanup。正式模型准入必须等待这次真实诊断的结果、`cpu_lane_admission` 与清理证据通过，不能用本 CPU 控制或注入 mock build 的返回值代替。

r1 的失败记录保持原样；r2 使用独立物理部署身份，现金授权不扩充。旧 9 个未进入 provider 的 admission 如何核对与恢复，由独立执行恢复回执记录，本文不从 CPU 控制推断已完成该步骤。
