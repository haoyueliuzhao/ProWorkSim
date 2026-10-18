# v052 OH_ref：固定官方 OpenHands 原生循环与共同原始模型桥接

本模块落实审计第二、六节要求：对照的是固定官方OpenHands原生Agent/Conversation与ProWorkSim受管OpenHands S1。它没有把CAL2的mini-SWE循环改名，也没有把受管HarnessWorker的调度和历史伪称为原生参照。这里只完成独立实现、官方来源核对和有限CPU/合成接口控制；没有加载权重、运行真实任务模型、执行新训练或放行正式十二槽。

实现为`src/proworksim/software_bridge_openhands_v052.py`，测试为`tests/test_software_bridge_openhands_v052.py`。root独立负责宿主、来源/输入资格和模型准入；本模块本身不启动后继。

## 官方来源、固定版本与最小组合

已浏览官方[架构入口](https://docs.openhands.dev/sdk/arch/overview)、[Hello World](https://docs.openhands.dev/sdk/guides/hello-world)与[工具扩展接口](https://docs.openhands.dev/sdk/guides/custom-tools)。官方文档将SDK、工具包、workspace和agent server分开；Agent负责动作循环，Conversation负责历史和生命周期，工具通过Action/Observation/Executor绑定。官方示例使用Agent、明确工具集合、Conversation.send_message与Conversation.run。这里据此选择公开扩展接缝，但实际签名和语义以本地固定源码为准，不能把当前在线文档直接当成旧版本逐字契约。

本地`runs/v016-sdk/upstream`的HEAD为`fcc102a697874d54a357e36004e02c95040dbdc0`，原resident安装的SDK为1.49.6。实际工具源码也取这个checkout的`openhands-tools`1.49.6。已核对官方`TerminalTool.create(..., executor=...)`支持注入executor；固定版本的`register_tool`只接收ToolDefinition实例或子类，不接受在线工具示例中出现的普通factory函数。实现因此由官方工厂创建真实TerminalTool实例后注册，没有改官方工具类、SDK源码或旧受管接入。

采用的组合明确是：

- 官方`Agent`、官方`Conversation`，只调用一次原生`conversation.run()`，由它决定后续推理、事件历史、工具执行、stuck处理和finish。
- 官方`TerminalTool`的Action、Observation和观察渲染；通过公开executor参数接独立受限执行器。
- 官方内建`FinishTool`；不暴露Think、FileEditor、TaskTracker、Browser、MCP、delegate、子agent或外部服务。
- 官方默认system prompt和事件历史，`condenser=None`，没有项目Γ1裁剪、受管逐机会循环或mini历史重建。
- 每次模型调用仍走同一原始Qwen的项目native provider，不另启reference SDPA、LiteLLM外部provider或自动重试。

这是明确较小的官方原生组合，**不是完整默认preset、CLI或容器产品复现**。工具输出仍使用固定官方TerminalObservation格式与截断。SDK事件、每次实际请求、真实native回包和工具命令分别保存，足以区分官方控制流与适配器操作。

## 独立tools overlay，不升级PS1

准备阶段发现原resident环境只安装`openhands-sdk`，未安装`openhands-tools`。原受管路径使用自定义工具，因此该缺项此前没有被需要。新参照将同commit工具源码复制到独立构建目录后，以`--no-deps --no-build-isolation`安装到`artifacts/software-bridge-v052/openhands-tools-runtime`，未改原SDK环境或上游checkout。

只补了导入所需的`libtmux==0.53.0`、`binaryornot==0.4.4`、`chardet==5.2.0`，版本和wheel SHA来自同commit的`uv.lock`，安装使用`--require-hashes --no-deps`。没有安装或启动浏览器栈，也没有升级torch、transformers、attention或数值库。

`reference-runtime`记录全部overlay文件SHA、实际依赖版本/模块路径、官方关键模块SHA和工具描述SHA。`bind_sdk`先从该manifest读取绝对overlay路径，追加到`sys.path`后再导入工具；已有SDK和数值库路径保持优先。它不依赖临时shell的PYTHONPATH，封存源码运行时也不按新的`__file__`位置猜overlay。若另一tools包遮蔽声明路径、版本不符或任何绑定文件改变，拒绝进入。

独立imports就绪原件位于`artifacts/software-bridge-v052/openhands-package/`。其通过只证明必要imports可用，不能充当真实SDK、测试或模型通过。

## 实际终端语义与共同测试入口

普通命令使用冻结r3的标准库shell helper，文件系统只开放当前缺陷工作树和声明的只读运行时；外部网络、正确源码、其它轨迹和项目父目录不开放。每个命令为新bash、起始cwd相同，文件编辑持久，cd/export/后台job不跨命令保留。timeout硬界为1–60秒，`is_input=True`、`reset=True`和空polling均无副作用拒绝，不伪称有正在运行的交互任务。

**原官方TerminalTool description带有持久交互终端承诺，因此本组合显式替换description为真实非持久语义，并在模型user前言再次说明。** 保留官方Action/Observation不等于保留全部默认工具行为；描述差异与SHA写入reference-runtime。有限合成场景包含is_input拒绝反例，模型实际收到的工具承诺与执行器一致。

模型可运行无参数的`bridge_run_tests`。只有这一明确命令调用`software_bridge_sources_v052.run_native_public_tests`：读取当前生产候选，恢复原只读tests/config/support，使用与PS1的run_tests及最终R_code完全相同的冻结解释器、依赖、r3隔离和原测试入口。真实socket类、asyncio/ssl语义不被替换；原需loopback的正式测试仍由共同runner预置受控FD，不能据此开放任意外部网络。

普通shell命令仍可做探索性操作，全部保存命令与输出，但不能宣称任意`pytest`变体都经过相同资格入口。OH终端机会、PS1的32次公开测试上限、工具/输出/错误反馈及finish和submit语义不同；该实验识别的是运行配置的组合差异，不是一个孤立字段的因果效应。

## 共同模型、预算与费用闭合

正式owner必须是既有`CalibrationActor`，`path='project'`、`raw_release=True`，checkpoint和adapter为空。模式为非思考，context18432、输出预约2048、T0.7、top-p1、top-k0、HF生成上限600秒；host外层时间和进程守卫另行保留。每槽128决定、128attempt、500000输入加输出token，90分钟软边界、100分钟硬边界，无旧余额转移、无自动生成重试。

SDK消息由官方Message序列化，工具schema由官方ToolDefinition生成，随后调用同一个owner.prepare_request。适配层不截断历史、不替换观察、不做二次候选选择。共享native renderer附加的原工具调用提示仍属于两路共同provider，不另立OH数值路径。

实际调用前先核完整prompt容量与prompt+2048预约；拒绝时保存完整准备输入、余额、身份、窗口和未生成/无新工具副作用证据。每次开始记录独立inflight预约；只有真实回包input、actor、output IDs与usage精确匹配才结算。原生attempt ID唯一，SDK回包与真实usage逐次绑定。未知回包保留预约，不能填0。

窗口为`openhands-bridge-v052:<slot_id>`，condition明确OH_ref。正常官方finish和有证据的执行前安全边界都可以唯一导出当前树；SDK错误、身份或账单未决不能凭代码得分转成通过。调用者外层仍负责100分钟硬终止及注册子进程清理。

## 关闭导出、guard与只读测量

正式关闭先保存唯一`candidate-files.json`及`export-lock.json`，返回绝对路径/SHA/bytes引用，不多次验收后择优。合法生产增删与原只读文件恢复由共同source模块处理；root随后锁定统一终态候选并调用唯一grade。该末树端点只适用于v052新槽，不给旧HOLD未提交树补验。

OH没有PS1固定交付合同，`R_joint=None`、`project_delivery_endpoint='not_applicable'`。代码评价R_code与PS1附加R_joint分开，未知与不适用不能写成0。

每槽调用owner的capture_evaluation_state/begin_window/reseed/finish_evaluation/finish_evaluation_guard。`evaluation-guard.json`至少记录learning未变、RNG精确恢复、SDK/software binding未变、actor身份未变。这里是原始actor只读推理，不是完整learner恢复。

`measure_closed(result, *, row, owner_identity, accounting)`只读绑定episode身份、原请求/native输入/实际usage、唯一attempt、工具记录、关闭guard和唯一导出，返回continue/pending/global_pause。root另核原生所有prepared/started/complete/fault、正式代码评分和owner guard。分数不参与机制门。

programmed owner只允许显式CPU控制；result带`fixture_only=true/formal_native_provider=false`，即使全部合成断言通过也只能得到formal测量pending。真实输入、账单或学习guard不能由CPU fixture冒充。

## 初态资格接口

API为：

```python
collect_episode(
    owner=owner,
    task_source=task_source,
    provider=provider,
    slot_id=slot_id,
    sampling_seed=seed,
    worktree=worktree,
    episode_folder=episode_folder,
    initial_capture=None,
    allow_cpu_fixture=False,
)
```

`task_source`采用`provider.build_case(task_id)`原结果，另带`runner_spec=provider.runner_spec(task_id)`、原workspace_origin与`reference_runtime`绝对引用。调用者先创建精确UTF-8缺陷工作树；collect比较原文件map后进入。工作树与episode证据目录必须分离。

`initial_capture(request, native_input)`在真实官方Conversation的第一次LLM入口、owner.prepare_request之后触发；回调可保存请求并返回，由adapter受控停止。该分支不调用capture_evaluation_state/begin_window/reseed或任何真实权重/RNGguard，不导出终态候选、不执行工具。metadata-only raw owner足够。

capture_counters如实区分：native SDK LLM入口1次；adapter决定、attempt、预约、回包、工具、模型生成均0。ProWorkSim harness/team决定计数不适用于OH，记null并写明原因，不能把已经进入官方step描述成尚未进入任何SDK逻辑。PS1初态自身的harness/team bookkeeping由原受管运行器保存，不与OH假装同值。资格初态不迁入正式episode或继承预算。

## 必要新控制与失败保留

控制只覆盖四个新合同，不重跑旧HOLD/mini/评分资格。首次pytest的一个纯fixture隔离控制通过；另三个因指定basetemp父目录缺失在setup前停止。修目录后暴露缺少官方tools安装，随后在首次Conversation构造前暴露该固定版本不接受普通factory注册。上述失败日志全部保留，均未产生SDK会话、工具或模型调用。

独立tools imports就绪后，正式工厂实例注册接缝修正；三个新场景实际运行。初态捕获和执行前context终止通过。真实SDK场景完成4份programmed响应：无副作用拒绝is_input、受限bash修改合成parse.py、`bridge_run_tests`执行唯一synthetic原node、官方finish。共同runner真实测试1次/1node通过，完整会话正常结束，账单4次/404个**合成计数字段**闭合；这些不是实际模型或tokenizer生成费用。

该场景末尾测试断言误读`tests[0].status`，实际共同runner字段为`outcome`。只修断言并从已经完成的原result/request/command/guard原件补完剩余判断，没有重跑SDK、shell或测试。四个不同合同最终均闭合，原首件保留。详见`artifacts/software-bridge-v052/openhands-controls/summary.json`、各轮log/XML和`readonly-completion.json`。

本子任务实际新增模型、权重装载、GPUworker、tokenizer、真实任务资格、业务模型与反向/更新均为0。实际合成SDK会话和唯一合成共享测试只证明各自接口接缝；正式18逻辑/9物理来源资格、12初态和12模型槽仍须root独立逐阶段准入。
