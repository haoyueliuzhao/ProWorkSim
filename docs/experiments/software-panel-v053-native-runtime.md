# v053 原生单 Agent 运行器和调度合同

日期：2026-10-20。本文记录实现及必要 CPU 合同控制，不是 200 题实验结果。文中的合成对话使用程序化回答，不加载权重，不调用 CUDA，不执行真实 SWE-smith 任务或评分。

## 不变的模型与循环

`software_panel_native_v053.py` 新建独立 v053 episode 绑定，绑定完整 panel SHA、task、slot、重复轮次、seed、真实模型身份和独立容器初态。复用官方 OpenHands SDK/Tools 1.49.6、官方 Agent/Conversation，以及项目原始 Qwen3.5-9B 数值 provider；不使用受管项目循环，不挂训练 adapter，不创建 optimizer、critic 或反向计算。工具集合明确为 TerminalTool 与 FinishTool，不将其称为完整默认 preset。

数值合同延续 18432 上下文、2048 输出预约、非思考、temperature 0.7、top-p 1、top-k 0、repetition penalty 1；模型主干 BF16、输出头 FP32及原项目 attention/generation 路径不变。每回合最多 128 决定、128 实际 attempt、500000 输入加输出 token。90 分钟后拒绝新模型调用，100 分钟为包含闭合与评分的外层硬界。

账本在实际 generation 前预约完整输入加 2048 输出；收到包含实际 token IDs、同一模型和输入身份的回包后，先结算实际 usage，再解析生成内容。格式错误不能抹去已经使用的 token。未结算的调用保留不确定预约，不能填成零费用。每轮重新设定预先锁定的 seed，开始独立的 SDK 对话与容器。

## 容器工具和候选

官方 TerminalTool 工厂本身要求一个存在的本地目录，因此 SDK 使用独立空目录完成配置发现与工厂初始化；真正的终端动作只调用 DockerBackend，在原任务镜像的 `/testbed` 执行。控制目录、其他回合及宿主文件不挂入业务容器。

终端每次为新的非交互 shell，文件修改保留，`cd`、环境变量及交互会话不跨命令保留。普通命令超时上限 60 秒。`bridge_run_tests` 运行原 profile 的可见测试命令；隐藏任务测试只有最终独立评分类环境恢复后才参与判定。公开测试通过不直接给出最终 R。模板明确说明最终恢复原测试及测试收集配置，候选只包含源文件，不传递 actor 的依赖环境。

闭合后只导出一个候选并锁定其证据，之后禁止 actor 继续执行。评分只接受这个候选锁，不在看过分数后选择其他树。SDK stuck、最大迭代、完整上下文拒绝、token 预算及已声明的本地截止属于回合停止原因，末树仍进入唯一评分；模型未完成任务的 0 分不会触发全局暂停。容器、provider、守卫、身份、未结算费用或评分技术异常单列未知并停止派发未开始任务。

## 模型来源和服务器绑定

live `software_calibration_runtime_v051.load_actor` 只增加来源与设备前置门，不改变数值加载代码。原数字 GPU 声明继续有效；新服务器允许完整 GPU UUID，同时要求 `PROWORKSIM_HOST_GPU_DEVICES` 声明单一物理编号，并在加载权重前核对 Torch 实际设备 UUID。不会临时把 UUID 改成数字来绕过原门槛。

模型准备阶段用 `prepare_model_source_receipt` 对 manifest 中每个文件完整核对一次 SHA256，并记录路径、device、inode、size、mtime_ns、ctime_ns。正式 worker 使用显式绑定的凭据，核对同一 manifest 与全部 stat 身份；漂移时拒绝，既不静默刷新凭据，也不每回合重新读取约 19 GB 权重做 hash。没有传入凭据的旧调用仍执行完整内容检查；旧冻结源码目录未修改。

## 准备和调度

`software_panel_host_v053.py prepare` 要求 src/scripts 已提交且无未提交修改，将 Git 跟踪文件复制为只读执行快照，冻结文件 SHA 与 stat 身份。快照中的 artifacts/runs 是读取既有资产的路径别名；业务容器没有这些宿主挂载。运行时两个 shell helper 与原 r3/r5 资源文件另绑定文件引用。

`capture-panel` 在一个 native Python 进程中只加载一次 tokenizer，对预定 200 个不同任务各捕获一次真实初始 SDK 请求，停止于 prepare_request 边界；没有 generation、业务工具、候选导出或评分。正式 admission 必须引用这份完整全 fit 清单、同一 panel/SDK/数值合同和预先环境准入记录。初态通过不保证后续增长的完整上下文也能装入。

