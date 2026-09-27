# v0.23 指定 D2 变体真实工作人员适配与 CPU 准入

本项已接通可复用现有 resident owner 的真实模型入口，CPU 正负控制通过。本文归档的是**模型运行前的适配准入**；归档时真实模型 episode、API 调用及 GPU 用量均为 0。真实初末结果应由后续 `initial/final/report.json` 单列，不能把本页控制结果记成模型成绩。

## 固定对象与分母

继续使用 TeamBench 提交 `d185aef1916fd86a9ba554d581fd256319a973af` 的 D2 生成器，以及 v0.21 明确命名的修订 grader，其 SHA256 为 `8b0a417ea3f810cfa07e376b80b869d479bf574305aef67c62903a738a9a096b`。没有修改旧隔离实现或扩大 54 项权限矩阵，grader 重跑提交代码仍通过既有 v0.22 Landlock/seccomp 入口。

[冻结提案](../../examples/id-vtdo-v23/external-d2-proposal.json) 在生成新材料或观察新模型结果前指定 generator seed `20261001/20261002/20261003`，配对 sampling seed `202610010000/202610010001/202610010002`，只比较内部 pilot 的 fresh 初态与预定终态。三 seed × 两 checkpoint = 六个外部 episode，单列在内部 72 例之外。两个岗位不构成两个独立任务，新 seed 不构成新来源。本项不会使用 R1 checkpoint 或挑选最好 checkpoint。

每例 executor 12、verifier 12 次生成机会；每 checkpoint 至多 72 次请求，共至多 144 次。两端点合计最多 2 GPU 小时、每端点最多 1 GPU 小时、每例计算监督最多 20 分钟。监督预算由 root stage worker 执行，`on_episode_start(seed)` 回调逐例刷新；它与角色职责机会预算分别记录。当前复用的模型温度、context 16384、输出上限 2048 来自既有 owner，不新增模型、精度或训练配方。

## 真实动作与材料绑定

本变体采用两个模型岗位。准备阶段将既有完整 specification 原文从 Planner 资料复制到 executor inbox，明确记为程序准备；没有模型 Planner，没有规则解答或参考程序交给模型，也没有把准备交接算作模型协作成绩。

Executor 可实际读取 brief、交接 specification、code、input、output；仅能编辑 `clean.py`、实际执行并显式提交。`submit` 固定 code/input/output 三者的内容 SHA，随后该岗位结束。`staff_done` 不会替它提交。没有显式提交时，Verifier 不激活，评分器产物与缺席复核仍分别记录。

Verifier 必须实际读取所固定 code/input/output 及自己的完整 specification，调用 `verify_submission` 提交**自己生成的 Python**，最后显式声明 `pass/fail`、submission ID、verification ID 和理由。该 Python 在另一个仍使用既有隔离 profile 的有限布局中执行：可读原 input、固定 code、spec，但不可读原提交 output。它必须返回完整 `columns/rows` JSON 表格，控制器逐行逐格与固定提交比较；控制器不提供正确行、参考程序或修复答案。

这证明的是模型请求触发了真实隔离计算，以及其产出的表格与这份固定资料的比较关系。它不证明模型的内在推理相互独立，也不是泛化到所有输入的程序语义证明：模型仍可能在上下文里看过提交内容。原始 verifier 程序、OS 执行、返回表格、比较结果和最终声明均保留。

所有角色 read/write/run 都经过既有 OS 隔离，而非只用 Python 路径过滤。控制器另拒绝 symlink 或超出 1 MiB 的角色文件。读写日志保留完整隔离 profile；模型只收到相关内容、退出码与实际输出，避免把宿主实现细节塞入工作对话。

## 评分分项

最终 grade 在独立复制的固定代码/输入上运行，避免评分重跑改写正在评价的固定提交。除原修订 grader 的 artifact predicates 与 `pass` 字符串 predicate 外，单列：

- 显式固定提交、固定材料实际读取、Verifier 实际表格计算及实际判断。
- 有检查支持的声明、无据批准、错误批准/拒绝。
- 原提交未变、grader 重跑是否逐字节重现原输出。
- 完整联合职责，以及成本、边界与未知状态。

