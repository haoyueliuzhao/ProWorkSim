# 后续 DeepSeek 生成目录使用独立副盘

## 路由与配置边界

r7 仅把尚未进入的 DeepSeek generation worker 放到已注册的真实副盘目录：

```
/data0/zhuxinrui/projects/ProWorkSim/runs/software-benchmark-v055/secondary-volume-r1/workers/generation-<原slot标识摘要>
```

该路径是 `/data1/proworksim-zhuxinrui/v055-worker-volume-r1` 的独立 bind mount，登记设备为 66307；主项目设备为 66306。它没有使用 `/data1/zhuxinrui` 这个指回 data0 的符号链接。实际启动前必须同时通过注册 manifest、marker UUID、源与目标 inode/设备/owner，以及 `/proc/self/mountinfo` 中源设备与挂载根的精确匹配。

原 queue state、coordinator lease、全局现金账本、Qwen worker、准备 worker、共享 template cache、评分 worker 目录及 Docker 评分运行环境继续使用主盘。生成产生的补丁、日志和评分请求跟随其新 episode 目录；其中指向 episode 的评分元数据不会被强行搬回主盘。因此这里的“评分留主盘”指评分 worker 与 Docker 执行环境，不宣称所有评分结果文件都位于同一设备。

既有 worker 通过其 durable record 的绝对路径继续收集，不移动在途目录，不改变 unit、slot、API身份或候选。模型/solver、采样、预算、调用上限、原始 3000 slot、seed 和评分语义保持原身份。GPU 模型和 Qwen 推理服务不因这次目录路由重载。

## 分卷预约与预热优先

共同 volume wrapper 先采用已经封存的 stage guard 计算每个活动任务剩余增长，再按该记录真实目录的 `st_dev` 分到两个注册卷。未知目录、设备不一致或挂载失效会阻止新派发；不会悄悄退回主盘，也不会把未识别任务当作零占用。

每个准入目标使用自身卷的 free 和预约总量。DeepSeek 新 generation 在副盘应用原 100 GiB 最低余量；主盘 Qwen/preparation 继续应用原 100/128 GiB 门，以及需要 cold preparation 时的 256 GiB 优先门。主盘预热优先空间不会重复扣在副盘 generation 上。

原 tick 仍要求主盘至少通过其原 100 GiB 总低水位检查，用于保护主盘评分、账本和共享基础设施。CPU/RAM、最大 generation=32、实际动态 CPU 容量、评分并发、API64、¥2000 现金门与结果收集逻辑均未更改；这次没有为了多盘把 generation 上限继续抬高。

两套 host 始终共用原 `disk-dispatch-r4.lock`，锁覆盖双方最新状态观察、分卷准入、durable intent 与 launch。r7 在一次新 generation launch 内临时选用副盘工作根，复用原父类的配置/solver/systemd builder，调用结束或抛异常后恢复原队列根。`state_path`、ledger 与 lease 没有随工作根改变。

若一个仍标为 pending 的任务已经存在旧主盘 generation 目录，r7 将其记录为技术延期，不会因新卷上同名目录尚不存在而重新执行。已进入状态同样不能借此次路由重新派发。

## 必要验证与解释范围

副盘的实际零模型生命周期验证由独立 control 提供：执行的是 MATCH 路径，覆盖真实 clone、设备 66307、既有 host 生命周期以及清理/候选边界。该 control 声明的 PROJECT fixture 未执行，不能称为 PROJECT 已进行一次新运行；原 PROJECT 接口资格保持已有证据，副盘主 actor 采用相同共享 clone 路径。

本 host 另外执行一次零 worker 的必要路由控制，验证：

- 只有未来 generation 使用副盘，评分和 state 路径仍为主盘。
- launch 抛异常后路由上下文恢复。
- 副盘 100 GiB 门与主盘 cold-prep 256 GiB 门分离。
- 已进入任务、已有旧主盘目录不会重放。
- 原 CPU/RAM/预算/API tick 与结果收集函数保持原实现。

路由控制还使用真实 volume registration 核对设备身份。没有额外模型、正式 claim、真实 worker 派发或旧 payload 搬迁。

## 封存证据

- 主机源码 `src/proworksim/software_benchmark_queue_native_host_v055_r7.py` SHA：`d53ab86b1a020d364084276e2f1798bfc6207b58a8d892e3ca2b2c31606119cf`。
- r7 revision SHA：`73c7aed3db508a483fd86c6772d32a72a767a85793cc4f6dc018e91069371f5b`。
- 共同多卷 wrapper SHA：`c1bdef5a87bb160fe9b0df24222d2ae5cc056ae9842b1cf00156cb6c9235b14c`。
- volume manifest SHA：`8b2b2d00cb78b28abb7ba4c78a4746ae07b8666b6722fc1021fc1b3ea5e58091`。
- 实际 MATCH 副盘生命周期 control SHA：`c559206c45b1ae7f113ded546ee55567e5c1b26424da8b4fd460869b9b249f7e`。
- r7 路由 CPU control SHA：`78342faf3e5cd997cf020c124da5fab18bc165099d950612d4efd88070e6644a`。

本 host 的小型证据归档于 `artifacts/software-benchmark-v055/secondary-generation-host-r7/`。实际切换和吞吐观察由主协调端记录；可用副盘容量与通过控制不等于已经达到某个并发数或完成率。
