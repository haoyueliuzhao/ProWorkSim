# v049 开发停止信号来源：有限只读核查

已确认 dev-B 的 SIGTERM handler 抛出 signal 15；未发现本次宿主资源守卫发 SIGTERM 的明确记录。发送者及来源未定，不能归因为 GPU、超时或后续用户消息；也不能写成已证仅外部 SIGTERM。

仅核查指定 run 的监督器、dev-B worker/资源记录及冻结宿主停止实现。未发信号、未启动模型/GPU、未测试/重试、未检查无关任务；只写本 ignored JSON/Markdown。

## 已知事实

worker 在 1791813127.981429（UTC 2026-10-12T13:52:07.981429+00:00）记录 KeyboardInterrupt: signal 15；traceback 落在已注册的 SIGTERM handler。宿主在 1791813131.6358905 记录 execution_fault / worker_exit_error、退出码 -2，终态 closed_with_unknowns。

dev-B 总驻留 1338.457052231 秒；第二槽从 task.started_at 到异常记录 49.285310745 秒。二者不能混用，异常记录时间也不是精确信号到达时间。软/硬截止分别5400/6000秒，两者触发标记均 false，第二槽未闭合。DA-s1 原 R1 与 B 已完成更新记录保留。

## 资源与源码证据

共 201 条资源原采样全部 fresh，guard.stop_reason 非空、guard errors、已存样本阈值越界均为0。最后样本完成于 1791813126.6340783，距异常记录 1.347350836 秒；GPU3 自用 27280 MiB，空闲 53865 MiB。

| 项目 | 已存样本极值 | 冻结阈值 |
| --- | ---: | ---: |
| GPU自用最大MiB | 27280 | 57344 |
| GPU空闲最小MiB | 53865 | 至少6144 |
| RSS最大字节 | 7944499200 | 68719476736 |
| artifact最大字节 | 90224566273 | 137438953472 |
| volume空闲最小字节 | 282283646976 | 至少21474836480 |

worker_exit_error 只在 poll 已发现退出时传给 close；close 仅对仍活着的 worker 调停止函数。因此记录的关闭路径是发现并回收退出。守卫若停止会保留具体资源原因；监督器异常会留下 supervisor_interrupted / supervisor-exception.json。本 run 只有两份 dev-B mechanism-stop，supervisor.log 为0字节，无资源守卫发信号或监督器异常记录。底层停止函数具有发 SIGTERM 的能力，不代表本次调用。9个相关源码均逐字节匹配冻结提交及plan源码SHA。

## 未知与最小接续建议

原记录未给出发送者PID/UID；离散采样也不能证明每个未采样瞬间。不能确认“仅外部SIGTERM”或内部实现故障，更不能把之后的用户消息当作因果证据。退出码-2与显式signal15原件分别保留。

用户最新“修复问题，继续实验”的授权仅作为新工作的依据，不回写历史。建议新建来源绑定接续根，仅白名单原未启动DB两个B槽，由原库存派生ID/seed/先手/顺序；保留DA-s1成功、DA-s2中断技术未知及原closed_with_unknowns。加载实际已保存B完整状态，不重训、不重跑DA-s2、不转未用预算、不补样。保持原资源/时限/完整性守卫、仅GPU3/4/5/7、最多3驻留。可窄增“宿主即将发信号”持久化回执，绑定原因、时间、PID/start identity、目标、task及触发样本，再记发送结果；它只改善未来可观测性，不能反推本次来源。本核查未实施或运行这些建议。

## 原文件SHA-256

| 文件 | SHA-256 |
| --- | --- |
| runs/software-learning-v049-resume-r1/plan.json | 9e39ce12fce9ff1a64dd772f34998c73197ab719eb939df937356e9d7f3db854 |
| runs/software-learning-v049-resume-r1/supervisor.json | bcee14c740ded81dc9db12bb0df2ab579d7473adef72b746df1e2eb8f929c083 |
| runs/software-learning-v049-resume-r1/supervisor.log | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| runs/software-learning-v049-resume-r1/mechanism-stops/dev-B-execution.json | fb5e0d08082f099e959d3906cd87b0463e82737572c6452ed7af5d08eeeceb55 |
| runs/software-learning-v049-resume-r1/mechanism-stops/dev-B-supervisor.json | 2ee6e86eb31aa4b5e69a7d5556eca2acaa7387238e127310fdb1af27c94dc6b3 |
| runs/software-learning-v049-resume-r1/dev-B/worker.log | 94c9f1c5fb2b726858ab3e3b388e6de77b3ff08d8677dbc7dfdf7793c174f6b0 |
| runs/software-learning-v049-resume-r1/dev-B/resources.jsonl | e4c85532d2cd251f1b0e596f5d217c09e92d02938cd61eb08c7df81e7674e120 |
| runs/software-learning-v049-resume-r1/dev-B/actual/report.json | abc911d87560e3c3a54b3bed61edf020b1c865c6db64dd0929c50e1dbbef2775 |
| runs/software-learning-v049-resume-r1/dev-B/actual/task.json | a2a4a4176747b7de035bbe52096ee3c8f38b76b70aefeb30f689ca485d6674e2 |
| runs/software-learning-v049-resume-r1/dev-B/actual/progress.json | c9b7e907b84b1e3db65d24a3421404814942abfc464a4b00ae74669a6eac5c99 |
| runs/software-learning-v049-resume-r1/dev-B/actual/episodes/org49-dev-DA-s2-B/interruption.json | e9a78475cd79cee5013318ece70a712188dd04ee31d3365eef7e18ca87fea3c6 |
| runs/software-learning-v049-resume-r1/dev-B/actual/episodes/org49-dev-DA-s2-B/deadline-receipt.json | 4d8e2dc01ee6e91edf71ab243f84c6ea0b88338ffdf953702bf35664ea1e3144 |
| scripts/software_learning_resume_supervisor_v049r1.py | 6b1ce0d0419e28325457c8e75115aa8df44bcb64fb1afedd11dd5b764ebb248a |
| scripts/software_learning_resume_v049r1.py | 6cdd28fe5dc49ea25cf637a46dce9e55803d94387d5767396a4bb00f5bcc2f99 |
| scripts/software_learning_v049.py | 9b6fa4d57996144306ac7cafa4724cb5d59f9ca751d2bcdd7c436e50aa03b3f6 |
| scripts/software_support_v036.py | 404d2c76840c280db9380b76bbc7357376cef033a74617cc0b1bed8baa03f6d0 |
| scripts/continue_model_selection_v031.py | 58e804a0d0e8462c22e307f1428f14b2a108734c0304f6ae04fcb4d7556a2860 |
| scripts/run_ne_v021.py | 023e57127826c390d7cd960791a03e9b9c66c265dda617ae9b5f5a4fc1bc5017 |
| scripts/software_allocation_v037.py | 12c2f13ee939f1844527e5704a9ea96712563004a1b0d1ddd3f7c2e230242aea |
| scripts/software_allocation_v036.py | b1004e960e63f38ee455961a85b2d8121441f03022c0ada2d833058133808d83 |
| src/proworksim/resource_monitor_v025.py | 060ee5921c7a7cdf3c8e2471e2228ee4d4adc501472d4cedda9f7fe90df2766b |

详细源码行号、阈值、已知/未知和机器可读引用见同名JSON。
