# v046 原生资格结果与四槽启动

本文件是启动快照，不是四槽终态。正式监督于北京时间 **2026-10-11 14:55:01.749165** 启动，PID 264873，执行冻结提交 `8dc6e4ce90b8e50080a0ce0a7f0b4851bc1bc9fc`。源码目录 `runs/v046-frozen-source`，运行根 `runs/software-organization-v046`。该源码已推送远端；运行期不热改。

## 唯一实际原生资格：通过

|项目|观察值|
|---|---:|
|实际请求次数|1|
|实际输入 token，含模板/schema|16,384|
|实际输出 token|28|
|实际总 token|16,412|
|预约/最大输出|2,048|
|声明容量|18,432|
|物理 GPU|5|
|资格 worker 分配时间|43.642117739 秒|
|世界动作、公开业务测试、参数/反向更新|均 0|

停止原因为 `tool_calls`；实际生成的 acknowledge 调用没有执行。完整请求、原投影、sealed preparation、实际输入 token IDs、全部原始输出 token、费用、profile 和窗口身份均一致。9 项资格检查通过，evaluation guard 确认学习状态同值且 RNG 精确恢复，执行前后 source 同一干净提交。没有第二次请求、隐式截短或后端替换。

原 common 先按原 16K metadata 恢复，state digest、actor identity、RNG 与步骤 3/3 严格通过。新容量绑定仅改变两个容量字段及派生的 profile/actor identity，14 个受保护 state 分量同值。旧 common 回执和旧软件坐标回执不回写为新容量。

这次非空输出说明实际序列超过旧 16K；实际只生成到总长 16,412，并未验证全部 18,432 个位置或任意后续工作轨迹。以上费用独立于正式四槽，不从任一正式槽扣减或转入其预算。原生生成时间嵌套在 worker 分配时间中，不重复累加。

## 四槽准入与启动

来源、CPU 控制、静态原生支持及上述实际资格已通过新四槽准入，机器准入摘要为 `5ee3b556fcee9695f8e5175c96343ec094fc8683b73872fc0178012c79100425`。四槽均从原初态开始，原完整 seed、先手、F2 二人成员集合、工具/权限/Γ/分页/预算/验收保持。原四历史基准只读复用。

首个 HA/451/F2 worker 已获得物理 GPU5；其他槽由相同资源门调度，最多三驻留，容量不足继续等待，仅可使用 3、4、5、7。实际调用的 Python 路径和虚拟环境 prefix 明确绑定原 SDK，调度器不会继承其他解释器。

成本、context/业务过程、反馈/工作三条只读核查对新闭槽增量缓存；不将分析结论送入模型，不改原件或重做验收。正式四槽未齐时 ΔC 保持 null。局部安全资源结束与全局完整性暂停继续按原规则区分；无自动重试或后继。

[启动机器快照](software-organization-v046-launch.json) · [资格原报告](software-organization-v046-qualification.json) · [冻结协议](software-organization-v046-protocol.md) · [CPU 准备](software-organization-v046-preparation.md)
