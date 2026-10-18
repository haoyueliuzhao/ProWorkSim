# v052 resume-r2：跨解释器绑定修订与零模型入口证据

本修订仅处理 resume-r1 的宿主入口故障，继续原三个尚无模型暴露的 xmltodict 槽。原 v052 四个已进入模型后中断的槽保持未知，不恢复、不重采；原 r1 的源码、运行目录、三条失败记录及 15.057310104370117 秒 worker 进程成本完整保留。正式释放、提交、prepare、生产清单入口检查和启动由独立 r2 协议控制。本说明记录实现与已完成的有限控制，不宣称 r2 模型执行或结果已完成。

## 已证实的 r1 故障

对同一份 r1 冻结模块，在实际宿主 `.venv/bin/python` 和原计划 `runs/v016-sdk/resident-venv/bin/python` 下各执行一次只读 `algorithm_binding()` 元数据探针。两次均令 `CUDA_VISIBLE_DEVICES=''`，未调用 worker、frozen、SDK、tokenizer 或模型；进程导入列表中没有 torch 或 OpenHands。stdout、stderr 和探针本身保存在 `artifacts/software-bridge-v052/resume-r1-binding-diagnostic/`。

宿主实际为 Python 3.14.6，原生解释器为 Python 3.12.3。3.14 的绑定完全匹配 r1 plan；3.12 唯一不一致字段为 `supervisor_AST_sha256`。原监督器源码 SHA 均为 `c1b480fe0b0d8c91fd942f917682d8db442610c34ad54ce8b6af81f4e0b467f7`。r1 plan 的 AST 散列为 `003d25a05bf06c570435373456bba0b14fb63fc93c4e57e2a1fd9d8e8297c800`，原生端得到 `3bebcbc27bc4b4b6d7b1e4a0a2a96a1b75ca8f87f49d4745b9e0d418d4112b4c`。

差异来自 `ast.dump` 默认文本表示：3.14 省略空字段，3.12 包含空列表。例如参数节点在前者为 `arguments(args=[arg(arg='root')])`，后者还包含 `posonlyargs=[]`、`kwonlyargs=[]`、`kw_defaults=[]`、`defaults=[]`。两棵树经过同一结构规范化后逐值完全相等，规范化 SHA 为 `a4527e3408ac5994172a3d66e2d64fd2ba864a0b1996fd9e152c9d5085522696`。因此这是跨解释器元数据格式故障，不是源码或科学参数差异。

已有独立零入口审计 `artifacts/software-bridge-v052/resume-r1-zero-entry-audit.json` 证明三个 worker 都在原 bridge.worker 的第一个 `frozen(root)` 操作失败，slot.started、task、resident/calls、prepared、episode、native-cache、report、terminal-code 均不存在；全部模型账本项为零。该回执用于判断原三槽没有增加业务暴露。运行器分配过 GPU 不等于发生过装载或生成。

## 最小独立实现

新文件 `scripts/software_bridge_v052_resume_r2.py`、新 root `runs/software-bridge-v052-resume-r2`、新 plan/release/version 均与 r1 分离。原 r1 文件 SHA `7859dd703f84e34f5ca184e7cfcca81cfcd81c1c19aea144c15c211a91c34cf6` 保持。原 616 个科学源码文件仍从原 v052 冻结目录同字节复制；r2 只另附自己的宿主文件。原模型、工具、世界、初态、种子、顺序、预算、GPU 容量门和资格记录不变。

`canonical_ast` 按 AST 节点类型与字段名序列化结构，只省略值为 `None` 或空列表的可选字段；列表顺序、所有非空字段和常量值均保留。随后用固定 `sort_keys=True` 与紧凑分隔符 JSON 编码并散列，明确记录 `supervisor_AST_encoding='nonempty-fields-json-v1'`。这一操作仅改变绑定元数据表示，不修改用于编译执行的 AST。原监督器源码字节散列继续单独验证，原唯一 worker-module 字符串替换继续绑定。r2 的 canonical AST SHA 为 `e2dbd8649ccd79b879b4bef54f656ece126d894c8a6cc8d8cf0137a6f6d24761`；它与诊断中 r1 的 canonical SHA 不同，是因为预先声明的 worker module 字符串已改为 r2。

原 worker、账本和 worker_completion 继续使用原函数 `__code__` 的私有命名空间绑定；没有修改原模块全局量，也没有更改模型循环、工具历史、资源/进程/截止算法。`predecessor_references` 和 `original_rows` 仍指向原 v052 第一阶段。r1 零入口成本由最终合并报告单列一次，不计入 r2 模型账本，不新增科学分母或转移旧预算。

新增 `zero_model_predecessor` 仅消费现成零入口回执和其原件。prepare 与 frozen 都核验回执通过、三行身份、已结束失败、模型账本全零，以及源文件、plan、supervisor、pause、信号日志、worker日志和launch的SHA绑定；若出现新的 slot/model 入口路径或 attempt 目录项目也拒绝。不能把 r1 有 started、模型费用或变更 trace 的情况当作未暴露重启。

Release 使用 `v052-bridge-resume-r2-release-v1`，stage 为 `v052-OH-BRIDGE-resume-r2`。原八项检查保留，新增 `r1_zero_model_entry_failure_preserved`；supporting_references 新增 `resume_r1_zero_model_failure` 和 `cross_interpreter_binding_diagnostic`。原三槽上限仍为 1,500,000 token、384 决定/attempt、两条 PS1 共 64 次公开测试；四个原中断槽排除规则不变。

## 本次必要控制与生产入口门

新增控制均首次通过，原三个纯控制和全部源码、初始输入、SDK、tokenizer、模型资格没有重跑：

1. 两个实际解释器各执行一次新增绑定控制，完整 adaptation 逐值相同；规范化编码已绑定，非空常量变化仍被检测，GPU 被禁用且没有 SDK/torch 导入。
2. 一个零入口准入控制接受既有回执；三个最小反例分别把 slot_entered 改为 true、已知模型token改为1、信号原件SHA改为错误值，全部拒绝。反例只写入控制目录，不修改原审计或运行原件。
3. 仅对新增 r2 宿主文件执行一次 Ruff，通过。

证据摘要为 `artifacts/software-bridge-v052/resume-r2-host-controls/summary.json`。源文件 SHA 为 `e6805b4381847903f3ec7ee5df83d66949352c54bcabe19ec347d93b0ecda0e5`。此次控制没有 prepare、真实 frozen、模型、GPU worker、参数更新或反向调用。

生产清单入口仍需在 r2 源码和 release 提交、prepare 完成后，由实际 native Python 3.12 在 `CUDA_VISIBLE_DEVICES=''` 下调用一次新 `frozen(root)`；成功后才允许宿主启动。这一必要门验证真实生产计划及原件绑定，不以 mock 代替，也不加载模型或重新资格化初态。其回执由正式 r2 执行阶段另存，本文不预填通过。
