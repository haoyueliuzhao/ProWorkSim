# v062 解释器探针终端控制序列窄修 r2

日期：2026-10-26。真实 BASE 诊断 1 已通过，FIX 诊断 2 在模型进入前因解释器准备凭据校验失败闭合；两次均为零模型调用，并完成清理。以下修订只针对诊断 2 已保存的实际证据，不改写原失败结果，也不重跑已进入的模型任务。

## 已证实原因

诊断 2 的首条原生 terminal 回执中，初始化 command 与预定文本一致，外层和 metadata 退出码均为 0，未超时，metadata 的 `py_interpreter_path` 与实际输出中的 `sys.executable` 都等于 `/opt/miniconda3/envs/testbed/bin/python`。

正文实际为：

```text
ESC[?2004lPWS_V062_PUBLIC_PYTHON=/opt/miniconda3/envs/testbed/bin/python
ESC[?2004h
```

前后两个序列是交互终端的 bracketed-paste 模式开关。r1 解析要求探针所在行以 `PWS_V062_PUBLIC_PYTHON=` 开头，却没有处理开头的终端模式控制序列，因此没有识别到真实探针。这是回执呈现解析问题；该回执不能支持“解释器仍然错误”的结论。

## 修改范围与保留边界

`software_benchmark_public_context_v062.py` 版本改为 `v062-public-context-and-native-feedback-r2`。`validate_terminal_initialization` 只在局部字符串副本中删除精确的 `ESC[?2004l` 和 `ESC[?2004h`，然后沿用原探针行解析与唯一性断言。不引入通用 ANSI 清洗，不删除未知控制序列。

原始 observation、`llm_content`、command、metadata、退出状态和全部回执原件不修改。原有要求继续全部成立：action 文本精确相等、原生响应类型与工具一致、无错误、未超时、两个退出码为零、metadata 路径一致、唯一探针输出路径一致。错误路径或重复探针不会因本修订放行。工具执行、权限、命令拒绝语义、模型提示、预算和继续次数没有改变。

`software_benchmark_sdk_bundle_v062.py` 的版本和输出目录独立切换到 r2：`runs/software-benchmark-v062/sdk-bundle-r2`。原 r1 archive、manifest、CPU 记录和诊断 1/2 原件保留，不覆盖。宿主来源封存、授权绑定以及备用诊断派发由主控制流程独立更新；本窄修没有执行 Docker、GPU、模型、网络、服务或评分操作。

## 必要回归控制

将诊断 2 的第一条实际 response 原样保存为 `tests/fixtures/v062-terminal-initialization-bracketed-paste.json`，附原 JSONL 文件和首行 SHA-256 来源记录，以及本次初始化所需的公开镜像环境投影。fixture 不依赖 CI 上存在本地运行目录。

仅运行新增加的 6 项针对性控制，首次全部通过，耗时 0.09 秒；原 14 项无关控制未重复：

1. 实际 bracketed-paste 回执通过，函数调用前后完整 response 相等，原始和模型可见内容保持不变。
2. 实际 probe 路径不同仍拒绝。
3. 两份真实 probe 正文重复拼接仍拒绝。
4. metadata 解释器不同仍拒绝。
5. command 增加额外内容仍拒绝。
6. 开头增加未知 `ESC[2J` 控制序列仍拒绝，证实没有扩大为通用控制字符清洗。

三个受影响 Python 文件的 Ruff 通过。r2 bundle 首次实际最小包导入与 BASE/FIX 生产工厂控制通过：BASE 完整接口与冻结 v054 工厂相等，FIX 五工具 schema 与 BASE 相等，network/GPU/weights/model/tools 五项计数均为零。新 archive 为 150,080,511 字节，SHA-256 为 `cf9e2bec7af5246a57ced732484a5483d857b7412cc753b975205e5dff952ada`，仍含 20 个明确项目模块。完整结果在新 `sdk-bundle-r2/manifest.json` 中记录。

上述 CPU 控制不替代后续真实容器备用诊断的证据。未经实际备用诊断通过，不能宣称 Docker 路径已经重新准入或模型实验已经开始。

## 后续实际部署结果

用户已授权的备用诊断3（BASE）和4（FIX）均实际通过，模型调用为0，对应自有容器／卷均已移除，原1／2记录保留。新评分与协调器记录写入`grading-r2`、`coordinator-r2`，原100份未运行控制请求和旧预备记录不覆盖。正式题单、174份配置、资源键及630容器／178卷上限不变。

随后协调器启动，GPU2／GPU4均取得853,008-token KV容量及精确中性调用准入，正式生成已进入。用户原授权原件、修订来源绑定、实际诊断与服务凭据见[启动记录](../../artifacts/software-benchmark-v062/runtime-start-r2/summary.json)。这是一项生成开始前的部署校验修复，未重跑任何正式回合、未改变模型看到的工具原始输出，也未扩大授权范围。
