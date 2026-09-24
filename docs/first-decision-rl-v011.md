# v0.11 首决策策略梯度实验合同

本文区分最初 v0.11 对照、v0.11.1 缓存重放与 v0.11.2 保存张量存储修订。原训练尝试在行为概率门槛处停止，optimizer_steps=0；第二次缓存重放正式尝试因进程 RSS 持续增长，由主运行者终止，未记录完成的反向组或参数更新。两份原报告均保留。v0.11.2在59f5e4a干净冻结下，实际完成两组反向、一次更新与保存重载；917,504个adapter元素变化，RSS峰值99.35 GiB。独立环境接入试跑仍格式失败，没有测得学习收益。完整证据见[实验报告](experiments/model-executable-v011.md)。

## 固定研究范围

训练代码在正式 36 个模型开发 episode 之后冻结；运行前的计划对话已指定选择 `finance-direct-qwen-1`、`finance-direct-qwen-2`、`finance-direct-qwen-3`，按这个顺序提供各自的封闭 `episode/` 目录。不能看奖励后换 episode、补采成功轨迹或改用后续决策。每个 episode 只有**首个实际模型生成的完整 token 序列**作为一个可学习宏动作；后续目标工作人员决策、环境同事与世界动作全部作为已经记录的固定行为续行。

这是一次首决策 REINFORCE LoRA 更新，不是完整多轮 Agentic RL，也不是“无训练／独立任务训练／项目群训练”三组对照。失败 episode 的零奖励正常进入训练；不能据此判断改善了未见任务能力，或认定首决策就是后续失败的根因。

## 真实数据准入

输入仅从 EpisodeManifest 固定的经历区间提取，先调用 `assess_historical_episode` 对封闭历史评价。选择的世界义务是 `FINANCE::reconcile`，角色是 `analyst`。

每项输入同时满足：

- `case/record.json` 的 `public_capture_matches` 非空且每项严格为 true；无捕获对照或对照失败单列为不合格，不替换 episode。
- 轨迹策略来自 `ModelPolicy` 的 `local-qwen-http`，模型为 Qwen2.5-7B-Instruct，修订为 `a09a35458c702b33eeacc393d103063234e8bc28`，温度 0.3，单 JSON 决策协议。DeepSeek Teacher 经历不作为这个实验的 on-policy 输入。
- 原始首决策的 call ID、完成响应、实际 HTTP attempt、角色和 episode 区间一一对应。只收纳一次成功 attempt；首决策发生服务重试或响应不可读时单列排除，不能从几个响应中挑一个。
- `input_ids`、`output_ids`、`input_mask`、`output_mask`、`behavior_logprobs` 来自本地推理时实际 token 与采样 logits。不得从最终文本重新分词、补写行为概率或猜测缺失 mask。
- 输入损失 mask 全为 0，输出损失 mask 全为 1（不同于注意力 mask：真实 token 为 1、左 padding 为 0）；实际 usage 与 ID 数量一致。保留整个输出序列，包括实际 EOS；不裁剪、不只选正确片段、不把输入作为预测目标。
- 行为分布为真实温度 0.3、top-p 1、top-k 0、repetition penalty 1。服务通过独立 logits processor 应用温度，因此其生成配置中的 temperature 为 1；训练复算使用真实 logits / 0.3。
- 三项可用输入必须来自同一未变化策略，源代码起止一致且干净；要求完整权重文件摘要与传入的只读 base 目录吻合，拒绝含已有 adapter 的目录。

这些条件仍依赖可信、冻结的本地推理服务及其记录，不是对服务器内存状态的密码学远程证明。模型别名本身不构成权重身份。

默认总长度硬限制为 8192 个实际输入加输出 token。超长记录保留完整原 token 和排除原因，不截断。服务、评价故障或未知奖励保持 null、eligible=false；可评但错误的输出、未交付以及格式失败不能因低奖励而被排除。若没有可用输入，报告明确没有训练，不能补取其他 episode。

## 奖励与目标

奖励来自历史 episode 末时的 `RewardSpec`：

```json
{
  "version": "reward-spec-v0.11",
  "reward_id": "first-decision-finance-v011",
  "objectives": [{"kind": "content", "work_node": "FINANCE::reconcile", "weight": 1}],
  "process_requirements": ["source-adoption"]
}
```

`source-adoption` 是正式主批开始前公开并冻结的 `required_source_adoption` 过程要求，覆盖 ledger、statement、definitions。资料可用、要求公开但模型遗漏采用时，过程违规得到零奖励；内容仍可保持 unassessed，不伪造数值错误。资料确实不可得、服务/评价故障继续分开报告。这一门槛不追溯加到此前没有该公开说明的 pilot。

