# v052 接续：异常信号证据与已实施的观察措施

原 v052 中首个 worker 和监督器所受 SIGTERM 的发送者仍未知。后续已执行的服务隔离、信号观察控制和 r2 入口修复改善了接续的运行方式与可观察性，但不能反推历史信号来源。本文只连接现成审计、控制和启动回执，不增加系统查询、GPU/模型检查、测试或信号探针；r2 运行结果由最终结案记录补充。

## 原中断：能证明什么

[窄信号审计摘要](../../artifacts/software-bridge-v052/interruption-audit/summary.json)与[时序说明](software-bridge-v052-interruption-audit.md)保留以下事实：

- `boltons-2/PS1` 首先以 `-15` 退出，原 `reason=null`，没有对应的宿主 `host-stop` 回执。最后保存的遥测没有资源守卫停止原因，记录中的生成和回合年龄也未到各自上限。这支持“没有记录到宿主资源守卫触发”，不能证明信号瞬间的一切物理状态，更不能据此确认或排除某个信号发送者。
- 监督器随后明确记录 `InterruptedError: CAL2 supervisor received signal 15`。原件没有保存内核投递的 sender PID/UID，首 worker 与监督器是否由同一来源发信号也未证实。
- 后续 `parse-1/PS1`、`parse-2/PS1`、`xmltodict-1/OH_ref` 三个兄弟 worker 有 `supervisor_interrupted_or_fault` 的宿主停止回执、登记子进程清理记录和 `-15` 退出。它们可绑定到原监督器收到异常后的清理路径；这仍不同于获得当时内核 siginfo。

已有一次限定 50 秒窗口的 user journal 查询返回无条目，未找到发送者证据。没有据此扩大系统历史搜索，也不能把无条目解释为信号没有发生。现有证据不支持将首中断归为 context 耗尽、团队/成员预算拒绝、OOM、用户主动停止或会话清理。四个原中断槽的科学结果继续保持未知，不因新观察方式而恢复、重采或改写。

## 从建议到实际控制与启动

原审计中的宿主观察建议已通过一个独立、无模型控制：[信号来源控制摘要](../../artifacts/software-bridge-v052/signal-provenance-control/summary.json)。它在新的短时 user service 中，只向新建探针父进程发送一次 SIGTERM；新子进程的 sender PID/UID 与监督器式 `strace` 输出中的 `SI_USER`、`si_pid`、`si_uid` 匹配。服务正常退出、`Restart=no`、无 fork 跟踪，未使用原实验 PID，也没有 GPU 或模型调用。这证明该观察方式能记录该类用户态 SIGTERM 的投递信息，不证明它一定能识别所有内核信号来源，也不解决历史发送者缺失。

接续采用独立 transient user service，明确冻结工作目录、Python、PYTHONPATH、环境与计划，设置 `Restart=no` 和 `KillMode=control-group`。服务隔离的作用是减少对启动 shell 生命周期的依赖，并留下独立启动回执；服务管理器退出或显式服务停止仍属于可能的生命周期事件。这是预防性运行安排，不是“历史 SIGTERM 来自会话清理”的证据。

信号观察仅包装监督器，命令形状为 `strace -ttt -e trace=none -e signal=SIGTERM,SIGINT -o <supervisor-log> <supervisor-command>`。没有 `-f`，不跟踪 native worker 或任意子进程，不给 native worker 增加包装，也不修改其模型数值路径、工具或资源守卫。若信号投递给被跟踪的监督器，日志可在可用时保存 `si_code/si_pid/si_uid`；若信号只直接投递给未跟踪的 worker，该通道不能捕获其来源。没有记录到监督器信号不能推导“任何子进程都未收信号”。

## r1 零入口故障与历史四个未知分开

[独立 r1 零入口回执](../../artifacts/software-bridge-v052/resume-r1-zero-entry-audit.json)记录，r1 监督器 trace 正常退出码为 0，未记录新的 SIGTERM/SIGINT。三个 worker 均以退出码 1 在原 bridge worker 的第一项 `frozen(root)` 操作失败，尚未越过 slot-started 边界；task、resident、模型 calls、prepared、episode 等入口材料均不存在，开始/完整调用、token 和不确定预约全部为 0。