完整联合职责要求固定交付、修订 grader 通过、材料完整读取、实际检查支持判断，且重跑输出与固定提交一致。**单独 `pass` 字符串不能建立复核责任**；评分阶段才产生的正确输出也不能冒充此前正确交付。

`compare_checkpoints` 固定三对种子，初末材料 SHA 不一致就拒绝比较。缺失或未知端点保留 `null`；不能给完整主点估计时返回已知配对和未知相容上下界，不偷偷缩分母。

## CPU 控制结果

所有控制只使用旧开发 seed 0，经过真实 `ModelPolicy → StaffRuntime → role tools → OS isolation → 修订 grader`，transport 明确返回 fake completion。共 47 次 fake transport 响应，真实模型调用 0，未用新 seed 选择修复。

| 显式 CPU 控制 | 修订 grader | 实际检查支持声明 | 完整联合职责 |
|---|---:|---:|---:|
| 正确程序＋完整实际检查＋pass | 11/11 | 是 | 是 |
| 正确程序＋无读取/检查的伪造 pass | 11/11 | 否 | 否 |
| 正确程序＋只执行 `print("pass")`＋pass | 11/11 | 否 | 否 |
| 错误部门纠正＋真实检查＋fail | 9/11 | 是 | 否 |

最后一项保留原 grader 的 `department_correction_fail` 和 `bad_attestation` 两项失败，不能把正确拒绝错误产品改称原 grader 通过。四控制均满足预声明期望。另有一项报告控制验证缺失的第三配对不被当作零或从分母删去。

必要测试：`5 passed in 7.64s`；三个新 Python 文件 Ruff 通过。没有重跑原 54 项隔离矩阵或新 GPU 诊断。

## 路线和实际 tokenizer 检查

正确控制路线为 executor 7 次、verifier 6 次，均在 12 次限额内。使用当前 Qwen3.5 的本地官方 tokenizer 和既有 native XML parser，对这条旧资料见证的真实请求及合法输出表示计数：

- 输入从 1215 至 4663 tokens。
- 最长见证 native 输出 368 tokens，低于 2048。
- 输入＋完整输出保留上限峰值 6711，低于 context 16384。

这是一条可行路线的存在性证据，不是最短路线，不保证模型走得出，也不把旧 seed 的长度当作新 seed 或任意轨迹的上界。

开发中，首版 CPU fake owner 沿用了通用 recipe 默认 512 输出上限；在模型运行前改为实际 2048/16384/0.7 并重做 CPU 准入与 tokenizer 归档。一次临时 tokenizer 脚本遗漏 `chat_template_kwargs` 因而在模板渲染前报错；补齐既有 `enable_thinking=False` 后完成。没有实际模型请求或候选精度更换，早期控制目录保留。

## 接入及复现

```python
from proworksim.teambench_model_v023 import run_checkpoint
report = run_checkpoint(
    owner,  # 已加载且 idle 的真实 resident owner，由 root 绑定正确 checkpoint
    assets="runs/assets/domain-v021/TeamBench",
    output="runs/domain-v023/external-initial",  # 尚不存在的目录
    checkpoint_label="initial",  # 或 final
    on_episode_start=callback,
)
```

每例独立 begin/finish frozen evaluation，核对 learning state 不变并恢复 RNG。该入口不加载第二模型，不执行参数更新。调用者负责 checkpoint 恢复身份和 GPU/宿主预算监督；失败的当前 episode 保持 `interrupted_or_unassessed`，不填零。

```bash
.venv/bin/python -m scripts.teambench_model_v023 --mode cpu-controls --output NEW_CPU_OUTPUT
PYTHONPATH=src CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  runs/v016-sdk/resident-venv/bin/python -m scripts.teambench_model_v023 \
  --mode token-lengths --output NEW_CPU_OUTPUT
```

最终 CPU 原始证据：`runs/teambench-v023-cpu-controls-admitted/`；机器可读归档和内容哈希见 [CPU 准入记录](teambench-v023-model-adapter.json)。真实外部模型结果尚未执行，不阻断内部 pilot。
