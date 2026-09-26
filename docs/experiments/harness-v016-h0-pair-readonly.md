# H0 双成员失败与公开错误反馈：只读核对

**没有发现 `select_context` 丢弃公开格式反馈或最近真实工具错误的证据。**这项判断来自实际模型 owner 的请求、原生模板消息和渲染提示，不是仅根据CPU夹具第二次答对，或模型随后采取了正确动作。

本次读取冻结提交 `7914e05381897b3cb8504287d7f31054a3a51032` 下已闭合的 `h0-real-pair`（slot-2），并读取实现情境slot-1发生格式错误后的实际请求。没有运行模型、修改冻结源、重判奖励或补发工具。

## 实际格式反馈确实进入了后续模型输入

双成员episode本身没有格式错误，18次均返回一个可解析原生工具调用。因此，它的R=0不能归因于格式反馈丢失。

单人实现episode第4次生成含一个非法参数结构，native parser记录 `invalid_tool_block: Native parameter does not match public JSON type`；SDK公开反馈记录了随后严格JSON控制解析的 `Expecting value: line 1 column 1 (char 0)`。原始响应仍完整归档，未执行该建议动作。

对之后第5–10次的**全部6次真实生成**，逐项核对确认：

- `request.messages` 保留与原 `model_format_feedback.feedback` 完全相同的对象。
- resident owner请求与归档请求完全相同。
- 相同反馈消息存在于 owner的 `actual_prompt_messages`。
- 完整反馈文本存在于实际 `rendered_prompt`。

冻结的 `select_context` 只移除先前已登记的公开观测和超出4回合的完整assistant/tool配对；未登记的user反馈会保守保留。随着旧工具回合被移除，这条反馈仍然保留。因而当前无需为这一假设修改上下文选择。

上述两个错误描述的具体程度不同，但原生解析诊断未丢失，保存在原response中；这不构成本轮“反馈未送达”的反例，也不能解释pair的R=0。

## 双成员episode为何没有形成成果

provider用完6次机会：读basis、向自己的供给route发起一次不合法请求、再读data/code/result/basis各一次。实际模型工具定义始终提供 `handoff_information`，但它没有生成任何交付调用。

implementer用完12次机会：3次请求basis，7次读取尚未共享的basis而被拒绝，最后2次读取data。两成员均未生成代码修改、构建或提交。provider没有交付，basis仍不适用于implementer；R=0、completed=false与实际工作轨迹相符。

8次真实世界拒绝（provider1次、implementer7次）均在**同角色下一次真实模型输入**中找到完整的相同tool结果：实际request、原生模板消息、渲染提示三个层次均存在。原生适配移除了SDK添加的 `name` 元数据，因此整条消息对象不字面相等；角色、tool_call_id和完整错误JSON均保留，完整JSON也确实进入渲染提示。初次整消息比较的false记录已保留，最终检查没有把元数据差异混同为内容丢失。每次拒绝的世界回执apply_delta为空。旧SDK `is_error=false` 的表示缺陷仍存在于这份原记录，但没有把 `ok:false` JSON从模型输入中丢掉。

18条模型包络、请求、token及概率均与owner记录一致；原始输出没有裁剪、概率有限且长度对应，每条在EOS结束。18条世界调用对应18个唯一提交回执。四回合窗口在这条较长轨迹中确实移除了较早配对，但没有移除最新错误。最后provider/implementer分别达到事前声明的6/12次决策上限，未追加预算。

## 结论边界

这是一条固定模型、harness和预算下未形成合同成果的有限轨迹。它不证明任何harness下都失败，也不能排除所有工具呈现和工作支持层面的可用性问题。不过，现有证据不支持“公开格式反馈或最新世界拒绝被上下文投影丢弃”这一具体解释。

保留原R=0，不以修正后的SDK错误标记回溯改判。本次没有新增源码修订；先前批准的 `is_error` 修订仍属于后继新Γ。分项证据、每次实际请求对应和SHA见 [JSON记录](harness-v016-h0-pair-readonly.json)。