计划中的完整 backend_config 按统一 canonical JSON 算法核对环境准入记录的 config_sha256。每个正式 worker 只核对自己任务的 `qualification.json` 与不可变环境总记录中唯一的原 task_receipts 引用一致，之后才取得 GPU 预约并创建后端；不接受现场重新计算的文件 hash 作为新的权威，也不为每个 worker 重读其余 199 题。初态捕获不创建 Docker，只使用已绑定的环境元数据。

所有 native 子进程的依赖优先级固定为 `snapshot/src`、`snapshot`、原 `runs/v030-runtime-deps`、最后才是独立的 harness 依赖目录；使用原 resident Python，不切换到 harness 的 Python。后端另核对其实际 harness 依赖身份与环境资格中的来源一致。SDK 的工具 overlay 仍按原方式 append，不抢占原数值包。准入准备配置必须把 `dependency_paths` 的第一项设为本项目 `runs/v030-runtime-deps`。

`supervise` 使用实际 `nvidia-smi` 空闲容量，允许符合条件的 A100/A800 80 GiB 卡；保留 46080 MiB 最低空闲、44 至 72 GiB 原缓存预约合同。全局最多四个 worker，同一物理卡不同时派发第二个 worker。每次按固定 panel.slots 顺序派发，不读取成绩来改顺序或配置。

启动器通过显式 `/usr/bin/env` 传递 UUID、物理编号、原生 allocator、资源 binding 和冻结 PYTHONPATH；进入私有运行时后再次切换到快照目录，防止 `python -m scripts...` 从 live 工作目录导入另一份脚本。宿主监督器自身不加载模型。

只有原 startup 预约返回具名可重试资源异常，且没有 resident、episode 或 model-entered 证据时，才允许用新进程重试。重试保持原 task/seed；冷却时间从 60 秒增长到最多 600 秒，不按五秒频率重新申请资源。第一次正式 loader 入口之前写 `model-entered.json`，此后不重采同槽。

宿主对启动预约与加载各给 900 秒、单次 generation 给 660 秒、整个 episode 给 6000 秒；工具、评分和测量有独立有限阶段界。超时只向本监督器用 `start_new_session` 启动的进程组发 TERM，30 秒后必要时发一次 KILL。容器清理必须同时匹配 v053 version、slot_id、精确 worker_root 三个标签，不清理其他 worker、环境预检或共享 daemon 的容器。

公共故障或源码漂移暂停未开始库存，已经运行的其他回合继续正常闭合。`state.json` 从一开始保留全部 280 行，每行保留全部资源尝试、PID、开始/结束时间、退出码和 model_entered；技术未知及资源等待均不填 0。监督器信号、启动参数、stdout、资源观察和清理证据持续保留。遇到公共暂停不会自动重启或更换配置；服务的 `Restart=no` 由外部启动配置设置。

## 准确运行入口

以下约定本轮文件路径，实际准备时这些文件必须已形成；命令不是已经执行的声明。`host-config.json` 必须提供绝对路径的 `project_root`、`runtime_launcher`、`native_python`、`model_path`、`task_source_root`，以及标准 `{path,sha256,bytes}` 引用形式的 `model_manifest`、`model_source_receipt`、`reference_runtime`、`environment_admission_ref`。`backend_config` 为与来源资格一致的完整 Docker 配置，包含显式 `docker_host`；`dependency_paths` 依上述顺序列出数值覆盖层和通过资格的 harness 依赖目录。

准备配置中的 `native_python` 为 `/data0/zhuxinrui/projects/ProWorkSim/runs/v016-sdk/resident-venv/bin/python`，`runtime_launcher` 为 `/data0/zhuxinrui/proworksim-runtime/run.sh`。本轮新路径统一使用私有运行时同样可见的 `/data0` 路径；模型一次来源凭据也使用同一路径，不能在核对 stat.path 时混用 `/data1` 别名。

源代码提交后，在项目根目录创建准备计划和只读快照：

```bash
v053_project=/data0/zhuxinrui/projects/ProWorkSim
v053_prepare="$v053_project/runs/software-panel-v053/preparation"
v053_artifacts="$v053_project/artifacts/software-panel-v053"

"$v053_project/.venv/bin/python" -B -m scripts.software_panel_host_v053 prepare \
  --config "$v053_artifacts/host-config.json" \
  --panel "$v053_artifacts/panel.json" \
  --output "$v053_prepare"
```

`prepare` 的输出目录必须不存在，环境和模型来源资格必须已经准备好；尚无最终模型 admission 的准备计划不能派发 worker。若任一代码未提交，快照创建直接拒绝。

在一个 CPU native 进程里捕获 200 个初始请求。这里的 `v053_harness` 必须填写 host-config 已锁定的目录；若其实际目录不同，应整体替换该变量，不能另外安装未准入依赖：

