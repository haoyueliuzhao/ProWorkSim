# v0.5.4：MATCH 原生接口与项目数值 provider 接缝

日期：2026-10-20（Asia/Shanghai）。本项为用户授权的准备工作；没有真实模型推理、GPU 调用、训练或正式评测。

## 实现范围

新增 `src/proworksim/software_benchmark_match_v054.py`，可以把 `software_benchmark_native_v054.build_conversation` 的同一套原生 OpenHands 工具和历史管理连接到实际项目 raw provider。没有修改旧 v051/v052/v053 模块、冻结源码或历史结果，也没有借用旧 SWE-smith 的题面、测试入口和 terminal executor。

实际绑定路径为：

```text
官方 Agent / 官方 LLMSummarizingCondenser
        ↓ 同一个 NativeMatchLLM bridge
官方 LLM.format_messages_for_llm + 官方完整工具 schema
        ↓
v054 原始模型 chat template（无项目 XML_SINGLE_CALL_HINT）
        ↓ 完整真实 input_ids、先预约
原 CalibrationActor.generate_native
        ↓ 仍为项目 path=project
原 candidate_runtime_v020.CandidateActor._generate_tokens
        ↓ 完整 output_ids / usage 先落盘并结算
独立 CPU 环境中的官方 vLLM qwen3 codec
        ↓
官方 SDK LLMResponse
```

新 `build_llm(bridge)` 可直接传入此前原生 `build_conversation`。condenser 对 LLM 做 `model_copy(usage_id="condenser")` 时保留同一个 bridge 和账本，因此不生成第二套预算，也不绕过模型 attempt 上限。原生文件编辑、任务记录、Terminal、Finish、Think 均保留；没有把 MATCH 换成受管 PROJECT 工具。

## 同一 raw owner 的明确准入条件

bridge 不根据名称相信某个对象就是原始模型。绑定时检查：

- `owner.path == "project"`，完整 inference contract 与本次 MATCH 合同相同。
- `freeze_identity().raw_release is True`。
- `checkpoint is None`、`adapter_sha256 is None`、`trained_adapter_loaded` 为 false。
- 正式分支要求实际 `CalibrationActor` 实例，`generate_native.__func__` 仍是该类原来的实现。
- 真实 owner 的原始 revision、完整来源 manifest SHA、BF16/FP32 storage profile、project 路径与完整 contract 都必须匹配冻结值；不接受另一个自称 raw 的检查点。
- 正式 codec 必须是固定官方 Unix socket 客户端；其 tokenizer 来源 manifest SHA 必须等于 owner 的 `base_manifest.sha256`。

程序化 CPU owner 只能通过显式 `programmed_fixture` 入口使用，而且不能设置正式执行授权。真实分支的 `execution_authorized` 默认 false；本次没有把它改成 true。

模型加载仍指向既有 `software_calibration_runtime_v051.load_actor(path="project", checkpoint=None)`。该加载器保持 BF16 主干、FP32 输出头、`sdpa_bf16_explicit_kv_v020`、原 FP32 sampling transform，模型本身仍由既有数值检查约束。新接缝不另建模型、不转换 dtype、不重复施加 temperature/top-p/top-k，也不调用任何学习函数。

可复用的原始模型来源凭据写入 `config/v054-match-seam.json`。复用以全部文件 stat 身份仍相同为条件；本次没有重新读取或哈希约 19GB 权重。

## 输入渲染与原生接口

旧 v051 `prepare_request` 会附加 `XML_SINGLE_CALL_HINT`，旧 v053 也只接收 `terminal/finish`。新接缝不调用旧 `prepare_request`，而使用原 tokenizer、原 chat template 和固定 `enable_thinking=false/preserve_thinking=false` 重新渲染完整请求，不添加项目提示。

消息导出实际委托官方 SDK 的 `LLM.format_messages_for_llm`；不独立强制字符串序列化或改写 reasoning 历史。新规范化只把 SDK 的 JSON 字符串工具参数恢复为模板所需对象，保留 SDK 已导出的字段及文本块，不再调用旧项目会移除 `reasoning_content` 的 normalizer。模板是否使用某个字段仍取决于冻结原模板，不能把“字段被保留”扩写为模板一定消费它。

输入记录沿用原 `generate_native` 接受的 native-input schema，并增加独立 `renderer_version=software-benchmark-match-v054-unmodified-native-template`。这里是数值调用协议兼容；不是把新实验称为 v051。记录完整原请求 SHA、实际 messages、渲染文本、全部 input_ids、token 数和模板参数。

完整窗口为 18,432、输出预约为 2,048，因此完整输入上限为 16,384。超过限制时拒绝该次 dispatch，不截断、筛选或重用旧 input_ids。

