# v052 首次 SIGTERM 与监督器连带清理：窄只读审计

## 已证实与仍未知的结论

原 `runs/software-bridge-v052` 的中断包含两个先后事件：**boltons-2／PS1 worker先被收割为退出码−15，随后监督器日志明确记录自身收到SIGTERM，并进入其余三个在途worker的异常清理路径。** 首worker和监督器的信号发送者 PID／UID均未被原记录捕获，来源仍为 unknown，不能断言同一发送者、会话结束、用户操作、OOM或资源管理器导致。

首worker原 `reason=null` 保留。没有其 `host-stop.json`，最后保存的资源守卫 `stop_reason=null`，已存phase时间也未达到原phase／episode上限。因此本证据**不支持将首异常归为已记录的宿主资源守卫主动停止**；它也不是已闭合的context或预算拒绝。缺少终态报告和guard不能被代码0替代。

独立机器摘要：[summary.json](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/interruption-audit/summary.json)，SHA256 `3734d06da9770c9dabbe228d2185f20e9f73c585128969fdfe2bd6077f8b07fd`，21,388 bytes。原run／plan／源码／退出原因均未修改。

## 范围与最小来源

范围仅为首异常 boltons-2／PS1、监督器启动／日志／停止记录、四个中断worker的当前task与registered-child cleanup，以及明确限定的50秒用户journal窗口。不读取大模型轨迹、不重算整个生成过程、不扫描全系统历史。没有模型、tokenizer、测试、复验候选、恢复库存、发信号或修改runtime。

主要原件为：

- [supervisor-launch-r2.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/supervisor-launch-r2.json)：真实监督器PID `3486402`，显式虚拟环境解释器、冻结source cwd和原plan引用。plan SHA为 `97de8f1993a1faa276de51d1505259bec965d0766ebcc16e900774b2d12ace05`。
- [pause.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/pause.json)：首异常槽、原−15／reason=null、结束收割时间及cleanup。
- [supervisor-r2.log](/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/supervisor-r2.log)：833 bytes，保存监督器的SIGTERM异常堆栈。
- [supervisor.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/supervisor.json)：最终5 complete、4 stopped、3 not_started及各worker原时间／退出／清理回执。
- [首worker task.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/workers/v052-cal2-boltons-2-PS1/attempt-001/task.json) 与 [最后已有 telemetry](/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/workers/v052-cal2-boltons-2-PS1/attempt-001.telemetry.json)：原generation阶段与最后保存的守卫结论。审计只是读取这些文件，没有重新执行其中记载的GPU查询命令。
- 三个兄弟槽的 `host-stop.json` 和当前task引用见独立summary的 `stopped_workers[].evidence`。

更早的 `host-import-failure-001.json` 是解释器路径解析导致的 `openpyxl` 导入失败，发生于0worker、0模型阶段，原件另存；不能把它与本次已进入模型运行后的SIGTERM混为同一个原因。

## 实际记录时序

下列为北京时间2026-10-18。`exit_observed_at` 是监督器收割／记账时间，**不是内核记录的精确信号送达时间**。

| 时间 | 原记录事件 |
|---|---|
| 19:45:52.639755 | 首worker最后已有telemetry完成；同PID／start_ticks仍alive，fresh=true，stop_reason=null |
| 19:45:58.609367 | boltons-2／PS1，PID3486410，GPU7，记录退出−15，reason=null，无worker report |
| 19:45:58.609594 | 写入首个 `execution_or_measurement_pause`，目标为上述worker |
| 该pause之后、首兄弟host-stop之前 | 监督器PID3486402收到signal15；日志有明确异常，无精确送达timestamp或sender字段 |
| 19:46:09.316599 | parse-1／PS1，PID3489942，写host-stop，reason=`supervisor_interrupted_or_fault` |
| 19:46:09.841455 | parse-1／PS1记录退出−15 |
| 19:46:09.842193 | parse-2／PS1，PID3493068，写同类host-stop |
| 19:46:10.170113 | parse-2／PS1记录退出−15 |
| 19:46:10.170843 | xmltodict-1／OH_ref，PID3498735，写同类host-stop；其最后阶段仍为loading |
| 19:46:10.388678 | xmltodict-1／OH_ref记录退出−15 |
| 19:46:10.389423 | 监督器写最终paused，无在途worker |

监督器SIGTERM日志原文为：

```text
InterruptedError: CAL2 supervisor received signal 15
```

日志中的动态函数行136对应冻结 [software_calibration_v051_cal2.py:657](/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/source/scripts/software_calibration_v051_cal2.py:657) 的 `time.sleep(LIMITS["poll_seconds"])`。`receive(signum, frame)` 在收到SIGTERM／SIGINT时抛出该异常；外层 `except BaseException`随后对仍active的worker调用 `close(name, "supervisor_interrupted_or_fault")`。

