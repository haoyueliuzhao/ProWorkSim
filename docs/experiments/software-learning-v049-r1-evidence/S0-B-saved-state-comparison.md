# v049 S0→B 完整保存状态：独立一次 CPU 比较

这是对原 S0 与完整 B checkpoint 的独立证据补充。原 reporter 的 `full_comparison=false` 保留在其原有只读报告范围内；本分析没有覆盖或回写该字段，也没有修改源码、运行原件、世界或验收结果。Q+、Q− 已封存为 `not_applicable`，本分析没有创建对应状态或虚构比较。

执行前仅在 ignored 分析脚本补入完成 worker/checkpoint/冻结源码/S0 绑定检查和 version 字段比较，作为纯报告修订披露；首次状态读取就在此修订之后完成，没有失败重读或重复张量比较。按冻结 plan 的 native Python 执行，`CUDA_VISIBLE_DEVICES=""`，所有 tensor 均 `map_location="cpu"`、`weights_only=True`。

## 文件与完成边界

B worker 的保存 checkpoint JSON 与完成报告中的 checkpoint 对象一致；worker 前后源码身份均与冻结 plan 一致，加载 S0 的已存完整 digest 也与原声明相同。两份 `.pt` 各从磁盘读取一次，文件 SHA/字节数分别匹配其 checkpoint 引用；随后在 CPU 计算完整 tensor tree digest，均与原保存清单一致。所有保存状态顶层字段均参与比较。

| 状态 | 文件 SHA-256 | 完整 tensor tree digest | 字节数 |
|---|---|---|---:|
| S0 | `96c11a5ad48a330d4188d87b844a49a745b5cef6f13272a45804e08fe8671dc5` | `ce1fcba63abe6724557d29f9ae5c1c660c1cdfa66c644762c5d18046215b766f` | 13440892 |
| B | `5d0886fa54c429a95ae2d62e0895e13a9afa287873aaebeaeab574e8c7f5d2c5` | `ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39` | 13440956 |

## 参数、Adam、步数与 RNG

| 成分 | 张量叶数 | 发生值变化的叶数 | 变化元素 / 对应总元素 | 差值 L2 | 最大绝对差 |
|---|---:|---:|---:|---:|---:|
| actor LoRA | 32 | 32 | 1114091 / 1114112 | 0.00481456405144 | 1.00643810583e-05 |
| critic | 4 | 4 | 833 / 1025 | 0.0174211750891 | 0.000957966549322 |
| actor Adam（含 step） | 96 | 96 | 2228256 / 2228256 | 5.65685647702 | 1 |
| critic Adam（含 step） | 12 | 12 | 1670 / 2054 | 2.00086899526 | 1 |

Adam 行的合并 L2 包含每个参数状态的 step 标量，不能解释为参数更新范数。其一阶/二阶矩与 step 的分解如下；param_groups 等非张量配置未出现变化。

| optimizer | 状态字段 | 变化张量数 | 变化元素 | 差值 L2 |
|---|---|---:|---:|---:|
| actor Adam | exp_avg | 32 | 1114112 | 0.00502011718555 |
| actor Adam | exp_avg_sq | 32 | 1114112 | 5.19995327928e-08 |
| actor Adam | step | 32 | 32 | 5.65685424949 |
| critic Adam | exp_avg | 4 | 833 | 0.0589633386652 |
| critic Adam | exp_avg_sq | 4 | 833 | 0.000246745402972 |
| critic Adam | step | 4 | 4 | 2 |

actor_steps、critic_steps、policy_revision 均为 3→4；两个 Adam 的每个参数 step 也均为 3→4，差值与原报告各一次 optimizer step 一致。actor identity 相应变化；原窗口标签/used_window_ids 的变化另存配套 JSON。

完整 recipe、base_identity、inference_profile、critic_has_nonzero_reward_history 与版本保持相同。CPU RNG 5,056 个 uint8 元素与存档 CUDA RNG 16 个 uint8 元素均完全相同；此处只是 CPU 读取、比较已有 CUDA RNG 张量，没有调用 CUDA API，也没有设置或推进原运行的 RNG。

## 已存原生梯度与 H=1 计算

原报告状态 `updated` / `complete`：206 行完整 backward，actor/critic 各一步。梯度裁剪前 L2 范数为 actor=0.0500310845673、critic=0.627356112003，均小于冻结裁剪阈值 1.0；这两个范数来自原生已存报告，没有重算梯度。

| 原生计量 | started | completed |
|---|---:|---:|
| 全部 actor wrapper forward | 414 | 414 |
| 其中 gradient actor forward | 206 | 206 |
| 其中 no_grad actor forward | 208 | 208 |

208 次 no_grad 前向由 206 行首轮核对和 2 行固定后更新测量组成；原生已存首轮、梯度前向概率核对均为 206/206 通过，losses 206 行。actor backward 与 critic backward 各 206，行级完成计量为 exact；内部 gradient checkpointing 的 kernel 重算没有另算 wrapper forward。

学习 interval 实际耗时 29529.8200297 秒（8.20272778603 小时），从证据验证后的原 updater 开始计时，不包含之前的装载/原生证据重放或之后完整 checkpoint 保存。该值已包含在驻留 worker 整段 GPU 成本内，不再相加。区间峰值 GPU allocated 为 37189235712 字节；它是原运行已存回执，不是此次分析访问 GPU 的结果。

原支持梯度回执覆盖 16 个原始 slot/member 组，每组 32 个 actor 参数张量，16 组范数均为正。它观察实际 B 既有 leaf 梯度，没有额外 forward/backward/optimizer step；本分析仅读取已保存 JSON 范数和来源引用，没有再次加载梯度 `.pt` 或重算其范数。

方向封存 `selected=false`、`reliable_base_material=true`。四块均仅有一个通过最少计数门的类别，Q±与其开发不适用；这不否定 B 的真实更新，也不证明更新带来开发收益。这里未读取开发评估结果。

## 独立 CPU 分析成本与边界

此次比较耗时 1.44209687505 秒，CPU process time 1.593435759 秒；峰值 RSS 747016 KiB。两个 shared-state.pt 合计读取 26881848 字节，总证据读取 32853335 字节，共 18 次源文件读取；Torch CPU 线程数为 2。输出序列化和本 Markdown 的轻量 JSON 渲染不包含在上述时钟内。

模型装载、optimizer 构造、新 forward/backward/optimizer step、GPU API 调用及 GPU worker 秒数均为 0。没有重复张量比较、测试或模型概率验证；两份状态都仅使用既有 checkpoint。训练回执成本与这次 CPU 审计成本分别保留。

配套 JSON SHA-256：`142214e7dd029f819c15378dfca7912d0c41d15b4f9d1f6983e7a3f461cfcb5b`。逐参数差异、全部绑定及原始计算回执均保留在 JSON 中。
