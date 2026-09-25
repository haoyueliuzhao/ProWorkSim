# D3：完整多轮基础 PPO 与 Q=B 预检

这是一条新管线，不继续 v0.11 的三条零奖励首决策。实现采用 PPO clipping 与集中训练、局部输入执行的基本结构；参考 [PPO 原论文](https://arxiv.org/abs/1707.06347)和[合作多智能体 PPO 研究](https://arxiv.org/abs/2103.01955)。本实现明确限定为共享语言模型 actor、过去联合观察结构 critic 的单窗口预检，不声称复现原论文全部架构或实验。CPU 恒等测试、真正参数更新、独立工作收益分别报告。

## 冻结输入与执行条件

选择总体计划中的四个 Qwen repeat1 联合槽位，每个槽位的 provider、implementer、reviewer 全部真实轮次。不能根据奖励换槽、补采成功、挑短输出、只保留首个 response 或以 DeepSeek 替代 Qwen 当前策略支持。输入为 `TeamRollout` 与 `MemberView`，程序见证和 Teacher 数据不准入 actor。

冻结 inventory 格式：

```json
{
  "version": "multiturn-ppo-inventory-v0.12",
  "member_ids": ["provider", "implementer", "reviewer"],
  "slots": [
    {"slot_id": "预先声明的槽位1", "team_rollout": ".../team-rollout.json", "team_rollout_sha256": "..."},
    {"slot_id": "预先声明的槽位2", "team_rollout": ".../team-rollout.json", "team_rollout_sha256": "..."},
    {"slot_id": "预先声明的槽位3", "team_rollout": ".../team-rollout.json", "team_rollout_sha256": "..."},
    {"slot_id": "预先声明的槽位4", "team_rollout": ".../team-rollout.json", "team_rollout_sha256": "..."}
  ],
  "expected_policy": {
    "system_fingerprint": "实际只读base版本",
    "inference_profile_sha256": "...",
    "weight_manifest_sha256": "...",
    "service_manifest_sha256": "..."
  },
  "service_manifest": ".../service.json",
  "service_records": "实际本地服务ledger目录",
  "d0_gate": {"path": ".../D0-report.json", "sha256": "...", "field_path": ["真实报告中的判定键"]}
}
```

四个槽名在采样前固定；收集后把实际文件摘要纳入训练冻结。D0 是否通过必须从摘要匹配的实际报告取值，不能手填一个 `passed=true`。每条 TeamRollout 再核对原封闭 EpisodeManifest、起止干净源身份和经历区间 SHA256；每个成员的实际 response/request 再与原本地服务 ledger 对齐。输入与输出 IDs、输出 mask、原行为概率来自实际采样，不重新分词，也不以复算概率覆盖原记录。

正式 GPU 门槛同时要求：

- D0 的独立工作正确门槛已通过。
- 四个固定槽都有可信终局 RewardSpec 回报、可靠记录及完整可恢复的所需动作；不是丢掉不合格槽后对剩余样本训练。
- 四个精确情境属于同一声明的 Γ、团队策略与收集窗口；base 文件 manifest、模型版本、服务 manifest、实际 inference profile 一致。使用 float32、单 batch 的新轨迹。
- 至少两个目标成员实际生成两次以上决定；全部已生成格式失败也留在自身动作中。明确未发 HTTP 的预算边界可以保留为 `actor_required=false`；发生过采样但缺失完成记录不能作为“没有动作”跳过。
- 四个可信回报存在差异；实际旧 critic 下的优势有限、非零且非退化。不同随机初始 critic 值不能替代真实回报差异门槛。
- 每个原输入加输出长度不超过预声明 16384；不裁剪，任一超限即整个窗口不训练。
- 更新前每个实际输出 token 的概率复算最大差 ≤0.02 nat、平均差 ≤0.002 nat；任何超界都停止，不提高阈值或换轨迹。

记录有效性 `V_record=true` 是 actor 可恢复性的要求。其他工作有效性（权限、依据、交付）失败仍可保留在可信基础 RL 中，不因失败而移出原分母；V 与 Mapper、支持资格不等同于奖励资格。没有自身动作的成员贡献零 actor 损失，不生成伪造目标，不把该成员质量转移给其他成员。当前实际更新固定 Q=B；支持不足不妨碍有信号的基础 RL，但也不赋予未支持类别正权。

## 固定基础配方

共享只读 Qwen base 加一个共享 LoRA actor：q_proj/v_proj、rank 8、alpha 16、dropout 0、无 bias 更新。critic 是独立 `Linear(30,32) → Tanh → Linear(32,1)`。三个角色各取最近实际公开观察中的工作数量、五种状态数量、工作区别名数量，以及过去真实成功/拒绝工具动作数量，共 27 个标量，再加当前角色的 3 维 one-hot。工作计数除以 10，别名和动作计数除以 100，不拟合数据归一化。

critic 特征只来自该模型调用开始之前的真实事件前缀，同时保存引用的各角色观察序号；不从封闭 episode 的终局倒填过去状态，不读正文业务数值、隐藏答案或终局评价作为过去输入。终局回报只作训练目标。actor 始终只收到该成员当时实际局部 token，不能读取 critic 的联合输入。

采用 gamma=1 的 Monte Carlo 终局回报；每个决定优势为 `可信终局R − 更新前冻结critic值`，不做优势标准化。终局 R 使用已冻结 RewardSpec 的结果，含其声明成本项，不另通过格式成功、发布次数或审批标签加奖。

设固定槽数 M=4、成员数 I=3，成员 i 在槽 s 的全部自身输出 token 数为 T_si。actor 损失按固定槽、固定成员、该成员全输出 token 平均：

\[
L_A = -\frac1{MI}\sum_{s,i}\frac1{T_{si}}
\sum_{d,t}\min(r_{sidt}A_{sid},\mathrm{clip}(r_{sidt},0.8,1.2)A_{sid}),
\quad r_{sidt}=\exp(\log\pi_\theta-\log\pi_{old}).
\]

无自身动作时整个成员项为 0。输入、同事消息、工具返回以及过去输出作为后来 prompt 的部分都不是当前生成目标；当前真实格式失败输出仍是生成目标。这里是 token-PPO surrogate，不能把整个多轮轨迹的新旧概率连乘成另一种目标。

critic 每个槽/成员/真实决定等权，损失项为 `0.5 × (V−R)^2`；总损失再乘固定 critic coefficient 0.5。entropy coefficient=0、KL coefficient=0，均明确固定。q/b 仅能重配 actor 项，不能改优势、critic、熵/KL或归一化，也不能再除以每个 minibatch 的权重和。q/b 与 PPO 新旧策略比率分别计算、记录。

一次完整窗口梯度累积、一次 AdamW 更新；actor lr=1e-6、critic lr=1e-3、weight_decay=0、betas=(0.9,0.999)、epsilon=1e-8，二者各裁剪到范数 1，seed=20260925。没有额外 epoch、早停挑最优或重复试训。在这一单步预检中 clipping 可能没有激活；不能据此宣称已验证多步 PPO 稳定性。

## 数值与资源路径

新管线使用每个真实 decision 的单条全序列 teacher forcing，`use_cache=False`，仅返回预测真实输出所需的 `logits_to_keep=输出长度+1`；不为 prompt 全部位置分配 vocabulary logits。不建立跨生成 token 的缓存反向图，不复刻 v0.11 的历史 batch/cache 存储方案。

原行为概率先以 eval/no-grad 逐条验证。实际梯度前向开启 HF training 模式以激活 nonreentrant gradient checkpointing，并明确要求 base 与 LoRA 的全部 dropout 为 0；实际 grad-enabled 概率另过相同门槛。仅调用 `eval()+gradient_checkpointing_enable()` 不足以证明 HF 已启用 checkpoint，本实现不作这种声明。所有决定通过且梯度有限后才执行 optimizer step。

预设主机 RSS 64 GiB，在决定计算边界记录当前及系统高水位，超限停止；这不是操作系统硬隔离，计算内部的瞬时分配可能先发生。GPU 由主运行者在正式训练前配置并记录实际共享占用，不停止其他项目。未到准入与概率门槛不执行更新。

保存完整 prepared tokens、critic 过去输入来源、原/复算概率、优势、逐决定损失、裁剪前梯度、更新前后 actor/critic/optimizer 共同状态及数值摘要。重载 actor/critic 全参数、optimizer 张量与参数组摘要，另对第一条真实决定检查 actor 函数输出；不冒称所有决定都做了函数重载。工作收益须在未用于更新的 fresh 情境实际执行后独立报告。

## 命令与已验证范围

默认和 `--prepare-only` 均只准入，不加载 GPU：

```bash
PYTHONPATH=src .venv/bin/python scripts/multiturn_ppo_v012.py \
  --inventory runs/某个已冻结训练清单.json \
  --output runs/multiturn-ppo-v012-admission-new --prepare-only
```

CPU 算术检查使用真实 Torch，合成小张量，不是模型工作数据：

```bash
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src .train-venv/bin/python \
  scripts/multiturn_ppo_v012.py --cpu-self-check \
  --output runs/multiturn-ppo-v012-cpu-new
```

它从含真实动量的共同 AdamW 状态出发，调用正式 `materialize_weights`，比较基础分支与 Q=B 分支的完整 loss、梯度、参数更新和 optimizer 状态；另验证 q/b 的基础加残余形式、失败残余权重 1、无自身动作零梯度、输入位置零目标梯度、critic 不随 q 变化、PPO ratio 与组成权重分离。报告保留实际小张量数值，不能把这些 CPU 检查当作真正 PPO 或学习收益。

只有主运行者确认全部门槛并另行冻结后，才使用 `--execute-training --model 只读base目录`。输出必须是新的独立目录，不覆盖既有数据。门槛不满足时保留四槽完整分母和 `not_run_data_or_learning_signal_gate` 报告；此报告是本轮允许的真实结果，不通过补采、Teacher 替换或回到旧三条首决策绕过它。