## 单题计量与失败处理

| 项目 | 已实现规则 |
| --- | --- |
| 全部 token 上限 | 500,000 输入加输出 |
| 全部实际模型 attempt 上限 | 128，包括 condenser |
| Agent decision 上限 | 128；condenser 不伪装为另一个 Agent decision |
| 预约 | 当前完整 input_ids 数量 + 固定 2,048 输出上限 |
| 已知成本 | 仅在 owner、input、attempt ID、完整 output_ids 和 usage 一致时结算 |
| 未知成本 | 保留全部未决预约，`complete_actual_tokens=null`，停止后续 dispatch |
| 格式／codec 故障 | 已发生且可识别的模型 token 先结算；保留完整原回包，再停止 |
| 自动重试 | 没有隐藏重采、endpoint fallback、旧 parser fallback 或自动 model retry |
| SDK metrics | agent、condenser 分别累计，各自指标与同一个总账本一致，避免重复累加 |
| 费用 | 本地金额估计为 null，不把未知费用写成 0 |

原生 SDK 在收到正常可解析回复后的后续决定仍属于官方 Agent 行为；每次真正请求都重新扣账。接缝不会为损坏的 provider 回包、未知 usage 或 codec 异常偷偷重新生成。发生 terminal stop 时使用独立 `BaseException` 边界，避免被官方 condenser 的常规 `Exception` 重试路径吞掉。

EOS、长度上限和时间边界分别保留；不会把被截断输出统一标为成功结束。输入、完整 native response 与转换后的 SDK response 分开落盘。时间检查包含 5,400 秒前置软边界和 6,000 秒生成后检查；原 provider 的 HF `max_time=600` 不是宿主硬中断，正式执行仍必须接入独立 host watchdog。

## 输出 parser 的独立环境

不能直接沿用项目 v017 XML parser：它对官方 SDK 的 nullable/`anyOf` 参数及部分原生格式的处理不等价于固定 REF `qwen3_coder`。

新增 `software_benchmark_codec_v054.py` 和 `tools/serve_match_codec_v054.py`，在独立 CPU `ref-venv` 中调用 **同版本 vLLM 0.32.0 的官方 `qwen3_coder/qwen3` parser**，通过权限为 `0600` 的 Unix socket 交换请求。模型 owner 的 resident 环境不导入 vLLM 的另一个 torch 版本。

codec 保留所有原输出 token 的成本和原始记录；只有文字呈现遵照 vLLM detokenizer 对终止 EOS 的规则，停止时最后一个 EOS 不进入展示文本。完整 token ID 不裁剪、不改写 usage。来源依据是该固定 wheel 的 `vllm/v1/engine/detokenizer.py` 中 `include_stop_str_in_output=false` 分支。decoder 启动只读取本地 tokenizer，禁止远端 tokenizer fallback。

准备命令如下；本轮已在独立 CPU 控制中临时启动该 sidecar 并清理，未启动常驻正式服务：

```bash
/data0/zhuxinrui/proworksim-runtime/run-cpu.sh --write-project \
  /usr/bin/env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1 \
  /data0/zhuxinrui/projects/ProWorkSim/runs/software-benchmark-v054/ref-venv/bin/python \
  tools/serve_match_codec_v054.py \
  --model-local runs/assets/models/Qwen3.5-9B-c20223623576 \
  --socket runs/software-benchmark-v054/codec/match.sock \
  --identity-output runs/software-benchmark-v054/codec/identity.json
```

它是 parser，不是 vLLM 模型服务，不会调用 `LLM()` 或模型生成。CLI 按固定源码路径加载独立 codec 模块，避免 `proworksim.__init__` 将业务适配器依赖带入已锁定的 REF 环境。没有为此往 REF 增加项目包，也没有修改已冻结依赖。

## 已完成的必要控制

七项不同的合成 CPU 控制通过（`tests/test_software_benchmark_match_v054.py`）：最初六项用时 0.11 秒，覆盖完整五工具和历史字段、agent/condenser 共用预算、完整输入加输出预约、未知 usage 保留预约并禁重采、codec 故障保留已知成本、长度结束与 owner 身份变化。随后新增一项真实 owner 元数据准入检查，未构造或加载模型；错误 raw revision 被拒绝（0.10 秒）。收紧长度边界后只重跑受影响的一项，仍通过。

另外执行真实缓存 tokenizer、真实 SDK `generate()` 和官方 condenser 的控制。响应由显式程序化 CPU fixture 提供；**这不是模型生成，也不是正式任务费用**。

最终 `r2` 于 **2026-10-20 22:55:31–22:55:40（UTC+8）**通过：

