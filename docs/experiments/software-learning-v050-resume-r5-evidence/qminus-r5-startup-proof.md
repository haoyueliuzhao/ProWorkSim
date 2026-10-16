# v050 r5：原 Qminus 启动失败只读证明

观察时间：2026-10-16T09:36:17.140438+08:00。结论：原 r4 Qminus 在模型加载前的首次 CUDA 显存快照失败；允许以原科学身份重新排队取得资源，不构成一次模型/训练重采。

## 原始时序与资源事实

- host_launch：2026-10-16T02:42:56.773698+08:00（1792089776.773698）。
- worker_report_started：2026-10-16T02:43:04.220613+08:00（1792089784.2206128）。
- reservation_wait_entered：2026-10-16T02:43:05.548237+08:00（1792089785.5482368）。
- worker_report_ended：2026-10-16T02:43:07.353920+08:00（1792089787.3539202）。
- host_observed_exit：2026-10-16T02:43:09.302082+08:00（1792089789.3020816）。

原 GPU3 worker PID4057937/start_ticks451417195。派发时空闲78839 MiB，约7秒后的原监测记录空闲4599 MiB；外部PID4057842新出现74218 MiB占用，本worker两次采样占用均0。资源竞争与失败时序相符；不推测外部任务意图。

## 源码与零模型边界

冻结源621219af的调用链：r4 run_worker:309 → v050 run_worker:495 → r3 _load_owner:269 → reserve_before_load:225 → cuda_snapshot:170 → torch.cuda.mem_get_info。最后一步在旧try块之前，旧异常处理只覆盖后续fill_cache的OutOfMemoryError，因此RuntimeError形式的首次CUDA OOM进入了全局execution_fault。

原actual目录严格只有 task.json 与 report.json；task为reservation_wait且model/backward计数0。原源码先成功完成reserve_before_load，才调用v049._load_owner；后者才创建DeterministicCandidateActor。失败发生于首次快照，连fill_cache都未到达。更新和training-compute写入又在owner成功返回之后。因此零模型加载/真实调用/反向/optimizer/训练区间由正向调用链与原始trace共同支持，不仅依赖缺文件。无.pt读取或torch导入。

## 费用和冻结预算

原启动GPUworker费用12.528383493423462秒（按派发至宿主收尸计），只计一次；本attempt训练区间消耗0秒。原Qminus的135481秒份额完整保留，r4整个q_compute_replay逐值复用，不重新等分、不增加144小时总界、不重置Qplus正在消费的份额。旧r1/r2部分训练及其保守上界继续保留。

## Qplus与16槽库存

本次只读观察：Qplus PID2111917/start_ticks449991926与原监督器PID2183667/start_ticks450192458均可读且存活；Qplus已确认反向179条，optimizer各0（运行中快照，非终态）。原r4监督循环仍执行target GPU身份/遥测、任务时限、RSS、磁盘与training_stop_reason守卫；机制停止分支只pause_unopened，不直接终止Qplus。未修改/信号原进程。

原Qplus/原supervisor动态文件不纳入冻结哈希或终态成本。此时没有Qplus机制停止，16开发槽全部attempted=false、elapsed_gpu_seconds=0，且对应目录全不存在。两分支各保留DA/DB/DC/DD×seed202610130601—608，各500000token，合8000000token/2048决定attempt/512测试。

| 原槽 | seed | 先手 | token上限 |
| --- | ---: | --- | ---: |
| org50-dev-DA-s1-Q_plus | 202610130601 | member_001 | 500000 |
| org50-dev-DA-s2-Q_plus | 202610130602 | member_001 | 500000 |
| org50-dev-DB-s1-Q_plus | 202610130603 | member_002 | 500000 |
| org50-dev-DB-s2-Q_plus | 202610130604 | member_002 | 500000 |
| org50-dev-DC-s1-Q_plus | 202610130605 | member_001 | 500000 |
| org50-dev-DC-s2-Q_plus | 202610130606 | member_001 | 500000 |
| org50-dev-DD-s1-Q_plus | 202610130607 | member_002 | 500000 |
| org50-dev-DD-s2-Q_plus | 202610130608 | member_002 | 500000 |
| org50-dev-DA-s1-Q_minus | 202610130601 | member_001 | 500000 |
| org50-dev-DA-s2-Q_minus | 202610130602 | member_001 | 500000 |
| org50-dev-DB-s1-Q_minus | 202610130603 | member_002 | 500000 |
| org50-dev-DB-s2-Q_minus | 202610130604 | member_002 | 500000 |
| org50-dev-DC-s1-Q_minus | 202610130605 | member_001 | 500000 |
| org50-dev-DC-s2-Q_minus | 202610130606 | member_001 | 500000 |
| org50-dev-DD-s1-Q_minus | 202610130607 | member_002 | 500000 |
| org50-dev-DD-s2-Q_minus | 202610130608 | member_002 | 500000 |

## 证据文件清单与SHA256

以下均为静态原件；JSON中还保存原源码6文件与调用链、完整预算封印、17个已停/未开worker身份。

| 原件 | SHA256 |
| --- | --- |
| update-Q_minus/actual/report.json | ad11894aa54a7fffc27deb186c9108fc708440535e8946a533519cc6a82c8151 |
| update-Q_minus/actual/task.json | e2d66af956e4596d2433aa5577fd8f01a752ea8c80529f73ed093c2fb56bcc54 |
| update-Q_minus/reservation-binding-verified.json | a23c73eae9c9886c5553e6e8f4d17d9ce4283f80d0ee17fda561991bbb7e045d |
| update-Q_minus/resources.jsonl | 31d60dfb07b35968a1401c0cb00f5eecbab81d9a09cdaf85e578fdb7eedbfaec |
| update-Q_minus/worker-launch.json | 6b98dabb9da8cd5a2027882291a65d575cbdc9392ccff6c17435ddc7cf270874 |
| update-Q_minus/worker.log | e2d951213c34c4a119c892fab29612990a29cf852bd48a2a7231a651fafe30e3 |
| mechanism-stops/update-Q_minus-supervisor.json | 0d80e78bf5fa1a888efc8c7d9035682ae05e122abb26f1820404b349addebb8a |
| mechanism-stops/update-Q_minus-execution.json | 7cf615ffba29cdfabafdc15cbdc533f0391e197eba2b79668e4fede1a96925e5 |

## 自动恢复边界

新r5只能把充分绑定、模型加载意图标记前、零模型/训练证据的资源取得失败归为pending；每次资源失败独立归档和计费，原科学worker/seed/预算不新增。模型加载意图标记一旦存在、任一模型/训练证据出现、身份/记录/费用未决或真实完整性错误均不可自动重试，继续原暂停规则。原r4两项mechanism-stop及16槽未启动事实不改写。

该证明脚本仅标准库和文件/进程元数据读取；没有GPU诊断、模型资格、样本追加、参数更新或提交。