[跨解释器根因摘要](../../artifacts/software-bridge-v052/resume-r1-binding-diagnostic/summary.json)证实，准备端 Python 3.14.6 与 native Python 3.12.3 对 `ast.dump` 空字段的默认文本表示不同，唯一不一致的绑定字段是 `supervisor_AST_sha256`；源码 SHA 和其它绑定元数据相同。按相同规则省略 `None` 和空列表后，两棵 AST 结构完全相同。这是已证的宿主元数据拒绝，与原模型阶段 SIGTERM 没有已证因果关系。

r1 三个 worker 的 15.057310104370117 秒进程成本独立保留、只计一次；没有产生三个新的科学样本或三个新的模型未知结果。原四个已进入模型阶段的未知槽仍独立保留。r1 源码、plan、release、停止记录与 trace 没有热改。

## r2 已执行入口与证据边界

[独立 r2 协议](software-bridge-v052-resume-r2-protocol.md)及[宿主方法说明](software-bridge-v052-resume-r2-host-method.md)使用明确版本化的 canonical AST 表示修复上述绑定，保持原科学源码、三槽身份、种子、预算、工具、模型和资源守卫。r2 同时绑定 r1 零入口证据；若该证据出现 started、模型费用、变更 trace 或新的执行材料，就不能按零模型入口修复继续。

冻结提交 `c3ead22` 后，[实际生产入口回执](../../artifacts/software-bridge-v052/resume-r2-production-entry/summary.json)记录：prepare 后使用正式 native Python 3.12、`CUDA_VISIBLE_DEVICES=''`，只调用一次真实 `frozen(root)`，退出码 0、`passed=true`；新增模型、tokenizer、SDK 调用均为 0。该回执验证完整生产计划与原件绑定，不能当作模型生成、验收或任务成功。

随后，[r2 服务启动回执](../../runs/software-bridge-v052-resume-r2/supervisor-service-launch.json)记录 `proworksim-v052-resume-r2.service` 已由 `systemd-run --user` 接受，客户端返回码 0；它绑定同一 plan、release 和生产入口回执，并明确 `native_workers_wrapped=false`、`strace_follow_forks=false`、`restart=no`、`global_runtime_cap_added=false`、`automatic_successors=false`。这证明启动安排实际执行，不表示三个槽已成功完成。原各阶段/回合资源守卫继续生效，没有因观察而新增全局等待超时。

本文的证据边界截至上述启动回执。r2 的最终槽状态、费用、是否出现新的监督器信号及相关来源信息，均待其实际终态原件与结案报告记录；本文不提前填写成功、信号不存在或历史根因已解决。即使后续运行正常，也不能用后验结果识别原两个 SIGTERM 的发送者。

## 终态补记（2026-10-18）

上述正文保留启动时点边界。随后 r2 三槽均正式闭合，80 次实际调用全部收到完整回包、888,289 token，无新增不确定预约；结果为 PS1 的 R_code=0/1、OH_ref 的 R_code=0，详见[唯一十二槽合并报告](software-bridge-v052-completion-final-r2.md)。

监督器信号 trace 的唯一终点为 `1792326667.195952 +++ exited with 0 +++`，没有记录 SIGTERM/SIGINT。终态服务仅查询一次，原工具结果保存于[service-status.json](../../artifacts/software-bridge-v052/resume-r2-terminal-observation/service-status.json)：inactive/dead、Result=success、Restart=no、MainPID=0。瞬态单元已结束，ControlGroup、InvocationID 等字段为空；实际启动身份仍绑定原启动回执，空字段不被填造为新身份记录。该文件从当次工具结果转存，工具未分别提供 stdout/stderr，二者明确保留 null。

本次正常退出表明这一次接续没有再次触发同类监督器中断，不证明历史信号来源已解决，也不扩展 supervisor-only 观察的覆盖范围。无需追加诊断或自动重启；原四条技术未知保持不变。