只进行一次优化步：

\[
L(\theta) = \frac{1}{N}\sum_{i\in\text{eligible}}
  -(R_i-0.5)\sum_{t\in\text{该首决策输出}}\log \pi_\theta(a_{it}\mid x_i,a_{i,<t}; T=0.3).
\]

`N` 是固定三个输入中按上述证据规则实际准入的 episode 数。常数基线是 0.5。输出 token 对数概率求和，不改成平均 token 交叉熵，不做长度归一化、优势标准化、重要性加权或奖励筛选。零奖励时损失可能为负，这是此策略梯度目标的符号，不应当作交叉熵解释。

## 模型与数值检查

LoRA 只更新 q_proj/v_proj，r=8、alpha=16、dropout=0、bias=none。采用 AdamW，学习率 1e-6、weight_decay=0、betas=(0.9,0.999)、eps=1e-8，一步，梯度范数裁剪到 1。输入来自真实 token ID，不再加载 tokenizer 重建轨迹。模型使用 BF16/SDPA；`model.eval()` 关闭 dropout，训练计算显式开启梯度。v0.11.1 默认 `cached_replay`：由原服务记录核对完整 batch 归属，每一步以 `prepare_inputs_for_generation`、`forward(use_cache=True, logits_to_keep=1)` 和 HF generation 的 kwargs 更新规则计算原 token 的概率；再追加已经记录的 token，不抽样。attention mask 随原生成规则追加 1，位置来自 mask 的累计和，已结束的同 batch 行继续使用原 pad。过去 KV 始终保留在计算图，不 detach、不只训练末尾 token。

三条实际记录组成原来的 1+2 两组。脚本核对 `runs/qwen-service-v11/{completion_id}.json` 的完整 response，扫描相同 batch 的全部原文件；缺少 peer、额外 peer 或内容不一致均拒绝，不能把 batch 静默缩小。原服务没有记录行号，重放采用预先声明的 episode 顺序并明确标记，没有根据文件时间补造原入队顺序。原逐 token 概率门槛为这种排布提供实测支持。

v0.11.2 正式反向使用 `saved_tensors_hooks` 管理 autograd 保存的数据。按 `device + untyped_storage().data_ptr()` 识别所有模型参数，包括参数的转置视图；这些保存数据继续引用原 GPU storage，不在每个生成步将同一冻结权重重复复制到 CPU。只将非参数激活保存为非 pinned CPU 数据；参数在整次反向结束前不会更新。hook 中 detach 仅用于 autograd 保存数据的标准封装，不对计算中的 past KV detach，完整跨 token 反向链保持。

若保存的注意力激活含重复 KV heads，仅在各 head 的完整值按字节完全一致时保存一份；unpack 按原重复次数恢复完整值、shape 和必要 stride。带不同符号的零等字节不同值也不合并。这是无损存储，不量化、不改变 query heads、注意力数学或模型计算路径。其余激活原样保存。记录参数引用次数、避免的重复复制字节数、激活原始/保存字节数、保存数据存活/峰值、RSS 与 GPU 峰值。

脚本默认进程 RSS 上限为 64 GiB。单组完整反向探测实测峰值 40.91 GiB，0 次更新，行为概率逐 token 零差、梯度有限且非零。基于该实测值及尚未验证的双行批次，新的正式三条轨迹运行在开始前单独声明 128 GiB 上限；这不是对旧操作终止的追溯解释，也不保证双行组一定完成。每次保存/恢复激活时读取当前 RSS，并在下一次保存复制前核对额外字节需求；超限明确记为 `resource_limit`，停止后续计算，不修改奖励、阈值或输入。这个软件检查位于 hook 边界，并非操作系统硬内存隔离，其他分配仍可能在两次检查之间发生。每组分别计算每个 episode 的完整输出 logp 总和，统一除以准入 episode 总数，不能把 1+2 两组误当成两个等权样本。

在任何 optimizer.step 之前，使用同 base 加初始零效果 LoRA 复算每个实际输出 token 的行为概率，分别保存原值、复算值、逐 token 有符号误差、最大/平均绝对误差及整个序列差异。默认预声明容差为最大绝对误差 0.2 nat、平均绝对误差 0.03 nat；这是接受 BF16 缓存／批 padding 数值差异的实验阈值，不是 bitwise 相等主张。任一准入记录不满足阈值，则整个训练在更新前停止，保留失败比较，不挑掉这条记录后继续。除 no-grad 前置核对外，实际 grad-enabled 前向也逐 token 复核同一门槛；其报告独立保存在 `gradient-probability-check.json`。