原 `pause()` 仅在 `pause.json` 尚不存在时写文件。因此稍后监督器自身的signal异常不会覆盖先前首worker的pause记录；`pause.json`仍保留首原因是预定的原件保留规则，不表示监督器没有收到后来的信号。

## 首worker与三兄弟的证据区别

冻结 [close分支](/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/source/scripts/software_calibration_v051_cal2.py:545) 只在 `process.poll() is None` 时写host-stop、做before-stop子组清理，然后调用 `os.killpg(worker_pid, SIGTERM)`；已经退出的进程直接进入after-exit清理和记账。

首 boltons-2／PS1没有host-stop，也没有before-stop cleanup；只有 `after_worker_exit:None`，0条registered children，passed=true。它与“监督器先写资源停止原因再主动kill”的已记录路径不同。退出−15说明以signal15终止，而不是正常 `return`；但原件没有siginfo，不能排除进程自行发信号，也不能辨认其它发送者。

另三个worker都有 `supervisor_interrupted_or_fault` host-stop，随后有before／after cleanup与−15退出，完整对应监督器异常清理代码路径。该证据绑定的是**记录的清理路径**；没有独立内核sender记录，不额外声称捕获了每一次kill syscall或排除了同时发生的其它信号。

已注册子组清理的范围也有限：首worker和xmltodict worker为0条记录；parse-1的2个、parse-2的3个已注册child在清理时均为`already_absent`；原before／after回执全部passed且`unresolved=[]`。这不等于证明其它无关进程或整台机器均已清空。

## 原限额核对与journal缺证

首worker最后generation阶段开始于epoch `1792323870.6286924`，到退出收割时约87.981秒，低于原宿主generation900秒。其episode开始于 `1792323339.7334504`，到收割约618.876秒，低于6000秒硬边界。最后已有telemetry采样开始于 `1792323952.555957`，fresh=true、查询完成、errors为空、stop_reason=null。

这些证据支持“没有记录到原资源守卫触发”，不能重建信号送达瞬间的RSS、磁盘或所有物理状态。没有`host_rss_budget`、`artifact_budget`等停止记录，不把未测得的现场数值写成已通过。context／模型预算另有自身的执行前拒绝回执，本次不能用SIGTERM代替这些类别。

按明确授权，只执行一次用户journal查询：

```text
XDG_RUNTIME_DIR=/run/user/1004
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1004/bus
journalctl --user --since=@1792323940 --until=@1792323990 --no-pager -o short-unix
```

即19:45:40—19:46:30，退出码0，输出`-- No entries --`。[查询观察记录](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/interruption-audit/user-journal-window-result.json)保存该窗口和原输出，没有扩大查询。无条目是缺证，不是“该时段无信号／无会话停止”的证明。

首worker日志末尾的 `Agent execution pause requested` 没有OS信号sender信息，不能因词语“pause”便把它当SIGTERM来源。未从普通退出码、阶段时间或另一GPU进程推断发送者。

## 仅针对后续宿主的最小记录／隔离建议

以下为预防性建议，本审计没有执行或修改任何启动方式；**不证明旧信号来自session生命周期**。

1. 用已可用的strace仅直接启动并跟踪监督器，类似 `strace -ttt -e trace=none -e signal=SIGTERM,SIGINT -o <new-signal-log> <explicit-python> -m <new-host> ...`。不加`-f`，避免跟踪原生GPU子进程的syscall；保存signal delivery中实际可得的`si_code`、`si_pid`、`si_uid`。无法提供这些字段的内核信号仍应记unknown。这个最小方案只覆盖监督器收信，不能反推任意直接发给worker的SIGTERM sender。
2. 用唯一命名、有限的transient user service承载新监督器，`Restart=no`，明确cwd、解释器、PYTHONPATH、plan和日志，保留原native worker命令与身份合同，不启用自动后继。这样可降低当前shell／login-session父链退出的耦合；user manager自身停止仍是独立生命周期条件，不能据此承诺消除一切信号。
3. 不修改模型loop、Γ、数值provider、预算、测试或评分规则。只接续原未开始库存的授权和新宿主协议必须单独记录。四个中断槽是否具备精确恢复所需状态由独立账单／状态证据判断，本审计不授权重复采样，也不把未到达的guard或末树验收补为通过。

恢复与费用边界另见 [partial-accounting-audit.json](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/partial-accounting-audit.json)。本文件没有重新计算逐请求账单；首异常原−15／reason=null、其余原−15／supervisor异常清理原因、5闭合／4中断／3未开的唯一库存均保留。
