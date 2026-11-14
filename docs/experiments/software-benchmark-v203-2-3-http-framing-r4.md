# r4 明文 HTTP 完整边界观测控制

旧 Requests empty 控制中的 idle timeout 只保留了 TCP 字节数，没有 HTTP framing 原件，不能因为收到 1024 字节或官方负控结果符合预期，就把历史连接改判为成功。r2/r3 原判定保持。本修订新增独立观测模块、CPU 控制和两个全新环境控制，已封存正式 API 源码与历史模型结果保持原样。

## 使用成熟解析器的语义依据

本地固定 scorer Python 中已有 h11 0.16.0，未安装或修改依赖。核对了官方 API 文档及本地 `_connection.py`、`_readers.py`、`_headers.py` 的实现：`receive_data` 只加入接收缓冲，`next_event` 才推进解析；`EndOfMessage` 表示已完成相应消息边界；双方达到 DONE 后才能 `start_next_cycle`；`trailing_data` 是尚未处理的字节。HEAD、204、304 的无消息体规则与 Content-Length/chunked/EOF framing 来自 h11 自己的 `_body_framing`，不是自制宽松 parser。[h11 官方 API 文档](https://h11.readthedocs.io/en/latest/api.html)

固定版本下调用私有 `_body_framing` 仅用于记录与解析器一致的 framing 元数据，h11 自己仍负责读出真实消息边界。`parser_descriptor()` 提供全部本地 h11 Python 源文件的路径、大小与 SHA256，供新 relay profile 封存；版本不是 0.16.0 时拒绝豁免。

## 独立模块与接口

新模块为 `src/proworksim/software_benchmark_http_framing_v203_2_3_r4.py`，每个连接一个 `HTTPKeepaliveTracker(port=80)`：

- `feed_client(data)`：仅喂给已经实际成功发送到 upstream 的原始字节。
- `feed_server(data)`：喂给 upstream 实际接收到的非空原始字节。
- `server_eof()`：只能在真实 recv 返回 EOF 时调用；idle timeout 不能伪造 EOF。
- `proof()`：返回 framing 与状态证据，不能单独当作 relay 成功或测试通过。

内部两个 h11 endpoint 分别解析客户端与服务器原始流，将解析事件镜像给另一端以维持请求 method 和响应状态。镜像事件产生的序列化字节全部丢弃，不进入网络，也不替换被转发字节。这样 HEAD、1xx、pipeline 都使用真实请求上下文。

只有明文 80 端口、至少一个完整请求/最终响应、所有请求体和响应体均收到完整 EndOfMessage、没有待响应请求、没有残余未解析字节、双方 h11 状态都回到 IDLE、没有错误或升级、没有 EOF 的连接，`eligible` 才为 true。新 relay 还必须同时证明该连接待发队列和全局发往 Docker 的队列都为空，才允许将 idle 关闭记作“已完成 keepalive”，不能仅凭本模块 eligible 字段放行。

这是仅关于传输完整边界的有限判断。即使 HTTP 状态是 4xx/5xx，framing 也可能完整；不据此推断应用、TLS 或测试成功。反之，EOF-delimited 响应只有实际 EOF 后才能记录完整，但它仍不取得 idle keepalive 豁免。

除 h11 原有语法与长度检查外，本模块明确拒绝 TE+CL 同时存在、framing/routing header 放入 trailer、CONNECT、Upgrade/101 和 HTTPS target。443/TLS、未知/不完整/冲突输入继续保持原有 relay 故障处理。HTTP/1.0 和要求 Connection: close 的连接不作 reusable idle 豁免。h11 合法归一化的相同重复 Content-Length 可完成；不同长度或冲突列表由 h11 拒绝。

每连接最多记录 256 个 exchange，未完成 header 上限 16 KiB，总 parser 缓冲上限 256 KiB。过界或解析异常只会永久取消本连接豁免资格，不修改转发数据、不重试、不延长旧 relay 时间/字节预算。proof 包含 method、最终状态、1xx 列表、request/response framing、声明及 framing Content-Length、实际 body 字节数、trailers、双方状态、计数和剩余缓冲量。

## CPU 控制结果及适用范围

在实际固定 scorer Python 与已有 h11 0.16.0 上运行：

```bash
.venv/bin/python -B tools/run_offline_scorer_v096.py -m pytest -q \
  tests/test_http_framing_v203_2_3_r4.py
```

35 项通过，pytest 报告用时 0.24 秒。控制覆盖完整与截断 Content-Length、相同/冲突重复长度、TE+CL、chunked 请求/响应与 trailer、单字节分片、HEAD、100+103、204/304、多请求 pipeline、未回答/未完成的下一请求、真实 EOF 与截断 EOF、TLS/升级拒绝及资源上限。控制没有打开 socket、Docker 或模型 API。

证据：[http-framing-cpu-r4/summary.json](../../artifacts/software-benchmark-v203-2-3/http-framing-cpu-r4/summary.json)，包含实际解释器、h11 源文件散列、模块/测试文件散列及本次成功 pytest 输出记录。

上述 CPU 结果证明合成原始流上的解析与保守判定。实际 relay 接线和真实环境准入由下述独立控制提供；旧 r2/r3 超时仍缺原始 HTTP 边界，历史未知保持。

## Relay 接线、原始记录与重放

`software_benchmark_tcp_transport_v203_2_3_r4.py` 在冻结 v066 relay 的精确位置接入观测：上游 send 实际成功之后记录发送字节，recv 收到非空数据后记录接收字节，只有真实 recv EOF 才调用 EOF 接口。连接、端口、公共端点、重试规则、64 MiB 应用流量上限和 60 秒 idle 阈值保持。两个主机发送队列必须同时为零；条件不满足时仍走原 upstream_idle_timeout 分支。

每个真实评分容器对应一个独立的 `official-output/http-framing-stream.jsonl`。80 端口原始字节按方向以 Base64 留存，并保留连接开启、结束、idle 判定、完整 framing、队列长度及相对时序。443 只记录连接元数据，不保存或解析 TLS payload。原始 HTTP 上限 64 MiB，日志上限 128 MiB、200000 条记录；解析、记录或边界异常会取消豁免，不能静默退化为通过。

新资格校验核验日志文件 SHA256，按原始顺序重放所有 HTTP 字节，用固定 h11 代码重新计算每个 idle 时刻的 framing，再核对原记录中的两发送队列为零。它同时检查 actual transport 中所有 `completed_http_keepalive_idle_close` 与原始日志的豁免记录一一对应。日志头绑定实际冷解释器 h11 源文件；环境 manifest 使用相同源文件名、大小和散列组成的可移植描述，避免仅因冷、热解释器安装路径不同而误判代码变化。

这里的完整性边界是上游 HTTP 帧及主机侧提交到容器 relay 的发送队列。它不声称应用已经消费、理解所有字节，也不把 HTTP 401/200 或消息边界当成测试通过。官方测试报告继续单独决定代码是否解决任务。

实际 frozen relay 的假 socket 控制和 scorer 绑定新增 8 项，全部通过。覆盖应用转发字节保持、完整 idle 可重放、截断仍失败、发往 Docker 的队列未空仍失败、443 不豁免、修改 proof 后原始流重放拒绝，以及固定环境绑定。连同 tracker 共 43 项必要 CPU 控制；没有用 CPU 测试替代真实环境准入。

## 两个全新实际环境控制

使用两个新身份 `control-r4-psf__requests-1766-gold` 和 `control-r4-psf__requests-1766-empty`，与正式运行共享单 grader 锁，保持每个 grader 的 4 CPU、16 GiB 限额。固定 IP 为先前独立 current DNS/probe 选定的 `3.221.253.123`，不轮换端点；沿用原已审计的评分侧 v116 CA profile，原仓库 CA 文件与候选字节保持。两个控制均未调用模型 API。

| 控制 | 官方回执 | resolved | 非豁免网络错误 | proved complete idle | 清理 |
|---|---|---:|---:|---:|---|
| 新 gold | official_report | true | 0 | 0 | quiescent，cleanup_errors=[] |
| 新 empty | official_report | false | 0 | 1 | quiescent，cleanup_errors=[] |

新 empty 的连接 4 为明文 80 端口，实际发送 730 字节、收到 1024 字节，约 60.887 秒后关闭。与旧记录不同，这次原始数据可重放确认两个完整 GET exchange：首先是 HTTP 401、Content-Length 0；其次是 HTTP 200、Content-Length 68，全部 68 个响应体字节均已观察到。idle 时请求与响应完成数均为 2、待响应数为 0、两个 parser buffer 为 0、两个 h11 endpoint pair 均为 IDLE、两个主机发送队列均为 0。这满足预先冻结的 r4 有限豁免规则。

新 gold/empty 已通过官方正负控制、原 TLS/CA 与物理清理校验，以及新增原始 HTTP 重放校验，生成独立 canonical qualification。`resolved=true` 使用原官方任务判据，不声称整个 raw pytest 输出没有任何额外失败。

证据：[实际控制与 framing 摘要](../../artifacts/software-benchmark-v203-2-3/grading-http-framing-controls-r4/summary.json)、[终态结果](../../artifacts/software-benchmark-v203-2-3/grading-http-framing-controls-r4/result.json)、[此前 idle 证据限制与恢复审计](../../artifacts/software-benchmark-v203-2-3/grading-empty-recovery-r3/idle-timeout-audit.json)。新资格位于 `runs/software-benchmark-v203-2-3/role-context-pilot12-r1/grading-coordinator-r4/qualifications/psf__requests-1766.json`。

本次新实证证明当前 r4 empty 存在完整响应后的 idle keepalive；它不能补造旧 r2/r3 缺失的 framing 原件。原技术未知、原失败端点、一次受控取消和独立重试均完整保留，没有回写成通过，也没有因此换题或重采模型结果。
