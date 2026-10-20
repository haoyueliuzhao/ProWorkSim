# v054 每题生命周期、宿主停止与候选闭合准备

本批完成的是独立生命周期模块及 CPU 合成控制，不是正式模型回合。固定 1,500 槽未消费；模型调用、权重读取、GPU 访问和评分调用均为 0。正式运行与预算授权仍为 false。既有 MATCH 数值桥、共同精确计量、SDK 工具、评分器和 PROJECT 双候选导出源码未改。

## 新增实现

`software_benchmark_episode_v054.Episode` 从带 SHA 的固定题槽清单选择唯一 slot，绑定 configuration、environment、owner 准入回执。正式 claim 目录固定为 `runs/software-benchmark-v054/episode-claims`，名称由 slot_id 决定，用原子目录创建避免并发重复领取。准备控制只能使用 `synthetic-` 前缀及独立目录，不能消费正式槽。正式进入另外要求明确运行授权回执，绑定题槽清单 SHA 和允许的 slot_id；已有 `execution_authorized=false` 清单本身不会放行运行。

进入窗口前先写不可覆盖的 `entered.json`。任何已进入槽，包括 owner 初始化或系统故障，都不能重新进入、重采或另选最终候选。重复构造同一个 claim 也会拒绝。实际模型回合计数仍由原有 ledger 负责，生命周期不会把“已进入”伪报成已生成一次。

MATCH/PROJECT 进入时核对真实 `CalibrationActor`、原始发布身份、无训练适配器、固定 revision/manifest、project 数值路径及 BF16 backbone／FP32 head，然后依次调用已有 `capture_evaluation_state`、`begin_window`、`reseed`。seed 取自固定槽。REF 检查既有 adapter 的固定任务 seed。`EpisodeAdapter` 包装两组已有共同计量 adapter，保持 tools、模板、condenser 和数值路径不变，agent 与 condenser 都经过同一生命周期门；原有计量时钟对齐本题进入时间，不把环境准备时间混入生成期限。

正常返回时，`finish_owner` 先关闭后续分派，再调用已有学习状态与 RNG guard。正常关闭仍受独立 hard timer 约束。强制终止路径不执行伪造的 RNG 恢复，不声明模型状态可复用，也不补写未知费用为 0；原 ledger 的完整预约与未知 actual 保留。后续真实 runner 仍须持久化并引用这个 ledger。

## 宿主监控与停止证据

`software_benchmark_supervision_v054` 只管理本次 claim 创建、带 UUID 的 `proworksim-v054-episode-<claim>-<role>.service`。每个服务登记宿主 MainPID、`/proc` start_ticks、实际 InvocationID、cgroup 路径和外层 `systemd-run` launcher 身份。namespace 内部 PID=1 不是宿主 PID，不用于停止其他进程。`systemd-run --pipe --wait` 保留 worker 的 stdin/stdout RPC 管道。

服务固定 `KillMode=control-group`、`SendSIGKILL=yes`，并有 systemd `RuntimeMaxSec` 兜底。独立宿主 Python 进程监控本题 hard deadline 和当前请求 deadline，不获取 SDK/RPC 锁。到期后向该服务发停止请求，systemd 在 TERM 宽限后 KILL 全 cgroup；仍无法证明静默时记录错误并拒绝候选导出。子进程自行 `setsid` 不会脱离 cgroup。

正式限制保持 soft 5,400 秒、hard 6,000 秒；新模型请求的宿主外层上限为 REF 1,860 秒、MATCH/PROJECT 660 秒，且不超过剩余 hard 时间。它们分别给现有 1,800/600 秒生成超时留出停止余量，不扩大生成预算。工具 RPC 使用既有有界读取及剩余 episode 时间；本模块不会给工具偷偷增加一个不受管入口。单次合成控制使用缩短期限，代码拒绝把该覆盖用于正式槽。

worker 的 `closed` ACK 仅说明 official terminal cleanup 返回。候选导出要求服务 inactive/failed、MainPID=0、cgroup `populated=0`，再要求外层 launcher 已退出并由其 Popen owner 回收。单纯关闭 ACK、PID1 返回、杀进程组或清空一个 Python busy 标志均不构成完整证据。正式 scope 清单要求 controller、actor、独占 model 三种角色；任何未登记的写入者或共享服务不得视为已被停止。