| 观察 | 结果 |
| --- | --- |
| 原生五工具及真实静态提示的合成主请求 | 7,400 input tokens |
| 官方 condenser 合成请求 | 521 input tokens |
| 程序化响应 | 各 5 个真实 tokenizer token ID，包含终止 EOS |
| 合成计量总数 | 7,931 tokens；仅账本控制 |
| decisions / attempts | 1 / 2 |
| 实际渲染 | 与直接调用同一原始 chat template 的文本和 token ID 完全相同 |
| 项目 XML hint | 未添加 |
| 真实模型调用、权重打开、网络尝试、GPU 打开 | 全部 0 |
| 此 SDK／tokenizer 控制中的官方输出 parser 执行 | 0；官方 parser 另做下述独立控制 |

`r1` 是手工指定 SDK 导出参数的初次控制；随后将运行路径改成同一官方 `format_messages_for_llm`，因此只重复受影响的接缝控制为 `r2`。两次合成输入的文本和 token ID 相同；保留两份回执，不把它们当独立评测样本。

最终回执：`software-benchmark-v054-match-seam-control-r2.json`，SHA256 `3ebb3c7d86bc7900dc7ca7131ffc8514bc7db7eabf102abc331191397ef08c24`。新模块、控制脚本和测试均通过 Ruff。

### 官方 codec 实际控制

REF 198 项依赖离线安装和 CPU 导入通过后，`check_match_codec_v054.py` 在该真实环境中通过私有 Unix socket 检查固定 vLLM 0.32.0 parser。最终 `r3` 于 **2026-10-20 23:08:43–23:09:19（UTC+8）**通过五项合成 case：

| case | 真实观察 |
| --- | --- |
| summary/EOS | 返回原 summary，最后 EOS 不进入展示文本；全部输出 token 仍保留 |
| 同一回复双工具 | 同时保留 terminal 和 task_tracker，未强制单工具 |
| 参数类型 | terminal 的 timeout 为数值、is_input 为布尔；task_list 为对象数组 |
| nullable 数组 | 官方 file_editor 的 `view_range` 正确还原为 `[1,3]` |
| finish | 保留官方 finish 工具调用 |
| 不完整 XML（第五个输入 case） | 官方 parser 返回 `terminal` 的空参数 `{}`，未重新生成；完整原模型回包由 transport 留存，后续由 SDK 作参数校验 |

“五项输入 case”和上表六行不同：第二个输入同时覆盖双工具及参数类型。对损坏 XML 不额外发明一个不同于 REF 的 parser 规则；它不是本次完成了真实 Agent 格式反馈循环的证据。

模型调用、真实工具执行、权重打开、GPU 打开和外部网络尝试全部为 0，只有本机 Unix IPC。临时 sidecar 在 SIGTERM 等待 10 秒后被控制程序 kill 并回收，已确认退出；正式宿主生命周期必须保留这种有界清理，不能等待无期限退出。

故障历史如实保留：`r1` 因项目包的 eager import 缺少 `openpyxl` 而在 parser 启动前失败；改为独立模块加载后，`r2` 在控制程序清理时发生 `TimeoutExpired`，且旧控制尚未保存完整 case 回执。**这不能证明某个 parser 请求超时或未通过**。增加逐 case 证据、先保存结果和 kill/reap 回收后，`r3` 完整通过；未改官方 parser 算法或 REF 依赖。

最终官方 codec 回执为 `software-benchmark-v054-match-codec-control-r3.json`，SHA256 `2ecd4e69540d91237e27c68552efe29776fde53c6586fee563b7377a0fe9394b`。`r1` 失败回执和 `r2` 的独立清理诊断也保留，不将其补写为成功。

## 正式运行前仍需闭合

本次已把真实数值 owner 入口、原生 SDK/condenser、完整 request、共享账本和输出 parser 通道实现为具体模块；但以下未完成条件不能省略：

1. 官方 codec 的非流式、多工具、nullable 参数、EOS 与损坏格式 CPU 控制已通过；后续仍须核对完整 REF 服务回包与 sidecar 的端到端传输绑定，不能把 parser 单元等价扩大为整个服务数值等价。
2. REF 和 MATCH 应采用同一个真实 tokenizer 计数策略。MATCH 已按完整实际模板计数；不能让 REF 仍使用默认近似计数，却宣称 condenser 的计量接口已经完全相同。
3. 调度器为每题独立绑定 owner window、预定 seed、workspace 和宿主硬 watchdog。
4. 最终候选、Docker Actor 初态和官方评分器接入，以及另行授权模型预算与 GPU 运行。

本次没有为使准备“看起来完成”而改小任务集、取消 PROJECT 约束、启动真实推理或放宽运行授权。
