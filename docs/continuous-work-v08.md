# v0.8 工作上下文与持续推进合同

依据：[审计](reference/continuous-work-audit.md)及[两阶段计划](continuous-work-v08-plan.md)。第一阶段先稳定评价与绑定；第二阶段的事件、后继工作和公开调度另行收口。实验结果不在本说明中预先宣称。

## 阶段 A：内容与工作绑定

新 schema 为 world-core-v0.8、语义 work-world-v0.8，内容评价版本另记 finite-products-v0.8。旧世界用其冻结版本；新运行时不把旧项目别名采用表当成新版工作绑定。

JSON 内容比较递归检查对象、数组和标量。布尔值不等于数值；有限 int/float 的既有等价保持，无浮点容差。顶层合并仍拒绝同键不同内容，不新增深层合并语义。冲突不以某个文件的值覆盖解决，不挑“正确”文件；正反提交顺序都按明确预期判断。

| 记录 | 语义 |
| --- | --- |
| workspaces[project][alias] | 项目发现入口，仅指一个世界对象 |
| adoptions[work_id::alias] | 一项具体工作/需求版本的采用事实；同alias可被另一工作独立采用另一版 |
| adoption_view | 该工作绑定的fixed/current_published/current_applicable政策目标 |
| submission.adoption_snapshot | 提交时该work的绑定/目标/政策范围，历史保持 |

adopt 需要明确非空work_ids，为各工作创建独立绑定；逐work校验真实对象权限。adopt_version 面向一个具体work_id更新；省略时仅允许一个无歧义当前绑定，新工作人员始终传work_id。旧工作的绑定不因修订而转给新工作；别名继续存在，新工作显式采用，既有上下文字段及历史前缀受转换保持保护。

requirements.input_policy 声明共同政策；input_policies[alias] 可逐输入覆盖；值为一个政策或明确允许列表。input_version/input_versions 可限定fixed精确版本。未声明允许选择，不由评价器事后强制；声明current_published时不能自行改为fixed绕过。current政策采用旧版可以留下可执行错误，但其提交时目标/内容检查仍会失败。

项目包和需求修订都验证政策合同，提交快照与评价再次核对同一声明，不能依赖被测对象自行填一个更宽政策。

## 可重复使用的资料路线

信息路线定义关联稳定work_node，具体请求记录真实work_item_id、requirement_version、证据版本及主体。公开观察按当前义务展开可用路线，工作被修订后可以同route_id发新请求，不复用旧请求或重装项目包。

version_policy 可为fixed、current_published或work_requirement。后者先取该工作的input_version(s)，否则按声明的current_published解析正式目标，不能由工作人员提供隐藏正确金额。请求时仍验证真实版本与提供者范围。迟到旧请求保存原始回应，但不满足新条件，也不为替代工作授予新的精确版本权限。

需求修订可给旧提交增加superseded_requirements等适用性注记；其固定文件、答案、采用快照与已有正式审阅保持。不能把保持固定历史误写成“所有状态字段完全不变”。
