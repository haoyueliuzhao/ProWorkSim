# v055 终态共享缓存最终清理 r4

2026-10-23 用户要求九组任务完成后释放 GPU 并清理磁盘。本组件只负责原 `native-lazy-cache` 下的已结束共享模板；GPU 释放与本轮 pre-entry recovery 环境的收尾由其他独立组件处理。

本次于 **10:19:06–10:19:17（Asia/Shanghai）** 清理六个精确 allowlist 模板，全部完成。一次预先 allocated 测量合计 **18,357,612,544 B＝17.096859 GiB**。仅删除六个 `rootfs`，保留模板清单、原资格证据、原失败与 quiescence、实验记录、补丁、评分、账本、模型、Docker 镜像以及存在的 `rootfs.tar`。不把并发活动期间的整盘 free 差值当作本组件收益；少量新增审计 metadata 未扣。

## 为什么需要独立恢复证明

实际浅层盘点发现原路径剩六个 `rootfs`，均有原准备锁。自动 watcher 仍 active，但因历史完整 writer quiescence 不充分而保守跳过。较早观察中的“三项”不是本次终态库存，不能照旧数量直接清理。

本轮复用已封存 `tools/reclaim_terminal_cache_v055_r2.py` 的 fresh 完整静止证明和原 `tools/reclaim_benchmark_cache_v055_r1.py` 安全 deleter，增加独立 r4 namespace、封存计划及精确六项名单。没有修改旧源码或旧失败，也没有把新现场已静止反推为旧生成已正常闭合。

单次只读预审在已有原准备锁内核对原 Qwen 三组及 DeepSeek 六组共九消费者；逐项绑定完整 slot/claim/scope registry、历史 attempt/result/completion、评分状态、systemd InvocationID/ControlGroup、主 PID/start ticks、outer launcher、claim slice 和 cgroup populated 状态。六项共覆盖 **54 消费者、142 scope**。已有 scope 清单和历史失败内容全部纳入，没有过滤旧失败 writer。

在实际删除入口，原锁、原模板身份、九消费者终态投影、完整当前静止证明、无内部 mount、真实目录 inode/device 与封存元数据再次核对，之后使用原 fd 防 symlink 的 deleter。第二次现场核对是删除前的必要守卫，不是重复运行模型、测试或遍历大文件。没有创建缺失 lock、补写假 quiet 或停止实验进程。

## 精确范围与执行结果

| 实例 | 原版本前缀 | allocated 字节 | 状态 |
| --- | --- | ---: | --- |
| django 13344 | `3c7420d774b6f859` | 3,036,549,120 | reclaimed |
| django 14053 | `d1e1e82ec5bfd879` | 3,137,957,888 | reclaimed |
| django 16136 | `983258ee39ad4862` | 3,180,957,696 | reclaimed |
| django 16877 | `a1f1762081160eee` | 3,241,091,072 | reclaimed |
| pytest 7236 | `3a3909f4c0385d3d` | 2,806,165,504 | reclaimed |
| sphinx 9230 | `31cf6b57ba41a36c` | 2,954,891,264 | reclaimed |

六份均位于 `runs/software-benchmark-v054/native-lazy-cache/<instance>/<prefix>/rootfs`，实际设备 66306。每项删除后生成独立 intent/completed、原位置 eviction tombstone，以及供原 watcher 识别的 forwarding completed。历史失败和旧科学结果保持。

有限工具：`tools/reclaim_final_shared_cache_v055_r4.py`，SHA `a5a9e1299a50846c73ffb34b8e5f2ec893196338eff040fd29139f9316dd0d14`。计划 SHA `4d31284e4fa5658909e9fb060c88d5fb37b00da3e4d53555465611b25023c947`。一次只读六目标 `du -s -B1 -x` 提供 allocated 数值，没有广泛磁盘扫描；执行时最多一个 deleter，逐项有限调用，无自动追加。必要纯 CPU 控制和定向 Ruff 通过，0 模型调用。

## 排除、容量与后续边界

`astropy__astropy-12907` 的原 `native-lazy-cache` 位置只有小型引用 metadata，原锁缺失，实际 payload 属于 `native-lazy-r3/.../843dcc65484d2d05/rootfs`。**本组件排除该实例的全部别名与恢复路径**，由 pre-entry recovery 归档组件在自身完整证据下处理。没有创建其原缺锁，没有借用这六项的证明清理该模板。

清理后的原 `native-lazy-cache/*/*/rootfs` 浅层库存为 0；这不代表其它版本缓存、正式实验现场或归档压缩包不存在。原 watcher 在本组件观察时仍 active；停止自动巡检由总收尾统一协调，未随本组件擅自停止。

结束时普通用户可用容量快照如下，单位 GiB。它是当时整个共享卷的可用空间，不能全部归因本次清理；另一归档组件仍可能改变后续空间。

| 数据盘 | 可用字节 | GiB |
| --- | ---: | ---: |
| `/data0` | 829,952,176,128 | 772.953 |
| `/data1` | 331,789,094,912 | 309.003 |
| `/data2` | 363,086,233,600 | 338.150 |

此前三模板、261 份旧文本、51 份异常现场归档已具备独立完成回执，本轮没有重新归档、解压验证或重复计入其收益；本组件新增收益只有上述六模板。保留的压缩对象、正式记录与候选属于仍需保存的实验资产，未将其泛称“无用数据”删除。

全部 r4 原生证据位于 `runs/software-benchmark-v055/final-shared-cache-recovery-r4/`，可发布小凭据复制至 `artifacts/software-benchmark-v055/final-shared-cache-recovery-r4/`，包括预审、原锁内 fresh 证明、封存 plan、必要 CPU 控制、逐项 dispatch/intent/completed 和最终容量/计量摘要。新清理证明只用于释放已经静止的环境，不改变过去 R、技术未知、scope 失败或评分结论。


## 自动 watcher 停止收口

按后续明确收尾授权，**10:27:19** 正常停止 `proworksim-v055-cache-reclamation-r2.service`。停止前固定核对原 MainPID 1357003、InvocationID 和精确 service cgroup；该 cgroup 全树只含 watcher 主进程，子进程清单为空，最后一次循环已结束且 reclaimed=0。没有在途 root helper 或归档进程，才发送一次 `systemctl --user stop`。

停止回执 returncode=0、Result=success、ExecMainStatus=0、inactive/dead、MainPID=0；旧主进程身份消失，精确 cgroup 已无成员。没有停止 snapshot agent 的独立归档服务或任何 GPU 服务。原缺失 astropy 锁的拒绝仍保留，不再由这个已结束 watcher 周期性重复查询。前文当时 active 的观察不覆写，以本节和独立 `watcher-stop/stop-receipt.json` 记录后续真实停止。