```bash
v053_source="$v053_prepare/source"
v053_native="$v053_project/runs/v016-sdk/resident-venv/bin/python"
v053_harness="$v053_project/runs/software-panel-v053/harness-venv/lib/python3.12/site-packages"

/data0/zhuxinrui/proworksim-runtime/run-cpu.sh --write-project \
  /usr/bin/env \
  "PYTHONPATH=$v053_source/src:$v053_source:$v053_project/runs/v030-runtime-deps:$v053_harness" \
  /bin/sh -c 'cd "$1" && shift && exec "$@"' v053-capture \
  "$v053_source" "$v053_native" -B -m scripts.software_panel_host_v053 capture-panel \
  --plan "$v053_prepare/preparation-plan.json" \
  --output "$v053_artifacts/initial-inputs"
```

`initial-inputs/initial-inputs.json` 完整通过后，最终 `model-admission.json` 必须绑定它的 `initial_inputs_ref`，绑定同一 panel SHA，并明确所有模型前置资格通过。封存正式计划：

```bash
"$v053_project/.venv/bin/python" -B -m scripts.software_panel_host_v053 seal \
  --plan "$v053_prepare/preparation-plan.json" \
  --admission "$v053_artifacts/model-admission.json" \
  --output "$v053_prepare/plan.json"
```

监督器的前台命令如下；正式长期运行由独立 `Restart=no` 服务执行同一入口，不在捕获流程内自动启动：

```bash
cd "$v053_source"
PYTHONPATH="$v053_source/src:$v053_source" \
  "$v053_project/.venv/bin/python" -B -m scripts.software_panel_host_v053 supervise \
  --plan "$v053_prepare/plan.json" \
  --run-root "$v053_project/runs/software-panel-v053/execution"
```

每个 worker 的完整实际参数另保存在 `slots/<slot>/attempt-NNN.launcher.json`。单独的 worker CLI 为 `scripts.software_panel_run_v053 worker --plan ... --slot-id ... --output ...`，必须由监督器传入资源预约、物理 GPU、UUID 和 allocator 声明后调用，不能把这一底层入口作为跳过准备门的手段。

## 一次持久流水线

`scripts/software_panel_pipeline_v053.py --config <pipeline-config.json>` 是薄的阶段串联入口，由宿主项目 `.venv` Python 执行。其顺序为：CPU 环境准入、冻结 200/40 panel、第一预定任务的完整容器导出到原 judge 控制、冻结已提交代码、单进程 200 初态捕获、构造有证据引用的 admission、封存、监督 280 槽，最后只读生成报告。所有 CPU/harness/native 准备子步使用无 `--gpu` 的私有运行时。

最小配置结构如下，路径应替换为本轮已经存在的输入；`pipeline_root` 必须是全新的目录：

```json
{
  "environment_config": "/data0/zhuxinrui/projects/ProWorkSim/runs/software-panel-v053/backend-config.json",
  "inventory": "/data0/zhuxinrui/projects/ProWorkSim/artifacts/software-panel-v053/candidate-inventory.json",
  "harness_python": "/data0/zhuxinrui/projects/ProWorkSim/runs/software-panel-v053/harness-venv/bin/python",
  "host_prepare_config_base": "/data0/zhuxinrui/projects/ProWorkSim/runs/software-panel-v053/host-prepare-base-config.json",
  "host_python": "/data0/zhuxinrui/projects/ProWorkSim/.venv/bin/python",
  "environment_workers": 4,
  "allow_image_pull": true,
  "paths": {
    "pipeline_root": "/data0/zhuxinrui/projects/ProWorkSim/runs/software-panel-v053/pipeline-r1"
  }
}
```

默认输出位于该根目录下：`evidence/environment-admission.json`、`evidence/panel.json`、`backend-control/`、`evidence/backend-control.json`、`evidence/host-config.json`、`preparation/`、`initial-inputs/`、`evidence/model-admission.json`、`execution/`、`report.json` 和 `report.md`。若需将小型冻结文件保存在 docs，可在 `paths` 中分别覆盖 `environment_admission`、`panel`、`backend_control`、`host_config`、`model_admission`、`report_json` 和 `report_markdown`；另支持 `backend_control_root`、`preparation_root`、`initial_inputs_root`、`execution_root`。所有目标必须原先不存在，不覆盖旧流水线或失败证据。

启动命令由独立 `Restart=no` 服务执行：

```bash
cd /data0/zhuxinrui/projects/ProWorkSim
.venv/bin/python -B -m scripts.software_panel_pipeline_v053 \
  --config runs/software-panel-v053/pipeline-config.json
```

流水线自动把环境准入和全链控制引用注入 host-config，不需要事前伪造最终 admission。`reference_runtime` 必须是本轮 `software_panel_native_v053.sdk_provenance` 生成的新 v053 清单，不能直接填旧 v052 清单：工具来源可以相同，但 terminal 描述和任务模板 SHA 属于新协议。