保存实际完整裁剪前/后 LoRA 梯度、更新前 adapter、更新后 checkpoint、参数摘要及改变的元素数。重新加载 base+adapter，验证 adapter 参数摘要完全相等；另对第一条原始输入/输出行以同样显式数值阈值比较更新后/重载后的函数输出，不冒称对全部三条另做重载函数比较。保存与重载成功只证明这个训练机制实际运行及参数持久化，不能替代独立工作结果的收益测试。

PEFT 的目标模块和 adapter 配置接口见[官方 LoRA 说明](https://huggingface.co/docs/peft/en/package_reference/lora)；`eval()` 与梯度开关独立，见[PyTorch autograd 说明](https://docs.pytorch.org/docs/stable/notes/autograd)。具体库版本以实际运行报告为准。

## 已保留的数值反例与修订依据

原 `teacher_forcing` 单条全序列复算对第一条通过；第二、第三条最大绝对差分别为 0.3891、0.5204 nat，超过预声明 0.2，而不是把失败改成“已完成训练”。整个尝试在 optimizer.step 前停止。阈值及三个零奖励 episode 均保持不变。

独立只读 GPU 诊断比较了单条全序列、保留原两行左 padding 与显式 position IDs 的成对全序列、原 batch/cache 强制 token 重放。成对全序列仍有第三条最大差约 0.4411；原 batch 的增量缓存重放则三条逐 token 与原记录相等。另以可微 helper 的 base/no-grad，以及初始零效果 LoRA 的 grad-enabled 前向检查，均得到相同结果；没有新采样、反传或优化步骤。

v0.11.1 的正式缓存重放使用 `save_on_cpu(pin_memory=True)`。运行 RSS 持续上升，最终停止快照为 363,003,944 KiB（约 346.19 GiB），主运行者向本项目训练进程发送 SIGTERM；当时没有完成的反向组或 optimizer step。原 `runs/first-decision-rl-v011-cached/operator-stop.json` 记录实际时刻、源与状态。这是操作干预，不能追溯称为预声明资源上限触发。重复保存完整冻结权重是存储代码检查得到的原因假设；v0.11.2 将参数 storage 保留在 GPU，直接消除这种重复复制路径。无损重复 head 存储也针对实际 SDPA 在有左 padding mask 时展开 KV heads 的保存需求。CPU 小测试对参数转置、重复激活、广播 stride 与原计算作精确梯度对照；独立单组 GPU 探测已经完成完整反向且未更新参数；双行组与完整训练是否完成仍以新的正式报告为准，不从 CPU 小测试或单组探测外推。

这支持修订复算与存储路径，不能解释为扩大容差或换数据。旧模式仍可通过 `--replay-mode teacher_forcing` 明确运行；它是保留的数值对照，不会被默认悄悄选用。上述小范围结果不宣称所有模型、硬件、batch 或精度路径都逐 bit 相等。

## 执行与产物

这份脚本须在正式模型批、奖励攻击验收完成并另行冻结后，由主运行者执行；不与本项目自己的推理服务同时占用双份模型内存。共享 GPU 的其他任务允许继续，运行前后记录实际 GPU、进程、显存和利用率，不中止其他项目。

```bash
CUDA_VISIBLE_DEVICES=7 PYTHONPATH=src .train-venv/bin/python scripts/first_decision_rl_v011.py \
  --episode runs/model-api-v11-development/finance-direct-qwen-1/episode \
            runs/model-api-v11-development/finance-direct-qwen-2/episode \
            runs/model-api-v11-development/finance-direct-qwen-3/episode \
  --model /data1/zhuxinrui/models/Qwen2.5-7B-Instruct-a09a35458c702b33eeacc393d103063234e8bc28 \
  --output runs/first-decision-rl-v011-resident-new \
  --max-length 8192 --logprob-max-atol 0.2 --logprob-mean-atol 0.03 \
  --replay-mode cached_replay --service-records runs/qwen-service-v11 --max-rss-gib 128
```

`--prepare-only` 仅验收输入、奖励及权重，不运行梯度更新。任何模式都要求新的独立输出目录，不能放在源模型或 episode 档案内部。`targets.json` 保留每项选择、奖励、完整 token/标签/mask 和排除原因；`behavior-probability-check.json` 保存真实行为概率核对；`gradient-probability-check.json` 另核对实际可微前向；`actual-gradients.safetensors` 保存实际梯度；`adapter/` 是独立 adapter；`reload-probability-check.json` 和 `report.json` 给出重载和执行事实。原 base 文件保持只读。
