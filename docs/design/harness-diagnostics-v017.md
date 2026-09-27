# v0.17：岗位来源自主权与公开格式诊断

本修订针对v0.16审计第三节，在H1首个样本前形成新的运行协议。SDK标识为 `openhands-managed-worker-v0.17`，原生ModelPolicy标识为 `model-policy-v0.17`，共同候选运行适配为 `candidate-runtime-v0.17`。这会改变模型收到的岗位指令与格式错误反馈，**不是“对行为没有影响”的文字勘误**。H0冻结提交7914e05、原始输出与原评分不变，不重跑H0。

## 模型有来源选择自主权，harness没有代选权

删除SDK SYSTEM中含糊的 `choose sources automatically` 禁止句。SDK与原生ModelPolicy均明确：模型根据当前公开合同和自己实际取得的证据，自主选择允许使用的来源；信息不足时查询或沟通，不臆造依据。共享参数或可见对象名不等于已取得证据。

harness仍只提供受管工具、原始反馈及声明的上下文组织，不查询隐藏评价器、不选择正确来源、不自动交接、构建、修改业务参数或提交。这里没有加入参考结果、参考SQL或固定业务步骤。

## 两级错误记录必须同时到达后续输入

`candidate_runtime_v017.py` 使用与原生候选parser相同的工具块和参数解码规则，在原本已被拒绝的情况中增加有依据的定位。`protocol_parse_error`在失败时成为版本化结构，保留：原生解析器名称、失败阶段、已知工具名、字段路径、公开schema路径、期望类型、实际JSON类型，以及确实来自JSONDecodeError的行/列/偏移。

例如，公开schema声明 `payload` 为object，而其XML参数文本不是完整JSON时，反馈能指出字段 `payload`、schema路径 `properties/payload/type`、期望object和该参数文本内的解析位置。不能从未解析完成的JSON中猜测内部字段，实际类型保持未知。完整文本能解析但类型不合时，实际类型来自真实解码值。诊断不复制参数值、不生成替代值，不提供业务答案。

随后ModelPolicy或SDK可能再尝试把无原生调用的assistant内容解析为显式JSON wait/done控制。新的公开反馈包含 `parse_diagnostics.native_parser` 与 `parse_diagnostics.adapter_parser`：后续JSON错误不会覆盖原生诊断。SDK原有严格类型检查失败时，同样从实际ValidationError保留公开schema字段/类型位置，不复制错误instance。历史字符串型诊断仍如实标为legacy，字段与位置未知时为null。

两臂使用同一个v0.17候选parser和同一诊断结构；接口名称分别标识native/SDK，保持真实来源。实际原始response、生成文本、token及概率原样归档；反馈只是后续模型输入，不修正或重判先前输出，也不触发同机会重采。

## 保持原尝试边界和数值路径

最终实现**保留旧原生parser的接受集合**。JSON合法但缺少必需参数、含未知函数/参数、违反enum或组合schema等情况，不因新增诊断而前移拒绝；多工具调用仍交由原有策略边界拒绝。SDK既有typed工具检查继续运行。这样避免为了反馈定位，同时改变原生世界尝试、时间与回执语义。一次开发中曾考虑完整schema前置验证，最终未采用；没有真实样本使用该中间方案。

v0.15/v0.15.1模块没有修改。新CandidateActor继承旧chat-stop加载器，将新profile身份在owner初始化前绑定；FP32、最高matmul精度、LoRA范围、温度、上下文、输出长度及EOS合同不因此改变。显式 `devices` 参数仍支持4卡；具体设备放置由H1协议另行核定，不能把设备变更归因于诊断优化。

## 必要控制

`tests/test_format_diagnostics_v017.py`包含4项控制：原生JSON字段/位置/类型且无参数值泄露；旧新parser在代表性边界上的相同接受/解码结果；4卡profile通过旧数值加载入口、在owner创建前绑定新身份；以及真实SDK与ModelPolicy的确定性CPU传输控制。

最后一项直接检查两臂**下一次实际transport请求**中的公开反馈，确认同一原生失败和后续JSON控制失败同时存在，而不只是观察夹具第二次答对。拒绝时两臂均只采样一次，没有世界动作；原始response和夹具token哨兵不变。这是接口控制，不是模型能力或训练收益实验。
