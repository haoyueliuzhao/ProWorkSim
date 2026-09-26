# v0.15 两候选后台筛选队列

`run_candidate_screen_v015.py` 只调度已经登记的两份开放权重：9B 固定 GPU 0，27B 固定 GPU 1/2/3。旧7B作为外部运行只读观察。队列不会改变模型 profile、协议、GPU 映射或样本数，也不会按结果重采。这里的完成表示执行和记录闭合，不表示模型完成了业务工作。

## 启动与续看

```bash
.venv/bin/python scripts/run_candidate_screen_v015.py \
  --config /absolute/frozen-queue-config.json \
  --output runs/v015-candidate-supervisor
```

输出必须为新目录。通过既有会话的后台启动方式保持该观察进程运行；队列自身无需 GPU。它保存 `config.json`、`scheduler.json`、两个阶段各自的 supervisor 日志，实际 S0/S1 均经现有 `runs/v015-launch/launcher.py` 保存精确命令、PID、时间、exit code和全卡资源采样。建议使用确定的绝对路径。

若观察进程退出，可用**同一个 config/source/output**加 `--resume`：

```bash
.venv/bin/python scripts/run_candidate_screen_v015.py \
  --config /absolute/frozen-queue-config.json \
  --output runs/v015-candidate-supervisor --resume
```

续看持独占文件锁，第二个观察进程不能同时调度。恢复只认原命令、cwd、GPU、PYTHONPATH、PID 起始标识或已经结束的 launcher 回执；不会再次启动已尝试阶段。原记录不存在/不完整而无法确认 exit 时，保留 `launch_outcome_unknown`，不能由等待推定成功。launcher JSON 的最终写入有60秒观察宽限，不涉及重试采样。

下游以 `start_new_session=True` 启动，stdin 断开，stdout/stderr 写文件。观察进程收到中断不向任何下游发信号。即使父 turn 中断或观察者退出，已启动模型进程仍自行执行；续看不会把它们重启。脚本不停止其他项目，也不重分配其他空闲卡。

## 固定配置示例

先将 `source` 和 `source_commit` 换成**包含分阶段 S0 封口的新冻结 checkout 与真实提交**，再登记配置。这里的占位值不能直接运行。两个候选使用模型运行环境 `runs/v015-runtime/venv/bin/python`，launcher 使用普通 `.venv`；脚本会保留 venv python 的符号链接路径，避免误解析成系统 Python。

```json
{
  "project": "/data1/zhuxinrui/projects/ProWorkSim",
  "source": "runs/FROZEN-CANDIDATE-SOURCE",
  "source_commit": "ACTUAL-FROZEN-COMMIT",
  "python": "runs/v015-runtime/venv/bin/python",
  "launcher_python": ".venv/bin/python",
  "launcher": "runs/v015-launch/launcher.py",
  "poll_seconds": 30,
  "download_wait_seconds": 172800,
  "environment": {
    "PROWORKSIM_RETAIL_ASSETS": "/data1/zhuxinrui/projects/ProWorkSim/runs/assets/uci-online-retail-v015"
  },
  "external_runs": [
    {"name": "screen-qwen25-7b", "run": "runs/learning-v015-screen-qwen25-7b"}
  ],
  "candidates": [
    {
      "name": "qwen35-9b", "candidate": "qwen3.5-9b", "gpus": [0], "dtype": "float32",
      "download_manifest": "runs/v015-downloads/Qwen3.5-9B.json",
      "model_path": "runs/assets/models/Qwen3.5-9B-c20223623576",
      "weight_manifest": "runs/assets/models/Qwen3.5-9B-c20223623576/proworksim-manifest.json",
      "preflight_output": "runs/candidate-v015-preflight-qwen35-9b",
      "screen_output": "runs/learning-v015-screen-qwen35-9b",
      "preflight_launch": "runs/v015-launch/preflight-qwen35-9b",
      "screen_launch": "runs/v015-launch/screen-qwen35-9b",
      "screen_protocol": "examples/learning-v15/screen-qwen35-9b.json"
    },
    {
      "name": "qwen38-27b", "candidate": "qwen3.8-27b", "gpus": [1, 2, 3], "dtype": "float32",
      "download_manifest": "runs/v015-downloads/Qwen3.8-27B.json",
      "model_path": "runs/assets/models/Qwen3.8-27B-1d4bf0f2ff60",
      "weight_manifest": "runs/assets/models/Qwen3.8-27B-1d4bf0f2ff60/proworksim-manifest.json",
      "preflight_output": "runs/candidate-v015-preflight-qwen38-27b",
      "screen_output": "runs/learning-v015-screen-qwen38-27b",
      "preflight_launch": "runs/v015-launch/preflight-qwen38-27b",
      "screen_launch": "runs/v015-launch/screen-qwen38-27b",
      "screen_protocol": "examples/learning-v15/screen-qwen38-27b.json"
    }
  ]
}
```

`screen_protocol` 相对 source，其他候选路径相对 project。devices 从固定GPU列表推得；若显式提供必须一致。源 checkout 必须 clean 且 HEAD 匹配指定 commit。队列冻结两个 runner、两个协议和 launcher 的哈希，等待后启动以及恢复都核对这些身份。protocol 必须总计36固定槽、全为 evaluate，候选/dtype/devices必须与S0一致。

## 阶段门与失败记录

