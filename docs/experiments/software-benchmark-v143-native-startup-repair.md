# v143：actor 启动版本接线修复

v142 首项零模型诊断在 actor 发出 ready 前失败。保留的 `diagnostic-1/actor.stderr` 显示：managed-worker 调用 packaged `worker.py` 的 `validate_config`，而该 alias 仍指向 v130，要求 `v130-public-test-evidence-r1`；实际配置已正确采用 `v141-session-bound-public-test-execution-r1`，因而被旧门拒绝。之前独立 actor helper 和离线 import 检查没有覆盖 `serve → native alias → validate_config` 这一层。此次未发生模型调用，旧失败记录不改写。

新文件 `run_native_worker_docker_v143.py` 保留原 v066 私有运行布局、原任务解释器、已准入镜像、干净 Git 基线、PID1、capabilities／no-new-privileges、隔离清理等检查，以及 v130 的公开合同、五个文件 SHA 和依赖描述校验。唯一语义变化是把 native 入口期望的测试结果版本明确绑定到已冻结的 v141 版本。seal 后还会复查公开文件 SHA。

`run_managed_worker_docker_v143.py` 在加载 alias 后检查其部署标识与结果版本；旧 alias 会明确失败。`software_benchmark_managed_actor_v143` 仅暴露部署标识，复用全部冻结 v141 managed operation、预检、角色权限、上传协议和公开测试实现。ready 增加 `actor_deployment_revision`，不修改模型可见合同、工具、上下文、输出、5M 团队预算或三组题单。

新离线包为 `runs/software-benchmark-v143/sdk-bundle-r1/manifest.json`。两个实际 alias 必须一起切换：

| alias | 新来源 |
| --- | --- |
| `worker.py` | `run_native_worker_docker_v143.py` |
| `managed-worker.py` | `run_managed_worker_docker_v143.py` |

controller、五个公开测试文件、dependency helper、tokenizer、S1／FREE2／REVIEW2 runtime 和模型配置均保持原冻结来源。新 episode 的实际 `runtime` 及 host schema 的 `runtime_bundle` 应同时绑定 `software_benchmark_sdk_bundle_v143`，不能只更新 managed alias。

本次 11 项必要 CPU 控制覆盖：三种组织真实执行 `serve`、实际加载 copied native alias、调用原配置／合同／SHA／依赖检查、构造真实 managed session、发出 ready，再通过真实分块上传协议完成初始 `sync_preflight`；反例覆盖旧结果版本、旧 alias、错误私有布局、文件 SHA、合同属主、依赖记录和 seal 后文件改变。原 PID1 拒绝门也独立验证仍在。

CPU 控制仅在临时目录创建小 Git 仓库。PID1 隔离动作和定时器用明确 fixture 表示，路径及合同属主元数据映射至该 fixture；没有实际修改宿主 PID、挂载、capabilities、进程限额或计时器，也没有执行 Docker、API 或模型。因此这证明完整初始化接线和拒绝门，没有把 CPU 模拟称为真实容器隔离通过。真实零模型容器准入仍由新的主控诊断完成。

新包自身的 Python／SDK 离线 probe 已验证实际 worker aliases、部署与结果标识、原 validate／seal 函数绑定、全部入口导入和冻结 tokenizer 编码；网络及子进程审计计数均为零。旧 v141/v142 源码、已封存配置和包均未修改。详细来源及哈希见 [native-startup-controls-r1](../../artifacts/software-benchmark-v143/native-startup-controls-r1/summary.json)。