服务创建与 user manager 注册异步。实现容忍短暂的 unit 未注册；身份准入失败时同时清理本次 UUID 服务和 launcher，不能只杀 `systemd-run` 客户端。

## 候选闭合

`software_benchmark_native_closure_v054` 仅在上述静默证据成立后进入一次性的 `candidate-claim.json` 边界：

- REF/MATCH 调用已有 `capture_repository` 和 `export_git_patch`，完整保留新增、删除、二进制、可执行位、符号链接等合法树变化，并使用原有 Git roundtrip 验证。只有 terminal-code 端点，delivery 为 null。
- PROJECT 调用已有 `lock_episode_candidates`，保持最终工作树与最后合法固定提交两个端点、版本关系和项目交付语义，不另造评分规则。
- 导出异常保留 `candidate_export_technical_unknown` 和不可重选 claim，不以初始树替代，不填正常 R0，不进入评分后选择。

这里是闭合原语及调用接口，尚未组装真正的模型调度 runner。实际 Docker 停止、模型独占服务、公开树路径、官方评分请求还须在各自准入后统一接线。

## 必要控制及实际观察

只执行一轮完整 CPU 合成集成：

```bash
.venv/bin/python tools/check_episode_lifecycle_v054.py \
  --output runs/software-benchmark-v054/lifecycle-control-r1
```

结果为 14 项检查全部通过，详见 `software-benchmark-v054-lifecycle-control-r1.json`。该控制创建一个本项目独占 user service；父进程忽略 TERM、返回不完整 JSON 帧，子进程另外建立 session 并持续写 heartbeat。使用当前生产 `NativeToolRPC` 的原始 AST 类执行真实 fd/select/os.read 路径，0.1 秒指定 timeout 得到 TimeoutError，失败 transport 的 close 被拒绝；没有重复创建 Agent，也没有把合成 ready 当作实际镜像准入。

独立 watchdog 在合成请求期限后停止该服务。实际观察为 cgroup 清空、外层 launcher 回收、父子进程不再运行、heartbeat 停止。之后才允许完整合成候选导出，并验证二进制 patch roundtrip；提前锁定、重复 slot claim、已进入重入和第二次候选选择均被拒绝。owner 是脚本化 CPU fixture，只验证 capture→window→seed 调用次序，不证明真实模型 RNG 或学习 guard 已执行。

完整集成后只补了一次针对性断言，见 `software-benchmark-v054-lifecycle-targeted-control.json`：新增外层 launcher 门拒绝活进程并接受原控制中已回收的 launcher；adapter 对齐本题起点并拒绝跨槽绑定。没有重跑整套集成。新增四个 Python 文件通过 Ruff 检查。正常真实 owner 清理路径和 PROJECT 新包装未在本轮重新运行，依赖的既有候选模块检查不重复执行。

## 仍未准入的边界

1. 真实 runner 尚未将 controller、数值 owner、actor、每题 ledger 和以上生命周期绑定成同一正式执行链；当前不能据此启动 1,500 回合。
2. 原生 worker 的真实镜像 UID／numeric ownership 门仍未通过；本轮不改变该门。
3. controller 与 worker 必须共同受原定 4 CPU／16 GiB／16,384 pids 环境限制约束。本模块尚未建立公共父 slice，不能分别给两者完整额度后声称总资源相同。本轮的 user-unit 控制只证明停止覆盖，不证明资源公平性。
4. 实际 vLLM GPU 服务、容量准入、正常 owner RNG guard、实际标准题最终树与官方评分仍待独立执行；本轮只使用合成 CPU 数据。
5. 如果生成进程或机器故障导致 ledger、可信最终树或停止证据缺失，结果必须保留技术未知，不恢复已进入槽，也不以未知为 0 成本或模型失败。

机器可读汇总为 `artifacts/software-benchmark-v054/lifecycle/preparation-manifest.json`，入口配置为 `config/v054-episode-lifecycle.json`；二者保持 `formal_execution_authorized=false`。