1. 同时等待下载 manifest `status=complete` 和 modeldir 下 `proworksim-manifest.json`；不以文件“看上去已满”代替完成标记。下载等待预算默认48小时，过期仅标 `download_timeout`，后续36槽未启动，不补零。外部下载状态变动由下载器管理，队列不启动或重试下载。
2. 每候选只启动一次 S0。Popen 前先原子登记 `launch_intent`；即便刚启动时观察者崩溃也不会因记录缺口擅自重采。
3. 进入S1须同时满足：launcher 真实 exit=0、S0 report `inference_ready=true`、report含200，以及 `owner/calls/*.json` 存在实际 status200、choices和非空 `token_trace.output_ids`。不能只相信成功布尔字段。
4. `training_ready` 独立核查原概率检查、有限非零反向、checkpoint实际保存/恢复及错误列表。数值或反向门失败而实际生成成立，仍可做纯评价S1。它不被记成业务能力失败；若S0加载或生成完全失败，保留36未启动槽。
5. S1启动后不复用S0的参数文件；它从协议指定相同公开检查点另起自身初始化。screen完成需 runner `online.status=complete`、实际36闭合 episode、actor/critic新增0及exit0。exit0但runner error/不完整不算完成。
6. 输出目录已存在，只有匹配的 launcher 元数据可被观察接管；不存在足够身份记录则 `blocked_existing_artifacts`，不覆盖、不删除、不重启。原S0/S1工作质量仍由只读报告读取真实reward与completed，调度器不打分。

## 定向验证

6项纯 fixture 通过，无GPU、子进程或模型调用：双下载标记；无概率训练准入但继续纯评价；矛盾 `training_ready=true` 不能绕过真实检查；200布尔记录缺实际token不得进入S1；恢复原PID不重采；丢失exit不推定成功；已有未归属输出拒绝；等待时限；配置变化拒绝恢复；venv Python符号链接保留。Ruff通过。这里仅验证排程机制，没有声称任何候选已经通过S0或完成S1。

## v0.15.1：独立 chat-stop 队列

新版队列允许每个 job 显式登记 `preflight_script`（相对冻结 source）和 `replay_calls`（相对 project 或绝对路径）。缺省仍为原 `scripts/candidate_preflight_v015.py` 且不做 replay；这只是旧入口的缺省声明，不授权恢复或修改已经归档的旧队列。

`qwen_hybrid_chatstop` 必须配套 `scripts/candidate_preflight_v0151.py`，不能拿旧S0的通过记录替代新终止协议验证。每个 replay 路径作为一个 `--replay-call` 参数传入，最多两条；原预检脚本不接受 replay，错配在启动前拒绝。队列冻结**实际选择的预检脚本**、`candidate_runtime_v0151.py`及其原runtime依赖、online runner、新profile源文件，以及被选择的原始call文件SHA。等待或恢复时任何这些身份改变均拒绝继续。

新文件：

- `examples/learning-v15/screen-chatstop-qwen35-9b.json`
- `examples/learning-v15/screen-chatstop-qwen38-27b.json`
- `examples/learning-v15/screening-study-chatstop.json`

新协议的runtime是 `qwen_hybrid_chatstop`，内嵌并逐字核对 `examples/candidates-v15-chatstop/` 对应profile，并记录其文件SHA。它与旧协议保持完全相同的36个case、case次序、sampling seed、task/fact/repeat、recipe、角色及token预算；改变的是明确的原生聊天停止合同、独立condition/window/slot身份与新输出位置。旧7B在新study里仅引用原测量作为只读baseline，不再采样；旧9B停止问题记录不纳入新9B的36槽，也不覆盖其内容。

可用配置草稿为 ignored `runs/v0151-chatstop-screen-queue-config.draft.json`。主线程需在新代码冻结后补充 `source` 和 `source_commit`，然后以**新supervisor目录**启动；不能用旧输出路径或 `--resume` 旧v0.15队列。两个候选保持GPU 0及GPU 1/2/3映射，新输出为：

| 阶段 | 9B | 27B |
|---|---|---|
| S0 | `runs/candidate-v0151-preflight-chatstop-qwen35-9b` | `runs/candidate-v0151-preflight-chatstop-qwen38-27b` |
| S1 | `runs/learning-v0151-screen-chatstop-qwen35-9b` | `runs/learning-v0151-screen-chatstop-qwen38-27b` |

9B仅登记 `docs/experiments/v0151-chat-stop-replay-plan.json` 中**第一条**完整原 public request：`resident_a77c1689c7424ba7b2efa2fb3d1199ff.json`。第二条不进入本配置。27B的 replay 列表为空。新S0对原请求重新生成且检查原生prompt token IDs完全一致；不执行其世界动作，不修剪旧输出，也不把这次选点诊断计入工作能力分母。原计划第一条新采样seed为2026092918，与新S0的固定 `recipe.seed+101` 相同。

进入S1还增加原始停止证据门：读取真实200回执中的 `raw_output_ids/raw_behavior_logprobs`，要求与保留的训练输入完全相同，首个声明EOS必须恰在末尾；被剪去的EOS后尾巴不能放行。对于已登记 replay，还必须有数量、源path/SHA、实际新响应ID、原prompt IDs相同、http200和停止检查都匹配的原报告记录。没有这个精确replay不能只因校准题成功就跳过登记要求。

新增3项fixture覆盖实际新预检命令与单条replay、源脚本/runtime/profile/replay哈希、真实EOS尾部不可隐去、缺失replay不得放行，以及新旧36槽与全部预算逐项一致。连同原6项共9项队列fixture通过；没有由这些测试启动模型或采样。
