# v052 两路初态实际 SDK 与 tokenizer 资格方法

本文件对应 `scripts/software_bridge_inputs_v052.py`。当前只完成脚本与三个纯控制；**实际十二份 SDK 初始请求及 tokenizer 测量尚未执行**。来源资格和 OH reference 的真实接缝稳定后，须由 root 独立签发输入执行 release；本方法和控制本身不放行。

## 固定十二个请求，不要求跨框架同输入

沿 `software-bridge-v052-design.json` 的六个原 CAL2 task、OH_ref/PS1 两条件和原 seed/order，每槽只捕获一份真实初始 SDK/provider 请求，共十二份。两个框架的指令、工具和历史管理原本不同，因此不要求输入逐字节同值，不作 branch_id/UUID 或其它字段归一化，也不将 PS1 的 Γ1 投影强加给 OH。两条件须绑定同题原 source row SHA、问题 SHA、初始文件 map SHA，以及同一 raw model/tokenizer 资产；只比较各自实际初始输入是否满足 `selected + 2048 <= 18432`。

正式输入仍可能因后续行为、反馈和随机世界标识改变；本次资格不是任意未来 ID 或全部后续输入的容量保证。正式每次请求继续原硬容量门，不增加新工程余量门、第二容量候选或模型资格题。

## 实际捕获路径与记账边界

PS1 使用原 `software_calibration_world_v051.case_spec/build_software_collaboration_case` 和 `software_calibration_collector_v051.build_runtime`，只有 member_001，保持原模型可见 Γ/工具/观察合同。调用原首个 `runtime.step()`，由复用的 `CaptureTransport.prepare_for_budget` 接收真实 SDK 已构造的 request 后抛出独立 BaseException；在原账户 `_reserve`、attempt、生成、响应和工具执行之前停止。

只读源码说明原 `harness_sdk.step` 先递增 harness meter，并调用 `team_budget.consume_decision`，随后才进入真实 Conversation/prepare_for_budget。故 PS1 实际资格会话应保留 **harness_decisions=1、team_decisions=1**；不能写成 ledger0。root 已明确采用真实路径，不加 no-op budget shim、不回滚计数、不改变首机会预算视图。capture 回执分别记录上述 CPU 资格调度记账与 `attempts=0/reservation_tokens=0/responses=0/tool_actions=0/model_generations=0`、charged_tokens=0；业务 world 必须原样。它不转移到新正式 episode，也不计作真实模型采样或生成费用。

OH_ref 调用独立 `software_bridge_openhands_v052.collect_episode(..., initial_capture=callback)`。调用者先将同一初始 tree 按 UTF8 原 bytes 写入新 worktree，并使 episode evidence 目录与之分离。真实官方 Agent/Conversation 的第一 LLM 请求经同一个 `owner.prepare_request` 后调用 callback(request,native)，由适配器自己的 InitialRequestCaptured 结束；不手造消息模板，不跳过官方 initial provider request。

OH capture 模式不调用 tensor state capture、begin_window、reseed 或任何正式参数/RNG guard；不锁终态候选、不评分。它分别记录 native_SDK_LLM_entries=1、实际 adapter_decisions/attempts/tool counters；ProWorkSim harness/team 计数为 N/A（null 并给原因），不能把 N/A 冒称官方 SDK 没有进入执行机会。调用者核对完整 worktree before/after 字节不变。只有 capture 请求通过之后才写初态测量原件，不重放既有 SDK fixture。

## 原 raw owner 元数据及资产

MetadataOwner 不创建 model、torch、optimizer 或 learner，不读取权重 tensor，不恢复旧 guard。可引用原 CAL2 首 P 的现成 `runs/software-calibration-v051-cal2/workers/v051-cal2-boltons-1-P/attempt-001/resident/owner.json`：raw_release=true、trained_adapter_loaded=false、checkpoint/adapter=null，base manifest `030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6`，project 数值路径与冻结 C18432/O2048/temperature0.7 合同。

脚本将该原身份作为 **metadata only** 提供给 SDK 的 weight_identity/model_revision；新回执同时绑定原 owner ref 与本轮 model manifest、tokenizer、source/design refs。原 owner 当年的 parameter_storage 字段不是本轮新装载的证明，不写入新的 guard 通过声明。正式模型宿主仍须独立装载原发布权重并验证实际状态。两条件使用相同 raw 元数据；window 为 `calibration-v051:<v052slot_id>`，PS1 原库窗口前缀不因改名而改变。

