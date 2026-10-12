# v049 学习接口与有限方向 CPU 控制

日期：2026-10-12。本文件记录学习接口子任务的必要控制及实际尝试，不代替整个 v049 准入报告，也不报告 9B 学习收益。

## 实现与继承范围

新增 `software_learning_v049.py` 使用原 `SharedActor.update_window` 的同一代码对象，通过私有 `FunctionType` globals 绑定 v049 组成验证器及可选梯度观察器。未改写原模块 globals、原 owner 更新方法、PPO 算术、critic 目标、原累积顺序、全局裁剪和 Adam 步骤。运行回执记录原函数代码摘要、源码引用、代码对象/闭包/defaults 同一性及仅有的扩展点。

先恢复原完整 common 3/3，复用原 18432 容量元数据绑定，再显式将原 `member_a/member_b/software_inactive` 三个 critic 坐标绑定为 `member_001/member_002/software_inactive`。除 recipe 的成员名称外，完整状态各字段都逐项摘要验同。新 S0 在生成前保存 actor、critic、两个 Adam、CPU/CUDA RNG、步数及历史窗口。训练入场同时绑定 S0、完整 recipe、冻结设计、Mapper 和 v048 唯一 Γ1 候选。

Γ1 学习材料直接使用生成响应中的实际 `input_ids/output_ids`；对原 SDK request、归档反馈生命周期、runner/member/call、selected request、budget seal 和原响应进行重放验同。不会把归档中展开的原请求替换为实际训练上下文。这里的 CPU 控制使用玩具 tokenizer/actor，未声称替代实际 9B 原生 tokenizer、概率或完整反向的运行证据。

新增 `software_allocation_v049.py` 复用原 `build_support/materialize_weights`，并绑定 v049 实际成员投影与原 learner admission。每个 root/member 的原库存 M=4，学习损失仍使用全局 8×2 的原分母。可信失败、未映射和不支持配置的基础材料保持单位组成。按 LA/LB、001/002、冻结两个类别的顺序，检查首个有支持、双侧可行且实际混合梯度非零的方向。

支持梯度仅由实际 B 的叶梯度 hooks 观察，返回 `None`，不修改训练梯度。按原 slot/member 顺序保存。方向诊断对 CPU 副本计算 `Σ(d_z/b_z)·g_slot`；原 B 梯度已经包含全局及本人输出分母。Q± 仍需分别从 S0 执行原生加权反向，不能使用这些诊断副本代替实际更新。支持诊断不读取开发结果、不追加采样或反向。

## 八项不同控制

| 控制 | 核实内容 |
|---|---|
| 学习整合 | Γ1 实际 token/反馈来源、S0 全状态、可信 R0/unmapped、原分母、单位组成恢复、观察器开关精确同值、非单位 actor 实变/critic 不变、新状态保存加载与开发冻结 guard |
| 旧成员名拒绝 | `member_a` 不能隐式进入新成员坐标 |
| 旧坐标顺序拒绝 | 原 a/b 顺序不能隐式传入新 critic feature 函数 |
| inactive 拒绝 | 不活动第三坐标不能接收伪造行动 |
| 支持与残余 | M=4/global16、可信失败/未映射保留、成员投影不合格只阻组成、单类仍可有 G-raw 类内自由度 |
| 未知原槽 | 不伪造第四次实际重复，不转移缺失基础质量，原八槽全部保留 |
| 半径及来源 | 双侧单纯形、[0.5,2] 比例盒与 TV≤0.2；原顺序、重复 episode、单类候选等拒绝 |
| CPU 梯度方向 | 跳过前一零方向后按固定顺序选择；原 global16 梯度尺度、正负权重、全零/单类 fallback、原梯度不变、错行及错摘要拒绝 |

整合控制每次成功执行含四次玩具 H=1：原 baseline、显式 unit、unit 加观察器、非单位组成。前三者的完整状态（含两个 Adam/RNG）、原始梯度和逐行 loss 精确同值。非单位组的 actor 梯度与参数改变，而 critic 与 critic Adam 精确同值。每个 H=1 使用 16 个原决定，各完成一次 actor 和 critic optimizer step；另有一次明确的玩具初始化步骤用于建立非空 Adam 历史。

## 所有本子任务执行尝试

| 顺序 | 命令范围 | 结果 | 秒 |
|---|---|---|---:|
| 1 | 学习文件 4 项 | 3 通过、1 失败 | 4.97 |
| 2 | 仅学习整合项 | 1 通过 | 8.26 |
| 3 | 加入实际 S0 强绑定后的学习 4 项 | 4 通过 | 8.15 |
| 4 | 支持/方向 4 项 | 4 失败 | 2.86 |
| 5 | 修正纯声明依赖后的支持/方向 4 项 | 4 通过 | 2.46 |

第一次失败发生在玩具 Γ1 fixture 的旧工具调用缺少 `function.arguments`，尚未实际玩具生成；补齐 fixture 原生调用字段后，仅重跑受影响整合项。第四次的四项失败都发生在新的 policy 声明验证器动态加载 SDK、普通 CPU 环境缺少 `jsonschema`，尚未进入支持/方向逻辑；验证器改用事前固定真实类字符串，并由 native `policy_spec` 另核对实际类身份后，重跑这四项。两类原失败均保留，不记作通过，也不是 9B 模型或学习数值失败。

不同控制 8 项，累计 pytest case 执行 17 次：12 通过、5 失败。最后学习文件 4/4、支持文件 4/4 均通过。新增学习/支持模块、两份测试及根 runner 的 Ruff 检查通过。该统计仅含本子任务列出的执行；后续项目集成执行应另外累计，不能把后续重复也写成本次同一个执行。

## 计算口径与限制

两次成功整合控制共执行 8 次玩具完整窗口更新，另有三次玩具非空 Adam 初始化（包括最早失败尝试已完成的初始化），累计玩具 actor/critic optimizer steps 各 11。玩具生成调用累计 32；各成功整合中的四组更新不可称四次 9B 更新。支持/方向控制只操作 CPU 梯度张量，没有 backward 或 optimizer step。

本子任务实际 9B 加载、9B 生成、9B backward、9B actor/critic optimizer steps 和 GPU worker 均为 0；CPU 控制也断言 CUDA 未初始化。没有重启旧 26/3/48 或 v037 缓存生产队列。

原 H=1 配方仍是一轮完整窗口累积，而非一次 backward。原历史 B 的 682 个决定曾耗时 92,126.65 秒；此处仅用作训练不得套用 episode 总时限的历史依据，不是新 v049 时间估计。新真实学习还需单列前向、反向、optimizer、保存恢复及 GPU 时间，并以实际新运行记录为准。

只读审阅确认根 runner 的 `expected_recipe` 与原保存配方经声明的容量/坐标元数据绑定相容。原 `software_learning_binding` sidecar 是迁移凭据，不是更新后 actor 身份；回合 guard 只要求它在该回合内不变。真正当前学习身份以完整 checkpoint、actor 身份、recipe 摘要和数值保护摘要为准。新 S0 恢复会还原 RNG/历史窗口；后续 `begin_window` 不消费 RNG，因而与共享逻辑采集窗口的检查相容。
