# v050 原首槽及 worker 边界只读复核

原首槽 `org50-train-LA-r01` 已正常业务闭合：**R_joint=R_token=0，Q_joint=Q_token=10/12**，不是技术结果未知。原 worker 的 `execution_error` 和监督器的 `closed_with_unknowns` 保留，它们描述导出与 collection 收口失败，不覆盖已经确定的业务结果。

本复核只读取现有 JSON/文本与计算来源字节 SHA；没有加载 `.pt` 或模型、执行 tokenizer、新测量、业务测试、验收、世界动作或反向更新。机器回执包含关键原件 SHA、冻结源码身份及实际剩余库存。首次临时提取脚本因 staff_done outcome 没有 decision 键在写报告前终止，随后按可选字段提取；原件无变化。

## 已完成的真实工作

首槽 seed `202610130501`，先手001，实际S_star为原v049 B **4/4**。14次决定、14次attempt、14份完整回包；输入183551、本人输出3944、合187495token，账本一致。两成员各7次生成，分别94788/92707token。3次成员测试已经执行；全部14项dispatch返回、全部14项预算settled，held=0、uncertain=0，没有在途请求可恢复。剩余312505token不转移。

实际共有3次submit_integration：001第一次因为未发布精确当前版本固定补丁被业务拒绝，随后两成员各一次合法提交。最后锁定的唯一验收对象是002的`delivery-2`，源树SHA `2202807ec07689209944cbffa9d7e1e334013c9c59faeebfa78ecae357b2a319`。最终验收仅1次，12项中通过10项，公开契约检查通过，未完整成功。没有对较早提交或工作区补验。通用episode manifest的`fixed_deliveries={}`原样保留；真实软件提交由原boundary outcomes与final-candidate-lock/deadline证明，不能把该通用字段补写成新事实。

## 故障与守卫边界

冻结执行顺序是：`collect_episode`完成闭合与唯一验收 → 原`measure_slot`返回continue → 保存progress中的已知R0 → `export_software_episode`进入旧v049 Mapper证据seal校验后抛出`Original v049 export evidence seal differs`。异常发生于业务结束后的导出阶段；`training-entry.json`、`training-export.json`、outer `collection-boundary`和`collection-guard.json`均未产生。

原episode `evaluation-guard.json`已经完整保存且learning/actor identity/software binding不变、RNG精确恢复；最终worker actor/critic仍4/4，新actor/critic更新和反向均0。outer collection guard未到达，**不记通过**。`common-restore.json`中的3/3是前置common初始化；实际后续`loaded-state.json`与episode_start_steps明确绑定S_star4/4，二者不能混淆。无需生成重跑；训练导出可以在新根按闭合原件重新物化，但仍必须通过修复后的精确导出与CPU训练准入，不能把本边界复核代替训练资格。

## 反馈与页面

直接复用已保存原机械测量：14条反馈全部保存；12条有后续同成员真实生成，12条均在首次后续实见。其余2条是staff_done后没有可达事件，无永久退休、无预算重置，反馈ID为`feedback-298`/`feedback-323`。001的业务拒绝`feedback-161`已有后续实际呈现；原`unclassified_exception/category unknown`标签不改写，该标签不是正式结果未知。原机械门continue，global violations/unresolved/measurement gaps均空，局部资源拒绝0。

3份测试报告均保存且目录及首正文页呈现；主动read_test_result=0，全报告全部呈现=0，均为未请求后页。以上不主张模型语义使用、因果收益或协作学习收益。

## 库存与成本

原24条训练中仅首槽实际启动和闭合，其余23条真实未开；update-B/Q±和全部32条开发均未启动。未对任何已完成槽重采、未启动更新或开发。

原物理GPU2分配保留：S_star worker 51.6819634437561秒，collect-0 worker 384.6467568874359秒，合**436.328720331192秒（0.12120242231422001小时）**。首槽内部340.61285042762756秒嵌套于collect-0，不重复相加。旧成本在接续汇总中只计一次。

来源与逐槽未启动清单详见同名JSON；旧原件、停止记录、正式R/Q和费用均不修改。
