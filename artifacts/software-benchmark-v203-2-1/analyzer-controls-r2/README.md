# v203.2.1 后处理 r2：启动前失败、隔离导入与零自然事件

本次只修改新的 `tools/analyze_passive_capture_v203_2_1_r2.py`，新增 `tests/test_passive_capture_analysis_v203_2_1_r2.py`。r1 analyzer、已封存队列源码、运行时捕获器和原始运行记录均未修改。此次被测模型/API、Docker、GPU、服务、原 Harness 世界动作均为 0；没有重复执行既有 SDK 控制。

## 修订原因及接口

r1 首两题在 controller 创建前因卷名前缀检查失败，主结果已经记录 `model_calls=0`、`model_dispatch_started=false`，也没有 controller_result 字段。旧 coordinator 在 `-S -P` loader 中用普通模块名导入 analyzer，因此先产生了无关 ModuleNotFoundError；即使解决该导入，直接访问缺失的 controller_result 仍然会失败。

新 coordinator 应按绝对路径 importlib 加载 r2，并调用：

```python
analyze_capture(controller_or_none, episode_id, host=episode_directory,
                generation_result=original_generation_result)
```

总完整性仍为 `report['integrity']['status']`。未获得 controller 时，只有匹配 episode 的主结果明确证明零模型调用、尚未派发且没有 controller 引用，才标记 `execution_state='NOT_STARTED'`；完整性为 PARTIAL，保留原始启动错误。null/未知的模型调用数量不会转为零调用证明；其他 episode 的主结果会使完整性 INVALID。单纯缺少 controller 路径只能得到 CONTROLLER_NOT_OBSERVED。

新 analyzer 对三个纯标准库观测模块使用绝对路径加载，不执行 proworksim 包初始化，不触发 openpyxl/world 等无关依赖，也不向 sys.modules 填充伪造的 proworksim package。首次加载持有进程级 import lock，避免两个准备线程读到尚未初始化完成的依赖模块。定向测试在 `/tmp` 工作目录、`python -S -P` 实际子进程中由两个线程同时首次 importlib 加载并调用成功。开发过程中发现的初次裸 -S 导入 openpyxl 失败未触发任何模型或世界动作；r2 已修复这一原因。

## 完整性不要求自然事件必须出现

COMPLETE 的条件是独立要求的来源齐全，不是必须创建任务、发布补丁、运行失败测试或提交交付。新增 CPU 控制只包含一次已接受输入和 staff_done，没有 T1–T6 事件；主 ledger、响应引用、物理字节、原 SDK 决策来源、工具回执与最终边界齐全时为 COMPLETE。该控制不代表成功完成软件任务，也不产生依赖或组织失配阳性标签。

`coverage_counts` 分维度列出 required_sources、observed_sources、missing_sources；`semantic_events_required_for_complete=false`。原 T1–T6 未观测会保留未观测，来源闭合后只能确认对应操作化阶段没有出现，不能推出没有语义依赖或组织失配。

没有后续阶段时，最后一次实际成员请求仍通过 `member_latest_requests` / `member_inputs` 保存，时间绑定其真实接受时刻。它不会回填到更早的 T0 成员视图中。图上全局任务/版本信息仍不自动传给成员。

## 使用已有原件的离线结果

本目录 `existing-sdk-normal-final.json` 使用既有 `sdk-controls-r1/normal` 原件，显式兼容该控制的 `primary/boundary.json` 和 `runtime/experience.jsonl` 路径。17 次已有脚本请求、16 次机会、原动作回执与独立 runtime trace 全部对账；由于没有物理 HTTP 捕获且旧日志缺少 capture_time，requests、responses、lifecycle 均为 PARTIAL。原控制未导出 controller-result，delivery 维度也保留 PARTIAL。其余已闭合局部维度保留，不把已有“脚本请求”命名当成真实 HTTP 原字节证据。

`existing-precontroller-failures.json` 使用 r1 两道首批题的主结果，分别输出 NOT_STARTED/PARTIAL，并保留原错误。输出和摘要只说明这些已有材料的状态，没有新建 controller、重试模型或重跑原题。

## 核验

定向命令：

```text
.venv/bin/python -m pytest -q tests/test_passive_capture_analysis_v203_2_1_r2.py --junitxml=artifacts/software-benchmark-v203-2-1/analyzer-controls-r2/pytest-junit.xml
```

5 项通过：隔离环境首次并行导入、未启动身份与零调用证据、零自然事件可完整、缺物理字节保留 PARTIAL、缺独立主清单不得 COMPLETE。旧广泛测试未重复执行。`generate_evidence.py` 只读已有原件，保存最终输出、JUnit 统计、源码哈希及前后原件哈希一致性；不调用 SDK/Harness/API。