任何环境公共故障、控制失败、初态不 fit 或后续阶段非零退出都会保存 `pipeline-state.json` 和该阶段日志，状态置为 `paused` 并以非零状态退出，不自动重跑流水线或模型。只有内部监督器有已明确证明零模型的资源重试权限。若 panel 尚未冻结，最终文件是明确无能力估计的准备暂停报告；若 panel 已冻结，即使全部模型未启动，也按完整 200 题身份只读报告。只有监督器正常退出、原 280 行全部 complete 且无 active 时，流水线才声明正式回合完成。

## 必要控制及边界

原生运行器共 11 项新增合成合同已按改动范围验证，包括真实固定 SDK 的终端历史、finish、唯一导出、零模型初态捕获，token 预约与实际结算，独立重复身份，技术未知分类，UUID 拒绝门，模型内容凭据的 stat/manifest 漂移拒绝，以及零模型资源等待。

随后针对最终环境绑定补充两项合成漂移控制：backend_config 改动、以及本题 qualification/image 内容改动都被拒绝。夹具故意不给其他题创建资格文件，证明检查只读取本题；两项控制及受影响的零模型资源等待控制通过。原生接口新增控制合计 13 项，没有重复执行已通过的 SDK 对话控制。

首次真实 SDK 控制有两项因官方工厂拒绝宿主不存在的 `/testbed` 目录而失败；改为本地空目录初始化、容器执行目录仍为 `/testbed` 后，固定 native Python 3.12 的十项控制全部通过。后加的资源等待控制及受影响分类做了定向核验。首次宿主调度 Ruff 发现两个未使用的测试 import，删除后限定检查通过。

宿主另有七项有限 CPU 合同通过，包括实际 r3/r5 binding、显式 UUID 与 shell quoting、零入口重排证明和冷却顺序、阶段截止、拒绝不完整容器标签、五槽 mock 调度的四并发上限与零成绩保留、源码漂移保留完整库存，以及只向本进程组发信号。没有为本轮重跑旧业务测试或模型性能测试。

流水线另有两项纯 CPU mock 控制通过：环境准入失败、以及初态捕获失败都不能封存模型 admission 或进入 supervisor；失败日志和只读暂停报告均保留。此控制没有启动实际子进程、Docker、任务测试、GPU 或模型。新增文件的限定 Ruff 通过。

上述证据只证明新增接口和调度合同。正式 200/40 任务环境、实际初始输入、真实 GPU 推理、280 回合状态及最终统计以各自本轮不可变记录为准，不能从合成控制推定已完成。

## v3 停机及外部运行时诊断的只读复核

2026-10-20 的 v3 环境准备因共同适配故障停止，尚未冻结正式 panel，也没有模型回合。`pipeline-v3/pipeline-state.json` 记录收到 SIGTERM，环境阶段的 wrapper PID 4153466 以 `-15` 退出；流水线在北京时间 14:24:37 左右记录为 paused。该状态只证明所等待的直接 wrapper 已退出，不证明其 user/mount namespace 内全部后代已经结束。

本次停止之后仍观察到环境子进程活动，并在约 14:25:06 创建了一个 admission-bug 容器。实际 transient systemd unit 保持 `Restart=no`、`TimeoutStopSec=45s`；由宿主的 systemd 停止超时清理剩余进程后，仍有一个属于本轮私有 Docker daemon 的容器 `91c71c42…`，已由主代理按其确切 ID 清理。Docker daemon 中的容器不能仅凭宿主 wrapper 退出推断已经释放；也不能把 paused 时间当作所有环境活动的最终结束时间。现有记录不足以唯一归因 namespace 子进程为何未随首次进程组信号终止，本轮不将推测写成已定位的信号缺陷。

这次只读检查还核对了私有运行时的挂载方式：每次入口独立创建 user/mount namespace，进入后立即执行 `mount --make-rprivate /`，临时目录各自独立。因此，共用 sysroot 的目录并不意味着各进程共用后续挂载表；现有代码和记录没有证明正式多 worker 之间存在挂载覆盖竞态。

外部诊断的 `cache-diagnostic-v3/inspect.log` 有一次首个项目 bind 的 `wrong fs type, bad option...` 错误。该错误发生在模型及 CUDA 加载之前；同一时间段的宿主 systemd 运行入口已有实际成功记录。外部工具父 namespace 的挂载限制与宿主 service 不同，是一种可能解释，但该日志没有给出足以确认根因的证据。不能把这一次外部诊断失败泛化为宿主并发运行失败，也不能据此宣称四个真实 GPU worker 已经通过验证。

按本次窄复核范围，仅记录上述边界，不修改 pipeline、host 或 runtime 的停止/挂载代码，不追加并发 `true`、业务测试、GPU 或模型实验。后续停止仍需结合 systemd 最终状态和本轮精确容器身份判断资源是否已经释放，不能只看流水线 paused 字段。
