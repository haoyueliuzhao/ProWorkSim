# 实验收尾后的项目GPU释放（2026-10-23）

用户明确要求实验完成后释放显卡、清理磁盘。本记录仅涉及已终态实验的4个GPU resident及其自动派发监控器，磁盘清理由独立记录负责。没有删除模型、镜像或实验文件，没有GPU reset，也没有向非本次登记的进程发送信号。

## 释放前资格

北京时间 **10:22:07** 的释放前证据确认：原Qwen1500槽、DeepSeek3000槽均无pending／intent／running generation；6个pre-entry恢复槽也已终态，其3个评分端点全部终态。独立恢复摘要引用为 `runs/software-benchmark-v055/pre-entry-recovery-r1/summary.json`，SHA `a23dfc36d64e3fd5e44e8bb2287e976edcbba15a6ac8451f27bc89beeea758c3`。当时没有活动的项目generation队列或worker unit。

按原注册事件和固定declaration精确定位如下服务。每个服务的MainPID、start_ticks、InvocationID、UUID、cgroup及成员UID与自身登记相符；admin status均为idle，active_claims为空、sessions为空、inflight为null。这里调用的是只读status，不是模型请求。

| GPU | 实际释放的resident unit | 释放前本项目GPU进程占用（MiB） |
| --- | --- | ---: |
| 3 | `proworksim-v054-resident-mp-g3-7cbe8217.service` | 71368 |
| 5 | `proworksim-v054-resident-mp-g5-a21ce1c9.service` | 68198 |
| 6 | `proworksim-v054-resident-mp-g6-kernel-r6.service` | 74370 |
| 7 | `proworksim-v054-resident-mp-g7-0303dcc7.service` | 74282 |

GPU6使用实际kernel-r6登记和进程身份；旧pool中的 `mp-g6-333b8542` 只是历史metadata，没有据此操作错误的服务。旧注册及qualified记录未重写；它们继续表示当时资格，不表示资源退役后仍有live resident。

## 执行与最终证据

先停止 `proworksim-v054-dynamic-pool-ref-handoff-r1.service`，证实其MainPID为0、inactive，再对上述4个精确resident正常执行 `systemctl --user stop`。停止resident前再次核对相同InvocationID和空闲session，避免在准备证据与执行之间误伤新任务。没有使用广泛进程名匹配、pkill或按整张卡杀进程。

GPU3／5／7较快完成退出。GPU6主PID先退出，原systemd停止流程继续清理其剩余子树；最初同步观察未生成最终回执，原同步wrapper退出码没有取得，记录为null而不是补写0。没有额外发送kill或重载模型；随后独立执行只读收尾核验。

北京时间 **10:26:17** 的最终证据证明：

- pool监控器已停止，不会继续自动占卡。
- 4个resident均MainPID=0，原cgroup为空，原活动进程身份已消失。
- NVML不再列出这4个resident原有的任何GPU进程。
- systemd保留resident停止后的failed／exit-code状态，没有清除历史。该unit状态不代表模型仍运行，也不改写任何任务或评分结果。

释放前本项目GPU进程合计占用 **288218 MiB，约281.5 GiB**。最终观察时GPU3可用71838 MiB，GPU5／6／7各可用81152 MiB。GPU3仍有3个不属于本次4个resident的GPU进程，均未触碰。显存空闲量受其他工作变化影响，因此上述数字是该时点的观察，不承诺持续空闲，也不把所有空闲量变化归因于本次释放。

## 保留材料

释放程序、before、永久intent、pool停止回执和最终released回执位于 `runs/software-benchmark-v055/final-gpu-release-r1/`。最终回执 `released.json` 的SHA为 `db42d608af8c2d68f641047bc2b577e7504bcc57c77bfca09533faf78656b097`。

5份小型材料共40332字节，按原字节封存至 `artifacts/software-benchmark-v055/final-gpu-release-r1/`，另有SHA索引。没有打包模型权重、rootfs或大队列state，仅保留必要身份和释放前后证据。新模型调用0、其他进程信号0、模型文件删除0；本轮原异常与未知结果继续保留。