## 实际 tokenizer 与证据计数

只在 release/来源/SDK/控制 gate 通过后加载本地 AutoTokenizer，不加载模型。精确复用 v051 `ExactTokenizer`：只有文本、模板消息及所有调用参数严格同值才命中缓存；底层 encoding、render 及两类缓存命中次数独立记录。

PS1 复用原 `project_software_request` 的 Γ1 和 `evaluate_request`，保存原 request、selected request、projection、全部实际 native render 记录及最终 selected native input，验证 projection 的 selected token 数等于最终 native IDs 长度。OH 不套 Γ1，其 selected 就是官方原 request 与原生模板的真实 native IDs，仍用 `validate_native_input` 核对输入、合同和容量。

两个框架的不同 prompt 不会因为来自同一任务就复用测量，也不会以删 UUID 的分析近似复用编码。输出中的 `actual_initial_SDK_requests=12` 是真实请求形状计数，不是模型调用数或 tokenizer 总调用数；实际底层编码/渲染由计数器如实产生。没有程序生成响应或新模型生成。

## 独立 release 和输出 schema

必须先有全部六题通过的 `v052-shared-source-qualification-v1`（passed=true、fixture_only=false、completed=true、qualified_case_ids 为原六题顺序、blocked=[]），并严格匹配本次 test_runtime。参考 runtime 要绑定 SDK/tools1.49.6、commit `fcc102a697874d54a357e36004e02c95040dbdc0` 和实际官方模块来源；各 source refs、输入脚本及其传递实现、有限控制在真实捕获前冻结。

root 输入 release schema：

```json
{
  "version": "v052-initial-input-execution-release-v1",
  "released": true,
  "maximum_initial_SDK_requests": 12,
  "design": {"path": "absolute", "sha256": "...", "bytes": 1},
  "source_qualification": {"path": "absolute", "sha256": "...", "bytes": 1},
  "test_runtime": {"path": "absolute", "sha256": "...", "bytes": 1},
  "reference_runtime": {"path": "absolute", "sha256": "...", "bytes": 1},
  "raw_owner_metadata": {"path": "absolute original owner.json", "sha256": "...", "bytes": 1},
  "model_manifest": {"path": "absolute proworksim-manifest.json", "sha256": "...", "bytes": 1},
  "tokenizer": {"model_path": "absolute model directory", "files": [{"path": "absolute", "sha256": "...", "bytes": 1}]},
  "implementation_sources": {"script/module": {"path": "absolute", "sha256": "...", "bytes": 1}},
  "control_refs": [{"path": "absolute passed summary", "sha256": "...", "bytes": 1}]
}
```

这是结构示意，不是已放行记录。implementation_sources 须包括本脚本实际执行路径；reference runtime 的 modules 及每个 control summary 的 passed 均检查。输出根必须不存在，拒绝覆盖旧资格或自动重试。

root 明确放行后才可执行。实际 SDK/tokenizer 资格使用正式 native interpreter 与 runtime dependency 路径；`.venv` 仅用于此前纯控制，不能把其解释器当作已具备真实 SDK 的正式执行环境：

```bash
PYTHONPATH=runs/v030-runtime-deps:src:. runs/v016-sdk/resident-venv/bin/python -m scripts.software_bridge_inputs_v052 --release /absolute/root-input-release.json --output /data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/initial-inputs
```

摘要 version=`v052-actual-initial-input-qualification-v1`，含 passed、fixture_only=false、completed、actual_initial_SDK_requests、new_model_calls=0、design/source/test/reference/model/tokenizer refs；每行含真实 original/selected request、projection、selected/all native inputs、capture counter 及 source/problem/map SHA。最终同时保留 PS1 harness/team 资格记账，OH 每行原生计数及明确 N/A，新增模型生成为 0。模型准入由 root 另行签发，不由一次输入测量自动启动。

## 有限控制与执行状态

三个新纯 CPU 控制一次通过：全部六题来源和稳定 SDK gate；raw metadata owner 不冒称权重/retained actor；真实首机会记账与 reserve/attempt/response/tool 边界。首次 pytest 3/3、Ruff 通过。未重放旧 SDK 两会话 fixture，未做新实际 tokenizer 编码、仓库资格或模型操作。

本控制只证明资格脚本的门和计数约束；它不宣称十二个实际初态已 fit。真实请求与计数必须在 root 来源资格及参考实现稳定 release 后生成，失败与未决原件保留，不换题或热改后悄悄补测。
