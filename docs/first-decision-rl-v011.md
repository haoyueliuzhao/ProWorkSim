# v0.11 首决策策略梯度实验合同

本文先描述待执行合同；脚本及离线数据测试通过不代表发生训练。实际执行后须以独立运行报告补充结果，不能预写参数变化或学习收益。

## 固定研究范围

在正式 36 个模型开发 episode 之后，预先选择 `finance-direct-qwen-1`、`finance-direct-qwen-2`、`finance-direct-qwen-3`，按这个顺序提供各自的封闭 `episode/` 目录。不能看奖励后换 episode、补采成功轨迹或改用后续决策。每个 episode 只有**首个实际模型生成的完整 token 序列**作为一个可学习宏动作；后续目标工作人员决策、环境同事与世界动作全部作为已经记录的固定行为续行。

这是一次首决策 REINFORCE LoRA 更新，不是完整多轮 Agentic RL，也不是“无训练／独立任务训练／项目群训练”三组对照。失败 episode 的零奖励正常进入训练；不能据此判断改善了未见任务能力，或认定首决策就是后续失败的根因。

## 真实数据准入

输入仅从 EpisodeManifest 固定的经历区间提取，先调用 `assess_historical_episode` 对封闭历史评价。选择的世界义务是 `FINANCE::reconcile`，角色是 `analyst`。

每项输入同时满足：

- `case/record.json` 的 `public_capture_matches` 非空且每项严格为 true；无捕获对照或对照失败单列为不合格，不替换 episode。
- 轨迹策略来自 `ModelPolicy` 的 `local-qwen-http`，模型为 Qwen2.5-7B-Instruct，修订为 `a09a35458c702b33eeacc393d103063234e8bc28`，温度 0.3，单 JSON 决策协议。DeepSeek Teacher 经历不作为这个实验的 on-policy 输入。
- 原始首决策的 call ID、完成响应、实际 HTTP attempt、角色和 episode 区间一一对应。只收纳一次成功 attempt；首决策发生服务重试或响应不可读时单列排除，不能从几个响应中挑一个。
- `input_ids`、`output_ids`、`input_mask`、`output_mask`、`behavior_logprobs` 来自本地推理时实际 token 与采样 logits。不得从最终文本重新分词、补写行为概率或猜测缺失 mask。
- 输入 mask 全为 0，输出 mask 全为 1；实际 usage 与 ID 数量一致。保留整个输出序列，包括实际 EOS；不裁剪、不只选正确片段、不把输入作为预测目标。
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

LoRA 只更新 q_proj/v_proj，r=8、alpha=16、dropout=0、bias=none。采用 AdamW，学习率 1e-6、weight_decay=0、betas=(0.9,0.999)、eps=1e-8，一步，梯度范数裁剪到 1。输入来自真实 token ID，不再加载 tokenizer 重建轨迹。模型使用 BF16/SDPA；`model.eval()` 关闭 dropout，训练计算显式开启梯度。采用非重入整次前向的激活重计算，不改变可见输入或输出目标。只计算最后输出相关的 logits，原始完整上下文仍进入模型。

在任何 optimizer.step 之前，使用同 base 加初始零效果 LoRA 复算每个实际输出 token 的行为概率，分别保存原值、复算值、逐 token 有符号误差、最大/平均绝对误差及整个序列差异。默认预声明容差为最大绝对误差 0.2 nat、平均绝对误差 0.03 nat；这是接受 BF16 缓存／批 padding 数值差异的实验阈值，不是 bitwise 相等主张。任一准入记录不满足阈值，则整个训练在更新前停止，保留失败比较，不挑掉这条记录后继续。

保存实际完整裁剪前/后 LoRA 梯度、更新前 adapter、更新后 checkpoint、参数摘要及改变的元素数。重新加载 base+adapter，验证 adapter 参数摘要完全相等；另以同样显式数值阈值比较更新后/重载后的函数输出。保存与重载成功只证明这个训练机制实际运行及参数持久化，不能替代独立工作结果的收益测试。

PEFT 的目标模块和 adapter 配置接口见[官方 LoRA 说明](https://huggingface.co/docs/peft/en/package_reference/lora)；`eval()` 与梯度开关独立，见[PyTorch autograd 说明](https://docs.pytorch.org/docs/stable/notes/autograd)。具体库版本以实际运行报告为准。

## 执行与产物

这份脚本须在正式模型批、奖励攻击验收完成并另行冻结后，由主运行者执行；不与本项目自己的推理服务同时占用双份模型内存。共享 GPU 的其他任务允许继续，运行前后记录实际 GPU、进程、显存和利用率，不中止其他项目。

```bash
CUDA_VISIBLE_DEVICES=7 .train-venv/bin/python scripts/first_decision_rl_v011.py \
  --episode runs/model-api-v11-development/finance-direct-qwen-1/episode \
            runs/model-api-v11-development/finance-direct-qwen-2/episode \
            runs/model-api-v11-development/finance-direct-qwen-3/episode \
  --model /data1/zhuxinrui/models/Qwen2.5-7B-Instruct-a09a35458c702b33eeacc393d103063234e8bc28 \
  --output runs/first-decision-rl-v011 \
  --max-length 8192 --logprob-max-atol 0.2 --logprob-mean-atol 0.03
```

`--prepare-only` 仅验收输入、奖励及权重，不运行梯度更新。任何模式都要求新的独立输出目录，不能放在源模型或 episode 档案内部。`targets.json` 保留每项选择、奖励、完整 token/标签/mask 和排除原因；`behavior-probability-check.json` 保存真实行为概率核对；`actual-gradients.safetensors` 保存实际梯度；`adapter/` 是独立 adapter；`reload-probability-check.json` 和 `report.json` 给出重载和执行事实。原 base 文件保持只读。
