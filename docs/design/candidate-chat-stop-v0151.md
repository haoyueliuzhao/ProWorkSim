# v0.15.1：修正真实聊天终止协议

v0.15 的 Qwen3.5-9B 首个工作案例暴露了一个实际接口错误：模型已生成完整原生工具块与 `<|im_end|>`，服务却继续采样新的用户／工具文本，直至更晚的 `<|endoftext|>` 或2,048上限。首案例没有真实业务工具执行，旧R=0不能用来判断该模型的工作能力。

## 已确认原因

实际下载的两个官方 tokenizer 都声明 `<|im_end|>` 为 EOS，ID为248046；248044对应 `<|endoftext|>`，也被用作pad。9B没有独立的 `generation_config.json`，v0.15 text-only loader 从 `text_config.eos_token_id=248044` 构造生成配置，漏掉了聊天轮终止符。27B官方生成配置已显式列出 `[248046,248044]`。

来源：[9B官方资产](https://huggingface.co/Qwen/Qwen3.5-9B/tree/c202236235762e1c871ad0ccb60c8ee5ba337b9a)、[27B官方生成配置](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/generation_config.json)。本地完整manifest及EOS相关文件SHA保存在实验目录；读取的是实际下载的注册检查点文件。

这属于本项目把text backbone接入聊天接口时漏掉停止语义，不应解释为模型不会理解工具。原S0的两次公共note生成也各在首个im_end之后多生成2个token；只因随后很快产生endoftext，工具解析与数值检查都通过了。原S0的概率与反向结果仍然是真实测量，但其`inference_ready/training_ready`没有检验聊天边界，因此是接口准入假阳性。

原S1首调用的首个im_end在零基位置86，仍继续至2,048 token；第二调用在176处出现im_end，却继续至245处endoftext，并产生两个工具调用，被原单调用合同拒绝。读取证据归档于 `docs/experiments/v0151-original-chat-stop-evidence.json`。旧S0、S1、R=0、原始输出和运行成本全部保留，不截取旧输出重新评分。

## 新停止合同

新模块 `candidate_runtime_v0151.py` 与新profile `candidate-runtime-v0.15.1` 保留了旧模块和旧profile。采样温度、全softmax分布、非思考模式、上下文／输出预算、FP32／highest路线、权重、LoRA和业务合同均不改变；新条件明确双EOS为 `[248046,248044]`。

加载器从实际tokenizer分别取得两个marker的ID，并核对注册ID、tokenizer的EOS声明、单token编码，以及官方assistant模板确实以im_end结束。核对成功后设置**真实model.generation_config**，保存原／新EOS、官方文件SHA与模板probe SHA到独立EOS contract；不靠解析器切掉已经生成的后续内容。

共享核心另外保留采样器返回的完整 `raw_output_ids/raw_behavior_logprobs`。若单样本真实生成在首个声明EOS之后仍有token，返回503并将完整序列留在owner调用账本，不能通过`completed_tokens`裁尾变成成功。训练成员视图核对raw序列与训练序列逐项相同。

## 有界新校准

`candidate_preflight_v0151.py` 保留两回合公共note测试，并支持至多两个事先指定的 `--replay-call`。本次只执行旧S1最早的第一条公共请求。第二条已包含旧错误生成的历史，不能视为正常prompt校准；它的CPU模板逐token相同事实仍保留，明确不安排新采样。首条请求计划与新采样种子存于 `docs/experiments/v0151-chat-stop-replay-plan.json`。

重放先逐token核对新入口渲染的输入与原输入相同，然后以固定新种子重新采样。它不执行World动作，不生成新业务得分，不修补旧token，不回填原经历，也不替代完整新screen。新样本同时记录首个chat/end marker的位置，要求它就是实际输出的末位，且raw IDs／logp与保留的训练trace相同。缺少raw记录、EOS后继续、仅事后裁切或未观察到合法结束，都不能作为通过的校准。

只有停止协议和指定重放完成后才可进入新S1。数值与反向、检查点仍是独立的训练可行性条件：数值失败保留真实推理记录，不伪报训练准入。S1重新加载同一原始权重和新profile，使用新的运行身份和完整固定预算。三个CPU mock控制覆盖合法终止、越界／伪裁尾拒绝，以及停止合法但数值异常时仅保留推理准入；CPU结果和配置核对不是模型实际重采结果，后者须另行记录。
